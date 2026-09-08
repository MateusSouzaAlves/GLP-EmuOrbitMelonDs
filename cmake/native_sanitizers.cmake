include_guard(GLOBAL)

# Opt-in instrumentation for local debug diagnostics. Production builds always
# pass "none" from Gradle and therefore retain their normal hardened flags.
function(emuorbit_enable_native_sanitizer)
    if(NOT DEFINED EMUORBIT_NATIVE_SANITIZER
            OR "${EMUORBIT_NATIVE_SANITIZER}" STREQUAL "")
        set(EMUORBIT_NATIVE_SANITIZER "none")
    endif()
    string(TOLOWER "${EMUORBIT_NATIVE_SANITIZER}" _emuorbit_sanitizer)

    if(_emuorbit_sanitizer STREQUAL "none")
        set(EMUORBIT_NATIVE_SANITIZER_ENABLED FALSE PARENT_SCOPE)
        return()
    endif()
    if(NOT ANDROID)
        message(FATAL_ERROR "EmuOrbit native sanitizer diagnostics require Android")
    endif()
    if(NOT CMAKE_BUILD_TYPE STREQUAL "Debug")
        message(FATAL_ERROR
                "EmuOrbit native sanitizers are allowed only in Debug builds")
    endif()

    set(_emuorbit_compile_options -fno-omit-frame-pointer -g)
    set(_emuorbit_link_options "")
    if(_emuorbit_sanitizer STREQUAL "undefined")
        list(APPEND _emuorbit_compile_options
                -fsanitize=undefined
                -fsanitize-minimal-runtime
                -fno-sanitize-recover=undefined)
        list(APPEND _emuorbit_link_options
                -fsanitize=undefined
                -fsanitize-minimal-runtime
                -fno-sanitize-recover=undefined)
    elseif(_emuorbit_sanitizer STREQUAL "address")
        list(APPEND _emuorbit_compile_options -fsanitize=address)
        list(APPEND _emuorbit_link_options -fsanitize=address)
    else()
        message(FATAL_ERROR
                "Unsupported EMUORBIT_NATIVE_SANITIZER: ${_emuorbit_sanitizer}")
    endif()

    add_compile_options(${_emuorbit_compile_options})
    add_link_options(${_emuorbit_link_options})
    set(EMUORBIT_NATIVE_SANITIZER_ENABLED TRUE PARENT_SCOPE)
    message(STATUS
            "EmuOrbit native sanitizer diagnostic enabled: ${_emuorbit_sanitizer}")
endfunction()
