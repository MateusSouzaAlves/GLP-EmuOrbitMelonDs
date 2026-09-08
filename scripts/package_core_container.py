#!/usr/bin/env python3
"""Build and verify the authenticated, per-build native-core container."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import struct
from pathlib import Path


_HEADER_SIZE = 16 + 12 + 8
_TAG_SIZE = 32
_MAX_CORE_SIZE = 128 * 1024 * 1024


def _derive(seed: str, context: str, label: str) -> bytes:
    return hashlib.sha256(
        f"{seed}|{context}|{label}".encode("ascii")
    ).digest()


def _rotate_left(value: int, count: int) -> int:
    return ((value << count) & 0xFFFFFFFF) | (value >> (32 - count))


def _quarter_round(state: list[int], a: int, b: int, c: int, d: int) -> None:
    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] = _rotate_left(state[d] ^ state[a], 16)
    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] = _rotate_left(state[b] ^ state[c], 12)
    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] = _rotate_left(state[d] ^ state[a], 8)
    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] = _rotate_left(state[b] ^ state[c], 7)


def _chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    constants = struct.unpack("<4I", b"expand 32-byte k")
    initial = list(constants + struct.unpack("<8I", key)
                   + (counter,) + struct.unpack("<3I", nonce))
    state = initial.copy()
    for _ in range(10):
        _quarter_round(state, 0, 4, 8, 12)
        _quarter_round(state, 1, 5, 9, 13)
        _quarter_round(state, 2, 6, 10, 14)
        _quarter_round(state, 3, 7, 11, 15)
        _quarter_round(state, 0, 5, 10, 15)
        _quarter_round(state, 1, 6, 11, 12)
        _quarter_round(state, 2, 7, 8, 13)
        _quarter_round(state, 3, 4, 9, 14)
    return struct.pack("<16I", *(
        (state[index] + initial[index]) & 0xFFFFFFFF for index in range(16)
    ))


def _chacha20_xor(data: bytes, key: bytes, nonce: bytes) -> bytes:
    output = bytearray(len(data))
    for block_index, offset in enumerate(range(0, len(data), 64), start=1):
        stream = _chacha20_block(key, block_index, nonce)
        block = data[offset:offset + 64]
        output[offset:offset + len(block)] = bytes(
            value ^ stream[index] for index, value in enumerate(block)
        )
    return bytes(output)


def _container_parts(
        seed: str,
        context: str,
        plaintext: bytes,
) -> tuple[bytes, bytes, bytes]:
    if not plaintext or len(plaintext) > _MAX_CORE_SIZE:
        raise ValueError("native module size is outside the accepted range")
    key = _derive(seed, context, "container-encryption")
    nonce = hashlib.sha256(
        f"{seed}|{context}".encode("ascii")
        + b"|container-nonce|"
        + hashlib.sha256(plaintext).digest()
    ).digest()[:12]
    header = (
        _derive(seed, context, "container-magic")[:16]
        + nonce
        + struct.pack("<Q", len(plaintext))
    )
    ciphertext = _chacha20_xor(plaintext, key, nonce)
    tag = hmac.new(
        _derive(seed, context, "container-authentication"),
        header + ciphertext,
        hashlib.sha256,
    ).digest()
    return header, ciphertext, tag


def pack(input_path: Path, output_path: Path, seed: str, context: str) -> None:
    plaintext = input_path.read_bytes()
    header, ciphertext, tag = _container_parts(seed, context, plaintext)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_bytes(header + ciphertext + tag)
    os.replace(temporary, output_path)


def unpack(input_path: Path, output_path: Path, seed: str, context: str) -> None:
    container = input_path.read_bytes()
    if len(container) < _HEADER_SIZE + _TAG_SIZE:
        raise ValueError("container is truncated")
    header = container[:_HEADER_SIZE]
    if not hmac.compare_digest(
            header[:16], _derive(seed, context, "container-magic")[:16]):
        raise ValueError("container identity mismatch")
    plaintext_size = struct.unpack("<Q", header[28:36])[0]
    if plaintext_size == 0 or plaintext_size > _MAX_CORE_SIZE:
        raise ValueError("container size is invalid")
    if len(container) != _HEADER_SIZE + plaintext_size + _TAG_SIZE:
        raise ValueError("container length is invalid")
    ciphertext = container[_HEADER_SIZE:-_TAG_SIZE]
    expected_tag = hmac.new(
        _derive(seed, context, "container-authentication"),
        header + ciphertext,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(container[-_TAG_SIZE:], expected_tag):
        raise ValueError("container authentication failed")
    plaintext = _chacha20_xor(
        ciphertext,
        _derive(seed, context, "container-encryption"),
        header[16:28],
    )
    if not plaintext.startswith(b"\x7fELF"):
        raise ValueError("container payload is not an ELF module")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(plaintext)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("pack", "unpack"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--input", required=True, type=Path)
        subparser.add_argument("--output", required=True, type=Path)
        subparser.add_argument("--seed", required=True)
        subparser.add_argument("--context", required=True)
    args = parser.parse_args()
    if not 8 <= len(args.seed) <= 128 or not all(
            value.isascii() and (value.isalnum() or value in "._-")
            for value in args.seed):
        raise ValueError("seed format is invalid")
    if not args.context or not all(
            value.isascii() and (value.isalnum() or value in "._-")
            for value in args.context):
        raise ValueError("context format is invalid")
    if args.command == "pack":
        pack(args.input, args.output, args.seed, args.context)
    else:
        unpack(args.input, args.output, args.seed, args.context)


if __name__ == "__main__":
    main()
