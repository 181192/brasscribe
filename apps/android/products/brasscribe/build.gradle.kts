import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.roborazzi)
}

/*
 * Brasscribe: a recording becomes a brass-band score. Its screens, words and navigation are here; the flow it
 * shares with Fretscribe is features/play, the score features/score.
 */
val repoRoot = rootProject.extra["repoRoot"] as File
// The band SoundFonts (data/sounds/band, outside git); SCRIBE_BAND_SOUNDS_DIR points at another pack to try it.
val bandSoundsDir = System.getenv("SCRIBE_BAND_SOUNDS_DIR")?.let(::File) ?: File(repoRoot, "data/sounds/band")
val play = project(":features:play").projectDir

android {
    namespace = "no.kalli.brasscribe"
    compileSdk = 37
    ndkVersion = "28.2.13676358"

    defaultConfig {
        applicationId = "no.kalli.brasscribe"
        minSdk = 36
        targetSdk = 37
        versionCode = 18
        versionName = "0.12.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        // The audio library with sfizz, the realistic tier.
        missingDimensionStrategy("product", "brasscribe")
    }

    androidResources {
        localeFilters += listOf("en", "nb")
        generateLocaleConfig = true
        // alphaTab ships its default SoundFont twice (SF2 and SF3) and only ever opens the SF2.
        ignoreAssetsPattern = "!sonivox.sf3:!.svn:!.git:!.ds_store:!*.scc:.*:!CVS:!thumbs.db:!picasa.ini:!*~"
        // The band SoundFont is copied out once; stored uncompressed it can be sized and streamed.
        noCompress += "sf2"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-onnx.pro")
        }
    }

    buildFeatures { compose = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    sourceSets {
        // The flow's tests (features/play) run in this app, beside its own: the screen tests (src/screenTest here,
        // src/appScreenTest there) are one source for two runs, on the JVM with the unit tests (Robolectric) and
        // on a device with the instrumented ones. What differs between the two (the text size, the language, a key
        // press, where the fixtures are read from) is behind ScreenDevice, which each run has its own of.
        getByName("test") {
            kotlin.directories.addAll(listOf("src/screenTest/kotlin", "$play/src/appScreenTest/kotlin", "$play/src/appTest/kotlin"))
            resources.directories.add("$play/src/appTest/resources")
            // alphaTab draws with alphaSkia's native library. The app carries the Android build of it; the unit
            // tests load the build for the machine they run on (syncHostSkia below).
            jniLibs.directories.add(layout.buildDirectory.dir("host-skia").get().asFile.path)
        }
        getByName("androidTest") {
            kotlin.directories.addAll(listOf("src/screenTest/kotlin", "$play/src/appScreenTest/kotlin", "$play/src/appDeviceTest/kotlin"))
            // The instrumented tests' finished score (apps/fixtures/old-hundredth, a public-domain hymn), in the
            // test APK only: no app build carries it.
            assets.directories.add(File(repoRoot, "apps/fixtures").path)
        }
        // Brasscribe's assets from outside git, and the band's part map.
        getByName("main").assets.directories.addAll(listOf(
            layout.buildDirectory.dir("generated/models").get().asFile.path,
            layout.buildDirectory.dir("generated/sounds").get().asFile.path,
        ))
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            it.screenTests(repoRoot, libs.versions.robolectric.get(), bandSoundsDir, "no.kalli.brasscribe.BrasscribeScreensTest",
                providers.gradleProperty("scribe.withoutCatalogues").isPresent)
        }
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
        checkDependencies = true
        lintConfig = rootProject.file("lint.xml")
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
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}

/*
 * Brasscribe's assets that come from outside git:
 * - models/: SwiftF0 (1.1 MB), Basic Pitch (0.26 MB) and Beat This! small (9.4 MB) ONNX from convert/ (all MIT),
 *   bundled in every build when present.
 * - sounds/brasscribe-band-mobile.sf2: the phone band SoundFont (apps/android/scripts/mobile_soundfont.py,
 *   VSCO 2 CE CC0, Univ. of Iowa MIS, MS Basic kit MIT), bundled in every build when present, so the band plays
 *   its own instruments without a download. Without it the app says the band sounds are missing.
 * And the band SoundFont's part map (committed in sounds/), so presets and balance match the other apps.
 */
val modelAssets = tasks.register<Sync>("syncModelAssets") {
    into(layout.buildDirectory.dir("generated/models"))
    into("models") {
        from(File(repoRoot, "models/converted/swift-f0")) { include("swift-f0-window.onnx") }
        from(File(repoRoot, "models/converted/basic-pitch")) { include("nmp-b1.onnx") }
        from(File(repoRoot, "models/converted/beat-this")) { include("beat-this-small0.onnx") }
    }
    into("sounds") { from(bandSoundsDir) { include("brasscribe-band-mobile.sf2") } }
    filePermissions { user { read = true; write = true } }
}
val soundMap = tasks.register<Sync>("syncSoundMap") {
    into(layout.buildDirectory.dir("generated/sounds"))
    into("sounds") { from(File(repoRoot, "sounds")) { include("mapping.json") } }
    filePermissions { user { read = true; write = true } }
}
tasks.named("preBuild") { dependsOn(modelAssets, soundMap) }

androidComponents {
    onVariants { variant ->
        val variantName = variant.name.replaceFirstChar(Char::uppercase)
        val verifyNoGoogleServices = tasks.register<VerifyNoGoogleServices>("verifyNoGoogleServices$variantName") {
            mergedManifest.set(variant.artifacts.get(com.android.build.api.artifact.SingleArtifact.MERGED_MANIFEST))
            report.set(layout.buildDirectory.file("reports/no-google-services/${variant.name}.txt"))
            modules.set(VerifyNoGoogleServices.modulesOf(variant.runtimeConfiguration))
        }
        // Every APK and bundle, every install, and every unit-test run (the fast checks) goes through the check.
        val checked = setOf("assemble", "package", "bundle", "install").map { "$it$variantName" }.toSet() +
            "test${variantName}UnitTest"
        tasks.matching { it.name in checked }.configureEach { dependsOn(verifyNoGoogleServices) }
    }
}

val hostSkia by configurations.creating { isTransitive = false }
val syncHostSkia = tasks.register<HostSkia>("syncHostSkia") {
    jars.from(hostSkia)
    platform.set(HostSkia.platform())
    into.set(layout.buildDirectory.dir("host-skia"))
}
tasks.withType<Test>().configureEach { dependsOn(syncHostSkia) }

dependencies {
    implementation(project(":features:play"))
    implementation(project(":design:brasscribe"))
    // Listening on the phone (OnPhoneModels): the models' code and ONNX Runtime to run them.
    implementation(project(":features:score:pitch"))
    // The reduced-operator ONNX Runtime (scripts/ort/build-reduced-ort.sh) when it has been built:
    // 13.4 MB instead of 33.0 MB per arm64 APK. Otherwise the full Maven build.
    val reducedOrt = rootProject.file("third_party/onnxruntime/onnxruntime-android-reduced.aar")
    if (reducedOrt.isFile) implementation(files(reducedOrt)) else implementation(libs.onnxruntime.android)

    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    // The screens on the JVM: Robolectric, the Compose test rule with the accessibility checks, and Roborazzi for
    // the screenshots. The desktop JNA loads the host build of the core.
    testImplementation(platform(libs.compose.bom))
    testImplementation(libs.robolectric)
    testImplementation(libs.roborazzi)
    testImplementation(libs.roborazzi.compose)
    testImplementation(libs.compose.ui.test.junit4)
    testImplementation(libs.compose.ui.test.junit4.accessibility)
    testImplementation(libs.androidx.test.ext.junit)
    testImplementation(libs.androidx.test.espresso.core)
    testImplementation(libs.androidx.test.espresso.accessibility)
    testImplementation(libs.atf)
    testImplementation(libs.jna)
    hostSkia(HostSkia.library(libs.alphaskia.macos, libs.alphaskia.windows, libs.alphaskia.linux))

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
