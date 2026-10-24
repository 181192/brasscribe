plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.serialization)
}

/*
 * The score: alphaTab's engraving and player around a MusicXML score, the marks on it, the band's sounds,
 * playback of a bar and of the recording beside it, and the PDF laid out on the phone. No screens.
 */
val repoRoot = rootProject.extra["repoRoot"] as File

android {
    namespace = "no.kalli.scribe.score"
    compileSdk = 37

    defaultConfig {
        minSdk = 36
        missingDimensionStrategy("product", "brasscribe")
    }

    buildFeatures { buildConfig = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.all {
            it.systemProperty("scribe.sounds", System.getenv("SCRIBE_SOUNDS_DIR") ?: File(repoRoot, "sounds").absolutePath)
            it.systemProperty("scribe.bandSounds", (System.getenv("SCRIBE_BAND_SOUNDS_DIR")?.let(::File) ?: File(repoRoot, "data/sounds/band")).absolutePath)
        }
    }
}

kotlin {
    compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
}

dependencies {
    api(project(":services:model"))
    api(project(":services:audio"))
    api(libs.alphatab)
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
}
