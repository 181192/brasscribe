import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.roborazzi)
}

/*
 * Fretscribe: a recording becomes tab for a fretted instrument. Its screens, words and navigation are here; the flow
 * it shares with Brasscribe is features/play, the tab's logic features/tab. It carries no band sounds, no on-device
 * models and no ONNX Runtime, and its audio library has no sfizz.
 */
val repoRoot = rootProject.extra["repoRoot"] as File
// Where the band's SoundFonts would be: the shared score tests look for them and skip without them.
val bandSoundsDir = System.getenv("SCRIBE_BAND_SOUNDS_DIR")?.let(::File) ?: File(repoRoot, "data/sounds/band")
// Fretscribe's own version, for a release of its own: -Pfretscribe.versionName=1.2.3 -Pfretscribe.versionCode=7.
// Without them it has the version below, as it is released with Brasscribe today.
val fretscribeVersionName = providers.gradleProperty("fretscribe.versionName").orNull?.takeIf(String::isNotBlank)
val fretscribeVersionCode = providers.gradleProperty("fretscribe.versionCode").orNull?.takeIf(String::isNotBlank)?.toInt()
val play = project(":features:play").projectDir

android {
    namespace = "no.kalli.fretscribe"
    compileSdk = 37
    ndkVersion = "28.2.13676358"

    defaultConfig {
        applicationId = "no.kalli.fretscribe"
        minSdk = 36
        targetSdk = 37
        versionCode = 18
        versionName = "0.12.0"
        fretscribeVersionCode?.let { versionCode = it }
        fretscribeVersionName?.let { versionName = it }
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        // The audio library without sfizz: Fretscribe has no realistic tier.
        missingDimensionStrategy("product", "fretscribe")
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
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
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
        // The band's part map (the shared score code reads it), and the tab's face.
        getByName("main").assets.directories.addAll(listOf(
            layout.buildDirectory.dir("generated/sounds").get().asFile.path,
            layout.buildDirectory.dir("generated/tab-font/assets").get().asFile.path,
        ))
    }

    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            it.screenTests(repoRoot, libs.versions.robolectric.get(), bandSoundsDir, "no.kalli.fretscribe.FretscribeScreensTest",
                providers.gradleProperty("scribe.withoutCatalogues").isPresent)
            // Fretscribe's tests ask the engine's own option check about the jobs the app sends, and read the
            // tab fixtures and the crate's presets: a change to any of them runs the tests again.
            it.inputs.files(fileTree(File(repoRoot, "engine/src/scribe_engine")) { include("*.py") }).withPropertyName("engineOptionCheck")
            it.inputs.files(File(repoRoot, "apps/android/scripts/check-tab-options.py"), File(repoRoot, "core/targets/fretted/src/instrument.rs"))
                .withPropertyName("tabOptionSources")
            it.inputs.files(fileTree(File(repoRoot, "apps/fixtures")) { include("*-line/*") }).withPropertyName("tabFixtures")
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

// The band SoundFont's part map (committed in sounds/): the shared score code reads it.
val soundMap = tasks.register<Sync>("syncSoundMap") {
    into(layout.buildDirectory.dir("generated/sounds"))
    into("sounds") { from(File(repoRoot, "sounds")) { include("mapping.json") } }
    filePermissions { user { read = true; write = true } }
}
// Fretscribe Tab, the face of the fret numbers (design/fretscribe/brand/fonts, OFL), with its licence.
val tabFont = tasks.register<Sync>("syncTabFont") {
    val fonts = File(repoRoot, "design/fretscribe/brand/fonts")
    into(layout.buildDirectory.dir("generated/tab-font"))
    into("assets/fonts") { from(fonts) { include("FretscribeTab-Regular.ttf") } }
    into("assets/licences") { from(fonts) { include("OFL-FretscribeTab.txt"); rename { "fretscribe-tab-OFL.txt" } } }
}
tasks.named("preBuild") { dependsOn(soundMap, tabFont) }

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
    implementation(project(":design:fretscribe"))
    implementation(project(":features:tab"))
    // alphaSkia's Java API, to register the tab's own face for the fret numbers. Every build already carries
    // the library (alphaTab brings it in); this only lets Fretscribe's code name it.
    implementation(libs.alphaskia)

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
