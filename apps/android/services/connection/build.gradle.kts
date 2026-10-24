// Pairing and reaching the computer: the stored credentials, the network's state, finding the engine on the
// local network, the pairing QR code and the engine's HTTP client.
plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "no.kalli.scribe.connection"
    compileSdk = 37

    defaultConfig { minSdk = 36 }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

dependencies {
    api(project(":services:engine-client"))
    implementation(libs.ktor.client.okhttp)
    implementation(libs.zxing.core)
    // Whether the app is asking for the local network, which the screens follow.
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.runtime)
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}
