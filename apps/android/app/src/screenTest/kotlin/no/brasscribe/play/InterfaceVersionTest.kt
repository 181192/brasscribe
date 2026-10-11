package no.brasscribe.play

import androidx.compose.ui.test.hasText
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.connection.ConnectionState
import no.brasscribe.play.engine.InterfaceMatch
import no.brasscribe.play.engine.InterfaceMismatchException
import no.brasscribe.play.engine.PairLink
import no.brasscribe.play.engine.Wire
import no.brasscribe.play.screen.ScreenTest
import no.brasscribe.play.screen.StubEngine
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The app and the engine are built for one interface version each. When the engine's is another (or it has none),
 * the app says which of the two to update and asks that engine for nothing but its health: no pairing, no job.
 */
@RunWith(AndroidJUnit4::class)
class InterfaceVersionTest : ScreenTest() {
    private var engine: StubEngine? = null

    @After fun stopTheEngine() { engine?.close() }

    private fun engine(interfaceVersion: Int?) = StubEngine(interfaceVersion).also { engine = it }

    private fun waitForState(id: Int) = waitUntil(10_000) { vm.companionState.value == text(id) }

    private fun onThePairingScreen() {
        rule.runOnUiThread { vm.navigate(Screen.SETTINGS); vm.navigate(Screen.COMPANION) }
        rule.waitForIdle()
    }

    /** A phone paired with [engine], as it was before one of the two was updated. */
    private fun pairedWith(engine: StubEngine) {
        rule.runOnUiThread {
            container.settings.url = engine.url
            container.settings.serverId = StubEngine.SERVER_ID
            container.settings.serverName = "Brasscribe on Studio"
            container.settings.paired = true
            vm.connection.retry()
            vm.home()
        }
    }

    @Test
    fun aCodeIsNotSentToANewerEngineAndTheAppSaysToUpdateItself() {
        val newer = engine(Wire.INTERFACE_VERSION + 1)
        onThePairingScreen()
        rule.runOnUiThread { vm.connect(newer.url, "482913") }
        waitForState(R.string.conn_update_app)
        assertEquals(listOf("GET /v1/health"), newer.requests.toList())
        assertFalse(container.settings.paired)
        waitUntil { rule.onAllNodes(hasText(text(R.string.conn_update_app))).fetchSemanticsNodes().isNotEmpty() }
    }

    @Test
    fun aCodeIsNotSentToAnOlderEngineAndTheAppSaysToUpdateBandroom() {
        for (version in listOf(Wire.INTERFACE_VERSION - 1, null)) {
            val older = StubEngine(version)
            try {
                onThePairingScreen()
                rule.runOnUiThread { vm.companionState.value = null; vm.connect(older.url, "482913") }
                waitForState(R.string.conn_update_computer)
                assertEquals("interface version $version", listOf("GET /v1/health"), older.requests.toList())
                assertFalse(container.settings.paired)
            } finally {
                older.close()
            }
        }
    }

    @Test
    fun aPairingLinkAndAskingTheComputerSendNothingEither() {
        val older = engine(null)
        onThePairingScreen()
        val link = checkNotNull(PairLink.parse("scribe://pair?v=1&id=${StubEngine.SERVER_ID}&name=Studio&h=${older.address}&code=482913"))
        rule.runOnUiThread { vm.pairWithLink(link) }
        waitForState(R.string.conn_update_computer)
        rule.runOnUiThread { vm.companionState.value = null; vm.askComputer(older.url) }
        waitForState(R.string.conn_update_computer)
        assertEquals(setOf("GET /v1/health"), older.requests.toSet())
        assertEquals(null, vm.matchCode.value)
        assertFalse(container.settings.paired)
    }

    @Test
    fun theSameVersionPairsAsBefore() {
        val same = engine(Wire.INTERFACE_VERSION)
        onThePairingScreen()
        rule.runOnUiThread { vm.connect(same.url, "482913") }
        waitUntil(10_000) { same.requests.contains("POST /v1/pair") }
    }

    @Test
    fun aPairedPhoneSaysWhichToUpdateKeepsThePairingAndSendsNoJob() {
        val older = engine(Wire.INTERFACE_VERSION - 1)
        pairedWith(older)
        waitUntil(10_000) { vm.connection.state.value is ConnectionState.NeedsUpdate }
        assertEquals(ConnectionState.NeedsUpdate("Brasscribe on Studio", InterfaceMatch.UPDATE_COMPUTER), vm.connection.state.value)
        // The row on Home says it, in both languages; never "Connected".
        for (tag in listOf("en-GB", "nb-NO")) {
            language(tag)
            rule.runOnUiThread { vm.home() }
            waitUntil { rule.onAllNodes(hasText(text(R.string.conn_update_computer))).fetchSemanticsNodes().isNotEmpty() }
            assertFalse(shown(), shown().contains(text(R.string.conn_connected, vm.serverDisplayName("Brasscribe on Studio"))))
        }
        assertTrue(text(R.string.conn_update_computer), text(R.string.conn_update_computer).startsWith("Oppdater Bandroom"))
        // The computer is not offered for a score, and a job that is asked for all the same is not sent.
        assertFalse(vm.computerThere())
        val refused = runCatching { runBlocking { vm.engineForJob() } }.exceptionOrNull()
        assertEquals(InterfaceMatch.UPDATE_COMPUTER, (refused as? InterfaceMismatchException)?.update)
        assertEquals(R.string.conn_update_computer, ErrorWords.of(refused!!))
        rule.runOnUiThread { vm.refreshComputerScores() }
        rule.waitForIdle()
        assertEquals(setOf("GET /v1/health"), older.requests.toSet())
        // Nothing is forgotten: once the computer is updated the same pairing works again.
        assertTrue(container.settings.paired)
        assertEquals(StubEngine.SERVER_ID, container.settings.serverId)
    }
}
