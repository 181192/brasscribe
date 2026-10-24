import java.io.File
import org.gradle.api.tasks.testing.Test

/**
 * What a product's unit tests need to run its screens on the JVM: the host build of the core, the fixtures the
 * instrumented tests carry as assets, the design's words, the sound files, and Robolectric's settings. A change
 * to any of the files they read runs them again.
 */
fun Test.screenTests(repoRoot: File, robolectric: String, bandSounds: File, catalogue: String, withoutCatalogue: Boolean) {
    systemProperty("jna.library.path", File(repoRoot, "core/target/release").absolutePath)
    systemProperty("scribe.fixtures", File(repoRoot, "apps/fixtures").absolutePath)
    inputs.dir(File(repoRoot, "apps/fixtures")).withPropertyName("screenFixtures")
    // MuteWordingTest reads the design's glossary and icon labels.
    inputs.files(File(repoRoot, "design/brand/brand.md"), File(repoRoot, "design/system.md"), File(repoRoot, "design/README.md"),
        File(repoRoot, "design/tokens/icons.json")).withPropertyName("designWording")
    inputs.files(project.fileTree(File(repoRoot, "core/target/release")) { include("libscribe_ffi.*") }).withPropertyName("hostCore")
    // (Robolectric reaches into the JDK for Android's file descriptors; a newer JDK asks for the export.)
    jvmArgs("--enable-native-access=ALL-UNNAMED", "--add-exports=java.base/jdk.internal.access=ALL-UNNAMED")
    systemProperty("robolectric.graphicsMode", "NATIVE")
    // For the message when a part of Robolectric the screen tests reach into has moved.
    systemProperty("scribe.robolectric", robolectric)
    systemProperty("robolectric.pixelCopyRenderMode", "hardware")
    // -Pscribe.withoutCatalogues: the screen catalogue is left to scripts/screenshots.sh (CI runs it there).
    if (withoutCatalogue) filter.excludeTestsMatching(catalogue)
    // Robolectric keeps one Android per SDK in memory, with native graphics beside it.
    maxHeapSize = "3g"
    // The shared resolver vectors (sounds/partsound-vectors.json) and part map.
    systemProperty("scribe.sounds", System.getenv("SCRIBE_SOUNDS_DIR") ?: File(repoRoot, "sounds").absolutePath)
    systemProperty("scribe.bandSounds", bandSounds.absolutePath)
    systemProperty("scribe.repo", repoRoot.absolutePath)
}
