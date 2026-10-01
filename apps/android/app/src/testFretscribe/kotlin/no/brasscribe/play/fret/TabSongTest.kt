package no.brasscribe.play.fret

import no.brasscribe.play.ErrorWords
import no.brasscribe.play.Product
import no.brasscribe.play.R
import no.brasscribe.play.Screen
import no.brasscribe.play.Source
import no.brasscribe.play.SourceKind
import no.brasscribe.play.TranscriptionResult
import no.brasscribe.play.engine.EngineException
import no.brasscribe.play.engine.FrettedInstrument
import no.brasscribe.play.engine.JobCreate
import no.brasscribe.play.engine.Octave
import no.brasscribe.play.engine.OctaveSource
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.engine.Recording
import no.brasscribe.play.engine.ReferencePitch
import no.brasscribe.play.engine.Refusal
import no.brasscribe.play.engine.Tab
import no.brasscribe.play.engine.TabLayout
import no.brasscribe.play.engine.TabOptions
import no.brasscribe.play.model.BrasscribeJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/**
 * A bass-tab job as Fretscribe sends it, Check the song's rows, the song's line in Your songs, and the
 * words for what the computer refuses. The recorded result is apps/fixtures/bass-line.
 */
class TabSongTest {
    // The repository root is two up from the sounds folder the build passes in.
    private val fixture: File? = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }?.resolve("apps/fixtures/bass-line")

    private fun recorded(): Tab {
        assumeTrue("apps/fixtures/bass-line is not in this checkout", fixture?.isDirectory == true)
        return BrasscribeJson.decodeFromString(Tab.serializer(), File(fixture, "tab.json").readText())
    }

    @Test
    fun theJobCarriesTheInstrumentAndTheAnswerForTheSong() {
        val mine = YourInstrument(strings = 5, tuning = "drop-a", reads = Reads.TAB_AND_NOTATION)
        assertEquals(
            TabOptions(FrettedInstrument.BASS_5, "drop-a", capo = 0, style = null, recording = Recording.INSTRUMENT, octave = Octave.AUTO, layout = TabLayout.TAB_AND_NOTATION),
            tabOptions(mine, SongAnswer(Recording.INSTRUMENT)),
        )
        assertEquals(Recording.SONG, tabOptions(mine, SongAnswer(Recording.SONG)).recording)
        // Every instrument, tuning and layout of Your instrument reaches the job as it is.
        for ((strings, tunings) in YourInstrument.BASS_TUNINGS) for (tuning in tunings) for (reads in Reads.entries) for (recording in listOf(Recording.SONG, Recording.INSTRUMENT)) {
            val o = tabOptions(YourInstrument(strings = strings, tuning = tuning, reads = reads), SongAnswer(recording))
            assertEquals("bass-$strings", o.instrument?.id)
            assertEquals(tuning, o.tuning)
            assertEquals(reads.id, o.layout?.id)
            assertEquals(recording, o.recording)
            assertEquals(0, o.capo)
            assertEquals(Octave.AUTO, o.octave)
            assertNull(o.style)
        }
        // The hand never reaches the job.
        assertEquals(tabOptions(YourInstrument(), SongAnswer(Recording.SONG)), tabOptions(YourInstrument(hand = FrettingHand.RIGHT), SongAnswer(Recording.SONG)))
    }

    @Test
    fun aSongIsWrittenDownAgainWithTheOptionsItWasMadeWithAndOneChange() {
        val tab = recorded()
        val alone = listOf("beats", "transcribe.bass.basic-pitch", "transcribe.bass.swift-f0", "notes", "arrange", "export")
        // Read back from the result and its job: nothing else has to remember the answers.
        val made = SongCheck.optionsOf(tab, alone)
        assertEquals(TabOptions(FrettedInstrument.BASS_4, "standard", capo = 0, style = no.brasscribe.play.engine.FingeringStyle.AS_PLAYED,
            recording = Recording.INSTRUMENT, octave = Octave.AUTO, layout = TabLayout.TAB), made)
        // A full song was separated first.
        assertEquals(Recording.SONG, SongCheck.optionsOf(tab, listOf("beats", "stems") + alone.drop(1)).recording)
        // What the player chose for the octave is kept; what Fretscribe chose stays its to choose.
        assertEquals(Octave.AUTO, SongCheck.optionsOf(tab.copy(octaveShift = -12), alone).octave)
        assertEquals(Octave.DOWN, SongCheck.optionsOf(tab.copy(octaveShift = -12, octaveSource = OctaveSource.CHOSEN), alone).octave)
        assertEquals(Octave.UP, SongCheck.optionsOf(tab.copy(octaveShift = 12, octaveSource = OctaveSource.CHOSEN), alone).octave)
        assertEquals(Octave.AS_HEARD, SongCheck.optionsOf(tab.copy(octaveSource = OctaveSource.CHOSEN), alone).octave)
        val fiveString = SongCheck.optionsOf(tab.copy(preset = "bass-5-drop-a", layout = TabLayout.NOTATION), alone)
        assertEquals(listOf(FrettedInstrument.BASS_5, "drop-a", TabLayout.NOTATION), listOf(fiveString.instrument, fiveString.tuning, fiveString.layout))

        // Use Drop D: those options with the tuning changed are the job, whatever Your instrument says now.
        val again = made.copy(tuning = "drop-d")
        assertEquals(again, tabOptions(YourInstrument(strings = 6, reads = Reads.NOTATION), SongAnswer(again.recording, again = again)))
        // Continue on What is this? starts afresh: the player's instrument as it is now.
        assertEquals("standard", tabOptions(YourInstrument(), SongAnswer(Recording.INSTRUMENT)).tuning)
    }

    @Test
    fun theTimeSignatureIsSaidInWords() {
        assertEquals("two-four", SongCheck.meterWords(2, 4, bokmal = false))
        assertEquals("four-four", SongCheck.meterWords(4, 4, bokmal = false))
        assertEquals("six-eight", SongCheck.meterWords(6, 8, bokmal = false))
        assertEquals("to firedels", SongCheck.meterWords(2, 4, bokmal = true))
        assertEquals("seks åttedels", SongCheck.meterWords(6, 8, bokmal = true))
        assertEquals("to halve", SongCheck.meterWords(2, 2, bokmal = true))
        // One with no words here is still said, as its digits.
        assertEquals("13 8", SongCheck.meterWords(13, 8, bokmal = false))
    }

    @Test
    fun theJobIsABassTabJobWithNoneOfTheBandsOptions() {
        val request = JobCreate("audio-1", Profile.BASS_TAB.id, title = "Riff", seat = "2nd-cornet", reads = "treble", lead = "seat")
        val job = tabJob(request, tabOptions(YourInstrument(tuning = "bead"), SongAnswer(Recording.INSTRUMENT)))
        assertEquals("bass-tab", job.profile)
        assertEquals("audio-1", job.audioId)
        assertEquals("Riff", job.title)
        assertEquals(listOf(null, null, null), listOf(job.seat, job.reads, job.lead))
        assertEquals(FrettedInstrument.BASS_4, job.instrument)
        assertEquals("bead", job.tuning)
        assertEquals(Recording.INSTRUMENT, job.recording)
        assertEquals(0, job.capo)
        assertEquals(Octave.AUTO, job.octave)
        assertEquals(TabLayout.TAB, job.layout)
        assertNull(job.style)
    }

    @Test
    fun aTabIsFollowedByCheckTheSongAndIsNeverArrangedForABand() {
        fun result(p: Profile) = TranscriptionResult(null, "<score-partwise/>", p, onDevice = false)
        // Check the song is drawn in the place of the output choices.
        assertEquals(Screen.OUTPUT, Product.afterTranscription(result(Profile.BASS_TAB)))
        assertEquals(Screen.REVIEW, Product.afterTranscription(result(Profile.SOLO)))
        assertTrue(Product.makes("bass-tab"))
        Profile.entries.filter { it != Profile.BASS_TAB }.forEach { assertFalse(it.id, Product.makes(it.id)) }
        Profile.entries.forEach { assertFalse(it.id, Product.arranges(it)) }
    }

    @Test
    fun theAnswerStaysWithItsRecording() {
        val riff = Source("riff.wav", SourceKind.FILE, 12.0, file = File("takes/riff.wav"))
        val other = Source("other.wav", SourceKind.FILE, 30.0, file = File("takes/other.wav"))
        SongAnswers.set(riff, SongAnswer(Recording.INSTRUMENT))
        assertEquals(SongAnswer(Recording.INSTRUMENT), SongAnswers.of(riff))
        // Another recording has not been asked about: nothing is chosen for it.
        assertEquals(SongAnswer(), SongAnswers.of(other))
        assertEquals(SongAnswer(), SongAnswers.of(null))
        SongAnswers.set(other, SongAnswer(Recording.SONG))
        assertEquals(SongAnswer(), SongAnswers.of(riff))
    }

    @Test
    fun theRecordedTabHasNothingUnusualSoItShowsTheTuningAndTheKeyAndTempo() {
        val tab = recorded()
        assertEquals(
            listOf(SongRow.Tuning("standard", null), SongRow.KeyAndTempo(fifths = 1, minor = true, bpm = 100, beats = 2, beatUnit = 4)),
            SongCheck.rows(tab),
        )
    }

    @Test
    fun aTuningThatFitsBetterIsOffered() {
        val tab = recorded()
        val dropD = tab.tuningSuggestions.first { it.preset == "bass-4-drop-d" }
        val suggested = tab.copy(tuningSuggestions = listOf(dropD) + tab.tuningSuggestions.filter { it != dropD })
        assertEquals(SongRow.Tuning("standard", "drop-d"), SongCheck.rows(suggested).first())
        // Written for the tuning that fits best: nothing to offer.
        assertEquals(SongRow.Tuning("drop-d", null), SongCheck.rows(suggested.copy(preset = "bass-4-drop-d")).first())
        assertEquals("drop-a", SongCheck.tuningOf("bass-5-drop-a"))
        assertEquals("eb-standard", SongCheck.tuningOf("bass-4-eb-standard"))
        assertNull(SongCheck.tuningOf("guitar-standard"))
        assertEquals(5, SongCheck.stringsOf("bass-5-drop-a"))
    }

    @Test
    fun theOctaveRowIsThereWhenTheLineOrSingleNotesWereMovedOrThePlayerChose() {
        val tab = recorded()
        fun octave(t: Tab) = SongCheck.rows(t).filterIsInstance<SongRow.Octave>().singleOrNull()
        assertNull(octave(tab))
        assertEquals(SongRow.Octave(-12, chosen = false, notesMoved = 0), octave(tab.copy(octaveShift = -12)))
        assertEquals(SongRow.Octave(-24, chosen = false, notesMoved = 0), octave(tab.copy(octaveShift = -24)))
        assertEquals(SongRow.Octave(0, chosen = false, notesMoved = 3), octave(tab.copy(octaveNotesMoved = 3)))
        assertEquals(SongRow.Octave(12, chosen = true, notesMoved = 0), octave(tab.copy(octaveShift = 12, octaveSource = OctaveSource.CHOSEN)))
        // "As it was heard" was chosen: the row stays, so the choice can be given back to Fretscribe.
        assertEquals(SongRow.Octave(0, chosen = true, notesMoved = 0), octave(tab.copy(octaveSource = OctaveSource.CHOSEN)))
    }

    @Test
    fun theReferencePitchRowIsThereOnlyWhenTheRecordingIsOff() {
        val tab = recorded()
        fun reference(t: Tab) = SongCheck.rows(t).filterIsInstance<SongRow.ReferencePitch>().singleOrNull()
        // The recording is 2 cents flat: in tune.
        assertNull(reference(tab))
        assertNull(reference(tab.copy(referencePitch = null)))
        assertNull(reference(tab.copy(referencePitch = ReferencePitch(10.0, 0.8, false))))
        assertEquals(SongRow.ReferencePitch(30, retuned = true), reference(tab.copy(referencePitch = ReferencePitch(30.2, 0.8, true))))
        assertEquals(SongRow.ReferencePitch(-18, retuned = false), reference(tab.copy(referencePitch = ReferencePitch(-17.6, 0.8, false))))
    }

    @Test
    fun doubtfulNotesAndNotesWithNoPlaceAreCounted() {
        val tab = recorded()
        val notes = tab.notes.mapIndexed { i, n ->
            when (i) {
                0, 1, 2 -> n.copy(confidence = 0.2)
                3 -> n.copy(string = null, fret = null, outOfRange = true)
                4 -> n.copy(string = null, fret = null)
                else -> n
            }
        }
        val rows = SongCheck.rows(tab.copy(notes = notes))
        assertEquals(SongRow.Doubtful(3), rows.filterIsInstance<SongRow.Doubtful>().single())
        assertEquals(SongRow.NoPlace(2), rows.filterIsInstance<SongRow.NoPlace>().single())
        // In the order of the screen: tuning, key and tempo, then the notes.
        assertEquals(listOf("Tuning", "KeyAndTempo", "Doubtful", "NoPlace"), rows.map { it::class.simpleName })
        // A note at the threshold is not doubtful.
        assertTrue(SongCheck.rows(tab.copy(notes = tab.notes.map { it.copy(confidence = 0.4) })).none { it is SongRow.Doubtful })
    }

    @Test
    fun aSavedSongsLineIsReadFromItsTabAndItsNotes() {
        assumeTrue("apps/fixtures/bass-line is not in this checkout", fixture?.isDirectory == true)
        val xml = File(fixture, "tab.musicxml").readText()
        val composition = File(fixture, "composition.json").readText()
        assertEquals(listOf(28, 33, 38, 43), SongFacts.openStrings(xml))
        assertEquals(SongFacts(4, "standard", 0), SongFacts.of(xml, composition))
        // Two notes the computer was unsure of.
        var n = 0
        val unsure = Regex(""""confidence": [0-9.]+""").replace(composition) { if (n++ < 2) "\"confidence\": 0.25" else it.value }
        assertEquals(SongFacts(4, "standard", 2), SongFacts.of(xml, unsure))
        // Drop D: the lowest string a whole step down.
        val dropD = xml.replaceFirst("<tuning-step>E</tuning-step>", "<tuning-step>D</tuning-step>")
        assertEquals(SongFacts(4, "drop-d", 0), SongFacts.of(dropD, null))
        // A tuning with no name here still says how many strings; a score that is no tab says nothing.
        val odd = xml.replaceFirst("<tuning-step>E</tuning-step>", "<tuning-step>C</tuning-step>")
        assertEquals(SongFacts(4, null, 0), SongFacts.of(odd, null))
        assertEquals(SongFacts(null, null, 0), SongFacts.of("<score-partwise/>", null))
    }

    @Test
    fun theOpenStringsAreTheCratesPresets() {
        assertEquals(YourInstrument.BASS_TUNINGS.flatMap { (strings, tunings) -> tunings.map { "bass-$strings-$it" } }, SongFacts.OPEN_STRINGS.keys.toList())
        // No two tunings of one instrument share their strings, so a tab's staff names its tuning.
        assertEquals(SongFacts.OPEN_STRINGS.size, SongFacts.OPEN_STRINGS.values.toSet().size)
        val source = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }?.resolve("core/target-fretted/src/instrument.rs")
        assumeTrue("core/target-fretted is not in this checkout", source?.isFile == true)
        // The crate's own tests list the open strings, highest first.
        val listed = Regex("""assert_eq!\(open\("(bass-[^"]+)"\), vec!\[([0-9, ]+)]\);""").findAll(source!!.readText())
            .associate { it.groupValues[1] to it.groupValues[2].split(",").map { p -> p.trim().toInt() }.reversed() }
        assertTrue("no bass tunings listed in ${source.name}", listed.isNotEmpty())
        listed.forEach { (preset, open) -> assertEquals(preset, open, SongFacts.OPEN_STRINGS[preset]) }
    }

    @Test
    fun everyRefusalOfATabJobHasItsOwnWords() {
        fun refused(code: Refusal) = ErrorWords.of(EngineException(422, "the engine's own English", code.code))
        // A computer whose Fretscribe cannot write tabs yet: an update, never "these choices".
        assertEquals(R.string.error_core_missing, refused(Refusal.CORE_MISSING))
        assertEquals(R.string.error_invalid_options, refused(Refusal.INVALID_OPTIONS))
        // An older computer that knows no bass-tab profile answers without a code.
        assertEquals(R.string.error_invalid_options, ErrorWords.of(EngineException(422, "unknown profile")))
        assertEquals(R.string.error_unreachable, ErrorWords.of(EngineException(0, "no answer")))
        assertEquals(R.string.error_pair_again, ErrorWords.of(EngineException(401, "x")))
        assertEquals(R.string.error_engine_failed, ErrorWords.of(no.brasscribe.play.EngineJobFailedException("stems failed")))
        assertEquals(R.string.where_companion_missing, ErrorWords.of(no.brasscribe.play.NoCompanionException()))
    }

    @Test
    fun fretscribesWordsForARefusalNameFretscribeInBothLanguages() {
        val res = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }?.resolve("apps/android/app/src/fretscribe/res")
        assumeTrue("the app's sources are not in this checkout", res?.isDirectory == true)
        val want = mapOf(
            "values" to "Fretscribe on your computer needs an update to write tabs. Update it there, then try again.",
            "values-nb" to "Fretscribe på datamaskinen trenger en oppdatering for å skrive tab. Oppdater den der, og prøv igjen.",
        )
        for ((dir, words) in want) {
            val strings = File(res, "$dir/strings.xml").readText()
            fun text(name: String) = Regex("""<string name="$name">(.*?)</string>""").find(strings)?.groupValues?.get(1)?.replace("\\'", "'")
            assertEquals(dir, words, text("error_core_missing"))
            // Nothing tells the player when the tab is ready while the app is away: no promise that it will.
            assertFalse(dir, Regex("tell you|sier fra|leave this screen|gå fra").containsMatchIn(text("transcribe_leave").orEmpty()))
            assertFalse(dir, Regex("guess|gjett").containsMatchIn(text("fs_what_hint").orEmpty()))
            // Every word this path can show is Fretscribe's, in both languages.
            for (name in listOf("error_core_missing", "error_unreachable", "error_engine_failed", "error_invalid_options", "where_companion_missing",
                "problem_score_title", "problem_score_body", "transcribe_leave", "transcribe_where_companion", "transcribe_done", "transcribe_cancel_title",
                "stage_beats", "stage_stems", "stage_transcribe", "stage_quantize", "stage_arrange", "stage_export")) {
                val t = text(name)
                assertTrue("$dir $name", t != null && !t.contains("Brasscribe") && !Regex("score|partitur|band", RegexOption.IGNORE_CASE).containsMatchIn(t))
            }
        }
    }
}
