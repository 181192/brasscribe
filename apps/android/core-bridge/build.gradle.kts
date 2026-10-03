plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.serialization)
}

/*
 * The Rust core (core/) behind CoreBridge. The UniFFI Kotlin bindings are compiled from
 * core/android/brasscribe-core/src/main/kotlin; the native libraries come from
 * scripts/build-core.sh (src/main/jniLibs, git-ignored). Without them the app uses the
 * Kotlin fallback: RustCoreBridge.load() returns null.
 */
val repoRoot = rootProject.extra["repoRoot"] as File
val coreRoot = File(repoRoot, "core")

android {
    namespace = "no.brasscribe.play.core"
    compileSdk = 37

    defaultConfig {
        minSdk = 29
        consumerProguardFiles("consumer-rules.pro")
    }

    sourceSets {
        getByName("main") {
            kotlin.directories.add(File(coreRoot, "android/brasscribe-core/src/main/kotlin").path)
        }
    }

    lint { lintConfig = file("lint.xml") }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.all {
            // JVM tests load the host build of the core (cargo build --release -p brasscribe-ffi).
            it.systemProperty("jna.library.path", File(coreRoot, "target/release").absolutePath)
            it.systemProperty("brasscribe.golden", File(repoRoot, "data/golden/mikkel-arranged-band").absolutePath)
            it.jvmArgs("--enable-native-access=ALL-UNNAMED")
            // ONNX Runtime without its telemetry uploader, as in :pitch (an upload answered at exit aborts the JVM).
            it.environment("ORT_DISABLE_TELEMETRY", "1")
            it.systemProperty("brasscribe.models", File(repoRoot, "models/converted").absolutePath)
            it.systemProperty("brasscribe.data", File(repoRoot, "data").absolutePath)
            // The engine's solo profile on the same clip, for comparison (see README); the test skips without it.
            (findProperty("brasscribe.engineSolo") as String?)?.let { p -> it.systemProperty("brasscribe.engineSolo", p) }
        }
    }
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

dependencies {
    api(project(":model"))
    implementation(libs.jna) { artifact { type = "aar" } }
    testImplementation(libs.junit)
    testImplementation(libs.jna)
    testImplementation(project(":pitch"))
    testImplementation(libs.onnxruntime.jvm)
}
