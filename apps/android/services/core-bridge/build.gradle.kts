plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.serialization)
}

/*
 * The Rust core (core/) behind CoreBridge. The UniFFI Kotlin bindings are compiled from
 * core/android/scribe-core/src/main/kotlin; the native libraries come from
 * scripts/build-core.sh (src/main/jniLibs, git-ignored). Without them the app uses the
 * Kotlin fallback: RustCoreBridge.load returns null.
 */
val repoRoot = rootProject.extra["repoRoot"] as File
val coreRoot = File(repoRoot, "core")

android {
    namespace = "no.kalli.scribe.core.bridge"
    compileSdk = 37

    defaultConfig {
        minSdk = 36
        consumerProguardFiles("consumer-rules.pro")
    }

    sourceSets {
        getByName("main") {
            kotlin.directories.add(File(coreRoot, "android/scribe-core/src/main/kotlin").path)
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.all {
            // JVM tests load the host build of the core (cargo build --release -p scribe-ffi).
            it.systemProperty("jna.library.path", File(coreRoot, "target/release").absolutePath)
            it.systemProperty("scribe.golden", File(repoRoot, "data/golden/mikkel-arranged-band").absolutePath)
            it.systemProperty("scribe.fixtures", File(repoRoot, "apps/fixtures").absolutePath)
            it.jvmArgs("--enable-native-access=ALL-UNNAMED")
            // ONNX Runtime without its telemetry uploader, as in :features:score:pitch (an upload answered at exit aborts the JVM).
            it.environment("ORT_DISABLE_TELEMETRY", "1")
            it.systemProperty("scribe.models", File(repoRoot, "models/converted").absolutePath)
            it.systemProperty("scribe.data", File(repoRoot, "data").absolutePath)
            it.systemProperty("scribe.vectors", File(repoRoot, "docs/accessibility/talking-score-vectors.json").absolutePath)
            it.inputs.file(File(repoRoot, "docs/accessibility/talking-score-vectors.json")).withPropertyName("vectors")
            // The engine's solo profile on the same clip, for comparison (see README); the test skips without it.
            (findProperty("scribe.engineSolo") as String?)?.let { p -> it.systemProperty("scribe.engineSolo", p) }
        }
    }
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

dependencies {
    api(project(":services:model"))
    implementation(libs.jna) { artifact { type = "aar" } }
    testImplementation(libs.junit)
    testImplementation(libs.jna)
    testImplementation(project(":features:score:pitch"))
    testImplementation(libs.onnxruntime.jvm)
}
