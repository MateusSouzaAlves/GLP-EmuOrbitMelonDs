#!/usr/bin/env python3
"""Post-build binary string replacement for emulator core shared libraries.

Replaces identifying upstream project names with same-length opaque
alternatives so that the packaged binary does not self-identify when
inspected with tools like ``strings`` or a disassembler.

Every replacement pair **must** have identical byte lengths to preserve
section offsets, ELF structure and null terminators.

Usage
-----
    python patch_core_strings.py <shared_library> <core_id> [--seed SEED]
        [--context ABI]

core_id
    ``b``  secondary (NDS) core — the only core processed today.
"""

import argparse
import os
import codecs
import hashlib
from pathlib import Path
import re
import struct
import sys


_DIVERSIFICATION_SEED = b"emuorbit-protected-v1"

# Opaque text is generated from the build seed.  Across a sufficiently large
# native image, a random-looking replacement can eventually reproduce a short
# upstream marker by chance (for example the four-byte savestate magic).  Keep
# the generator independent from the post-patch gate, but reserve every compact
# identity fragment that could be formed by its alphanumeric alphabet.
_OPAQUE_GENERATED_FORBIDDEN = (
    b"meln",
    b"melon",
    b"jessetg",
    b"mgba",
    b"libretro",
    b"retro",
    b"teakra",
    b"ndscart",
    b"corestate",
    b"gbacart",
    b"firmwaremem",
    b"cartretailnand",
    b"cartretailir",
    b"cartretailbt",
    b"carthomebrew",
    b"interpreter",
    b"matchercreator",
    b"armjit",
    b"hybridsidescreendisplay",
    b"formattedpcapflags",
    b"powerstatusupdatetask",
    b"importdsiwaresavedata",
    b"flushgbasramtask",
    b"libslirp",
    b"localmp",
    b"altwfc",
    b"touchmode",
    b"nextscreenlayout",
    b"alternatecontrols",
    b"gbasramflush",
    b"virtualsdcarddirectory",
    b"internalerroroccurred",
    b"fastmem",
    b"private.sav",
    b"0:/title",
)

_EXTERNAL_DS_PATHS = (
    b"bios9.bin",
    b"bios7.bin",
    b"dsi_bios9.bin",
    b"dsi_bios7.bin",
    b"wfcsettings.bin",
    b"dsi_sd_card.bin",
    b"dldi_sd_card.bin",
    b"dsi_sd_card",
    b"dldi_sd_card",
    b"melonDS DS",
)


_CPP_STRING_TOKEN = br'"(?:\\.|[^"\\])*"'
_CPP_STRING_RUN = br'(?:' + _CPP_STRING_TOKEN + br'[ \t\r\n]*)+'
_DIAGNOSTIC_CALLS = (
    re.compile(
        br'(?<![A-Za-z0-9_])(?:Platform::)?Log\s*\('
        br'[\s\S]{0,160}?,\s*(?P<strings>' + _CPP_STRING_RUN + br')'
    ),
    re.compile(
        br'(?<![A-Za-z0-9_])(?:retro::)?(?:debug|info|warn|error)\s*\('
        br'\s*(?P<strings>' + _CPP_STRING_RUN + br')'
    ),
    re.compile(
        br'(?<![A-Za-z0-9_])(?:retro::)?(?:set_error_message|set_warn_message)\s*\('
        br'\s*(?P<strings>' + _CPP_STRING_RUN + br')'
    ),
    re.compile(
        br'(?<![A-Za-z0-9_])throw\s+[A-Za-z0-9_:<>]+\s*\('
        br'\s*(?P<strings>' + _CPP_STRING_RUN + br')'
    ),
)

# A throw may wrap its message in fmt::format(), so looking only for a string
# immediately after the exception constructor misses useful source-search
# fingerprints.  The bounded statement scan deliberately collects text only;
# replacing an exception message cannot change the exception's control flow.
_THROW_STATEMENT = re.compile(
    br'(?<![A-Za-z0-9_])throw\b(?P<body>[\s\S]{0,1024}?);'
)

_INPUT_DESCRIPTOR_BLOCK = re.compile(
    br'\bretro_input_descriptor\b[^=;\n]{0,160}\[\]\s*=\s*\{'
    br'(?P<body>[\s\S]{0,8192}?)\n\s*\};'
)
_TASK_LABEL = re.compile(
    br'(?:retro::task::)?(?:ASAP|WHEN_IDLE)\s*,\s*'
    br'(?P<strings>' + _CPP_STRING_RUN + br')'
)
_INTERNAL_ERROR_DECL = re.compile(
    br'\bINTERNAL_ERROR_MESSAGE\b\s*=\s*'
    br'(?P<strings>' + _CPP_STRING_RUN + br')\s*;'
)

_KNOWN_ATTRIBUTION_LITERALS = (
    b"Touch Mode",
    b"Next Screen Layout",
    b"Speedup/Slowdown Pointer+Enable Alternate Controls",
    b"GBA SRAM Flush",
    b"Failed to create virtual SD card directory at {}",
    b"An internal error occurred with melonDS DS. "
    b"Please contact the developer with the log file.",
    b"An internal error occurred with",
    b"Please contact the developer with the log file.",
    b"BOKTAI STUB",
    b"melonDS DLDI driver",
    b"BTDMP: transmit buffer overrun\n",
    b"BTDMP RECEIVE TODO!!\n",
    b"Unimplemented MMIO space",
    b"MMIO: cell %04X set = %04X\n",
    b"MMIO: cell %04X get\n",
)

_CORE_OPTION_KEY = re.compile(br'"(melonds[a-z0-9_]+)"')
_SOURCE_TYPE_DECL = re.compile(
    br'\b(?:class|struct|enum\s+class)\s+'
    br'(?P<token>[A-Z][A-Za-z0-9_]{4,})\b'
)
_QUALIFIED_FUNCTION_TOKEN = re.compile(
    br'::(?P<token>[A-Z][A-Za-z0-9_]{4,})\s*\('
)


def _decode_cpp_string_run(run):
    result = bytearray()
    for token in re.finditer(br'"((?:\\.|[^"\\])*)"', run):
        decoded, _ = codecs.escape_decode(token.group(1))
        result.extend(decoded)
    return bytes(result)


def _diagnostic_literals():
    workspace_root = Path(__file__).resolve().parent.parent
    source_roots = (
        workspace_root / "third_party" / "melonds" / "src",
        workspace_root / "third_party" / "melonds-ds" / "src" / "libretro",
    )
    literals = set()
    for source_root in source_roots:
        if not source_root.is_dir():
            continue
        for source_path in source_root.rglob("*"):
            if source_path.suffix.lower() not in {".c", ".cc", ".cpp", ".h", ".hpp"}:
                continue
            source = source_path.read_bytes()
            for call_pattern in _DIAGNOSTIC_CALLS:
                for match in call_pattern.finditer(source):
                    literal = _decode_cpp_string_run(match.group("strings"))
                    # These identifiers are resolved with dlsym by the host.
                    # A log message may contain the exact same bytes, and a
                    # global in-place replacement would corrupt the dynstr ABI.
                    is_libretro_abi = re.fullmatch(br"retro_[a-z0-9_]+", literal)
                    if (
                        len(literal) >= 6
                        and b"\0" not in literal
                        and not is_libretro_abi
                    ):
                        literals.add(literal)
            for statement in _THROW_STATEMENT.finditer(source):
                for string_run in re.finditer(
                        _CPP_STRING_RUN, statement.group("body")):
                    literal = _decode_cpp_string_run(string_run.group(0))
                    if len(literal) >= 6 and b"\0" not in literal:
                        literals.add(literal)
    return sorted(literals, key=len, reverse=True)


def _attribution_literals():
    """Return non-functional text that can identify the upstream DS core.

    These strings are never consumed as option keys or machine values.  They
    are frontend-facing input descriptions, private task labels, and stable
    error prose.  Keeping the collector source-driven makes a future upstream
    update fail the post-decryption audit instead of silently reintroducing a
    searchable phrase.
    """
    workspace_root = Path(__file__).resolve().parent.parent
    libretro_root = (
        workspace_root / "third_party" / "melonds-ds" / "src" / "libretro"
    )
    literals = set(_KNOWN_ATTRIBUTION_LITERALS)

    input_path = libretro_root / "input" / "input.cpp"
    if input_path.is_file():
        source = input_path.read_bytes()
        for block in _INPUT_DESCRIPTOR_BLOCK.finditer(source):
            for string_run in re.finditer(
                    _CPP_STRING_RUN, block.group("body")):
                literal = _decode_cpp_string_run(string_run.group(0))
                # A generic single word such as "Microphone" is not an
                # attribution signal and can legitimately be emitted by other
                # embedded components.  Compound controller descriptions are
                # the searchable source fingerprint we need to neutralize.
                is_compound_description = any(
                    separator in literal for separator in (b" ", b"/", b"+")
                )
                if (
                    len(literal) >= 8
                    and is_compound_description
                    and b"\0" not in literal
                ):
                    literals.add(literal)

    tasks_path = libretro_root / "core" / "tasks.cpp"
    if tasks_path.is_file():
        source = tasks_path.read_bytes()
        for match in _TASK_LABEL.finditer(source):
            literal = _decode_cpp_string_run(match.group("strings"))
            if len(literal) >= 6 and b"\0" not in literal:
                literals.add(literal)

    core_path = libretro_root / "core" / "core.cpp"
    if core_path.is_file():
        source = core_path.read_bytes()
        for match in _INTERNAL_ERROR_DECL.finditer(source):
            literal = _decode_cpp_string_run(match.group("strings"))
            if len(literal) >= 6 and b"\0" not in literal:
                literals.add(literal)

    return sorted(literals, key=len, reverse=True)


def _source_identity_tokens():
    """Collect distinctive C++ identifiers retained by RTTI/pretty functions.

    Namespace randomization alone leaves project-defined type and qualified
    function names searchable.  Declarations and qualified definitions are
    used instead of every CamelCase token, which avoids treating imported APIs
    and ordinary language labels as implementation identity.
    """
    workspace_root = Path(__file__).resolve().parent.parent
    base_core_root = workspace_root / "third_party" / "melonds" / "src"
    source_roots = (
        (base_core_root, False),
        (base_core_root / "teakra" / "src", True),
        (
            workspace_root / "third_party" / "melonds-ds" / "src" / "libretro",
            True,
        ),
    )
    base_domain_marker = re.compile(
        br"(?:NDS|DSi|GBA|Firmware|Screen|Cart|Renderer|ARMJIT)"
    )
    camel_transition = re.compile(br"[a-z0-9][A-Z]")
    compact_distinctive_tokens = {
        b"BitFieldCell",
        b"BitFieldSlot",
        b"Btdmp",
        b"ConstCell",
        b"CoreConfig",
        b"CountMode",
        b"FATStorage",
        b"NetDriver",
        b"NetState",
        b"RumbleState",
        b"RumbleTask",
    }
    tokens = set()
    for source_root, include_all_local_identifiers in source_roots:
        if not source_root.is_dir():
            continue
        for source_path in source_root.rglob("*"):
            if source_path.suffix.lower() not in {
                    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"}:
                continue
            relative_parts = tuple(
                part.lower() for part in source_path.relative_to(source_root).parts
            )
            if (
                source_path.stem.lower().startswith("test")
                or any(part in {"frontend", "tests", "test_verifier", "fuzzers"}
                       for part in relative_parts)
            ):
                continue
            if source_root == base_core_root and "teakra" in relative_parts:
                continue
            source = source_path.read_bytes()
            for pattern in (_SOURCE_TYPE_DECL, _QUALIFIED_FUNCTION_TOKEN):
                for match in pattern.finditer(source):
                    token = match.group("token")
                    is_distinctive_local = (
                        include_all_local_identifiers
                        and (
                            (len(token) >= 14 and camel_transition.search(token))
                            or token in compact_distinctive_tokens
                        )
                    )
                    if base_domain_marker.search(token) or is_distinctive_local:
                        tokens.add(token)
    return sorted(tokens, key=len, reverse=True)


def _metadata_literals():
    """Return descriptive upstream text that the embedded frontend never shows.

    The Android bridge consumes option keys and machine values, but it does not
    display libretro's category names, labels or help text.  Long string runs in
    the option-definition headers are therefore safe to neutralize without
    changing the values the core reads.  Exception and error-screen sources are
    included for the same reason: the app reports its own stable Java/JNI errors.
    """
    workspace_root = Path(__file__).resolve().parent.parent
    source_files = list(
        (workspace_root / "third_party" / "melonds-ds" / "src" / "libretro"
         / "config" / "definitions").glob("*.hpp")
    )
    source_files.extend((
        workspace_root / "third_party" / "melonds-ds" / "src" / "libretro"
        / "exceptions.cpp",
        workspace_root / "third_party" / "melonds-ds" / "src" / "libretro"
        / "message" / "error.cpp",
        workspace_root / "third_party" / "melonds-ds" / "src" / "libretro"
        / "format.cpp",
        workspace_root / "third_party" / "melonds-ds" / "src" / "libretro"
        / "info.cpp",
    ))

    literals = set()
    for source_path in source_files:
        if not source_path.is_file():
            continue
        source = source_path.read_bytes()
        for match in re.finditer(_CPP_STRING_RUN, source):
            literal = _decode_cpp_string_run(match.group(0))
            is_presentation_text = (
                b" " in literal
                or b"/" in literal
                or b"(" in literal
                or b"#" in literal
            )
            is_numeric_choice = re.fullmatch(
                br"[+-]?\d+\s+(?:second|minute|hour|day|year)s?",
                literal,
            )
            if (
                len(literal) >= 6
                and (len(literal) >= 12 or is_presentation_text)
                and b"\0" not in literal
                and not is_numeric_choice
            ):
                literals.add(literal)
    literals.update(_attribution_literals())
    return sorted(literals, key=len, reverse=True)


def _core_option_keys():
    """Collect public libretro option keys that would fingerprint the core."""
    source_root = (
        Path(__file__).resolve().parent.parent
        / "third_party" / "melonds-ds" / "src" / "libretro"
    )
    keys = set()
    if source_root.is_dir():
        for source_path in source_root.rglob("*"):
            if source_path.suffix.lower() not in {".c", ".cc", ".cpp", ".h", ".hpp"}:
                continue
            for match in _CORE_OPTION_KEY.finditer(source_path.read_bytes()):
                keys.add(match.group(1))
    return sorted(keys, key=len, reverse=True)


def _opaque_identifier(original):
    """Create a same-length option key diversified by build and ABI."""
    digest = hashlib.sha256(
        _DIVERSIFICATION_SEED + b"|ds-option|" + original
    ).hexdigest().encode("ascii")
    return b"q" + digest[:len(original) - 1]


def _opaque_external_path(original):
    """Match the per-build, same-length path alias generated by CMake."""
    digest = hashlib.sha256(
        _DIVERSIFICATION_SEED + b"|ds-path|" + original
    ).hexdigest().encode("ascii")
    return b"q" + digest[:len(original) - 1]


def _opaque_state_section(original):
    """Match a four-byte savestate section alias generated by CMake."""
    prefixes = {
        b"DSIG": b"q",
        b"DSPi": b"r",
    }
    try:
        prefix = prefixes[original]
    except KeyError as error:
        raise ValueError("unsupported savestate section tag") from error
    digest = hashlib.sha256(
        _DIVERSIFICATION_SEED + b"|state-section|" + original
    ).hexdigest().encode("ascii")
    return prefix + digest[:3]


def _opaque_diagnostic(original):
    alphabet = b"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    for retry in range(256):
        opaque = bytearray()
        counter = 0
        random_block = b""
        # Preserve the historical output for the overwhelmingly common first
        # attempt.  Only a colliding value enters a separate deterministic
        # domain, so builds remain stable unless the old output was unsafe.
        retry_domain = (
            b"" if retry == 0
            else b"\0retry\0" + retry.to_bytes(2, "little")
        )
        for original_byte in original:
            if original_byte in (ord("\r"), ord("\n"), ord("\t")):
                opaque.append(original_byte)
                continue
            if not random_block:
                random_block = hashlib.sha256(
                    b"emuorbit-release-diagnostic\0"
                    + _DIVERSIFICATION_SEED
                    + b"\0"
                    + original
                    + retry_domain
                    + counter.to_bytes(4, "little")
                ).digest()
                counter += 1
            opaque.append(alphabet[random_block[0] % len(alphabet)])
            random_block = random_block[1:]

        candidate = bytes(opaque)
        lowered_candidate = candidate.lower()
        if not any(
                marker in lowered_candidate
                for marker in _OPAQUE_GENERATED_FORBIDDEN):
            return candidate

    raise RuntimeError("unable to generate a collision-free opaque diagnostic")


def _scrub_literals(data, literals):
    """Replace diagnostic text only inside read-only string storage.

    A diagnostic word can also be a substring of a dynamic-linker symbol. For
    example, the core contains the message ``mismatch`` while UBSan imports
    ``__ubsan_handle_type_mismatch_minimal_abort``. A whole-file replacement
    silently corrupts ``.dynstr`` and makes the instrumented ELF unloadable.
    Restricting substitutions to ``.rodata`` preserves the dynamic ABI and all
    relocation metadata while still covering compiled string literals.
    """
    mutable = bytearray(data)
    scrubbed_count = 0
    matched_literals = []
    rodata_ranges = _elf_section_ranges(data, {".rodata"})
    for literal in literals:
        opaque = _opaque_diagnostic(literal)
        literal_count = 0
        for section_start, section_end in rodata_ranges:
            cursor = section_start
            while True:
                position = mutable.find(literal, cursor, section_end)
                if position < 0:
                    break
                mutable[position:position + len(literal)] = opaque
                literal_count += 1
                cursor = position + len(literal)
        if literal_count:
            scrubbed_count += literal_count
            matched_literals.append(literal)
    return bytes(mutable), scrubbed_count, matched_literals


def _scrub_build_paths(data):
    # Compiler/assertion paths are diagnostic-only. Match the printable tail
    # as well as fully ASCII paths, since a non-ASCII workspace component can
    # cause tools such as `strings` to begin displaying midway through it.
    # Clang also embeds paths inside long RTTI names for lambdas, so scrub the
    # source fragment first instead of requiring a particular extension. This
    # also covers assembly, generated includes and other compiler inputs.
    embedded_source_pattern = re.compile(
        br'(?:\./)?third_party(?:[/\\][A-Za-z0-9_.-]+)+'
        br'(?::(?:\d+|%[A-Za-z]))?(?::(?:\d+|%[A-Za-z]))?'
    )
    source_path_pattern = re.compile(
        br'[\x20-\x7e]{8,}\.(?:cpp|cxx|cc|c|hpp|hh|h)'
        br'(?::%[A-Za-z])?'
    )
    user_profile_prefix_pattern = re.compile(
        br'[A-Za-z]:[/\\]Users[/\\][A-Za-z0-9_. -]+[/\\]'
    )
    path_markers = (
        b"third_party/",
        b"third_party\\",
        b".cxx/",
        b".cxx\\",
        b"_deps/",
        b"_deps\\",
    )
    scrubbed_count = 0

    # Remove the absolute workspace prefix wherever a toolchain component
    # ignored the prefix-map flags. Keep both native and compiler separators.
    workspace_root = str(Path(__file__).resolve().parent.parent)
    workspace_variants = {
        workspace_root.encode("utf-8"),
        workspace_root.replace("\\", "/").encode("utf-8"),
    }
    for workspace_bytes in workspace_variants:
        occurrence_count = data.count(workspace_bytes)
        if occurrence_count:
            data = data.replace(workspace_bytes, _opaque_diagnostic(workspace_bytes))
            scrubbed_count += occurrence_count

    def replace_embedded_source(match):
        nonlocal scrubbed_count
        scrubbed_count += 1
        return _opaque_diagnostic(match.group(0))

    def replace_path_marker(match):
        nonlocal scrubbed_count
        scrubbed_count += 1
        return _opaque_diagnostic(match.group(0))

    def replace_if_build_path(match):
        nonlocal scrubbed_count
        candidate = match.group(0)
        if not any(marker in candidate for marker in path_markers):
            return candidate
        scrubbed_count += 1
        return _opaque_diagnostic(candidate)

    data = embedded_source_pattern.sub(replace_embedded_source, data)
    # A UTF-8 workspace component may split an absolute Windows path into
    # multiple printable runs. Removing the stable user-profile prefix keeps
    # that partial path from becoming a build-machine fingerprint even when
    # the complete workspace byte sequence cannot be matched.
    data = user_profile_prefix_pattern.sub(replace_path_marker, data)
    data = re.sub(
        br'\.cxx[/\\]RelWithDebInfo|_deps[/\\]',
        replace_path_marker,
        data,
    )
    data = source_path_pattern.sub(replace_if_build_path, data)
    return data, scrubbed_count


def _elf_section_ranges(data, section_names):
    """Return byte ranges for named sections in a little/big-endian ELF file."""
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise RuntimeError("core binary is not a valid ELF file")

    elf_class = data[4]
    byte_order = data[5]
    if byte_order == 1:
        endian = "<"
    elif byte_order == 2:
        endian = ">"
    else:
        raise RuntimeError("unsupported ELF byte order")

    if elf_class == 2:
        header = struct.unpack_from(endian + "HHIQQQIHHHHHH", data, 16)
        section_offset, section_entry_size = header[5], header[10]
        section_count, names_index = header[11], header[12]
        section_format = endian + "IIQQQQIIQQ"
    elif elf_class == 1:
        header = struct.unpack_from(endian + "HHIIIIIHHHHHH", data, 16)
        section_offset, section_entry_size = header[5], header[10]
        section_count, names_index = header[11], header[12]
        section_format = endian + "IIIIIIIIII"
    else:
        raise RuntimeError("unsupported ELF class")

    expected_entry_size = struct.calcsize(section_format)
    if (
            section_count == 0
            or names_index >= section_count
            or section_entry_size < expected_entry_size
            or section_offset + section_count * section_entry_size > len(data)):
        raise RuntimeError("invalid ELF section table")

    sections = []
    for index in range(section_count):
        values = struct.unpack_from(
            section_format, data, section_offset + index * section_entry_size)
        name_offset = values[0]
        section_type = values[1]
        file_offset, size = values[4], values[5]
        # SHT_NOBITS (most notably .bss) has a memory size but deliberately
        # occupies no bytes in the ELF file.
        if section_type != 8 and file_offset + size > len(data):
            raise RuntimeError("ELF section extends beyond the core binary")
        sections.append((name_offset, section_type, file_offset, size))

    _, _, names_offset, names_size = sections[names_index]
    names = data[names_offset:names_offset + names_size]
    ranges = []
    for name_offset, section_type, file_offset, size in sections:
        if section_type == 8:
            continue
        if name_offset >= len(names):
            continue
        name_end = names.find(b"\0", name_offset)
        if name_end < 0:
            continue
        name = names[name_offset:name_end].decode("ascii", errors="ignore")
        if name in section_names:
            ranges.append((file_offset, file_offset + size))
    return ranges


def _scrub_rodata_identity_strings(data, fingerprints):
    """Hash complete read-only strings that expose implementation internals.

    Release builds retain C++ RTTI names even after the local symbol table is
    stripped. Replacing only a namespace still leaves distinctive class-name
    combinations that can be pasted into a source search. Hash the complete
    NUL-terminated string instead, limited to .rodata so code bytes, relocation
    data and the dynamic symbol hash remain untouched.
    """
    lowered_fingerprints = tuple(value.lower() for value in fingerprints)
    mutable = bytearray(data)
    scrubbed_count = 0
    # Diagnostics may be one C string containing embedded newlines. Include
    # the normal ASCII whitespace controls so the whole NUL-terminated literal
    # is replaced instead of leaving the searchable first line untouched.
    printable_string = re.compile(br"[\x09\x0a\x0d\x20-\x7e]{6,}\0")
    for section_start, section_end in _elf_section_ranges(data, {".rodata"}):
        section = data[section_start:section_end]
        for match in printable_string.finditer(section):
            literal = match.group(0)[:-1]
            lowered_literal = literal.lower()
            if not any(value in lowered_literal for value in lowered_fingerprints):
                continue
            absolute_start = section_start + match.start()
            mutable[absolute_start:absolute_start + len(literal)] = (
                _opaque_diagnostic(literal)
            )
            scrubbed_count += 1
    return bytes(mutable), scrubbed_count


def _literal_remains_in_sections(data, literal, section_names):
    return any(
        literal in data[section_start:section_end]
        for section_start, section_end in _elf_section_ranges(data, section_names)
    )


def _patch(
        filepath,
        replacements,
        forbidden_patterns=(),
        scrub_diagnostics=False,
        scrub_metadata=False,
        rodata_identity_fingerprints=()):
    with open(filepath, "rb") as fh:
        data = fh.read()

    original = data
    diagnostic_count = 0
    diagnostic_literals = []
    if scrub_diagnostics:
        data, diagnostic_count, diagnostic_literals = _scrub_literals(
            data, _diagnostic_literals())

    metadata_count = 0
    metadata_literals = []
    if scrub_metadata:
        data, metadata_count, metadata_literals = _scrub_literals(
            data, _metadata_literals())

    replacement_counts = []
    for find_pattern, replace_bytes in replacements:
        if isinstance(find_pattern, bytes):
            pattern = re.compile(re.escape(find_pattern))
            expected_length = len(find_pattern)
        else:
            pattern = find_pattern
            expected_length = len(pattern.pattern)

        if expected_length != len(replace_bytes):
            raise ValueError(
                "Length mismatch: %r (%d) vs %r (%d)"
                % (pattern.pattern, expected_length, replace_bytes, len(replace_bytes))
            )

        data, count = pattern.subn(lambda _match: replace_bytes, data)
        replacement_counts.append((pattern.pattern, count))

    # Apply the targeted key translations first. Otherwise a functional core
    # option containing an upstream name would be swallowed by the complete
    # read-only-string scrub and the bridge could no longer address it.
    rodata_identity_count = 0
    if rodata_identity_fingerprints:
        data, rodata_identity_count = _scrub_rodata_identity_strings(
            data, rodata_identity_fingerprints)

    data, build_path_count = _scrub_build_paths(data)

    for forbidden_pattern in forbidden_patterns:
        match = forbidden_pattern.search(data)
        if match is not None:
            raise RuntimeError(
                "forbidden core identity remained after patching: %r"
                % match.group(0)
            )

    for diagnostic_literal in diagnostic_literals:
        if _literal_remains_in_sections(
                data, diagnostic_literal, {".rodata"}):
            raise RuntimeError("diagnostic fingerprint remained after scrubbing")
    for metadata_literal in metadata_literals:
        if _literal_remains_in_sections(data, metadata_literal, {".rodata"}):
            raise RuntimeError("metadata fingerprint remained after scrubbing")

    if data != original:
        with open(filepath, "wb") as fh:
            fh.write(data)
        matched_patterns = sum(1 for _, count in replacement_counts if count)
        replacements_applied = sum(count for _, count in replacement_counts)
        print(
            "patch_core_strings: patched %d identity occurrence(s) across %d "
            "pattern(s), scrubbed %d RTTI/read-only identity, %d diagnostic, "
            "%d metadata and %d build-path occurrence(s) in %s"
            % (
                replacements_applied,
                matched_patterns,
                rodata_identity_count,
                diagnostic_count,
                metadata_count,
                build_path_count,
                os.path.basename(filepath),
            )
        )
    else:
        print("patch_core_strings: no patterns matched in %s"
              % os.path.basename(filepath))


def main():
    parser = argparse.ArgumentParser(
        description="Remove identifying strings from a packaged native module"
    )
    parser.add_argument("so_file")
    parser.add_argument("core_id")
    parser.add_argument("--seed", default="emuorbit-protected-v1")
    parser.add_argument("--context", default="arm64-v8a")
    parser.add_argument("--strict-protected", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]{8,128}", args.seed):
        parser.error("--seed must be 8-128 ASCII letters, digits, '.', '_' or '-'")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.context):
        parser.error("--context must contain ASCII letters, digits, '.', '_' or '-'")

    global _DIVERSIFICATION_SEED
    _DIVERSIFICATION_SEED = (
        f"{args.seed}|{args.context}".encode("ascii")
    )
    filepath = args.so_file
    core_id = args.core_id

    if core_id == "b":
        # Secondary core (NDS engine).
        # Keep replacements length-preserving so ELF offsets, relocations and
        # string terminators remain untouched. The bridge uses the matching
        # opaque core-option prefix, so replacing the option keys is safe.
        # Longest/specific matches must run before the broad case-insensitive
        # fallbacks so C++ RTTI names remain readable but non-identifying.
        option_key_replacements = [
            (key, _opaque_identifier(key)) for key in _core_option_keys()
        ]
        # Names such as bios9.bin are suffixes of dsi_bios9.bin. Replacing the
        # short name first used to leave a visible dsi_ prefix and produced an
        # alias different from the one understood by the bridge.
        external_path_replacements = [
            (path, _opaque_external_path(path))
            for path in sorted(_EXTERNAL_DS_PATHS, key=len, reverse=True)
        ]
        state_section_replacements = [
            (tag, _opaque_state_section(tag)) for tag in (b"DSIG", b"DSPi")
        ]
        teakra_alias = _opaque_diagnostic(b"Teakra")
        strict_forbidden_patterns = []
        strict_rodata_fingerprints = ()
        if args.strict_protected:
            strict_source_identity_tokens = tuple(_source_identity_tokens())
            strict_forbidden_patterns = [
                re.compile(br"Slot 1 & 2 Boot", re.IGNORECASE),
                re.compile(br"CoreState", re.IGNORECASE),
                re.compile(br"GBACart", re.IGNORECASE),
                re.compile(br"DSi_NAND", re.IGNORECASE),
                re.compile(br"[a-z0-9]+_exception", re.IGNORECASE),
                re.compile(br"(?:^|[^A-Za-z0-9])5retro", re.IGNORECASE),
                re.compile(br"Assertion '%s' failed", re.IGNORECASE),
                re.compile(br"out/llvm-project/", re.IGNORECASE),
                re.compile(
                    br"(?:[A-Za-z0-9_.-]+[/\\])+"
                    br"[A-Za-z0-9_.-]+\.(?:cpp|cxx|cc|hpp|hh|h)",
                    re.IGNORECASE,
                ),
                re.compile(br"(?:build|\.cxx)[/\\]generated[/\\]patched", re.IGNORECASE),
                re.compile(br"[A-Za-z]:[/\\]Users[/\\]", re.IGNORECASE),
                re.compile(br"HybridSideScreenDisplay", re.IGNORECASE),
                re.compile(br"FormattedPCapFlags", re.IGNORECASE),
                re.compile(br"PowerStatusUpdateTask", re.IGNORECASE),
                re.compile(br"ImportDsiwareSaveData", re.IGNORECASE),
                re.compile(br"FlushGbaSramTask", re.IGNORECASE),
                re.compile(br"DSi_BPTWL", re.IGNORECASE),
                re.compile(br"ARMJIT", re.IGNORECASE),
                re.compile(br"Nintendo DS \(Slot 1\)", re.IGNORECASE),
                re.compile(br"nds\|dsi\|ids\|gba", re.IGNORECASE),
                re.compile(br"nds\|ids\|dsi", re.IGNORECASE),
                re.compile(br"bios7\.bin", re.IGNORECASE),
                re.compile(br"bios9\.bin", re.IGNORECASE),
                re.compile(br"dsi_bios7\.bin", re.IGNORECASE),
                re.compile(br"dsi_bios9\.bin", re.IGNORECASE),
                re.compile(br"wfcsettings\.bin", re.IGNORECASE),
                re.compile(br"dsi_sd_card(?:\.bin)?", re.IGNORECASE),
                re.compile(br"dldi_sd_card(?:\.bin)?", re.IGNORECASE),
                re.compile(br"firmware\.bin", re.IGNORECASE),
                re.compile(br"NDS7CurrentE", re.IGNORECASE),
                re.compile(br"DSi_NWifi", re.IGNORECASE),
                re.compile(br"FirmwareMem", re.IGNORECASE),
                re.compile(br"CartRetailNAND", re.IGNORECASE),
                re.compile(br"CartRetailIR", re.IGNORECASE),
                re.compile(br"CartRetailBT", re.IGNORECASE),
                re.compile(br"CartHomebrew", re.IGNORECASE),
                re.compile(br"Corrupted firmware detected", re.IGNORECASE),
                re.compile(br"Any game that alters Wi-fi", re.IGNORECASE),
                re.compile(br"BadExceptionRegion", re.IGNORECASE),
                re.compile(br"DS Firmware", re.IGNORECASE),
                re.compile(br"Firmware Flush", re.IGNORECASE),
                re.compile(br"nus\.cdn\.t\.shop\.nintendowifi\.net", re.IGNORECASE),
                re.compile(br"Interpreter", re.IGNORECASE),
                re.compile(br"MatcherCreator", re.IGNORECASE),
                re.compile(br"DSi ARM[79]", re.IGNORECASE),
                re.compile(br"DSi_Camera", re.IGNORECASE),
                re.compile(br"DSi_I2CDevice", re.IGNORECASE),
                re.compile(br"DSi_MMCStorage", re.IGNORECASE),
                re.compile(br"DSi_SDDevice", re.IGNORECASE),
                re.compile(br"DSi_TSC", re.IGNORECASE),
                re.compile(br"3DSiE"),
                re.compile(br"libretro", re.IGNORECASE),
                re.compile(br"retro_[a-z0-9_]+", re.IGNORECASE),
                re.compile(br"Touch Mode", re.IGNORECASE),
                re.compile(br"Next Screen Layout", re.IGNORECASE),
                re.compile(br"Speedup/Slowdown Pointer", re.IGNORECASE),
                re.compile(br"Enable Alternate Controls", re.IGNORECASE),
                re.compile(br"GBA SRAM Flush", re.IGNORECASE),
                re.compile(br"virtual SD card directory", re.IGNORECASE),
                re.compile(br"An internal error occurred with", re.IGNORECASE),
                re.compile(br"contact the developer with the log file", re.IGNORECASE),
                re.compile(br"DLDI driver", re.IGNORECASE),
                re.compile(br"BTDMP", re.IGNORECASE),
                re.compile(br"Btdmp"),
                re.compile(br"Unimplemented MMIO space", re.IGNORECASE),
                re.compile(br"MMIO: cell", re.IGNORECASE),
                re.compile(br"DSIG"),
            ]
            strict_forbidden_patterns.extend(
                re.compile(re.escape(token))
                for token in strict_source_identity_tokens
            )
            strict_rodata_fingerprints = (
                b"Slot 1 & 2 Boot",
                b"CoreState",
                b"GBACart",
                b"DSi_NAND",
                b"_exception",
                b"5retro",
                b"Assertion '%s' failed",
                b"out/llvm-project/",
                b".cpp",
                b".cxx",
                b".cc",
                b".hpp",
                b".hh",
                b"build/generated/patched",
                b"build\\generated\\patched",
                b"C:/Users/",
                b"C:\\Users\\",
                b"HybridSideScreenDisplay",
                b"FormattedPCapFlags",
                b"PowerStatusUpdateTask",
                b"ImportDsiwareSaveData",
                b"FlushGbaSramTask",
                b"DSi_BPTWL",
                b"ARMJIT",
                b"Nintendo DS (Slot 1)",
                b"nds|dsi|ids|gba",
                b"nds|ids|dsi",
                b"DSi_NWifi",
                b"FirmwareMem",
                b"CartRetailNAND",
                b"CartRetailIR",
                b"CartRetailBT",
                b"CartHomebrew",
                b"Corrupted firmware detected",
                b"Any game that alters Wi-fi",
                b"BadExceptionRegion",
                b"DS Firmware",
                b"Firmware Flush",
                b"nus.cdn.t.shop.nintendowifi.net",
                b"Interpreter",
                b"MatcherCreator",
                b"DSi ARM9",
                b"DSi ARM7",
                b"DSi_Camera",
                b"DSi_I2CDevice",
                b"DSi_MMCStorage",
                b"DSi_SDDevice",
                b"DSi_TSC",
                b"3DSiE",
                b"libretro",
                b"retro_",
                b"Touch Mode",
                b"Next Screen Layout",
                b"Speedup/Slowdown Pointer",
                b"Enable Alternate Controls",
                b"GBA SRAM Flush",
                b"virtual SD card directory",
                b"An internal error occurred with",
                b"contact the developer with the log file",
                b"DLDI driver",
                b"BTDMP",
                b"Btdmp",
                b"Unimplemented MMIO space",
                b"MMIO: cell",
            ) + strict_source_identity_tokens
        _patch(filepath, state_section_replacements
               + option_key_replacements + external_path_replacements + [
            (b"MELN",                                   b"Q7X9"),
            ("melonDS".encode("utf-16le"),
             _opaque_diagnostic(b"melonDS").decode("ascii").encode("utf-16le")),
            ("melonDS".encode("utf-16be"),
             _opaque_diagnostic(b"melonDS").decode("ascii").encode("utf-16be")),
            (b"1.3.1 (RelWithDebInfo)",
             _opaque_diagnostic(b"1.3.1 (RelWithDebInfo)")),
            (b"1.3.1", _opaque_diagnostic(b"1.3.1")),
            (re.compile(br"Teakra", re.IGNORECASE),
             teakra_alias),
            (re.compile(br"NDSCart", re.IGNORECASE),
             _opaque_diagnostic(b"NDSCart")),
            (re.compile(br"DSi_DSP", re.IGNORECASE),
             _opaque_diagnostic(b"DSi_DSP")),
            (re.compile(br"Net_PCap", re.IGNORECASE),
             _opaque_diagnostic(b"Net_PCap")),
            (re.compile(br"Net_Slirp", re.IGNORECASE),
             _opaque_diagnostic(b"Net_Slirp")),
            (re.compile(br"LocalMP", re.IGNORECASE),
             _opaque_diagnostic(b"LocalMP")),
            (re.compile(br"libslirp", re.IGNORECASE),
             _opaque_diagnostic(b"libslirp")),
            (b"MelonDsDs", _opaque_diagnostic(b"MelonDsDs")),
            (re.compile(br"melondsds", re.IGNORECASE),
             _opaque_diagnostic(b"melondsds")),
            (re.compile(br"melonds_", re.IGNORECASE),
             _opaque_diagnostic(b"melonds_")),
            (re.compile(br"melonds", re.IGNORECASE),
             _opaque_diagnostic(b"melonds")),
            (re.compile(br"melon", re.IGNORECASE),
             _opaque_diagnostic(b"melon")),
            (b"libretropy", _opaque_diagnostic(b"libretropy")),
        ], forbidden_patterns=[
            re.compile(br"melon", re.IGNORECASE),
            re.compile(br"1\.3\.1", re.IGNORECASE),
            re.compile(br"third_party[/\\]orbit", re.IGNORECASE),
            re.compile(br"\.cxx[/\\]RelWithDebInfo", re.IGNORECASE),
            re.compile(br"Kaeru WFC", re.IGNORECASE),
            re.compile(br"AltWFC", re.IGNORECASE),
            re.compile(br"Threaded Software Renderer", re.IGNORECASE),
            re.compile(br"does not support (?:compressed|archived) GBA save data", re.IGNORECASE),
            re.compile(br"libretropy", re.IGNORECASE),
            re.compile(br"Teakra", re.IGNORECASE),
            re.compile(br"NDSCart", re.IGNORECASE),
            re.compile(br"DSi_DSP", re.IGNORECASE),
            re.compile(br"Net_PCap", re.IGNORECASE),
            re.compile(br"Net_Slirp", re.IGNORECASE),
            re.compile(br"LocalMP", re.IGNORECASE),
            re.compile(br"libslirp", re.IGNORECASE),
            re.compile(br"MELN"),
        ] + strict_forbidden_patterns,
            scrub_diagnostics=True, scrub_metadata=True,
            rodata_identity_fingerprints=(
                b"melon",
                b"q7k3n9p",
                b"Teakra",
                teakra_alias,
                b"NDSCart",
                b"DSi_DSP",
                b"Net_PCap",
                b"Net_Slirp",
                b"LocalMP",
                b"libslirp",
            ) + strict_rodata_fingerprints)
    else:
        print("Unknown core_id: %s" % core_id, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
