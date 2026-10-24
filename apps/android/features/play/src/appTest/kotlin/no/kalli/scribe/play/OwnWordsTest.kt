package no.kalli.scribe.play

import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.testedProduct
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Every app has its own words, complete, in every language it speaks: each string the shared screens name
 * (features/play's res, which the shared code compiles against) is the app's own too, in the same folder, so no
 * shared default is ever shown.
 */
@RunWith(AndroidJUnit4::class)
class OwnWordsTest {
    private val android = File(checkNotNull(System.getProperty("scribe.repo")) { "scribe.repo is not set by the build" }, "apps/android")

    private fun names(dir: File): Set<String> =
        dir.listFiles { f -> f.extension == "xml" }.orEmpty().flatMap { file ->
            Regex("""<(?:string|plurals|string-array)\s+name="([^"]+)"""").findAll(file.readText()).map { it.groupValues[1] }.toList()
        }.toSet()

    @Test
    fun everySharedStringIsTheAppsOwnInEveryLanguage() {
        val shared = File(android, "features/play/src/main/res")
        val own = File(android, "products/${testedProduct.name.lowercase()}/src/main/res")
        assertTrue("the app's words are where this test reads them: $own", own.isDirectory)
        val folders = shared.listFiles { f -> f.isDirectory && f.name.startsWith("values") }.orEmpty()
        assertTrue("the shared words are found", folders.any { it.name == "values-nb" })
        for (folder in folders) {
            val missing = names(folder) - names(File(own, folder.name))
            assertEquals("${testedProduct.name} ${folder.name}", emptySet<String>(), missing)
        }
    }
}
