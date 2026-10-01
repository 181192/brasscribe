import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

val repoRoot = rootProject.extra["repoRoot"] as File
// The band SoundFonts (data/sounds/band, outside git); BRASSCRIBE_BAND_SOUNDS_DIR points at another pack to try it.
val bandSoundsDir = System.getenv("BRASSCRIBE_BAND_SOUNDS_DIR")?.let(::File) ?: File(repoRoot, "data/sounds/band")

android {
    namespace = "no.brasscribe.play"
    compileSdk = 37
    ndkVersion = "28.2.13676358"

    defaultConfig {
        applicationId = "no.brasscribe.play"
        minSdk = 29
        targetSdk = 36
        versionCode = 5
        versionName = "0.3.2"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    androidResources {
        localeFilters += listOf("en", "nb")
        generateLocaleConfig = true
        // alphaTab ships its default SoundFont twice (SF2 and SF3) and only ever opens the SF2.
        ignoreAssetsPattern = "!sonivox.sf3:!.svn:!.git:!.ds_store:!*.scc:.*:!CVS:!thumbs.db:!picasa.ini:!*~"
        // The band SoundFont is copied out once; stored uncompressed it can be sized and streamed.
        noCompress += "sf2"
    }

    // One code base, two apps. Brasscribe is the default and overrides nothing; Fretscribe installs beside
    // it under its own applicationId and version. The namespace (R, packages) is shared.
    flavorDimensions += "product"
    productFlavors {
        create("brasscribe") { isDefault = true }
        create("fretscribe") {
            applicationId = "no.fretscribe.play"
            versionCode = 1
            versionName = "0.0.1"
        }
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

    // The instrumented tests' finished score (apps/fixtures/old-hundredth, a public-domain hymn), in the
    // test APK only: no app build carries it.
    sourceSets["androidTest"].assets.srcDir(File(repoRoot, "apps/fixtures"))

    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            // The shared resolver vectors (sounds/partsound-vectors.json) and part map.
            it.systemProperty("brasscribe.sounds", System.getenv("BRASSCRIBE_SOUNDS_DIR") ?: File(repoRoot, "sounds").absolutePath)
            it.systemProperty("brasscribe.bandSounds", bandSoundsDir.absolutePath)
        }
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
 * Brasscribe's assets that come from outside git; the Fretscribe app carries neither:
 * - models/: SwiftF0 (1.1 MB), Basic Pitch (0.26 MB) and Beat This! small (9.4 MB) ONNX from convert/ (all MIT),
 *   bundled in every Brasscribe build when present.
 * - sounds/brasscribe-band-mobile.sf2: the phone band SoundFont (apps/android/scripts/mobile_soundfont.py,
 *   VSCO 2 CE CC0, Univ. of Iowa MIS, MS Basic kit MIT), bundled in every Brasscribe build when present, so
 *   the band plays its own instruments without a download. Without it the app says the band sounds are missing.
 */
val modelAssets = tasks.register<Sync>("syncModelAssets") {
    into(layout.buildDirectory.dir("generated/brasscribe/models"))
    into("models") {
        from(File(repoRoot, "models/converted/swift-f0")) { include("swift-f0-window.onnx") }
        from(File(repoRoot, "models/converted/basic-pitch")) { include("nmp-b1.onnx") }
        from(File(repoRoot, "models/converted/beat-this")) { include("beat-this-small0.onnx") }
    }
    into("sounds") { from(bandSoundsDir) { include("brasscribe-band-mobile.sf2") } }
    filePermissions { user { read = true; write = true } }
}
// The band SoundFont's part map (committed in sounds/), so presets and balance match the other apps. The
// shared score code reads it, so both apps carry it.
val soundMap = tasks.register<Sync>("syncSoundMap") {
    into(layout.buildDirectory.dir("generated/shared/sounds"))
    into("sounds") { from(File(repoRoot, "sounds")) { include("mapping.json") } }
    filePermissions { user { read = true; write = true } }
}

/*
 * Each product's design system, generated from its tokens by design/tokens/build.py: Brasscribe's in
 * design/dist, Fretscribe's in design/fretscribe/dist. Both have the same Kotlin names, so the shared
 * screens compile against either. The Compose theme and icon enum are compiled from <dist>/android/kotlin
 * as they are; the icon drawables, the display face (as res/font/display, whichever face it is) and the
 * launcher icons are synced into one generated res folder per product (res/font may hold only fonts, so
 * the font's licence goes to the assets instead).
 */
class ProductDesign(val dist: File, val displayFont: String)
val designs = mapOf(
    "brasscribe" to ProductDesign(File(repoRoot, "design/dist"), "instrument_serif"),
    "fretscribe" to ProductDesign(File(repoRoot, "design/fretscribe/dist"), "atkinson_hyperlegible_next"),
)
val designSyncs = designs.flatMap { (product, design) ->
    val name = product.replaceFirstChar(Char::uppercase)
    val dist = design.dist
    val font = design.displayFont
    listOf(
        tasks.register<Sync>("sync${name}DesignResources") {
            into(layout.buildDirectory.dir("generated/$product/design/res"))
            from(File(dist, "android/res")) {
                exclude("font/OFL.txt")
                rename { if (it == "$font.ttf") "display.ttf" else it }
            }
            from(File(dist, "icons/android/res"))
        },
        tasks.register<Sync>("sync${name}DesignLicence") {
            into(layout.buildDirectory.dir("generated/$product/design/assets/licences"))
            from(File(dist, "android/res/font")) {
                include("OFL.txt")
                rename { "${font.replace('_', '-')}-OFL.txt" }
            }
        },
    )
}

androidComponents {
    // Fretscribe has no release build yet.
    beforeVariants(selector().withFlavor("product" to "fretscribe").withBuildType("release")) { it.enable = false }
    onVariants { variant ->
        val product = variant.productFlavors.single { it.first == "product" }.second
        fun generated(path: String) = layout.buildDirectory.dir("generated/$path").get().asFile.path
        variant.sources.kotlin?.addStaticSourceDirectory(File(designs.getValue(product).dist, "android/kotlin").path)
        variant.sources.res?.addStaticSourceDirectory(generated("$product/design/res"))
        variant.sources.assets?.addStaticSourceDirectory(generated("$product/design/assets"))
        variant.sources.assets?.addStaticSourceDirectory(generated("shared/sounds"))
        if (product == "brasscribe") variant.sources.assets?.addStaticSourceDirectory(generated("brasscribe/models"))
    }
}
tasks.named("preBuild") { dependsOn(modelAssets, soundMap, designSyncs) }

// The task names from before there were two products stay, and mean the Brasscribe app.
mapOf(
    "testDebugUnitTest" to "testBrasscribeDebugUnitTest",
    "installDebug" to "installBrasscribeDebug",
    "connectedDebugAndroidTest" to "connectedBrasscribeDebugAndroidTest",
).forEach { (name, variantTask) -> tasks.register(name) { dependsOn(variantTask) } }

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
    implementation(libs.play.services.code.scanner)
    implementation(libs.alphatab)
    implementation(libs.alphaskia.android)
    // The reduced-operator ONNX Runtime (scripts/ort/build-reduced-ort.sh) when it has been built:
    // 13.4 MB instead of 33.0 MB per arm64 APK. Otherwise the full Maven build.
    val reducedOrt = rootProject.file("third_party/onnxruntime/onnxruntime-android-reduced.aar")
    if (reducedOrt.isFile) implementation(files(reducedOrt)) else implementation(libs.onnxruntime.android)

    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)

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
