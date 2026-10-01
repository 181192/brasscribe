package no.brasscribe.play.fret

import no.brasscribe.play.connection.CredentialStoreTest.MemoryStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/** "Your instrument": the defaults, what a job is asked for, and the stored answer. */
class YourInstrumentTest {
    @Test
    fun notNowIsAFourStringBassInStandardTuningReadAsTab() {
        val d = YourInstrument.DEFAULT
        assertEquals(Instrument.BASS, d.instrument)
        assertEquals(4, d.strings)
        assertEquals("standard", d.tuning)
        assertEquals(FrettingHand.LEFT, d.hand)
        assertEquals(Reads.TAB, d.reads)
        assertEquals(TabJobOptions("bass-4", "standard", "tab"), d.jobOptions())
        // Nothing stored reads as the same.
        assertEquals(d, YourInstrumentStore(MemoryStore()).load())
    }

    @Test
    fun onlyTheBassCanBeChosen() {
        assertEquals(listOf(Instrument.BASS), Instrument.entries.filter { it.available })
        assertEquals(listOf(Instrument.BASS, Instrument.GUITAR, Instrument.UKULELE, Instrument.MANDOLIN), Instrument.entries)
        assertEquals(listOf(4, 5, 6), YourInstrument.stringsOf(Instrument.BASS))
        assertEquals(emptyList<Int>(), YourInstrument.stringsOf(Instrument.GUITAR))
    }

    @Test
    fun everyInstrumentTuningAndLayoutMapsToItsJobOptions() {
        val layouts = mapOf(Reads.TAB to "tab", Reads.TAB_AND_NOTATION to "tab-and-notation", Reads.NOTATION to "notation")
        assertEquals(Reads.entries.toSet(), layouts.keys)
        var seen = 0
        for ((strings, tunings) in YourInstrument.BASS_TUNINGS) for (tuning in tunings) for ((reads, layout) in layouts) for (hand in FrettingHand.entries) {
            val chosen = YourInstrument(Instrument.BASS, strings, tuning, hand, reads)
            assertEquals(chosen, chosen.valid())
            // The hand is for the screens that draw a neck: it never reaches the job.
            assertEquals("$chosen", TabJobOptions("bass-$strings", tuning, layout), chosen.jobOptions())
            assertEquals("bass-$strings-$tuning", chosen.preset)
            seen++
        }
        assertEquals((5 + 2 + 1) * 3 * 3, seen)
        // Standard comes first for every instrument.
        YourInstrument.BASS_TUNINGS.values.forEach { assertEquals("standard", it.first()) }
    }

    @Test
    fun theTuningsAreTheCratesPresets() {
        // The repository root is two up from the sounds folder the build passes in.
        val source = System.getProperty("brasscribe.sounds")?.let { File(it).parentFile }
            ?.resolve("core/target-fretted/src/instrument.rs")
        assumeTrue("core/target-fretted is not in this checkout", source?.isFile == true)
        val list = source!!.readText().substringAfter("pub const PRESET_IDS: &[&str] = &[").substringBefore("];")
        val bass = Regex("\"(bass-[^\"]+)\"").findAll(list).map { it.groupValues[1] }.toList()
        assertTrue("no bass presets found in ${source.name}", bass.isNotEmpty())
        val ours = YourInstrument.BASS_TUNINGS.flatMap { (strings, tunings) -> tunings.map { "bass-$strings-$it" } }
        assertEquals(bass, ours)
    }

    @Test
    fun changingTheStringsKeepsATuningTheNewBassHas() {
        val dropD = YourInstrument(tuning = "drop-d")
        assertEquals(YourInstrument(strings = 5, tuning = "standard"), dropD.withStrings(5))
        assertEquals(YourInstrument(strings = 4, tuning = "standard"), YourInstrument(strings = 5, tuning = "drop-a").withStrings(4))
        assertEquals(YourInstrument(strings = 6), YourInstrument(strings = 5).withStrings(6))
        // A count the bass doesn't come with is the default count.
        assertEquals(4, dropD.withStrings(7).strings)
    }

    @Test
    fun theAnswerComesBackAsItWasSaved() {
        val map = linkedMapOf<String, String>()
        for ((strings, tunings) in YourInstrument.BASS_TUNINGS) for (tuning in tunings) for (hand in FrettingHand.entries) for (reads in Reads.entries) {
            val chosen = YourInstrument(Instrument.BASS, strings, tuning, hand, reads)
            YourInstrumentStore(MemoryStore(map)).save(chosen)
            // A new store on the same preferences: what the next start of the app reads.
            assertEquals(chosen, YourInstrumentStore(MemoryStore(map)).load())
        }
        assertEquals(
            setOf(YourInstrumentStore.INSTRUMENT, YourInstrumentStore.STRINGS, YourInstrumentStore.TUNING, YourInstrumentStore.HAND, YourInstrumentStore.READS),
            map.keys,
        )
    }

    @Test
    fun savingLeavesEverythingElseInThePreferencesAlone() {
        val map = linkedMapOf("appearance" to "dark", "seat" to "solo-cornet")
        YourInstrumentStore(MemoryStore(map)).save(YourInstrument(strings = 5, tuning = "drop-a", hand = FrettingHand.RIGHT))
        assertEquals("dark", map["appearance"])
        assertEquals("solo-cornet", map["seat"])
    }

    @Test
    fun storedValuesThisVersionCantOfferReadAsTheDefaults() {
        fun load(vararg stored: Pair<String, String>) = YourInstrumentStore(MemoryStore(linkedMapOf(*stored))).load()
        val d = YourInstrument.DEFAULT
        // An instrument that is still "Later", or one this version has never heard of.
        assertEquals(d, load(YourInstrumentStore.INSTRUMENT to "guitar", YourInstrumentStore.STRINGS to "6"))
        assertEquals(d, load(YourInstrumentStore.INSTRUMENT to "banjo"))
        // Strings the bass doesn't come with, or not a number: four strings, and a tuning four strings have.
        assertEquals(d, load(YourInstrumentStore.STRINGS to "7", YourInstrumentStore.TUNING to "drop-a"))
        assertEquals(d, load(YourInstrumentStore.STRINGS to "many"))
        // A tuning the instrument has no preset for; the strings stay.
        assertEquals(d.copy(strings = 5), load(YourInstrumentStore.STRINGS to "5", YourInstrumentStore.TUNING to "drop-d"))
        assertEquals(d, load(YourInstrumentStore.TUNING to "dadgad"))
        // An unknown hand or reading is the default; the rest of the answer stays.
        assertEquals(d.copy(tuning = "bead"), load(YourInstrumentStore.TUNING to "bead", YourInstrumentStore.HAND to "both", YourInstrumentStore.READS to "braille"))
        assertEquals(d.copy(hand = FrettingHand.RIGHT_UPSIDE_DOWN, reads = Reads.NOTATION),
            load(YourInstrumentStore.HAND to "right-upside-down", YourInstrumentStore.READS to "notation"))
    }

    @Test
    fun anAnswerThatCantBeChosenNeverReachesAJobOrTheStore() {
        val guitar = YourInstrument(Instrument.GUITAR, 6, "dadgad", FrettingHand.RIGHT, Reads.NOTATION)
        assertEquals(TabJobOptions("bass-4", "standard", "notation"), guitar.jobOptions())
        val map = linkedMapOf<String, String>()
        YourInstrumentStore(MemoryStore(map)).save(guitar)
        assertEquals("bass", map[YourInstrumentStore.INSTRUMENT])
        assertFalse(map.containsValue("dadgad"))
    }
}
