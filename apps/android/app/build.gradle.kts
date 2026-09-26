import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

val repoRoot = rootProject.extra["repoRoot"] as File

android {
    namespace = "no.brasscribe.play"
    compileSdk = 37
    ndkVersion = "28.2.13676358"

    defaultConfig {
        applicationId = "no.brasscribe.play"
        minSdk = 29
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    androidResources {
        localeFilters += listOf("en", "nb")
        generateLocaleConfig = true
        // alphaTab ships its default SoundFont twice (SF2 and SF3) and only ever opens the SF2.
        ignoreAssetsPattern = "!sonivox.sf3:!.svn:!.git:!.ds_store:!*.scc:.*:!CVS:!thumbs.db:!picasa.ini:!*~"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
        checkDependencies = true
        lintConfig = file("lint.xml")
        htmlReport = true
        xmlReport = true
    }

    // One APK per ABI for release (what a phone downloads), plus a universal one. ONNX Runtime and
    // alphaSkia dominate the native size, so shipping both ABIs in one file would double it.
    splits {
        abi {
            isEnable = gradle.startParameter.taskNames.any { it.contains("Release", ignoreCase = true) }
            reset()
            include("arm64-v8a", "x86_64")
            isUniversalApk = true
        }
    }

    packaging {
        jniLibs { useLegacyPackaging = false }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
        // alphaTab's generated Kotlin API is marked with these.
        optIn.addAll("kotlin.contracts.ExperimentalContracts", "kotlin.ExperimentalUnsignedTypes")
    }
}

/*
 * Assets that come from outside git:
 * - models/: SwiftF0 (1.1 MB), Basic Pitch (0.26 MB) and Beat This! small (9.4 MB) ONNX from convert/ (all MIT),
 *   bundled in every build when present.
 * - fixtures/: the golden Mikkel output, debug builds only, for the built-in sample engine.
 */
val modelAssets = tasks.register<Sync>("syncModelAssets") {
    from(File(repoRoot, "models/converted/swift-f0")) { include("swift-f0-window.onnx") }
    from(File(repoRoot, "models/converted/basic-pitch")) { include("nmp-b1.onnx") }
    from(File(repoRoot, "models/converted/beat-this")) { include("beat-this-small0.onnx") }
    into(layout.buildDirectory.dir("generated/brasscribe/models/models"))
    filePermissions { user { read = true; write = true } }
}
val fixtureAssets = tasks.register<Sync>("syncFixtureAssets") {
    from(File(repoRoot, "data/golden/mikkel-arranged-band")) {
        include("composition.json", "brass-band.musicxml", "brass-band.pdf", "brass-band.mp3", "brass-band.brf", "brass-band.mid")
    }
    into(layout.buildDirectory.dir("generated/brasscribe/fixtures/fixtures"))
    // The golden output is read-only; the copies must stay writable so the next sync can replace them.
    filePermissions { user { read = true; write = true } }
}

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addStaticSourceDirectory(layout.buildDirectory.dir("generated/brasscribe/models").get().asFile.path)
        if (variant.buildType == "debug") {
            variant.sources.assets?.addStaticSourceDirectory(layout.buildDirectory.dir("generated/brasscribe/fixtures").get().asFile.path)
        }
    }
}
tasks.named("preBuild") { dependsOn(modelAssets, fixtureAssets) }

dependencies {
    implementation(project(":model"))
    implementation(project(":engine-client"))
    implementation(project(":pitch"))
    implementation(project(":audio"))
    implementation(project(":core-bridge"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.service)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.alphatab)
    // The reduced-operator ONNX Runtime (scripts/ort/build-reduced-ort.sh) when it has been built:
    // 13.4 MB instead of 33.0 MB per arm64 APK. Otherwise the full Maven build.
    val reducedOrt = rootProject.file("third_party/onnxruntime/onnxruntime-android-reduced.aar")
    if (reducedOrt.isFile) implementation(files(reducedOrt)) else implementation(libs.onnxruntime.android)

    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(libs.junit)

    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)
    androidTestImplementation(libs.compose.ui.test.junit4.accessibility)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.espresso.core)
    androidTestImplementation(libs.androidx.test.espresso.accessibility)
    androidTestImplementation(libs.atf)
    androidTestImplementation(libs.kotlinx.coroutines.test)
}
