plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

/*
 * The flow both apps are built on: Home, recording and opening, sending to the computer and writing down,
 * the library, sharing, pairing, Settings, Help and the problems, with PlayViewModel and the services they
 * run on. It names no product: each product module hands in its Product and its navigation.
 *
 * The screens compile against Brasscribe's design module and run with the product's own (compileOnly): every
 * brand generates the neutral theme (no.kalli.scribe.design) with the same declarations and resource names.
 *
 * The tests in src/appTest, src/appScreenTest and src/appDeviceTest need an app: each product module runs them
 * under its own (products/<app>/build.gradle.kts).
 */
android {
    namespace = "no.kalli.scribe.play"
    compileSdk = 37

    defaultConfig {
        minSdk = 36
        consumerProguardFiles("consumer-rules.pro")
    }

    buildFeatures { compose = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // The audio library is built for each product; this module takes either.
    defaultConfig { missingDimensionStrategy("product", "brasscribe") }
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

dependencies {
    api(project(":services:model"))
    api(project(":services:engine-client"))
    api(project(":services:audio"))
    api(project(":services:core-bridge"))
    api(project(":services:connection"))
    api(project(":services:library"))
    api(project(":features:score"))
    compileOnly(project(":design:brasscribe"))

    api(libs.androidx.core.ktx)
    api(libs.androidx.activity.compose)
    api(libs.androidx.lifecycle.runtime.compose)
    api(libs.androidx.lifecycle.viewmodel.compose)
    api(libs.androidx.lifecycle.service)
    api(platform(libs.compose.bom))
    api(libs.compose.ui)
    api(libs.compose.ui.graphics)
    api(libs.compose.ui.tooling.preview)
    api(libs.compose.material3)
    api(libs.kotlinx.coroutines.android)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.camera.camera2)
    implementation(libs.camera.lifecycle)
    implementation(libs.camera.view)
    implementation(libs.zxing.core)
    api(libs.alphatab)
    implementation(libs.alphaskia.android)
}
