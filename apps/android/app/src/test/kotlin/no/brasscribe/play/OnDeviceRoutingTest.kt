package no.brasscribe.play

import no.brasscribe.play.connection.ConnectionState
import no.brasscribe.play.engine.Profile
import no.brasscribe.play.model.songLineup
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** Where a recording is written down, and the band draft's words (design/system.md §3). */
class OnDeviceRoutingTest {
    private val R_ = OnDeviceRouting

    @Test
    fun theComputerIsThereWhenConnectedOrReconnecting() {
        assertTrue(R_.computerThere(ConnectionState.Connected("Mac")))
        assertTrue(R_.computerThere(ConnectionState.Reconnecting("Mac")))
        assertFalse(R_.computerThere(ConnectionState.Offline(paired = true)))
        assertFalse(R_.computerThere(ConnectionState.Offline(paired = false)))
        assertFalse(R_.computerThere(ConnectionState.NeedsPairing("Mac")))
    }

    @Test
    fun aBrassBandGoesToTheComputerWhenItIsThereAndIsADraftOtherwise() {
        val onDevice = R_.canRunOnDevice(Profile.BRASS_BAND, hasPitchModel = true, hasBandModels = true, audioInMemory = true)
        assertTrue(onDevice)
        assertEquals(Where.COMPANION, R_.defaultWhere(Profile.BRASS_BAND, onDevice, computerThere = true))
        assertEquals(Where.DEVICE, R_.defaultWhere(Profile.BRASS_BAND, onDevice, computerThere = false))
        assertTrue(R_.isDraft(Profile.BRASS_BAND, Where.DEVICE))
        assertFalse(R_.isDraft(Profile.BRASS_BAND, Where.COMPANION))
        // Without the models or a take in memory, the computer is the only way.
        assertFalse(R_.canRunOnDevice(Profile.BRASS_BAND, true, hasBandModels = false, audioInMemory = true))
        assertFalse(R_.canRunOnDevice(Profile.BRASS_BAND, true, true, audioInMemory = false))
        assertEquals(Where.COMPANION, R_.defaultWhere(Profile.BRASS_BAND, onDevice = false, computerThere = false))
    }

    @Test
    fun popAndTheSoloistNeverRunOnThePhone() {
        for (p in listOf(Profile.POP_ROCK, Profile.ORCHESTRA_WITH_SOLOIST, null)) {
            assertFalse(R_.canRunOnDevice(p, true, true, true))
            assertEquals(Where.COMPANION, R_.defaultWhere(p, onDevice = false, computerThere = false))
            assertEquals(no.brasscribe.play.R.string.where_device_solo_only, R_.deviceCard(p, true, true, true))
        }
    }

    @Test
    fun aSoloIsStillMadeOnThePhoneWhateverTheComputer() {
        assertTrue(R_.canRunOnDevice(Profile.SOLO, hasPitchModel = true, hasBandModels = false, audioInMemory = true))
        assertEquals(Where.DEVICE, R_.defaultWhere(Profile.SOLO, onDevice = true, computerThere = true))
        assertFalse(R_.isDraft(Profile.SOLO, Where.DEVICE))
        assertEquals(no.brasscribe.play.R.string.where_device, R_.whereTitle(Profile.SOLO, Where.DEVICE))
        assertEquals(no.brasscribe.play.R.string.where_device_desc, R_.deviceSubtitle(Profile.SOLO))
        assertEquals(no.brasscribe.play.R.string.transcribe_where_device, R_.transcribingWhere(draft = false))
    }

    @Test
    fun theDraftIsCalledADraftEverywhere() {
        assertEquals(no.brasscribe.play.R.string.where_device_draft, R_.whereTitle(Profile.BRASS_BAND, Where.DEVICE))
        assertEquals(no.brasscribe.play.R.string.where_companion, R_.whereTitle(Profile.BRASS_BAND, Where.COMPANION))
        assertEquals(no.brasscribe.play.R.string.where_device_draft_desc, R_.deviceSubtitle(Profile.BRASS_BAND))
        assertEquals(no.brasscribe.play.R.string.where_device_draft_card, R_.deviceCard(Profile.BRASS_BAND, true, true, true))
        assertEquals(no.brasscribe.play.R.string.where_device_unavailable, R_.deviceCard(Profile.BRASS_BAND, true, hasBandModels = false, audioInMemory = true))
        assertNull(R_.deviceCard(Profile.BRASS_BAND, true, true, audioInMemory = false))
        assertEquals(no.brasscribe.play.R.string.transcribe_where_device_draft, R_.transcribingWhere(draft = true))
    }

    @Test
    fun aBandTakeIsTheMinimalBandOrTheQuartet() {
        assertEquals("minimal", songLineup("band"))
        assertEquals("minimal", songLineup("minimal"))
        assertEquals("quartet", songLineup("quartet"))
    }

    /** The words are the design system's, in both languages. */
    @Test
    fun theWordsAreTheSpecs() {
        val en = strings("values"); val nb = strings("values-nb")
        assertEquals("On this phone: a quick draft", en["where_device_draft"])
        assertEquals("Your computer makes a better score.", en["where_device_draft_desc"])
        assertEquals("A quick draft. Nothing leaves the phone.", en["where_device_draft_card"])
        assertEquals("Only for one instrument or a brass band.", en["where_device_solo_only"])
        assertEquals("On this phone, as a draft", en["transcribe_where_device_draft"])
        assertEquals("Make the full score", en["draft_make_full"])
        assertEquals("Draft", en["draft_label"])
        assertTrue(en.getValue("draft_notice").contains("can differ slightly from the computer"))
        assertEquals("På telefonen: et raskt utkast", nb["where_device_draft"])
        assertEquals("Datamaskinen lager et bedre partitur.", nb["where_device_draft_desc"])
        assertEquals("Bare for ett instrument eller et brassband.", nb["where_device_solo_only"])
        assertEquals("På telefonen, som utkast", nb["transcribe_where_device_draft"])
        assertEquals("Lag hele partituret", nb["draft_make_full"])
        assertEquals("Utkast", nb["draft_label"])
        assertTrue(nb.getValue("draft_notice").contains("litt annerledes enn på datamaskinen"))
        for (key in en.keys.filter { it.startsWith("draft_") || it.contains("_draft") }) assertTrue("nb $key", key in nb)
    }

    private fun strings(dir: String): Map<String, String> =
        Regex("""<string name="([^"]+)">([^<]*)</string>""").findAll(File("src/main/res/$dir/strings.xml").readText())
            .associate { it.groupValues[1] to it.groupValues[2].replace("\\'", "'") }
}
