// Android library (AAR) around the brasscribe Rust core: the UniFFI Kotlin
// bindings (src/main/kotlin, from core/scripts/bindings.sh) and the native
// libraries per ABI (src/main/jniLibs, from core/scripts/build-all.sh).
plugins {
    id("com.android.library") version "9.3.3"
}

android {
    namespace = "no.brasscribe.core"
    compileSdk = 36

    defaultConfig {
        minSdk = 26
        consumerProguardFiles("consumer-rules.pro")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    // UniFFI's Kotlin bindings call the native library through JNA.
    implementation("net.java.dev.jna:jna:5.17.0@aar")
}
