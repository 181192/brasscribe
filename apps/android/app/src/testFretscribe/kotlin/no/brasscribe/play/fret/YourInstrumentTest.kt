package no.brasscribe.play.fret

import no.brasscribe.play.connection.CredentialStoreTest.MemoryStore
import no.brasscribe.play.engine.FrettedInstrument
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/** "Your instrument": the defaults, what can be chosen, what a job is asked for, and the stored answer. */
class YourInstrumentTest {
    /** Every instrument, kind and tuning the screen offers. */
    private val offered: List<Pair<FrettedInstrument, String>> =
        Instrument.entries.flatMap { i -> i.kinds.flatMap { kind -> kind.tunings.map { kind to it } } }

    @Test
    fun notNowIsASixStringGuitarInStandardTuningReadAsTab() {
        val d = YourInstrument.DEFAULT
        assertEquals(Instrument.GUITAR, d.instrument)
        assertEquals(FrettedInstrument.GUITAR_6, d.kind)
        assertEquals(6, d.strings)
        assertEquals("standard", d.tuning)
        assertEquals(FrettingHand.LEFT, d.hand)
        assertEquals(Reads.TAB, d.reads)
        assertEquals(TabJobOptions("guitar-6", "standard", "tab"), d.jobOptions())
        // Nothing stored reads as the same.
        assertEquals(d, YourInstrumentStore(MemoryStore()).load())
    }

    @Test
    fun everyInstrumentCanBeChosenWithItsKinds() {
        assertEquals(listOf(Instrument.GUITAR, Instrument.BASS, Instrument.UKULELE, Instrument.MANDOLIN), Instrument.entries)
        assertEquals(listOf("guitar-6", "guitar-7", "guitar-8"), Instrument.GUITAR.kinds.map { it.id })
        assertEquals(listOf("bass-4", "bass-5", "bass-6"), Instrument.BASS.kinds.map { it.id })
        // Soprano, concert and tenor are one kind; the baritone is another.
        assertEquals(listOf("ukulele", "ukulele-baritone"), Instrument.UKULELE.kinds.map { it.id })
        assertEquals(listOf("mandolin"), Instrument.MANDOLIN.kinds.map { it.id })
        // Every instrument the computer writes tab for is offered, once.
        val kinds = Instrument.entries.flatMap { it.kinds }
        assertEquals(FrettedInstrument.entries.filter { it.id != null }.toSet(), kinds.toSet())
        assertEquals(kinds.size, kinds.toSet().size)
        kinds.forEach { assertTrue(it.name, Instrument.of(it)!!.kinds.contains(it)) }
        assertNull(Instrument.of(FrettedInstrument.UNKNOWN))
        // A guitar and a bass are chosen by their strings; a ukulele by its size; a mandolin comes in one kind.
        assertEquals(listOf(6, 7, 8, 4, 5, 6), (Instrument.GUITAR.kinds + Instrument.BASS.kinds).map { YourInstrument.stringsOf(it) })
        (Instrument.UKULELE.kinds + Instrument.MANDOLIN.kinds).forEach { assertNull(YourInstrument.stringsOf(it)) }
        // A capo is asked about for a guitar and a ukulele.
        assertEquals(listOf(Instrument.GUITAR, Instrument.UKULELE), Instrument.entries.filter { it.takesCapo })
    }

    @Test
    fun theTuningsOfEachInstrumentAreTheOnesTheComputerHasItsUsualOneFirst() {
        fun tunings(kind: FrettedInstrument) = YourInstrument(kind).tunings
        assertEquals(listOf("standard", "eb-standard", "d-standard", "c-standard", "drop-d", "drop-c", "drop-b", "dadgad", "open-g", "open-d", "open-e"),
            tunings(FrettedInstrument.GUITAR_6))
        assertEquals(listOf("standard", "eb-standard"), tunings(FrettedInstrument.GUITAR_7))
        assertEquals(listOf("standard"), tunings(FrettedInstrument.GUITAR_8))
        assertEquals(listOf("standard", "eb-standard", "d-standard", "drop-d", "bead"), tunings(FrettedInstrument.BASS_4))
        assertEquals(listOf("standard", "drop-a"), tunings(FrettedInstrument.BASS_5))
        assertEquals(listOf("standard"), tunings(FrettedInstrument.BASS_6))
        assertEquals(listOf("high-g", "low-g"), tunings(FrettedInstrument.UKULELE))
        assertEquals(listOf("standard"), tunings(FrettedInstrument.UKULELE_BARITONE))
        assertEquals(listOf("standard"), tunings(FrettedInstrument.MANDOLIN))
        // A new answer starts in the instrument's usual tuning: a ukulele's is high G, not "standard".
        Instrument.entries.flatMap { it.kinds }.forEach { assertEquals(it.tunings.first(), YourInstrument(it).tuning) }
        assertEquals("high-g", YourInstrument(FrettedInstrument.UKULELE).tuning)
    }

    @Test
    fun everyInstrumentTuningAndLayoutMapsToItsJobOptions() {
        val layouts = mapOf(Reads.TAB to "tab", Reads.TAB_AND_NOTATION to "tab-and-notation", Reads.NOTATION to "notation")
        assertEquals(Reads.entries.toSet(), layouts.keys)
        var seen = 0
        for ((kind, tuning) in offered) for ((reads, layout) in layouts) for (hand in FrettingHand.entries) {
            val chosen = YourInstrument(kind, tuning, hand, reads)
            assertEquals(chosen, chosen.valid())
            // The hand is for the screens that draw a neck: it never reaches the job.
            assertEquals("$chosen", TabJobOptions(kind.id!!, tuning, layout), chosen.jobOptions())
            assertEquals(kind.id, chosen.family)
            assertEquals(kind.preset(tuning), chosen.preset)
            seen++
        }
        assertEquals((11 + 2 + 1 + 5 + 2 + 1 + 2 + 1 + 1) * 3 * 3, seen)
        assertEquals("guitar-drop-d", YourInstrument(FrettedInstrument.GUITAR_6, "drop-d").preset)
        assertEquals("ukulele-baritone", YourInstrument(FrettedInstrument.UKULELE_BARITONE).preset)
        assertEquals("mandolin", YourInstrument(FrettedInstrument.MANDOLIN).preset)
    }

    @Test
    fun theTuningsAreTheCratesPresets() {
        // The repository root is two up from the sounds folder the build passes in.
        val source = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }
            ?.resolve("core/target-fretted/src/instrument.rs")
        assumeTrue("core/target-fretted is not in this checkout", source?.isFile == true)
        val list = source!!.readText().substringAfter("pub const PRESET_IDS: &[&str] = &[").substringBefore("];")
        val crate = Regex("\"([^\"]+)\"").findAll(list).map { it.groupValues[1] }.toList()
        assertTrue("no presets found in ${source.name}", crate.isNotEmpty())
        // In the crate's order: the guitars, the basses, the ukuleles, the mandolin, each kind's usual tuning first.
        assertEquals(crate, offered.map { (kind, tuning) -> YourInstrument(kind, tuning).preset })
    }

    @Test
    fun changingTheKindKeepsATuningTheNewOneHas() {
        val dropD = YourInstrument(FrettedInstrument.BASS_4, "drop-d")
        assertEquals(YourInstrument(FrettedInstrument.BASS_5, "standard"), dropD.withKind(FrettedInstrument.BASS_5))
        assertEquals(YourInstrument(FrettedInstrument.BASS_4, "standard"), YourInstrument(FrettedInstrument.BASS_5, "drop-a").withKind(FrettedInstrument.BASS_4))
        assertEquals(YourInstrument(FrettedInstrument.BASS_6), YourInstrument(FrettedInstrument.BASS_5).withKind(FrettedInstrument.BASS_6))
        assertEquals(YourInstrument(FrettedInstrument.GUITAR_7, "eb-standard"), YourInstrument(FrettedInstrument.GUITAR_6, "eb-standard").withKind(FrettedInstrument.GUITAR_7))
        assertEquals(YourInstrument(FrettedInstrument.GUITAR_7, "standard"), YourInstrument(FrettedInstrument.GUITAR_6, "dadgad").withKind(FrettedInstrument.GUITAR_7))
        // A baritone has no high or low G; back on the smaller ones the usual tuning is high G.
        val baritone = YourInstrument(FrettedInstrument.UKULELE, "low-g").withKind(FrettedInstrument.UKULELE_BARITONE)
        assertEquals(YourInstrument(FrettedInstrument.UKULELE_BARITONE, "standard"), baritone)
        assertEquals(YourInstrument(FrettedInstrument.UKULELE, "high-g"), baritone.withKind(FrettedInstrument.UKULELE))
        // The hand and what is read stay.
        val mine = YourInstrument(FrettedInstrument.GUITAR_6, "drop-d", FrettingHand.RIGHT, Reads.NOTATION)
        assertEquals(mine.copy(kind = FrettedInstrument.GUITAR_8, tuning = "standard"), mine.withKind(FrettedInstrument.GUITAR_8))
    }

    @Test
    fun anotherInstrumentStartsInItsOwnUsualTuning() {
        val mine = YourInstrument(FrettedInstrument.GUITAR_6, "drop-d", FrettingHand.RIGHT, Reads.TAB_AND_NOTATION)
        // A four-string bass has a drop D too, but the player has not said the bass is in it.
        assertEquals(mine.copy(kind = FrettedInstrument.BASS_4, tuning = "standard"), mine.withInstrument(Instrument.BASS))
        assertEquals(mine.copy(kind = FrettedInstrument.UKULELE, tuning = "high-g"), mine.withInstrument(Instrument.UKULELE))
        assertEquals(mine.copy(kind = FrettedInstrument.MANDOLIN, tuning = "standard"), mine.withInstrument(Instrument.MANDOLIN))
        // The same instrument again changes nothing.
        assertEquals(mine, mine.withInstrument(Instrument.GUITAR))
        val seven = YourInstrument(FrettedInstrument.GUITAR_7, "eb-standard")
        assertEquals(seven, seven.withInstrument(Instrument.GUITAR))
        Instrument.entries.forEach { assertEquals(it, mine.withInstrument(it).instrument) }
    }

    @Test
    fun theAnswerComesBackAsItWasSaved() {
        val map = linkedMapOf<String, String>()
        for ((kind, tuning) in offered) for (hand in FrettingHand.entries) for (reads in Reads.entries) {
            val chosen = YourInstrument(kind, tuning, hand, reads)
            YourInstrumentStore(MemoryStore(map)).save(chosen)
            // A new store on the same preferences: what the next start of the app reads.
            assertEquals(chosen, YourInstrumentStore(MemoryStore(map)).load())
        }
        assertEquals(setOf(YourInstrumentStore.KIND, YourInstrumentStore.TUNING, YourInstrumentStore.HAND, YourInstrumentStore.READS), map.keys)
    }

    @Test
    fun aChoiceStoredByTheVersionThatOfferedOnlyTheBassLoadsUnchanged() {
        // What that version wrote: the instrument, its strings, the tuning, the hand and what is read.
        fun stored(strings: Int, tuning: String, hand: String = "left", reads: String = "tab") = linkedMapOf(
            "fret_instrument" to "bass", "fret_strings" to "$strings", "fret_tuning" to tuning, "fret_hand" to hand, "fret_reads" to reads)
        val basses = mapOf(4 to FrettedInstrument.BASS_4, 5 to FrettedInstrument.BASS_5, 6 to FrettedInstrument.BASS_6)
        var seen = 0
        for ((strings, kind) in basses) for (tuning in kind.tunings) for (hand in FrettingHand.entries) for (reads in Reads.entries) {
            val map = stored(strings, tuning, hand.id, reads.id)
            val loaded = YourInstrumentStore(MemoryStore(map)).load()
            assertEquals(YourInstrument(kind, tuning, hand, reads), loaded)
            assertEquals(Instrument.BASS, loaded.instrument)
            // The job is the one that version asked for.
            assertEquals(TabJobOptions("bass-$strings", tuning, reads.id), loaded.jobOptions())
            seen++
        }
        assertEquals((5 + 2 + 1) * 3 * 3, seen)

        // Saved again from this version, it is still that bass; a later choice wins over what the old version left.
        val map = stored(5, "drop-a", "right", "notation")
        val store = YourInstrumentStore(MemoryStore(map))
        store.save(store.load())
        assertEquals("bass-5", map[YourInstrumentStore.KIND])
        assertEquals(YourInstrument(FrettedInstrument.BASS_5, "drop-a", FrettingHand.RIGHT, Reads.NOTATION), YourInstrumentStore(MemoryStore(map)).load())
        store.save(YourInstrument(FrettedInstrument.UKULELE, "low-g"))
        assertEquals(YourInstrument(FrettedInstrument.UKULELE, "low-g"), YourInstrumentStore(MemoryStore(map)).load())
    }

    @Test
    fun savingLeavesEverythingElseInThePreferencesAlone() {
        val map = linkedMapOf("appearance" to "dark", "seat" to "solo-cornet")
        YourInstrumentStore(MemoryStore(map)).save(YourInstrument(FrettedInstrument.BASS_5, "drop-a", hand = FrettingHand.RIGHT))
        assertEquals("dark", map["appearance"])
        assertEquals("solo-cornet", map["seat"])
    }

    @Test
    fun storedValuesThisVersionCantOfferReadAsTheDefaults() {
        fun load(vararg stored: Pair<String, String>) = YourInstrumentStore(MemoryStore(linkedMapOf(*stored))).load()
        val d = YourInstrument.DEFAULT
        // An instrument this version has never heard of.
        assertEquals(d, load(YourInstrumentStore.KIND to "banjo-5"))
        assertEquals(d, load(YourInstrumentStore.KIND to "banjo-5", YourInstrumentStore.TUNING to "open-g"))
        assertEquals(d, load(YourInstrumentStore.INSTRUMENT to "banjo"))
        // The bass-only version never stored a guitar (it was "Later"): what it left for one says nothing.
        assertEquals(d, load(YourInstrumentStore.INSTRUMENT to "guitar", YourInstrumentStore.STRINGS to "7"))
        // Its bass with strings the bass doesn't come with, or not a number: four strings, and a tuning four strings have.
        val bass = YourInstrument(FrettedInstrument.BASS_4)
        assertEquals(bass, load(YourInstrumentStore.INSTRUMENT to "bass", YourInstrumentStore.STRINGS to "7", YourInstrumentStore.TUNING to "drop-a"))
        assertEquals(bass, load(YourInstrumentStore.INSTRUMENT to "bass", YourInstrumentStore.STRINGS to "many"))
        assertEquals(bass, load(YourInstrumentStore.INSTRUMENT to "bass"))
        // A tuning the instrument has no preset for is its usual one; the instrument stays.
        assertEquals(YourInstrument(FrettedInstrument.BASS_5), load(YourInstrumentStore.KIND to "bass-5", YourInstrumentStore.TUNING to "drop-d"))
        assertEquals(YourInstrument(FrettedInstrument.UKULELE, "high-g"), load(YourInstrumentStore.KIND to "ukulele", YourInstrumentStore.TUNING to "standard"))
        assertEquals(YourInstrument(FrettedInstrument.MANDOLIN), load(YourInstrumentStore.KIND to "mandolin", YourInstrumentStore.TUNING to "dadgad"))
        assertEquals(YourInstrument(FrettedInstrument.UKULELE), load(YourInstrumentStore.KIND to "ukulele"))
        // An unknown hand or reading is the default; the rest of the answer stays.
        assertEquals(d.copy(tuning = "dadgad"), load(YourInstrumentStore.KIND to "guitar-6", YourInstrumentStore.TUNING to "dadgad",
            YourInstrumentStore.HAND to "both", YourInstrumentStore.READS to "braille"))
        // A tuning with no instrument beside it says nothing.
        assertEquals(d, load(YourInstrumentStore.TUNING to "dadgad"))
        assertEquals(d.copy(hand = FrettingHand.RIGHT_UPSIDE_DOWN, reads = Reads.NOTATION),
            load(YourInstrumentStore.HAND to "right-upside-down", YourInstrumentStore.READS to "notation"))
    }

    @Test
    fun anAnswerThatCantBeChosenNeverReachesAJobOrTheStore() {
        val unknown = YourInstrument(FrettedInstrument.UNKNOWN, "dadgad", FrettingHand.RIGHT, Reads.NOTATION)
        assertEquals(TabJobOptions("guitar-6", "standard", "notation"), unknown.jobOptions())
        assertEquals(Instrument.GUITAR, unknown.instrument)
        assertEquals("guitar-standard", unknown.preset)
        // A tuning of another instrument: the instrument's usual one is asked for.
        assertEquals(TabJobOptions("ukulele", "high-g", "tab"), YourInstrument(FrettedInstrument.UKULELE, "drop-d").jobOptions())
        assertEquals(TabJobOptions("bass-6", "standard", "tab"), YourInstrument(FrettedInstrument.BASS_6, "bead").jobOptions())
        val map = linkedMapOf<String, String>()
        YourInstrumentStore(MemoryStore(map)).save(unknown)
        assertEquals("guitar-6", map[YourInstrumentStore.KIND])
        assertFalse(map.containsValue("dadgad"))
    }
}
