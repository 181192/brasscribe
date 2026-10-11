import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.roborazzi)
}

val repoRoot = rootProject.extra["repoRoot"] as File
// The band SoundFonts (data/sounds/band, outside git); BRASSCRIBE_BAND_SOUNDS_DIR points at another pack to try it.
val bandSoundsDir = System.getenv("BRASSCRIBE_BAND_SOUNDS_DIR")?.let(::File) ?: File(repoRoot, "data/sounds/band")
// Fretscribe's own version, for a release of its own: -Pfretscribe.versionName=1.2.3 -Pfretscribe.versionCode=7.
// Without them it has the version in defaultConfig, as it is released with Brasscribe today.
val fretscribeVersionName = providers.gradleProperty("fretscribe.versionName").orNull?.takeIf(String::isNotBlank)
val fretscribeVersionCode = providers.gradleProperty("fretscribe.versionCode").orNull?.takeIf(String::isNotBlank)?.toInt()

android {
    namespace = "no.brasscribe.play"
    compileSdk = 37
    ndkVersion = "28.2.13676358"

    defaultConfig {
        applicationId = "no.brasscribe.play"
        minSdk = 29
        targetSdk = 36
        versionCode = 13
        versionName = "0.9.0"
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
    // it under its own applicationId. Its version is the one above unless the build is given its own
    // (fretscribe.versionName, fretscribe.versionCode). The namespace (R, packages) is shared.
    flavorDimensions += "product"
    productFlavors {
        create("brasscribe") { isDefault = true }
        create("fretscribe") {
            applicationId = "no.fretscribe.play"
            fretscribeVersionName?.let { versionName = it }
            fretscribeVersionCode?.let { versionCode = it }
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

    // The screen tests (src/screenTest*) are one source for two runs: on the JVM with the unit tests
    // (Robolectric), and on a device with the instrumented ones. What differs between the two (the text size,
    // the language, a key press, where the fixtures are read from) is behind ScreenDevice, which each run has
    // its own of (src/test and src/androidTest).
    for ((shared, runs) in mapOf(
        "screenTest" to listOf("test", "androidTest"),
        "screenTestBrasscribe" to listOf("testBrasscribe", "androidTestBrasscribe"),
        "screenTestFretscribe" to listOf("testFretscribe", "androidTestFretscribe"),
    )) for (run in runs) sourceSets[run].kotlin.directories.add("src/$shared/kotlin")
    // alphaTab draws with alphaSkia's native library. The app carries the Android build of it; the unit tests
    // load the build for the machine they run on (syncHostSkia below), found like a test's own JNI library.
    sourceSets["test"].jniLibs.directories.add(layout.buildDirectory.dir("host-skia").get().asFile.path)

    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            // The screens run against the host build of the core (as core-bridge's tests do) and read the
            // fixtures the instrumented tests carry as assets.
            it.systemProperty("jna.library.path", File(repoRoot, "core/target/release").absolutePath)
            it.systemProperty("brasscribe.fixtures", File(repoRoot, "apps/fixtures").absolutePath)
            it.inputs.dir(File(repoRoot, "apps/fixtures")).withPropertyName("screenFixtures")
            // MuteWordingTest reads the design's glossary and icon labels.
            it.inputs.files(File(repoRoot, "design/brand/brand.md"), File(repoRoot, "design/system.md"), File(repoRoot, "design/README.md"),
                File(repoRoot, "design/tokens/icons.json")).withPropertyName("designWording")
            it.inputs.files(fileTree(File(repoRoot, "core/target/release")) { include("libscribe_ffi.*") }).withPropertyName("hostCore")
            // (Robolectric reaches into the JDK for Android's file descriptors; a newer JDK asks for the export.)
            it.jvmArgs("--enable-native-access=ALL-UNNAMED", "--add-exports=java.base/jdk.internal.access=ALL-UNNAMED")
            it.systemProperty("robolectric.graphicsMode", "NATIVE")
            // For the message when a part of Robolectric the screen tests reach into has moved.
            it.systemProperty("brasscribe.robolectric", libs.versions.robolectric.get())
            it.systemProperty("robolectric.pixelCopyRenderMode", "hardware")
            // -Pbrasscribe.withoutCatalogues: the screen catalogues are left to scripts/screenshots.sh (CI runs them there).
            if (providers.gradleProperty("brasscribe.withoutCatalogues").isPresent) {
                it.filter.excludeTestsMatching("no.brasscribe.play.BrasscribeScreensTest")
                it.filter.excludeTestsMatching("no.brasscribe.play.FretscribeScreensTest")
            }
            // Robolectric keeps one Android per SDK in memory, with native graphics beside it.
            it.maxHeapSize = "3g"
            // The shared resolver vectors (sounds/partsound-vectors.json) and part map.
            it.systemProperty("brasscribe.sounds", System.getenv("BRASSCRIBE_SOUNDS_DIR") ?: File(repoRoot, "sounds").absolutePath)
            it.systemProperty("brasscribe.bandSounds", bandSoundsDir.absolutePath)
            // Fretscribe's tests ask the engine's own option check about the jobs the app sends, and read the
            // tab fixtures and the crate's presets: a change to any of them runs the tests again.
            it.inputs.files(fileTree(File(repoRoot, "engine/src/brasscribe_engine")) { include("*.py") }).withPropertyName("engineOptionCheck")
            it.inputs.files(File(repoRoot, "apps/android/scripts/check-tab-options.py"), File(repoRoot, "core/targets/fretted/src/instrument.rs"))
                .withPropertyName("tabOptionSources")
            it.inputs.files(fileTree(File(repoRoot, "apps/fixtures")) { include("*-line/*") }).withPropertyName("tabFixtures")
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

// Fretscribe Tab, the face of the fret numbers (design/fretscribe/brand/fonts, OFL), with its licence: in the
// Fretscribe app only.
val tabFont = tasks.register<Sync>("syncFretscribeTabFont") {
    val fonts = File(repoRoot, "design/fretscribe/brand/fonts")
    into(layout.buildDirectory.dir("generated/fretscribe/tab-font"))
    into("assets/fonts") { from(fonts) { include("FretscribeTab-Regular.ttf") } }
    into("assets/licences") { from(fonts) { include("OFL-FretscribeTab.txt"); rename { "fretscribe-tab-OFL.txt" } } }
}

/**
 * Fails when a component that reports off the phone is in a variant's merged manifest: ONNX Runtime's (its AAR adds a
 * telemetry provider, which the app's manifest removes with tools:node="remove"), and Google's ML Kit, Play services,
 * Firebase and datatransport (Firelog) ones, which the Play services code scanner brought in and which logged ML Kit
 * usage to Google. Those four are not to be in the app at all, so a library of theirs on the variant's runtime
 * classpath fails it too, components or not. A new AAR, a renamed class, a lost line or a new dependency would bring
 * them, or something like them, back.
 */
abstract class VerifyNoTelemetry : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val mergedManifest: RegularFileProperty

    /** The variant's runtime classpath, as group:module. */
    @get:Input
    abstract val modules: ListProperty<String>

    @get:OutputFile
    abstract val report: RegularFileProperty

    @TaskAction
    fun verify() {
        val libraries = modules.get().filter { module -> REPORTERS.any { module.startsWith("$it:") || module.startsWith("$it.") } }
        check(libraries.isEmpty()) {
            "Libraries that report off the phone are on the runtime classpath: $libraries. Remove the dependency that brings them " +
                "(./gradlew :app:dependencies shows which)."
        }
        val manifest = mergedManifest.get().asFile.readText()
        val found = Regex("""android:(?:name|authorities)="([^"]*)"""").findAll(manifest).map { it.groupValues[1] }
            .filter { name -> "onnxruntime" in name || REPORTERS.any { name.startsWith(it) } }.toList()
        check(found.isEmpty()) {
            "Components that report off the phone are in ${mergedManifest.get().asFile}: $found. " +
                "Remove the dependency that brings them, or remove them in app/src/main/AndroidManifest.xml (tools:node=\"remove\")."
        }
        report.get().asFile.writeText("no ONNX Runtime, ML Kit, Play services, Firebase or datatransport component\n")
    }

    companion object {
        val REPORTERS = listOf("com.google.mlkit", "com.google.android.datatransport", "com.google.android.gms", "com.google.firebase")
    }
}

androidComponents {
    onVariants { variant ->
        val variantName = variant.name.replaceFirstChar(Char::uppercase)
        val verifyNoTelemetry = tasks.register<VerifyNoTelemetry>("verifyNoTelemetry$variantName") {
            mergedManifest.set(variant.artifacts.get(com.android.build.api.artifact.SingleArtifact.MERGED_MANIFEST))
            report.set(layout.buildDirectory.file("reports/no-telemetry/${variant.name}.txt"))
            modules.set(variant.runtimeConfiguration.incoming.resolutionResult.rootComponent.map { root ->
                val seen = mutableSetOf(root.id)
                val queue = ArrayDeque(listOf(root))
                val found = sortedSetOf<String>()
                while (queue.isNotEmpty()) {
                    val component = queue.removeFirst()
                    (component.id as? org.gradle.api.artifacts.component.ModuleComponentIdentifier)?.let { found += "${it.group}:${it.module}" }
                    component.dependencies.filterIsInstance<org.gradle.api.artifacts.result.ResolvedDependencyResult>()
                        .map { it.selected }.filter { seen.add(it.id) }.forEach(queue::add)
                }
                found.toList()
            })
        }
        // Every APK and bundle, every install, and every unit-test run (the fast checks) goes through the check.
        val checked = setOf("assemble", "package", "bundle", "install").map { "$it$variantName" }.toSet() +
            "test${variantName}UnitTest"
        tasks.matching { it.name in checked }.configureEach { dependsOn(verifyNoTelemetry) }
        val product = variant.productFlavors.single { it.first == "product" }.second
        fun generated(path: String) = layout.buildDirectory.dir("generated/$path").get().asFile.path
        variant.sources.kotlin?.addStaticSourceDirectory(File(designs.getValue(product).dist, "android/kotlin").path)
        variant.sources.res?.addStaticSourceDirectory(generated("$product/design/res"))
        variant.sources.assets?.addStaticSourceDirectory(generated("$product/design/assets"))
        variant.sources.assets?.addStaticSourceDirectory(generated("shared/sounds"))
        if (product == "brasscribe") variant.sources.assets?.addStaticSourceDirectory(generated("brasscribe/models"))
        if (product == "fretscribe") variant.sources.assets?.addStaticSourceDirectory(generated("fretscribe/tab-font/assets"))
    }
}
tasks.named("preBuild") { dependsOn(modelAssets, soundMap, designSyncs, tabFont) }

// alphaSkia for the machine the unit tests run on: the same drawing code as the app's, from the same release.
val hostOs = System.getProperty("os.name").lowercase().let { if ("mac" in it) "macos" else if ("win" in it) "windows" else "linux" }
val hostArch = System.getProperty("os.arch").let { if (it == "aarch64" || it == "arm64") "arm64" else "x64" }
val hostSkia by configurations.creating { isTransitive = false }
val hostSkiaLibrary = when (hostOs) { "macos" -> libs.alphaskia.macos; "windows" -> libs.alphaskia.windows; else -> libs.alphaskia.linux }
abstract class HostSkia @Inject constructor(private val archives: ArchiveOperations, private val files: FileSystemOperations) : DefaultTask() {
    @get:InputFiles abstract val jars: ConfigurableFileCollection
    @get:Input abstract val platform: Property<String>
    @get:OutputDirectory abstract val into: DirectoryProperty

    @TaskAction
    fun sync() {
        val folder = "native/${platform.get()}/*"
        files.sync {
            from(jars.map { archives.zipTree(it) }) {
                include(folder)
                eachFile { path = name }
                includeEmptyDirs = false
            }
            into(into)
        }
    }
}
val syncHostSkia = tasks.register<HostSkia>("syncHostSkia") {
    jars.from(hostSkia)
    platform.set("$hostOs-$hostArch")
    into.set(layout.buildDirectory.dir("host-skia"))
}
tasks.withType<Test>().configureEach { dependsOn(syncHostSkia) }

// The task names from before there were two products stay, and mean the Brasscribe app.
mapOf(
    "testDebugUnitTest" to "testBrasscribeDebugUnitTest",
    "installDebug" to "installBrasscribeDebug",
    "connectedDebugAndroidTest" to "connectedBrasscribeDebugAndroidTest",
).forEach { (name, variantTask) -> tasks.register(name) { dependsOn(variantTask) } }

dependencies {
    implementation(project(":model"))
    implementation(project(":engine-client"))
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
    implementation(libs.camera.camera2)
    implementation(libs.camera.lifecycle)
    implementation(libs.camera.view)
    implementation(libs.zxing.core)
    implementation(libs.alphatab)
    implementation(libs.alphaskia.android)
    // alphaSkia's Java API, to register the tab's own face for the fret numbers. Every build already carries
    // the library (alphaTab brings it in); this only lets Fretscribe's code name it.
    "fretscribeImplementation"(libs.alphaskia)
    // The recording as the sound of the tab: slowed down or sped up with its pitch kept. Fretscribe only.
    "fretscribeImplementation"(libs.media3.exoplayer)
    // Listening on the phone is Brasscribe's (src/brasscribe, OnPhoneModels): the models' code and ONNX Runtime
    // to run them. Fretscribe's tabs are written on the computer, so its app has neither.
    "brasscribeImplementation"(project(":pitch"))
    // The reduced-operator ONNX Runtime (scripts/ort/build-reduced-ort.sh) when it has been built:
    // 13.4 MB instead of 33.0 MB per arm64 APK. Otherwise the full Maven build.
    val reducedOrt = rootProject.file("third_party/onnxruntime/onnxruntime-android-reduced.aar")
    if (reducedOrt.isFile) "brasscribeImplementation"(files(reducedOrt)) else "brasscribeImplementation"(libs.onnxruntime.android)

    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    // The screens on the JVM (src/screenTest*): Robolectric, the Compose test rule with the accessibility
    // checks, and Roborazzi for the screenshots. The desktop JNA loads the host build of the core.
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
    hostSkia(hostSkiaLibrary)

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
