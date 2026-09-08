// Release-link wrappers for diagnostic-only upstream logging.
//
// GNU/LLD --wrap redirects references to the symbols below without modifying
// the pinned upstream submodules. The real implementations remain available
// to the linker, while ThinLTO sees these wrappers as side-effect-free and can
// remove their format strings and argument construction from release builds.

extern "C" void
__wrap__ZN7melonDS8Platform3LogENS0_8LogLevelEPKcz() noexcept {
}

extern "C" void
__wrap__ZN5retro7fmt_logE15retro_log_levelN3fmt3v1117basic_string_viewIcEENS2_17basic_format_argsINS2_7contextEEE()
        noexcept {
}

extern "C" void
__wrap__ZN5retro4vlogE15retro_log_levelPKcSt9__va_list() noexcept {
}
