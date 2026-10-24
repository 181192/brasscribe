plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.compose)
}

/*
 * The tab's logic: the player's fretted instrument, the practice player's state and clock, and the recording
 * played at any speed with its pitch kept. No screens and no words: Fretscribe's are in its product module.
 */
android {
    namespace = "no.kalli.scribe.tab"
    compileSdk = 37

    defaultConfig { minSdk = 36 }

    buildFeatures { compose = true }

    testOptions {
        unitTests.all {
            // The tests find the repository's fixtures and sources beside the sounds folder.
            it.systemProperty("scribe.sounds", File(rootProject.extra["repoRoot"] as File, "sounds").absolutePath)
        }
    }

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
    api(project(":services:connection"))
    api(libs.media3.exoplayer)
    api(libs.androidx.lifecycle.viewmodel.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}
