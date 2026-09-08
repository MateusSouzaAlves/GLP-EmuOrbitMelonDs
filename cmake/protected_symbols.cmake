# Deterministic DS-module diversification shared by the host bridge and the
# separately built secondary module. Keep this transformation outside pinned
# third-party trees so upstream updates remain reproducible.
function(emuorbit_compute_ds_symbols seed context)
    if("${seed}" STREQUAL "")
        message(FATAL_ERROR
                "EMUORBIT_BUILD_SEED is required; Gradle generates one per invocation")
    endif()

    if("${context}" STREQUAL "" OR NOT "${context}" MATCHES "^[A-Za-z0-9._-]+$")
        message(FATAL_ERROR
                "DS protection context must contain only ASCII letters, digits, '.', '_' or '-'")
    endif()
    set(_emuorbit_domain "${seed}|${context}")

    string(LENGTH "${seed}" _emuorbit_seed_length)
    if(_emuorbit_seed_length LESS 8 OR _emuorbit_seed_length GREATER 128
            OR NOT "${seed}" MATCHES "^[A-Za-z0-9._-]+$")
        message(FATAL_ERROR
                "EMUORBIT_BUILD_SEED must be 8-128 ASCII letters, digits, '.', '_' or '-'")
    endif()

    # lld accepts a deterministic positive integer for section shuffling.
    # Keep the value inside 28 bits so it is portable across CMake/host integer
    # parsing while still changing independently for code layout and codegen.
    # Do not shuffle .rodata input sections: the DS JIT has position-sensitive
    # constant tables, and lld shuffling caused deterministic gameplay crashes.
    foreach(_emuorbit_layout_kind text codegen)
        string(SHA256 _emuorbit_layout_hash
                "${_emuorbit_domain}|link-layout|${_emuorbit_layout_kind}")
        string(SUBSTRING "${_emuorbit_layout_hash}" 0 7
                _emuorbit_layout_short_hash)
        math(EXPR _emuorbit_layout_seed
                "0x${_emuorbit_layout_short_hash}")
        if(_emuorbit_layout_seed EQUAL 0)
            set(_emuorbit_layout_seed 1)
        endif()
        string(TOUPPER "${_emuorbit_layout_kind}"
                _emuorbit_layout_variable)
        set("EMUORBIT_LAYOUT_${_emuorbit_layout_variable}_SEED"
                "${_emuorbit_layout_seed}" PARENT_SCOPE)
    endforeach()

    set(_emuorbit_abi_names
            retro_set_environment
            retro_set_video_refresh
            retro_set_audio_sample
            retro_set_audio_sample_batch
            retro_set_input_poll
            retro_set_input_state
            retro_api_version
            retro_init
            retro_deinit
            retro_load_game
            retro_unload_game
            retro_get_system_av_info
            retro_run
            retro_reset
            retro_get_memory_data
            retro_get_memory_size
            retro_serialize_size
            retro_serialize
            retro_unserialize
            retro_cheat_reset
            retro_cheat_set
    )

    foreach(_emuorbit_abi_name IN LISTS _emuorbit_abi_names)
        string(SHA256 _emuorbit_hash "${_emuorbit_domain}|abi|${_emuorbit_abi_name}")
        string(SUBSTRING "${_emuorbit_hash}" 0 14 _emuorbit_short_hash)
        string(TOUPPER "${_emuorbit_abi_name}" _emuorbit_abi_variable)
        set("EMUORBIT_ABI_${_emuorbit_abi_variable}"
                "q${_emuorbit_short_hash}" PARENT_SCOPE)
    endforeach()

    # NDS::Current creates a compiler-generated TLS helper in .dynstr even
    # after the local symbol table is stripped. Give the class token a valid,
    # same-length C++ identifier that changes with every build. Both the
    # standalone engine and its libretro frontend receive this definition.
    string(SHA256 _emuorbit_nds_type_hash "${_emuorbit_domain}|ds-type|NDS")
    string(SUBSTRING "${_emuorbit_nds_type_hash}" 0 2
            _emuorbit_nds_type_short_hash)
    set(EMUORBIT_DS_TYPE_NDS
            "Q${_emuorbit_nds_type_short_hash}" PARENT_SCOPE)

    # Functional literals which must retain their runtime value are encoded in
    # the disposable source copy instead of being rewritten post-link.  Both
    # the byte stream and the decoding schedule change per build and ABI.
    string(SHA256 _emuorbit_literal_seed_hash
            "${_emuorbit_domain}|protected-functional-literals")
    string(SUBSTRING "${_emuorbit_literal_seed_hash}" 0 8
            _emuorbit_literal_seed_short_hash)
    set(EMUORBIT_PROTECTED_LITERAL_SEED
            "0x${_emuorbit_literal_seed_short_hash}" PARENT_SCOPE)

    # Android exposes this name only for diagnostics.  Replace the whole
    # upstream value rather than keeping a semantic suffix after a randomized
    # project-name prefix.
    string(SHA256 _emuorbit_shared_memory_hash
            "${_emuorbit_domain}|ds-shared-memory")
    string(SUBSTRING "${_emuorbit_shared_memory_hash}" 0 13
            _emuorbit_shared_memory_short_hash)
    set(EMUORBIT_DS_SHARED_MEMORY_NAME
            "q${_emuorbit_shared_memory_short_hash}" PARENT_SCOPE)

    string(SHA256 _emuorbit_library_hash "${_emuorbit_domain}|secondary-library")
    string(SUBSTRING "${_emuorbit_library_hash}" 0 15 _emuorbit_library_short_hash)
    set(EMUORBIT_SECONDARY_BASENAME
            "q${_emuorbit_library_short_hash}" PARENT_SCOPE)

    # DS layout, input and audio options selected directly by the host. All
    # other option keys are learned from the core at runtime. Keep these aliases
    # synchronized with patch_core_strings.py and seed-sensitive so the
    # option-definition table cannot be aligned across protected builds.
    foreach(_emuorbit_option_name
            melonds_number_of_screen_layouts
            melonds_screen_layout1
            melonds_screen_gap
            melonds_hybrid_ratio
            melonds_mic_input
            melonds_mic_input_active
            melonds_show_mic_state
            melonds_show_cursor
            melonds_touch_mode
            melonds_audio_bitdepth
            melonds_audio_interpolation)
        string(LENGTH "${_emuorbit_option_name}" _emuorbit_option_length)
        math(EXPR _emuorbit_option_hash_length
                "${_emuorbit_option_length} - 1")
        string(SHA256 _emuorbit_option_hash
                "${_emuorbit_domain}|ds-option|${_emuorbit_option_name}")
        string(SUBSTRING "${_emuorbit_option_hash}" 0
                ${_emuorbit_option_hash_length} _emuorbit_option_short_hash)
        string(TOUPPER "${_emuorbit_option_name}"
                _emuorbit_option_variable)
        set("EMUORBIT_DS_OPTION_${_emuorbit_option_variable}"
                "q${_emuorbit_option_short_hash}" PARENT_SCOPE)
    endforeach()

    # Paths that the upstream core normally embeds verbatim. The post-link
    # transformer replaces each one with its matching same-length alias. The
    # bridge receives only the aliases plus per-build encoded byte arrays for
    # the public compatibility names, so neither ELF contains the plaintext.
    set(_emuorbit_ds_paths
            "bios9.bin"
            "bios7.bin"
            "dsi_bios9.bin"
            "dsi_bios7.bin"
            "wfcsettings.bin"
            "dsi_sd_card.bin"
            "dldi_sd_card.bin"
            "dsi_sd_card"
            "dldi_sd_card"
            "melonDS DS"
    )
    set(_emuorbit_path_index 0)
    foreach(_emuorbit_public_path IN LISTS _emuorbit_ds_paths)
        string(LENGTH "${_emuorbit_public_path}" _emuorbit_path_length)
        math(EXPR _emuorbit_alias_hash_length "${_emuorbit_path_length} - 1")
        string(SHA256 _emuorbit_path_hash
                "${_emuorbit_domain}|ds-path|${_emuorbit_public_path}")
        string(SUBSTRING "${_emuorbit_path_hash}" 0
                ${_emuorbit_alias_hash_length} _emuorbit_path_short_hash)
        set(_emuorbit_path_alias "q${_emuorbit_path_short_hash}")

        string(HEX "${_emuorbit_public_path}" _emuorbit_public_hex)
        string(HEX "${_emuorbit_path_alias}" _emuorbit_alias_hex)
        set(_emuorbit_mask_state 2166136261)
        math(EXPR _emuorbit_last_alias_byte
                "${_emuorbit_path_length} - 1")
        foreach(_emuorbit_byte_index RANGE 0 ${_emuorbit_last_alias_byte})
            math(EXPR _emuorbit_hex_offset "${_emuorbit_byte_index} * 2")
            string(SUBSTRING "${_emuorbit_alias_hex}"
                    ${_emuorbit_hex_offset} 2 _emuorbit_alias_byte_hex)
            math(EXPR _emuorbit_alias_byte "0x${_emuorbit_alias_byte_hex}")
            math(EXPR _emuorbit_mask_state
                    "((${_emuorbit_mask_state} ^ ${_emuorbit_alias_byte}) * 16777619) & 0xffffffff")
        endforeach()
        set(_emuorbit_encoded_values "")
        math(EXPR _emuorbit_last_path_byte "${_emuorbit_path_length} - 1")
        foreach(_emuorbit_byte_index RANGE 0 ${_emuorbit_last_path_byte})
            math(EXPR _emuorbit_hex_offset "${_emuorbit_byte_index} * 2")
            string(SUBSTRING "${_emuorbit_public_hex}"
                    ${_emuorbit_hex_offset} 2 _emuorbit_public_byte_hex)
            math(EXPR _emuorbit_public_byte "0x${_emuorbit_public_byte_hex}")
            math(EXPR _emuorbit_mask_state
                    "(${_emuorbit_mask_state} ^ ((${_emuorbit_mask_state} << 13) & 0xffffffff)) & 0xffffffff")
            math(EXPR _emuorbit_mask_state
                    "(${_emuorbit_mask_state} ^ (${_emuorbit_mask_state} >> 17)) & 0xffffffff")
            math(EXPR _emuorbit_mask_state
                    "(${_emuorbit_mask_state} ^ ((${_emuorbit_mask_state} << 5) & 0xffffffff)) & 0xffffffff")
            math(EXPR _emuorbit_mask_byte "${_emuorbit_mask_state} & 0xff")
            math(EXPR _emuorbit_encoded_byte
                    "${_emuorbit_public_byte} ^ ${_emuorbit_mask_byte}")
            list(APPEND _emuorbit_encoded_values "${_emuorbit_encoded_byte}")
        endforeach()
        list(JOIN _emuorbit_encoded_values ", " _emuorbit_encoded_csv)

        set("EMUORBIT_DS_PATH_ALIAS_${_emuorbit_path_index}"
                "${_emuorbit_path_alias}" PARENT_SCOPE)
        set("EMUORBIT_DS_PATH_DATA_${_emuorbit_path_index}"
                "${_emuorbit_encoded_csv}" PARENT_SCOPE)
        math(EXPR _emuorbit_path_index "${_emuorbit_path_index} + 1")
    endforeach()
    set(EMUORBIT_DS_PATH_COUNT "${_emuorbit_path_index}" PARENT_SCOPE)

    # A few four-byte savestate section tags are sufficiently distinctive to
    # identify the embedded implementation after the protected payload is
    # recovered.  Give the core per-build aliases while keeping the public
    # on-disk format stable through the bridge.  The bridge receives the
    # public tags only as encoded byte arrays, never as plaintext strings.
    set(_emuorbit_state_tags "DSIG" "DSPi")
    set(_emuorbit_state_prefixes "q" "r")
    set(_emuorbit_state_tag_index 0)
    foreach(_emuorbit_public_tag IN LISTS _emuorbit_state_tags)
        list(GET _emuorbit_state_prefixes ${_emuorbit_state_tag_index}
                _emuorbit_state_prefix)
        string(SHA256 _emuorbit_state_hash
                "${_emuorbit_domain}|state-section|${_emuorbit_public_tag}")
        string(SUBSTRING "${_emuorbit_state_hash}" 0 3
                _emuorbit_state_short_hash)
        set(_emuorbit_state_alias
                "${_emuorbit_state_prefix}${_emuorbit_state_short_hash}")

        string(HEX "${_emuorbit_public_tag}" _emuorbit_state_public_hex)
        string(HEX "${_emuorbit_state_alias}" _emuorbit_state_alias_hex)
        set(_emuorbit_state_mask 2166136261)
        foreach(_emuorbit_byte_index RANGE 0 3)
            math(EXPR _emuorbit_hex_offset "${_emuorbit_byte_index} * 2")
            string(SUBSTRING "${_emuorbit_state_alias_hex}"
                    ${_emuorbit_hex_offset} 2 _emuorbit_alias_byte_hex)
            math(EXPR _emuorbit_alias_byte "0x${_emuorbit_alias_byte_hex}")
            math(EXPR _emuorbit_state_mask
                    "((${_emuorbit_state_mask} ^ ${_emuorbit_alias_byte}) * 16777619) & 0xffffffff")
        endforeach()
        set(_emuorbit_state_encoded_values "")
        foreach(_emuorbit_byte_index RANGE 0 3)
            math(EXPR _emuorbit_hex_offset "${_emuorbit_byte_index} * 2")
            string(SUBSTRING "${_emuorbit_state_public_hex}"
                    ${_emuorbit_hex_offset} 2 _emuorbit_public_byte_hex)
            math(EXPR _emuorbit_public_byte "0x${_emuorbit_public_byte_hex}")
            math(EXPR _emuorbit_state_mask
                    "(${_emuorbit_state_mask} ^ ((${_emuorbit_state_mask} << 13) & 0xffffffff)) & 0xffffffff")
            math(EXPR _emuorbit_state_mask
                    "(${_emuorbit_state_mask} ^ (${_emuorbit_state_mask} >> 17)) & 0xffffffff")
            math(EXPR _emuorbit_state_mask
                    "(${_emuorbit_state_mask} ^ ((${_emuorbit_state_mask} << 5) & 0xffffffff)) & 0xffffffff")
            math(EXPR _emuorbit_mask_byte "${_emuorbit_state_mask} & 0xff")
            math(EXPR _emuorbit_encoded_byte
                    "${_emuorbit_public_byte} ^ ${_emuorbit_mask_byte}")
            list(APPEND _emuorbit_state_encoded_values
                    "${_emuorbit_encoded_byte}")
        endforeach()
        list(JOIN _emuorbit_state_encoded_values ", "
                _emuorbit_state_encoded_csv)
        set("EMUORBIT_DS_STATE_SECTION_ALIAS_${_emuorbit_state_tag_index}"
                "${_emuorbit_state_alias}" PARENT_SCOPE)
        set("EMUORBIT_DS_STATE_SECTION_DATA_${_emuorbit_state_tag_index}"
                "${_emuorbit_state_encoded_csv}" PARENT_SCOPE)
        math(EXPR _emuorbit_state_tag_index
                "${_emuorbit_state_tag_index} + 1")
    endforeach()
    set(EMUORBIT_DS_STATE_SECTION_COUNT
            "${_emuorbit_state_tag_index}" PARENT_SCOPE)

    string(SHA256 _emuorbit_container_asset_hash
            "${_emuorbit_domain}|container-asset")
    string(SUBSTRING "${_emuorbit_container_asset_hash}" 0 23
            _emuorbit_container_asset_short_hash)
    set(EMUORBIT_DS_CONTAINER_ASSET
            "q${_emuorbit_container_asset_short_hash}" PARENT_SCOPE)

    # Build the magic and both key triplets as logical material first. The
    # generated header receives only a masked permutation split across four
    # banks, so neither the keys nor their XOR shares remain adjacent in the
    # wrapper. The layout and masks change for every build and ABI context.
    set(_emuorbit_material_plain_values "")
    foreach(_emuorbit_key_kind encryption authentication)
        string(SHA256 _emuorbit_key_hex
                "${_emuorbit_domain}|container-${_emuorbit_key_kind}")
        string(SHA256 _emuorbit_key_part_a_hex
                "${_emuorbit_domain}|container-key-a|${_emuorbit_key_kind}")
        string(SHA256 _emuorbit_key_part_b_hex
                "${_emuorbit_domain}|container-key-b|${_emuorbit_key_kind}")
        set(_emuorbit_key_part_a_values "")
        set(_emuorbit_key_part_b_values "")
        set(_emuorbit_key_part_c_values "")
        foreach(_emuorbit_byte_index RANGE 0 31)
            math(EXPR _emuorbit_hex_offset "${_emuorbit_byte_index} * 2")
            string(SUBSTRING "${_emuorbit_key_hex}"
                    ${_emuorbit_hex_offset} 2 _emuorbit_key_byte_hex)
            string(SUBSTRING "${_emuorbit_key_part_a_hex}"
                    ${_emuorbit_hex_offset} 2 _emuorbit_key_part_a_byte_hex)
            string(SUBSTRING "${_emuorbit_key_part_b_hex}"
                    ${_emuorbit_hex_offset} 2 _emuorbit_key_part_b_byte_hex)
            math(EXPR _emuorbit_key_byte "0x${_emuorbit_key_byte_hex}")
            math(EXPR _emuorbit_key_part_a_byte
                    "0x${_emuorbit_key_part_a_byte_hex}")
            math(EXPR _emuorbit_key_part_b_byte
                    "0x${_emuorbit_key_part_b_byte_hex}")
            math(EXPR _emuorbit_key_part_c_byte
                    "${_emuorbit_key_byte} ^ ${_emuorbit_key_part_a_byte} ^ ${_emuorbit_key_part_b_byte}")
            list(APPEND _emuorbit_key_part_a_values
                    "${_emuorbit_key_part_a_byte}")
            list(APPEND _emuorbit_key_part_b_values
                    "${_emuorbit_key_part_b_byte}")
            list(APPEND _emuorbit_key_part_c_values
                    "${_emuorbit_key_part_c_byte}")
        endforeach()
        list(APPEND _emuorbit_material_plain_values
                ${_emuorbit_key_part_a_values}
                ${_emuorbit_key_part_b_values}
                ${_emuorbit_key_part_c_values})
    endforeach()

    string(SHA256 _emuorbit_container_magic_hex
            "${_emuorbit_domain}|container-magic")
    set(_emuorbit_container_magic_values "")
    foreach(_emuorbit_byte_index RANGE 0 15)
        math(EXPR _emuorbit_hex_offset "${_emuorbit_byte_index} * 2")
        string(SUBSTRING "${_emuorbit_container_magic_hex}"
                ${_emuorbit_hex_offset} 2 _emuorbit_magic_byte_hex)
        math(EXPR _emuorbit_magic_byte "0x${_emuorbit_magic_byte_hex}")
        list(APPEND _emuorbit_container_magic_values
                "${_emuorbit_magic_byte}")
    endforeach()
    list(APPEND _emuorbit_material_plain_values
            ${_emuorbit_container_magic_values})

    set(_emuorbit_material_size 256)
    set(_emuorbit_material_logical_size 208)
    string(SHA256 _emuorbit_material_layout_hash
            "${_emuorbit_domain}|container-material-layout")
    string(SUBSTRING "${_emuorbit_material_layout_hash}" 0 2
            _emuorbit_material_offset_hex)
    string(SUBSTRING "${_emuorbit_material_layout_hash}" 2 2
            _emuorbit_material_stride_hex)
    string(SUBSTRING "${_emuorbit_material_layout_hash}" 4 2
            _emuorbit_material_mask_a_hex)
    string(SUBSTRING "${_emuorbit_material_layout_hash}" 6 2
            _emuorbit_material_mask_b_hex)
    string(SUBSTRING "${_emuorbit_material_layout_hash}" 8 2
            _emuorbit_material_mask_c_hex)
    string(SUBSTRING "${_emuorbit_material_layout_hash}" 10 2
            _emuorbit_material_mask_d_hex)
    math(EXPR _emuorbit_material_offset
            "0x${_emuorbit_material_offset_hex}")
    math(EXPR _emuorbit_material_stride
            "(0x${_emuorbit_material_stride_hex} | 1) & 0xff")
    math(EXPR _emuorbit_material_mask_a
            "0x${_emuorbit_material_mask_a_hex}")
    math(EXPR _emuorbit_material_mask_b
            "(0x${_emuorbit_material_mask_b_hex} | 1) & 0xff")
    math(EXPR _emuorbit_material_mask_c
            "(0x${_emuorbit_material_mask_c_hex} | 1) & 0xff")
    math(EXPR _emuorbit_material_mask_d
            "0x${_emuorbit_material_mask_d_hex}")

    set(_emuorbit_material_encoded_values "")
    foreach(_emuorbit_physical_index RANGE 0 255)
        math(EXPR _emuorbit_filler_byte
                "(${_emuorbit_material_mask_a} + (${_emuorbit_physical_index} * ${_emuorbit_material_mask_b}) + ((${_emuorbit_physical_index} ^ 0xa5) * ${_emuorbit_material_mask_c})) & 0xff")
        list(APPEND _emuorbit_material_encoded_values
                "${_emuorbit_filler_byte}")
    endforeach()
    foreach(_emuorbit_logical_index RANGE 0 207)
        list(GET _emuorbit_material_plain_values
                ${_emuorbit_logical_index} _emuorbit_plain_byte)
        math(EXPR _emuorbit_physical_index
                "(${_emuorbit_material_offset} + (${_emuorbit_logical_index} * ${_emuorbit_material_stride})) & 0xff")
        math(EXPR _emuorbit_mask_byte
                "(${_emuorbit_material_mask_a} + (${_emuorbit_logical_index} * ${_emuorbit_material_mask_b}) + (${_emuorbit_physical_index} * ${_emuorbit_material_mask_c}) + ((${_emuorbit_logical_index} ^ ${_emuorbit_physical_index}) * ${_emuorbit_material_mask_d})) & 0xff")
        math(EXPR _emuorbit_encoded_byte
                "${_emuorbit_plain_byte} ^ ${_emuorbit_mask_byte}")
        list(REMOVE_AT _emuorbit_material_encoded_values
                ${_emuorbit_physical_index})
        list(INSERT _emuorbit_material_encoded_values
                ${_emuorbit_physical_index} "${_emuorbit_encoded_byte}")
    endforeach()

    foreach(_emuorbit_bank_index RANGE 0 3)
        set("_emuorbit_material_bank_${_emuorbit_bank_index}" "")
    endforeach()
    foreach(_emuorbit_physical_index RANGE 0 255)
        math(EXPR _emuorbit_bank_index "${_emuorbit_physical_index} & 3")
        list(GET _emuorbit_material_encoded_values
                ${_emuorbit_physical_index} _emuorbit_encoded_byte)
        list(APPEND "_emuorbit_material_bank_${_emuorbit_bank_index}"
                "${_emuorbit_encoded_byte}")
    endforeach()
    foreach(_emuorbit_bank_index RANGE 0 3)
        list(JOIN "_emuorbit_material_bank_${_emuorbit_bank_index}" ", "
                _emuorbit_material_bank_csv)
        set("EMUORBIT_DS_MATERIAL_BANK_${_emuorbit_bank_index}"
                "${_emuorbit_material_bank_csv}" PARENT_SCOPE)
    endforeach()
    set(EMUORBIT_DS_MATERIAL_SIZE "${_emuorbit_material_size}" PARENT_SCOPE)
    set(EMUORBIT_DS_MATERIAL_LOGICAL_SIZE
            "${_emuorbit_material_logical_size}" PARENT_SCOPE)
    set(EMUORBIT_DS_MATERIAL_OFFSET
            "${_emuorbit_material_offset}" PARENT_SCOPE)
    set(EMUORBIT_DS_MATERIAL_STRIDE
            "${_emuorbit_material_stride}" PARENT_SCOPE)
    set(EMUORBIT_DS_MATERIAL_MASK_A
            "${_emuorbit_material_mask_a}" PARENT_SCOPE)
    set(EMUORBIT_DS_MATERIAL_MASK_B
            "${_emuorbit_material_mask_b}" PARENT_SCOPE)
    set(EMUORBIT_DS_MATERIAL_MASK_C
            "${_emuorbit_material_mask_c}" PARENT_SCOPE)
    set(EMUORBIT_DS_MATERIAL_MASK_D
            "${_emuorbit_material_mask_d}" PARENT_SCOPE)
    set(EMUORBIT_BUILD_SEED_RESOLVED "${seed}" PARENT_SCOPE)
    set(EMUORBIT_BUILD_CONTEXT_RESOLVED "${context}" PARENT_SCOPE)
endfunction()
