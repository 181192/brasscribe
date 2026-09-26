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
}
