package no.brasscribe.play

import no.brasscribe.play.engine.Profile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** What Brasscribe does with a score and its result: as before there were two apps, and a tab is not its to open. */
class BrasscribeProductTest {
    @Test
    fun everyBandScoreIsMadeAndArrangedHereAndATabIsNot() {
        val band = listOf(Profile.SOLO, Profile.BRASS_BAND, Profile.ORCHESTRA_WITH_SOLOIST, Profile.POP_ROCK)
        band.forEach {
            assertTrue(it.id, Product.makes(it.id))
            assertTrue(it.id, Product.arranges(it))
        }
        // A tab is Fretscribe's, whichever instrument it is for: also a bass tab an older app made.
        val tabs = listOf(Profile.TAB, Profile.BASS_TAB)
        assertEquals(Profile.entries.toSet(), (band + tabs).toSet())
        tabs.forEach {
            assertFalse(it.id, Product.makes(it.id))
            // No band options and no Check the notes for it.
            assertFalse(it.id, Product.arranges(it))
        }
        assertFalse(Product.makes("tab"))
        assertFalse(Product.makes("bass-tab"))
        // A profile a newer computer has and this app has never heard of is listed as a score, as before.
        assertTrue(Product.makes("big-band"))
    }

    @Test
    fun aTabInTheComputersListOpensInFretscribeAndIsListedApartFromTheBandScoreOfTheSameRecording() {
        fun job(id: String, profile: String, created: Double) = no.brasscribe.play.engine.Job(id, profile, no.brasscribe.play.engine.JobStatus.SUCCEEDED, created,
            emptyList(), audioId = "audio-1", title = id, outputs = listOf(if (Profile.writesTab(profile)) "tab.musicxml" else "brass-band.musicxml"))
        val entries = ScoreEntry.merge(emptyList(), listOf(job("band", "brass-band", 1000.0), job("guitar", "tab", 2000.0), job("bass", "bass-tab", 3000.0)))
        // The two tab runs of the recording collapse to the latest; the band score is never hidden by them.
        assertEquals(listOf("bass", "band"), entries.map { it.title })
        val tab = entries.first()
        assertFalse(tab.opening(review = false, stand = false, Product::makes).here)
        assertTrue(entries.last().opening(review = false, stand = false, Product::makes).here)
        for (profile in listOf("tab", "bass-tab")) {
            val entry = ScoreEntry.merge(emptyList(), listOf(job("t", profile, 1.0))).single()
            assertTrue(profile, entry.onComputer && !Product.makes(entry.profile))
            assertFalse(profile, entry.opening(review = true, stand = false, Product::makes).here)
        }
    }

    @Test
    fun theWordsForATabNameNoInstrumentInEitherLanguage() {
        val res = System.getProperty("brasscribe.sounds")?.let { java.io.File(it).parentFile }?.resolve("apps/android/app/src/main/res")
        org.junit.Assume.assumeTrue("the app's sources are not in this checkout", res?.isDirectory == true)
        val want = mapOf(
            "values" to listOf("Tab · opens in Fretscribe", "This is a tab. Open it in Fretscribe."),
            "values-nb" to listOf("Tab · åpnes i Fretscribe", "Dette er en tab. Åpne den i Fretscribe."),
        )
        for ((dir, words) in want) {
            val strings = java.io.File(res, "$dir/strings.xml").readText()
            fun text(name: String) = Regex("""<string name="$name">(.*?)</string>""").find(strings)?.groupValues?.get(1)
            assertEquals(dir, words, listOf(text("other_product_row"), text("other_product_opens")))
        }
    }

    @Test
    fun aTranscriptionIsFollowedByCheckTheNotes() {
        Profile.entries.forEach {
            assertEquals(it.id, Screen.REVIEW, Product.afterTranscription(TranscriptionResult(null, "<score-partwise/>", it, onDevice = false)))
        }
    }
}
