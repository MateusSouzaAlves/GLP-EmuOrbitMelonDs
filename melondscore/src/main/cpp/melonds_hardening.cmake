# Included immediately after upstream project() without modifying the submodule.
# Defer target changes until the upstream CMakeLists has created the core.
unset(EMUORBIT_MELONDS_HARDENING_SCHEDULED CACHE)
get_property(
        _emuorbit_melonds_hardening_scheduled
        GLOBAL
        PROPERTY EMUORBIT_MELONDS_HARDENING_SCHEDULED
        SET
)
if(NOT _emuorbit_melonds_hardening_scheduled)
    # A global property lasts for this configure pass only. A cache entry would
    # incorrectly suppress the deferred target changes on later Gradle builds,
    # leaving the packaged filename out of sync with the native bridge.
    set_property(GLOBAL PROPERTY EMUORBIT_MELONDS_HARDENING_SCHEDULED TRUE)

    get_filename_component(
            _emuorbit_sanitizer_workspace_root
            "${CMAKE_CURRENT_LIST_DIR}/../../../.."
            ABSOLUTE
    )
    include("${_emuorbit_sanitizer_workspace_root}/cmake/native_sanitizers.cmake")
    emuorbit_enable_native_sanitizer()
    set(_emuorbit_native_lto_options "")
    if(NOT EMUORBIT_NATIVE_SANITIZER_ENABLED)
        list(APPEND _emuorbit_native_lto_options -flto=thin)
    endif()

    function(emuorbit_harden_melonds)
        if(NOT TARGET melondsds_libretro)
            message(FATAL_ERROR "Secondary libretro target was not created")
        endif()

        get_filename_component(
                _emuorbit_workspace_root
                "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../../../.."
                ABSOLUTE
        )

        include("${_emuorbit_workspace_root}/cmake/protected_symbols.cmake")
        emuorbit_compute_ds_symbols("${EMUORBIT_BUILD_SEED}" "${ANDROID_ABI}")

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
        set(_emuorbit_version_script
                    "${CMAKE_CURRENT_BINARY_DIR}/emuorbit/protected.exports.map")
        file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/emuorbit")
        set(_emuorbit_version_contents "EMUORBIT_1 {\n    global:\n")
        set(_emuorbit_json "{\n  \"seed\": \"${EMUORBIT_BUILD_SEED_RESOLVED}\",\n  \"context\": \"${EMUORBIT_BUILD_CONTEXT_RESOLVED}\",\n")
        string(APPEND _emuorbit_json
                    "  \"library\": \"${EMUORBIT_SECONDARY_BASENAME}.so\",\n  \"container\": \"${EMUORBIT_DS_CONTAINER_ASSET}\",\n  \"types\": {\n    \"NDS\": \"${EMUORBIT_DS_TYPE_NDS}\"\n  },\n  \"layout\": {\n    \"textSeed\": ${EMUORBIT_LAYOUT_TEXT_SEED},\n    \"codegenSeed\": ${EMUORBIT_LAYOUT_CODEGEN_SEED}\n  },\n  \"symbols\": {\n")
        set(_emuorbit_json_separator "")
        set(_emuorbit_abi_definitions "")
        foreach(_emuorbit_abi_name IN LISTS _emuorbit_abi_names)
                string(TOUPPER "${_emuorbit_abi_name}" _emuorbit_abi_suffix)
                set(_emuorbit_abi_variable "EMUORBIT_ABI_${_emuorbit_abi_suffix}")
                set(_emuorbit_opaque_name "${${_emuorbit_abi_variable}}")
                list(APPEND _emuorbit_abi_definitions
                        "${_emuorbit_abi_name}=${_emuorbit_opaque_name}")
                string(APPEND _emuorbit_version_contents
                        "        ${_emuorbit_opaque_name};\n")
                string(APPEND _emuorbit_json
                        "${_emuorbit_json_separator}    \"${_emuorbit_abi_name}\": \"${_emuorbit_opaque_name}\"")
                set(_emuorbit_json_separator ",\n")
        endforeach()
        string(APPEND _emuorbit_version_contents "    local:\n        *;\n};\n")
        string(APPEND _emuorbit_json "\n  },\n  \"paths\": {\n")
        set(_emuorbit_public_paths
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
        set(_emuorbit_json_separator "")
        set(_emuorbit_path_index 0)
        foreach(_emuorbit_public_path IN LISTS _emuorbit_public_paths)
                set(_emuorbit_alias_variable
                        "EMUORBIT_DS_PATH_ALIAS_${_emuorbit_path_index}")
                string(APPEND _emuorbit_json
                        "${_emuorbit_json_separator}    \"${_emuorbit_public_path}\": \"${${_emuorbit_alias_variable}}\"")
                set(_emuorbit_json_separator ",\n")
                math(EXPR _emuorbit_path_index "${_emuorbit_path_index} + 1")
        endforeach()
        string(APPEND _emuorbit_json "\n  },\n  \"stateSections\": {\n")
        string(APPEND _emuorbit_json
                "    \"DSIG\": \"${EMUORBIT_DS_STATE_SECTION_ALIAS_0}\",\n")
        string(APPEND _emuorbit_json
                "    \"DSPi\": \"${EMUORBIT_DS_STATE_SECTION_ALIAS_1}\"\n  }\n}\n")
        file(CONFIGURE
                    OUTPUT "${_emuorbit_version_script}"
                    CONTENT "${_emuorbit_version_contents}"
                    @ONLY
                    NEWLINE_STYLE UNIX
        )

        target_compile_definitions(
                    melondsds_libretro
                    PRIVATE
                    ${_emuorbit_abi_definitions}
                    "NDS=${EMUORBIT_DS_TYPE_NDS}"
                    "EMUORBIT_PROTECTED_LITERAL_SEED=${EMUORBIT_PROTECTED_LITERAL_SEED}U"
        )
        if(NOT DEFINED EMUORBIT_PROTECTED_LIBRETRO_CONSOLE
                    OR NOT EXISTS "${EMUORBIT_PROTECTED_LIBRETRO_CONSOLE}")
                message(FATAL_ERROR "Protected libretro console source is required")
        endif()
        get_target_property(
                    _emuorbit_libretro_source_dir
                    melondsds_libretro
                    SOURCE_DIR
        )
        set(_emuorbit_original_console
                    "${_emuorbit_libretro_source_dir}/config/console.cpp")
        set_source_files_properties(
                    "${_emuorbit_original_console}"
                    TARGET_DIRECTORY melondsds_libretro
                    PROPERTIES HEADER_FILE_ONLY TRUE
        )
        target_sources(
                    melondsds_libretro
                    PRIVATE
                    "${EMUORBIT_PROTECTED_LIBRETRO_CONSOLE}"
        )
        target_include_directories(
                    melondsds_libretro
                    PRIVATE
                    "${_emuorbit_libretro_source_dir}/config"
                    "${CMAKE_CURRENT_FUNCTION_LIST_DIR}"
        )
        if(NOT TARGET core)
            message(FATAL_ERROR "Secondary engine target was not created")
        endif()
        target_compile_definitions(
                    core
                    PRIVATE
                    "NDS=${EMUORBIT_DS_TYPE_NDS}"
                    "EMUORBIT_PROTECTED_LITERAL_SEED=${EMUORBIT_PROTECTED_LITERAL_SEED}U"
                    "EMUORBIT_DS_SHARED_MEMORY_NAME=\"${EMUORBIT_DS_SHARED_MEMORY_NAME}\""
        )
        target_include_directories(
                    core
                    PRIVATE
                    "${CMAKE_CURRENT_FUNCTION_LIST_DIR}"
        )
        set(_emuorbit_output_name "${EMUORBIT_SECONDARY_BASENAME}")
        set(_emuorbit_patch_seed_args
                    --seed "${EMUORBIT_BUILD_SEED_RESOLVED}"
                    --context "${EMUORBIT_BUILD_CONTEXT_RESOLVED}")
        set(_emuorbit_patch_strict_args --strict-protected)
        if(EMUORBIT_NATIVE_SANITIZER_ENABLED)
                # UBSan/ASan deliberately embed source-location metadata outside
                # .rodata. It is required for a useful local diagnostic and is
                # never present in release, where Gradle forces sanitizer=none.
                set(_emuorbit_patch_strict_args "")
        endif()

        if(NOT DEFINED EMUORBIT_HARDENING_MAP
                    OR "${EMUORBIT_HARDENING_MAP}" STREQUAL "")
                message(FATAL_ERROR
                        "EMUORBIT_HARDENING_MAP is required for protected DS builds")
        endif()
        get_filename_component(
                _emuorbit_hardening_map_dir
                "${EMUORBIT_HARDENING_MAP}"
                DIRECTORY
        )
        set(_emuorbit_staged_identity_map
                "${CMAKE_CURRENT_BINARY_DIR}/emuorbit/identity-map.json")
        file(CONFIGURE
                OUTPUT "${_emuorbit_staged_identity_map}"
                CONTENT "${_emuorbit_json}"
                @ONLY
                NEWLINE_STYLE UNIX
        )
        # Build every object participating in the final core with ThinLTO so
        # the linker can discard calls to the protected-build no-op log wrappers.
        # Prefix maps also prevent __FILE__, assertions and debug metadata from
        # embedding the developer's checkout path in the distributed binary.
        foreach(_emuorbit_target melondsds_libretro core slirp)
            if(TARGET ${_emuorbit_target})
                target_compile_options(
                        ${_emuorbit_target}
                        PRIVATE
                        ${_emuorbit_native_lto_options}
                        -ffunction-sections
                        -fdata-sections
                        -fvisibility=hidden
                        $<$<COMPILE_LANGUAGE:CXX>:-fvisibility-inlines-hidden>
                        -fno-ident
                        -ffile-prefix-map=${_emuorbit_workspace_root}=.
                        -fmacro-prefix-map=${_emuorbit_workspace_root}=.
                        -fdebug-prefix-map=${_emuorbit_workspace_root}=.
                        -mllvm
                        "-rng-seed=${EMUORBIT_LAYOUT_CODEGEN_SEED}"
                )
            endif()
        endforeach()

        # The standalone engine is linked as a static archive. Marking its
        # symbols hidden prevents compiler-generated TLS helpers from escaping
        # the final shared library while leaving the libretro entry points on
        # the outer target available to the version script.
        if(TARGET core)
            set_target_properties(
                    core
                    PROPERTIES
                    C_VISIBILITY_PRESET hidden
                    CXX_VISIBILITY_PRESET hidden
                    VISIBILITY_INLINES_HIDDEN YES
            )
        endif()

        target_sources(
                melondsds_libretro
                PRIVATE
                "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/quiet_core_log.cpp"
        )
        target_link_options(
                melondsds_libretro
                PRIVATE
                "-Wl,--version-script=${_emuorbit_version_script}"
                -Wl,--exclude-libs,ALL
                -Wl,-z,relro
                -Wl,-z,now
                -Wl,-z,noexecstack
                ${_emuorbit_native_lto_options}
                -Wl,--gc-sections
                "-Wl,--mllvm=-rng-seed=${EMUORBIT_LAYOUT_CODEGEN_SEED}"
                # Function/data sections already exist for garbage collection.
                # Reorder executable input sections with a per-build seed.
                # Never shuffle .rodata.* here: the DS JIT relies on constant
                # table layout, and doing so caused a deterministic bad branch
                # after gameplay input in real ROMs.
                "-Wl,--shuffle-sections=.text.*=${EMUORBIT_LAYOUT_TEXT_SEED}"
                -Wl,--wrap=_ZN7melonDS8Platform3LogENS0_8LogLevelEPKcz
                -Wl,--wrap=_ZN5retro7fmt_logE15retro_log_levelN3fmt3v1117basic_string_viewIcEENS2_17basic_format_argsINS2_7contextEEE
                -Wl,--wrap=_ZN5retro4vlogE15retro_log_levelPKcSt9__va_list
        )
        # Produce an opaque filename so the packaged binary does not disclose
        # the upstream project it originates from.
        set_target_properties(
                melondsds_libretro
                PROPERTIES
                OUTPUT_NAME "${_emuorbit_output_name}"
                PREFIX ""
                SUFFIX ".so"
        )

        # Replace identifying upstream strings compiled into the binary so
        # that post-build inspection with 'strings' cannot reveal the core.
        find_program(EMUORBIT_PYTHON NAMES python3 python)
        if(EMUORBIT_PYTHON)
            set(EMUORBIT_PATCH_SCRIPT
                    "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../../../../scripts/patch_core_strings.py")
            if(NOT DEFINED EMUORBIT_PRIVATE_SYMBOL_DIR
                    OR "${EMUORBIT_PRIVATE_SYMBOL_DIR}" STREQUAL "")
                message(FATAL_ERROR
                        "EMUORBIT_PRIVATE_SYMBOL_DIR is required for protected DS builds")
            endif()
            if(NOT DEFINED EMUORBIT_CONTAINER_OUTPUT
                    OR "${EMUORBIT_CONTAINER_OUTPUT}" STREQUAL "")
                message(FATAL_ERROR
                        "EMUORBIT_CONTAINER_OUTPUT is required for protected DS builds")
            endif()
            set(EMUORBIT_CONTAINER_SCRIPT
                    "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../../../../scripts/package_core_container.py")
            set(_emuorbit_protected_payload
                    "${CMAKE_CURRENT_BINARY_DIR}/emuorbit/${_emuorbit_output_name}.protected")
            add_custom_target(emuorbit_patch_secondary
                    # The private diagnostic map is variant-specific but shared by
                    # successive CMake work directories. Refresh it during every
                    # packaging run so an incremental build cannot leave the map
                    # pointing at a container generated with an older seed.
                    COMMAND ${CMAKE_COMMAND} -E make_directory
                            "${_emuorbit_hardening_map_dir}"
                    COMMAND ${CMAKE_COMMAND} -E copy_if_different
                            "${_emuorbit_staged_identity_map}"
                            "${EMUORBIT_HARDENING_MAP}"
                    COMMAND ${CMAKE_COMMAND} -E make_directory
                            "${EMUORBIT_PRIVATE_SYMBOL_DIR}/${ANDROID_ABI}"
                    COMMAND ${CMAKE_COMMAND} -E copy
                            $<TARGET_FILE:melondsds_libretro>
                            "${EMUORBIT_PRIVATE_SYMBOL_DIR}/${ANDROID_ABI}/${_emuorbit_output_name}.so"
                    COMMAND ${CMAKE_COMMAND} -E copy
                            $<TARGET_FILE:melondsds_libretro>
                            "${_emuorbit_protected_payload}"
                    COMMAND ${CMAKE_STRIP} --strip-all --remove-section=.comment
                            "${_emuorbit_protected_payload}"
                    COMMAND ${EMUORBIT_PYTHON} ${EMUORBIT_PATCH_SCRIPT}
                            "${_emuorbit_protected_payload}" b
                            ${_emuorbit_patch_strict_args}
                            ${_emuorbit_patch_seed_args}
                    COMMAND ${CMAKE_COMMAND} -E remove_directory
                            "${EMUORBIT_CONTAINER_OUTPUT}"
                    COMMAND ${CMAKE_COMMAND} -E make_directory
                            "${EMUORBIT_CONTAINER_OUTPUT}"
                    COMMAND ${EMUORBIT_PYTHON} ${EMUORBIT_CONTAINER_SCRIPT}
                            pack
                            --input "${_emuorbit_protected_payload}"
                            --output "${EMUORBIT_CONTAINER_OUTPUT}/${EMUORBIT_DS_CONTAINER_ASSET}"
                            --seed "${EMUORBIT_BUILD_SEED_RESOLVED}"
                            --context "${EMUORBIT_BUILD_CONTEXT_RESOLVED}"
                    DEPENDS melondsds_libretro
                    COMMENT "Diversifying and sealing the protected DS module"
                    VERBATIM
            )
        else()
            message(FATAL_ERROR
                    "Python is required to remove protected DS fingerprints")
        endif()
    endfunction()

    cmake_language(DEFER CALL emuorbit_harden_melonds)
endif()
