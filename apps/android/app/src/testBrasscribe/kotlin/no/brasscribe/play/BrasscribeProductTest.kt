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
    fun aDraftOpensOnTheScoreAndEveryOtherTranscriptionInCheckTheNotes() {
        // A draft marks every melody note "?" (Basic Pitch alone votes on it): Check the notes would list them all.
        val draft = TranscriptionResult(null, "<score-partwise/>", Profile.BRASS_BAND, onDevice = true, draft = true)
        assertEquals(Screen.SCORE, Product.afterTranscription(draft))
        assertEquals(Screen.REVIEW, Product.afterTranscription(draft.copy(draft = false)))
        assertEquals(Screen.REVIEW, Product.afterTranscription(TranscriptionResult(null, "<score-partwise/>", Profile.BRASS_BAND, onDevice = false, jobId = "j")))
        assertEquals(Screen.REVIEW, Product.afterTranscription(TranscriptionResult(null, "<score-partwise/>", Profile.SOLO, onDevice = true)))
    }

    @Test
    fun aSoloGoesFromCheckTheNotesStraightToTheScoreAndABandTakeAsksHowItShouldBe() {
        assertEquals(Screen.SCORE, Product.afterReview(TranscriptionResult(null, "<score-partwise/>", Profile.SOLO, onDevice = true)))
        assertEquals(Screen.SCORE, Product.afterReview(TranscriptionResult(null, "<score-partwise/>", Profile.SOLO, onDevice = false, jobId = "j")))
        for (band in listOf(Profile.BRASS_BAND, Profile.ORCHESTRA_WITH_SOLOIST, Profile.POP_ROCK))
            assertEquals(band.id, Screen.OUTPUT, Product.afterReview(TranscriptionResult(null, "<score-partwise/>", band, onDevice = false, jobId = "j")))
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
    fun theTranscribingScreenPromisesNothingTheAppDoesNotKeep() {
        // A solo made on the phone has nothing to keep it going while the app is away: the screen says to keep it open and
        // stays on. A draft (its service) and a job on the computer (followed by a service, with a notification when it is
        // done) say the player can switch to another app.
        assertTrue(Product.KEEP_OPEN_WHILE_WRITING)
        val res = System.getProperty("brasscribe.sounds")?.let { java.io.File(it).parentFile }?.resolve("apps/android/app/src/main/res")
        org.junit.Assume.assumeTrue("the app's sources are not in this checkout", res?.isDirectory == true)
        val want = mapOf(
            "values" to listOf("%1\$s. Keep Brasscribe open until the score is ready.",
                "%1\$s. You can switch to another app: the draft goes on, and it is on the screen when you come back."),
            "values-nb" to listOf("%1\$s. Hold Brasscribe åpen til partituret er klart.",
                "%1\$s. Du kan bytte til en annen app: utkastet lages videre, og det er på skjermen når du kommer tilbake."),
        )
        for ((dir, words) in want) {
            val strings = java.io.File(res, "$dir/strings.xml").readText()
            fun text(name: String) = Regex("""<string name="$name">(.*?)</string>""").find(strings)?.groupValues?.get(1)
            assertEquals(dir, words, listOf(text("transcribe_leave"), text("transcribe_leave_draft")))
        }
        val computer = mapOf(
            "values" to listOf("%1\$s. You can switch to another app: Brasscribe tells you when the score is ready, or soon after if the phone is asleep.",
                "%1\$s. You can switch to another app: when the score is ready, it is in Your scores while your phone is connected to your computer."),
            "values-nb" to listOf("%1\$s. Du kan bytte til en annen app: Brasscribe sier fra når partituret er klart, eller litt etter hvis telefonen sover.",
                "%1\$s. Du kan bytte til en annen app: når partituret er klart, ligger det i Partiturene dine så lenge telefonen er koblet til datamaskinen."),
        )
        for ((dir, words) in computer) {
            val strings = java.io.File(res, "$dir/strings.xml").readText()
            fun text(name: String) = Regex("""<string name="$name">(.*?)</string>""").find(strings)?.groupValues?.get(1)
            assertEquals(dir, words, listOf(text("transcribe_leave_computer"), text("transcribe_leave_computer_quiet")))
        }
    }

    @Test
    fun aTranscriptionIsFollowedByCheckTheNotes() {
        Profile.entries.forEach {
            assertEquals(it.id, Screen.REVIEW, Product.afterTranscription(TranscriptionResult(null, "<score-partwise/>", it, onDevice = false)))
        }
    }

    @Test
    fun notConnectedIsInformationNotAWarning() {
        // A score is made on the phone without the computer: nothing is wrong, so the row has an ⓘ, not a warning.
        assertEquals(R.drawable.ic_bc_info, no.brasscribe.play.ui.connectionIcon(no.brasscribe.play.connection.ConnectionState.Offline(paired = false)))
        assertEquals(R.drawable.ic_bc_info, no.brasscribe.play.ui.connectionIcon(no.brasscribe.play.connection.ConnectionState.Offline(paired = true)))
    }
}
