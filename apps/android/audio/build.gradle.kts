plugins {
    alias(libs.plugins.android.library)
}

/** sfizz checkout for the realistic playback tier; see gradle.properties. */
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
                if (sfizzDir != null) arguments += "-DSFIZZ_SOURCE_DIR=$sfizzDir"
            }
        }
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures { prefab = true }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.31.6"
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
    implementation(libs.oboe)
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.ext.junit)
}
