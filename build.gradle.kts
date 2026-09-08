plugins {
    id("com.android.library") version "9.3.0" apply false
}

val configuredProtectedBuildSeed = providers
    .gradleProperty("EMUORBIT_BUILD_SEED")
    .orElse(providers.environmentVariable("EMUORBIT_BUILD_SEED"))
    .orNull
val protectedBuildSeed = configuredProtectedBuildSeed
    ?: "build-${java.util.UUID.randomUUID().toString().replace("-", "")}"
if (!protectedBuildSeed.matches(Regex("[A-Za-z0-9._-]{8,128}"))) {
    throw GradleException(
        "EMUORBIT_BUILD_SEED must be 8-128 ASCII letters, digits, '.', '_' or '-'"
    )
}
extra["emuorbitProtectedBuildSeed"] = protectedBuildSeed

val configuredNativeSanitizer = providers
    .gradleProperty("EMUORBIT_NATIVE_SANITIZER")
    .orElse(providers.environmentVariable("EMUORBIT_NATIVE_SANITIZER"))
    .orNull
    ?.trim()
    ?.lowercase()
    .orEmpty()
val nativeSanitizer = when (configuredNativeSanitizer) {
    "", "none" -> "none"
    "undefined" -> "undefined"
    "address" -> "address"
    else -> throw GradleException(
        "EMUORBIT_NATIVE_SANITIZER must be none, undefined or address"
    )
}
extra["emuorbitNativeSanitizer"] = nativeSanitizer
