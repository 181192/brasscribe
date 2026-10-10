plugins {
    alias(libs.plugins.android.library)
}

val repoRoot = rootProject.extra["repoRoot"] as File

/** sfizz checkout for the realistic playback tier (Brasscribe only); see gradle.properties. */
val sfizzDir: String? = (findProperty("brasscribe.sfizzDir") as String?)
    ?: rootDir.resolve("third_party/sfizz").takeIf { it.resolve("CMakeLists.txt").isFile }?.absolutePath

android {
    namespace = "no.brasscribe.play.audio"
    compileSdk = 37
    ndkVersion = "28.2.13676358"

    defaultConfig {
        minSdk = 29
        consumerProguardFiles("consumer-rules.pro")
        externalNativeBuild {
            cmake {
                arguments += listOf("-DANDROID_STL=c++_shared")
            }
        }
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // The app's two products (app/build.gradle.kts), so each gets its own native library. Only Brasscribe
    // has the realistic tier: Fretscribe plays the recording, so its library is always built with the stub
    // and carries no sfizz, with or without a checkout.
    flavorDimensions += "product"
    productFlavors {
        create("brasscribe") {
            isDefault = true
            if (sfizzDir != null) externalNativeBuild { cmake { arguments += "-DSFIZZ_SOURCE_DIR=$sfizzDir" } }
        }
        create("fretscribe")
    }

    buildFeatures { prefab = true }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.31.6"
        }
    }

    testOptions {
        unitTests.all {
            // The shared output-stage vectors (sounds/output-stage-vectors.json).
            it.systemProperty("brasscribe.sounds", System.getenv("BRASSCRIBE_SOUNDS_DIR") ?: File(repoRoot, "sounds").absolutePath)
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

// The task names from before there were two products stay, and mean Brasscribe's library (the one with sfizz
// when there is a checkout). The Kotlin and its tests are the same for both.
mapOf(
    "testDebugUnitTest" to "testBrasscribeDebugUnitTest",
    "connectedDebugAndroidTest" to "connectedBrasscribeDebugAndroidTest",
).forEach { (name, variantTask) -> tasks.register(name) { dependsOn(variantTask) } }

dependencies {
    implementation(libs.oboe)
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.serialization.json)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.ext.junit)
}
