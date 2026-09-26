import org.gradle.api.tasks.Sync

plugins {
    id("com.android.library")
}

val protectedBuildSeed = rootProject.extra["emuorbitProtectedBuildSeed"] as String
val nativeSanitizer = rootProject.extra["emuorbitNativeSanitizer"] as String
val upstreamMelonds = rootProject.layout.projectDirectory.dir("third_party/melonds")
val patchedMelonds = layout.buildDirectory.dir("generated/patched-melonds")
val protectedLibretroConsole = layout.buildDirectory
    .file("generated/protected-libretro/config/console.cpp")
val upstreamLibretroConsole = rootProject.layout.projectDirectory
    .file("third_party/melonds-ds/src/libretro/config/console.cpp")
val melondsSanitizerPatch = rootProject.layout.projectDirectory
    .file("cmake/patches/melonds-sanitizer-fixes.patch")
val protectedCoreSourcePatch = rootProject.layout.projectDirectory
    .file("scripts/patch_protected_core_sources.py")
val fetchContentSourceCache = layout.projectDirectory
    .dir(".cxx/fetchcontent/debug-arm64-v8a")
val fetchContentDependencies = listOf(
    listOf("libretro-common", "LIBRETRO-COMMON", "https://github.com/libretro/libretro-common", "ad9124f"),
    listOf("embed-binaries", "EMBED-BINARIES", "https://github.com/andoalon/embed-binaries", "078b62b"),
    listOf("glm", "GLM", "https://github.com/g-truc/glm", "e7970a8"),
    listOf("zlib", "ZLIB", "https://github.com/madler/zlib", "v1.3.1"),
    listOf("libslirp", "LIBSLIRP", "https://github.com/JesseTG/libslirp-mirror", "e61dbd4"),
    listOf("pntr", "PNTR", "https://github.com/robloach/pntr", "922aed0"),
    listOf("fmt", "FMT", "https://github.com/fmtlib/fmt", "11.2.0"),
    listOf("yamc", "YAMC", "https://github.com/yohhoy/yamc", "4e015a7"),
    listOf("span-lite", "SPAN-LITE", "https://github.com/martinmoene/span-lite", "00afc28"),
    listOf("date", "DATE", "https://github.com/HowardHinnant/date", "1ead671")
)

val prepareStableFetchContentSources by tasks.registering {
    group = "build setup"
    description = "Prepares one verified source checkout per pinned melonDS dependency"
    doLast {
        val cacheRoot = fetchContentSourceCache.asFile
        cacheRoot.mkdirs()

        fun runGit(directory: File, vararg arguments: String): String {
            val command = listOf("git", "-c", "advice.detachedHead=false") + arguments
            val process = ProcessBuilder(command)
                .directory(directory)
                .redirectErrorStream(true)
                .start()
            val output = process.inputStream.bufferedReader().use { it.readText() }.trim()
            check(process.waitFor() == 0) {
                "Git failed while preparing ${directory.absolutePath}: " +
                        "${arguments.joinToString(" ")}\n$output"
            }
            return output
        }

        fetchContentDependencies.forEach { dependency ->
            val name = dependency[0]
            val repository = dependency[2]
            val revision = dependency[3]
            val sourceDirectory = cacheRoot.resolve("$name-src")
            if (!sourceDirectory.isDirectory) {
                val cloneOutput = runGit(
                    cacheRoot,
                    "clone",
                    "--no-checkout",
                    repository,
                    sourceDirectory.name
                )
                if (cloneOutput.isNotBlank()) {
                    logger.info(cloneOutput)
                }
                runGit(sourceDirectory, "checkout", revision, "--")
                runGit(sourceDirectory, "submodule", "update", "--recursive", "--init")
            }
            check(sourceDirectory.resolve(".git").exists()) {
                "Incomplete stable FetchContent source: ${sourceDirectory.absolutePath}"
            }
            val head = runGit(sourceDirectory, "rev-parse", "HEAD")
            val expected = runGit(sourceDirectory, "rev-parse", "$revision^{commit}")
            check(head == expected) {
                "Unexpected $name dependency revision: $head; expected $expected ($revision)"
            }
            sourceDirectory.resolve(".emuorbit-fetch-ref").writeText(
                "$repository\n$revision\n$head\n",
                Charsets.UTF_8
            )
        }
    }
}

val stableFetchContentArguments = fetchContentDependencies.flatMap { dependency ->
    val name = dependency[0]
    val variable = dependency[1]
    val source = fetchContentSourceCache.asFile.resolve("$name-src")
        .absolutePath.replace('\\', '/')
    val fetchContentArgument = "-DFETCHCONTENT_SOURCE_DIR_${variable}=$source"
    val melonDsLookupVariable = variable.replace('-', '_')
    if (melonDsLookupVariable == variable) {
        listOf(fetchContentArgument)
    } else {
        // melonDS uses underscore names for its local/remote diagnostic while
        // CMake's FetchContent lookup retains the dependency's hyphenated name.
        listOf(
            fetchContentArgument,
            "-DFETCHCONTENT_SOURCE_DIR_${melonDsLookupVariable}=$source"
        )
    }
}
val stableEmbedBinariesCmake = fetchContentSourceCache.asFile
    .resolve("embed-binaries-src/cmake")
    .absolutePath.replace('\\', '/')

val preparePatchedMelondsSources by tasks.registering(Sync::class) {
    from(upstreamMelonds) {
        exclude(".git", ".git/**")
    }
    into(patchedMelonds)
    inputs.file(melondsSanitizerPatch)
    inputs.file(protectedCoreSourcePatch)
    inputs.file(upstreamLibretroConsole)
    outputs.file(protectedLibretroConsole)

    doLast {
        val outputDirectory = patchedMelonds.get().asFile
        val relativeOutput = rootProject.projectDir.toPath()
            .relativize(outputDirectory.toPath())
            .toString()
            .replace('\\', '/')
        val process = ProcessBuilder(
            "git",
            "apply",
            "--directory=$relativeOutput",
            "--whitespace=nowarn",
            melondsSanitizerPatch.asFile.absolutePath
        )
            .directory(rootProject.projectDir)
            .inheritIO()
            .start()
        check(process.waitFor() == 0) {
            "Unable to apply the versioned native sanitizer fixes"
        }
        val pythonExecutable = if (
            System.getProperty("os.name").lowercase().contains("windows")
        ) "python" else "python3"
        val protectedConsoleFile = protectedLibretroConsole.get().asFile
        protectedConsoleFile.parentFile.mkdirs()
        upstreamLibretroConsole.asFile.copyTo(protectedConsoleFile, overwrite = true)
        val protectionProcess = ProcessBuilder(
            pythonExecutable,
            protectedCoreSourcePatch.asFile.absolutePath,
            "--source-root",
            outputDirectory.absolutePath,
            "--libretro-console",
            protectedConsoleFile.absolutePath
        )
            .directory(rootProject.projectDir)
            .inheritIO()
            .start()
        check(protectionProcess.waitFor() == 0) {
            "Unable to protect functional literals in the native source copy"
        }
    }
}

val debugIdentityMap = layout.buildDirectory
    .file("outputs/hardening/debug/identity-map.json")
    .get().asFile.absolutePath.replace('\\', '/')
val debugNativeSymbols = layout.buildDirectory
    .dir("outputs/native-symbols/debug")
    .get().asFile.absolutePath.replace('\\', '/')
val releaseIdentityMap = layout.buildDirectory
    .file("outputs/hardening/release/identity-map.json")
    .get().asFile.absolutePath.replace('\\', '/')
val releaseNativeSymbols = layout.buildDirectory
    .dir("outputs/native-symbols/release")
    .get().asFile.absolutePath.replace('\\', '/')
val debugCoreContainer = layout.buildDirectory
    .dir("generated/core-container/debug")
    .get().asFile.absolutePath.replace('\\', '/')
val releaseCoreContainer = layout.buildDirectory
    .dir("generated/core-container/release")
    .get().asFile.absolutePath.replace('\\', '/')

android {
    namespace = "com.mateussouza.emuorbit.nativecore"
    compileSdk = libs.versions.compileSdk.get().toInt()
    ndkVersion = libs.versions.ndk.get()

    defaultConfig {
        minSdk = libs.versions.minSdk.get().toInt()

        ndk {
            // melonDS DS officially supports Android ARM64. Keeping the core
            // module ARM64-only also prevents an accidental unsupported ABI
            // from entering a release bundle.
            abiFilters += "arm64-v8a"
        }

        externalNativeBuild {
            cmake {
                targets += listOf(
                    "melondsds_libretro",
                    "emuorbit_patch_secondary"
                )
                arguments += listOf(
                    "-DBUILD_AS_SHARED_LIBRARY=ON",
                    "-DBUILD_TESTING=OFF",
                    "-DENABLE_OPENGL=OFF",
                    "-DENABLE_NETWORKING=ON",
                    "-DENABLE_JIT=ON",
                    "-DENABLE_THREADED_RENDERER=ON",
                    "-DCMAKE_MODULE_PATH=$stableEmbedBinariesCmake",
                    "-DCMAKE_PROJECT_INCLUDE=" +
                            project.file("src/main/cpp/melonds_hardening.cmake")
                                .absolutePath.replace('\\', '/'),
                    "-DFETCHCONTENT_SOURCE_DIR_MELONDS=" +
                            patchedMelonds.get().asFile.absolutePath.replace('\\', '/'),
                    "-DEMUORBIT_PROTECTED_LIBRETRO_CONSOLE=" +
                            protectedLibretroConsole.get().asFile.absolutePath
                                .replace('\\', '/')
                )
                arguments += stableFetchContentArguments
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = rootProject.file("third_party/melonds-ds/CMakeLists.txt")
            version = libs.versions.cmake.get()
        }
    }

    buildTypes {
        debug {
            externalNativeBuild {
                cmake {
                    // The DS CPU/GPU/SPU core cannot sustain real-time audio at
                    // CMake's default -O0 debug level on physical devices. The
                    // private pre-strip copy retains symbols; the APK receives
                    // the same optimized native protection as release.
                    arguments += listOf(
                        "-DCMAKE_C_FLAGS_DEBUG=-O2 -g -DNDEBUG",
                        "-DCMAKE_CXX_FLAGS_DEBUG=-O2 -g -DNDEBUG",
                        "-DEMUORBIT_BUILD_SEED=$protectedBuildSeed",
                        "-DEMUORBIT_HARDENING_MAP=$debugIdentityMap",
                        "-DEMUORBIT_PRIVATE_SYMBOL_DIR=$debugNativeSymbols",
                        "-DEMUORBIT_CONTAINER_OUTPUT=$debugCoreContainer",
                        "-DEMUORBIT_NATIVE_SANITIZER=$nativeSanitizer"
                    )
                }
            }
        }
        release {
            isMinifyEnabled = false
            externalNativeBuild {
                cmake {
                    arguments += listOf(
                        "-DEMUORBIT_BUILD_SEED=$protectedBuildSeed",
                        "-DEMUORBIT_HARDENING_MAP=$releaseIdentityMap",
                        "-DEMUORBIT_PRIVATE_SYMBOL_DIR=$releaseNativeSymbols",
                        "-DEMUORBIT_CONTAINER_OUTPUT=$releaseCoreContainer",
                        "-DEMUORBIT_NATIVE_SANITIZER=none"
                    )
                }
            }
        }
    }

    sourceSets {
        getByName("debug").assets.directories.add(debugCoreContainer)
        getByName("release").assets.directories.add(releaseCoreContainer)
    }

    packaging {
        jniLibs {
            excludes += "**/q*.so"
        }
    }
}

tasks.matching { it.name == "mergeDebugAssets" }.configureEach {
    dependsOn("externalNativeBuildDebug")
}
tasks.matching { it.name == "mergeReleaseAssets" }.configureEach {
    dependsOn("externalNativeBuildRelease")
}
tasks.matching { it.name.startsWith("configureCMake") }.configureEach {
    dependsOn(preparePatchedMelondsSources, prepareStableFetchContentSources)
}
