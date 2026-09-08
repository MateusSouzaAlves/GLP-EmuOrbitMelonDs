#!/usr/bin/env python3
"""Patch a disposable upstream source copy with protected runtime literals.

The pinned submodule stays untouched. Gradle invokes this script only after it
has synchronized the upstream tree into ``melondscore/build/generated``. Every
replacement is count-checked so an upstream update fails closed instead of
silently restoring a searchable functional fingerprint.
"""

from __future__ import annotations

import argparse
from pathlib import Path


NAND_PATHS = (
    ("kHwInfoS", "0:/sys/HWINFO_S.dat", 1),
    ("kHwInfoN", "0:/sys/HWINFO_N.dat", 1),
    ("kTwlCfg0", "0:/shared1/TWLCFG0.dat", 2),
    ("kTwlCfg1", "0:/shared1/TWLCFG1.dat", 2),
    ("kTitleTmd", "0:/title/%08x/%08x/content/title.tmd", 3),
    ("kTitleCategory", "0:/title/%08x", 2),
    ("kTitleApp", "0:/title/%08x/%08x/content/%08x.app", 4),
    ("kTicketCategory", "0:/ticket/%08x", 1),
    ("kTicketFile", "0:/ticket/%08x/%08x.tik", 2),
    ("kTitleRoot", "0:/title/%08x/%08x", 2),
    ("kTitleContent", "0:/title/%08x/%08x/content", 1),
    ("kTitleData", "0:/title/%08x/%08x/data", 1),
    ("kPublicSave", "0:/title/%08x/%08x/data/public.sav", 3),
    ("kPrivateSave", "0:/title/%08x/%08x/data/private.sav", 3),
    ("kBannerSave", "0:/title/%08x/%08x/data/banner.sav", 3),
)

CONSTANT_ANCHOR = "namespace melonDS::DSi_NAND\n{\n"
INCLUDE_ANCHOR = '#include "fatfs/ff.h"\n'
JIT_INCLUDE_ANCHOR = '#include "ARMJIT_Global.h"\n'
LIBRETRO_CONSOLE_INCLUDE_ANCHOR = '#include "console.hpp"\n'
LIBRETRO_CONSOLE_NAMESPACE_ANCHOR = "namespace MelonDsDs {\n"
DSIWARE_SENTINEL_PATH = '0:/title/{:08x}/{:08x}/data/{}'


def _replace_exact(text: str, old: str, new: str, expected: int, label: str) -> str:
    actual = text.count(old)
    if actual != expected:
        raise ValueError(f"{label}: expected {expected} occurrences, found {actual}")
    return text.replace(old, new)


def patch_nand_source(source: str) -> str:
    source = _replace_exact(
        source,
        INCLUDE_ANCHOR,
        INCLUDE_ANCHOR + '#include "protected_literal.hpp"\n',
        1,
        "DSi_NAND include anchor",
    )
    for name, literal, expected in NAND_PATHS:
        source = _replace_exact(
            source,
            f'"{literal}"',
            f"{name}.Decode().c_str()",
            expected,
            f"DSi_NAND path {literal}",
        )
    if '"0:/' in source:
        raise ValueError("DSi_NAND retains an unprotected virtual NAND path")
    declarations = ["\nnamespace\n{\n"]
    for index, (name, literal, _) in enumerate(NAND_PATHS, start=1):
        declarations.append(
            f"constexpr auto {name} = emuorbit::protection::Encode<"
            f"0x{index:08X}U>(\"{literal}\");\n"
        )
    declarations.append("}\n")
    source = _replace_exact(
        source,
        CONSTANT_ANCHOR,
        CONSTANT_ANCHOR + "".join(declarations),
        1,
        "DSi_NAND namespace anchor",
    )
    return source


def patch_jit_source(source: str) -> str:
    guard = (
        JIT_INCLUDE_ANCHOR
        + "\n#if defined(__ANDROID__) && !defined(EMUORBIT_DS_SHARED_MEMORY_NAME)\n"
        + '#error "Protected Android shared-memory name is required"\n'
        + "#endif\n"
    )
    source = _replace_exact(
        source,
        JIT_INCLUDE_ANCHOR,
        guard,
        1,
        "ARMJIT include anchor",
    )
    source = _replace_exact(
        source,
        '"melondsfastmem"',
        "EMUORBIT_DS_SHARED_MEMORY_NAME",
        2,
        "Android shared-memory name",
    )
    source = _replace_exact(
        source,
        '"/melondsfastmem%d"',
        '"/" EMUORBIT_DS_SHARED_MEMORY_NAME "%d"',
        2,
        "POSIX shared-memory name",
    )
    if "melondsfastmem" in source:
        raise ValueError("ARMJIT source retains the upstream shared-memory name")
    return source


def patch_libretro_console_source(source: str) -> str:
    source = _replace_exact(
        source,
        LIBRETRO_CONSOLE_INCLUDE_ANCHOR,
        LIBRETRO_CONSOLE_INCLUDE_ANCHOR + '#include "protected_literal.hpp"\n',
        1,
        "libretro console include anchor",
    )
    declaration = (
        "namespace\n{\n"
        "constexpr auto kDsiwareSentinelPath = "
        "emuorbit::protection::Encode<0x00010001U>("
        f'"{DSIWARE_SENTINEL_PATH}");\n'
        "}\n\n"
    )
    source = _replace_exact(
        source,
        LIBRETRO_CONSOLE_NAMESPACE_ANCHOR,
        declaration + LIBRETRO_CONSOLE_NAMESPACE_ANCHOR,
        1,
        "libretro console namespace anchor",
    )
    old = (
        f'        auto sentinel = fmt::format("{DSIWARE_SENTINEL_PATH}", '
        "header.DSiTitleIDHigh, header.DSiTitleIDLow, SENTINEL_NAME);"
    )
    new = (
        "        char sentinel_path[64] {};\n"
        "        emuorbit::protection::ProtectedSnprintf(\n"
        "            sentinel_path, sizeof(sentinel_path), kDsiwareSentinelPath,\n"
        "            header.DSiTitleIDHigh, header.DSiTitleIDLow, SENTINEL_NAME);\n"
        "        auto sentinel = std::string(sentinel_path);"
    )
    source = _replace_exact(
        source,
        old,
        new,
        1,
        "libretro DSiWare sentinel path",
    )
    return source


def patch_tree(root: Path) -> None:
    source_root = root / "src"
    targets = (
        (source_root / "DSi_NAND.cpp", patch_nand_source),
        (source_root / "ARMJIT_Memory.cpp", patch_jit_source),
    )
    for path, transformer in targets:
        if not path.is_file():
            raise FileNotFoundError(f"missing protected source target: {path}")
        original = path.read_text(encoding="utf-8")
        transformed = transformer(original)
        path.write_text(transformed, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--libretro-console", type=Path)
    args = parser.parse_args()
    patch_tree(args.source_root.resolve())
    if args.libretro_console:
        console_path = args.libretro_console.resolve()
        original = console_path.read_text(encoding="utf-8")
        console_path.write_text(
            patch_libretro_console_source(original),
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
