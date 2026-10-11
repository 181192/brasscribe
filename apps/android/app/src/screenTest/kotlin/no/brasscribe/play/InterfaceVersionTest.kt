package no.brasscribe.play

import androidx.compose.ui.test.hasText
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.connection.Check
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
 * the app says which of the two to update and asks that engine for nothing but its health: no pairing, no job, no
 * score, whichever screen asks.
 */
@RunWith(AndroidJUnit4::class)
class InterfaceVersionTest : ScreenTest() {
    private val engines = mutableListOf<StubEngine>()

    @After fun stopTheEngines() { engines.forEach(StubEngine::close) }

    private fun engine(interfaceVersion: Int?) = StubEngine(interfaceVersion).also { engines += it }

    private fun waitForState(id: Int) = waitUntil(10_000) { vm.companionState.value == text(id) }

    private fun shows(id: Int) = rule.onAllNodes(hasText(text(id))).fetchSemanticsNodes().isNotEmpty()

    private fun onThePairingScreen() {
        rule.runOnUiThread { vm.navigate(Screen.SETTINGS); vm.navigate(Screen.COMPANION) }
        rule.waitForIdle()
    }

    /** What [engine] was asked besides the two requests that say its interface version. */
    private fun askedBesidesItsVersion(engine: StubEngine) = engine.requests.toSet() - setOf("GET /v1/health", "GET /v1/devices/me")

    @Test
    fun aCodeIsNotSentToANewerEngineAndTheAppSaysToUpdateItself() {
        val newer = engine(Wire.INTERFACE_VERSION + 1)
        onThePairingScreen()
        rule.runOnUiThread { vm.connect(newer.url, "482913") }
        waitForState(R.string.conn_update_app)
        assertEquals(listOf("GET /v1/health"), newer.requests.toList())
        assertFalse(container.settings.paired)
        waitUntil { shows(R.string.conn_update_app) }
    }

    @Test
    fun aCodeIsNotSentToAnOlderEngineAndTheAppSaysToUpdateBandroom() {
        // Older, from before the number, and with something that is no number in its place.
        for (version in listOf((Wire.INTERFACE_VERSION - 1).toString(), null, "1.5", "\"1\"", "true")) {
            val older = StubEngine(version).also { engines += it }
            onThePairingScreen()
            rule.runOnUiThread { vm.companionState.value = null; vm.connect(older.url, "482913") }
            waitForState(R.string.conn_update_computer)
            assertEquals("interface version $version", listOf("GET /v1/health"), older.requests.toList())
            assertFalse(container.settings.paired)
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
    fun aPairedPhonesHeartbeatIsOneRequest() {
        val same = engine(Wire.INTERFACE_VERSION)
        pairedWith(same.url)
        waitUntil(10_000) { vm.connection.state.value is ConnectionState.Connected && same.requests.contains("GET /v1/jobs") }
        same.requests.clear()
        val check = runBlocking { no.brasscribe.play.connection.EngineConnection(container).check(same.url) }
        assertTrue("$check", check is no.brasscribe.play.connection.Check.Ok)
        // The phone's own entry says which engine answers and its interface version: health is not asked beside it.
        assertEquals(listOf("GET /v1/devices/me"), same.requests.toList())
    }

    @Test
    fun aPairedPhoneSaysWhichToUpdateKeepsThePairingAndAsksNothingElse() {
        val older = engine(Wire.INTERFACE_VERSION - 1)
        pairedWith(older.url)
        waitUntil(10_000) { vm.connection.state.value is ConnectionState.NeedsUpdate }
        assertEquals(ConnectionState.NeedsUpdate("Brasscribe on Studio", InterfaceMatch.UPDATE_COMPUTER), vm.connection.state.value)
        // Only what says the engine's number was asked: its health, or the phone's own entry there.
        assertEquals(emptySet<String>(), askedBesidesItsVersion(older))
        // The row on Home says it, in both languages, with the way to the latest Bandroom; never "Connected".
        for (tag in listOf("en-GB", "nb-NO")) {
            language(tag)
            rule.runOnUiThread { vm.home() }
            waitUntil { shows(R.string.conn_update_computer) }
            assertTrue(shown(), shows(R.string.bandroom_get_title))
            assertFalse(shown(), shown().contains(text(R.string.conn_connected, vm.serverDisplayName("Brasscribe on Studio"))))
        }
        assertTrue(text(R.string.conn_update_computer), text(R.string.conn_update_computer).startsWith("Oppdater Bandroom"))
        // The computer is not offered for a score, and whatever asks it all the same is refused before it is sent:
        // a job, the list of scores, a score to open, a title to change, a score to delete, a job to stop.
        assertFalse(vm.computerThere())
        val api = checkNotNull(container.engine())
        val calls: List<suspend () -> Any?> = listOf(
            { api.jobs() }, { api.profiles() }, { api.musicXml("j1") }, { api.composition("j1") }, { api.renameRun("j1", "Title") },
            { api.deleteRun("j1") }, { api.cancel("j1") }, { api.job("j1") }, { api.renderedAudio("j1") }, { api.rotateToken() },
        )
        for (call in calls) {
            val refused = runCatching { runBlocking { call() } }.exceptionOrNull()
            assertEquals(InterfaceMatch.UPDATE_COMPUTER, (refused as? InterfaceMismatchException)?.update)
            assertEquals(R.string.conn_update_computer, ErrorWords.of(refused!!))
        }
        rule.runOnUiThread { vm.refreshComputerScores(); vm.openFinishedJob("0123456789abcdef") }
        rule.waitForIdle()
        assertEquals(emptySet<String>(), askedBesidesItsVersion(older))
        // Nothing is forgotten: once the computer is updated the same pairing works again.
        assertTrue(container.settings.paired)
        assertEquals(StubEngine.TOKEN, container.settings.token)
        older.interfaceVersion = Wire.INTERFACE_VERSION.toString()
        rule.runOnUiThread { vm.connection.retry() }
        waitUntil(10_000) { vm.connection.state.value is ConnectionState.Connected }
        // And its scores are asked for again, without anyone asking.
        waitUntil(10_000) { older.requests.contains("GET /v1/jobs") }
    }

    @Test
    fun anAppThatOpensPairedAsksTheEnginesVersionBeforeAnythingElse() {
        val newer = engine(Wire.INTERFACE_VERSION + 1)
        // As the app opens: paired, and nothing known yet of the engine that answers now.
        rule.runOnUiThread {
            container.settings.url = newer.url
            container.settings.serverId = StubEngine.SERVER_ID
            container.settings.serverName = "Brasscribe on Studio"
            container.credentials.put(no.brasscribe.play.connection.Credential(StubEngine.SERVER_ID, StubEngine.TOKEN, "d1", "Brasscribe on Studio", newer.url))
            container.settings.paired = true
        }
        // Whatever asks first (here the list of scores) is not sent: the engine's number is asked, and it is another.
        val first = runCatching { runBlocking { checkNotNull(container.engine()).jobs() } }.exceptionOrNull()
        assertEquals(InterfaceMatch.UPDATE_APP, (first as? InterfaceMismatchException)?.update)
        assertEquals(listOf("GET /v1/health"), newer.requests.toList())
        rule.runOnUiThread { vm.connection.retry() }
        waitUntil(10_000) { vm.connection.state.value is ConnectionState.NeedsUpdate }
        assertEquals(ConnectionState.NeedsUpdate("Brasscribe on Studio", InterfaceMatch.UPDATE_APP), vm.connection.state.value)
        assertEquals(emptySet<String>(), askedBesidesItsVersion(newer))
        // The app is the one behind: the row has the way to its latest version.
        rule.runOnUiThread { vm.home() }
        waitUntil { shows(R.string.conn_update_app) }
        assertTrue(shown(), shows(R.string.conn_get_app_update))
    }

    @Test
    fun forgettingTheComputerThenForgetsOnThePhoneOnly() {
        val older = engine(null)
        pairedWith(older.url)
        waitUntil(10_000) { vm.connection.state.value is ConnectionState.NeedsUpdate }
        rule.runOnUiThread { vm.unpair() }
        waitUntil(10_000) { !container.settings.paired }
        assertEquals(null, container.settings.token)
        assertEquals(emptySet<String>(), askedBesidesItsVersion(older))
    }

    private fun check(engine: StubEngine) = runBlocking { no.brasscribe.play.connection.EngineConnection(container).check(engine.url) }

    /** The phone holds the credential of the paired engine, and nothing runs but the checks the test asks for. */
    private fun credentialFor(engine: StubEngine) {
        rule.runOnUiThread {
            container.fixtureSource = null
            container.settings.url = engine.url
            container.settings.serverId = StubEngine.SERVER_ID
            container.settings.serverName = "Brasscribe on Studio"
            container.credentials.put(no.brasscribe.play.connection.Credential(StubEngine.SERVER_ID, StubEngine.TOKEN, "d1", "Brasscribe on Studio", engine.url))
            container.settings.paired = true
            vm.connection.stop()
        }
    }

    @Test
    fun anotherEngineAtTheAddressIsNotTheOneToUpdate() {
        // Another computer answers where the paired one was, does not know this phone, and is an old one: the paired
        // one is looked for; nothing says to update a computer that is not ours.
        val other = StubEngine(null, serverId = "ffffffffffffffffffffffffffffffff").also { engines += it }
        other.deviceStatus = 401
        credentialFor(other)
        assertEquals(Check.Unreachable, check(other))
        assertEquals(listOf("GET /v1/devices/me", "GET /v1/health"), other.requests.toList())
        // Nothing the app asks next is sent to that engine or answered with "update": it is not the paired one.
        other.requests.clear()
        val next = runCatching { runBlocking { checkNotNull(container.engine()).jobs() } }.exceptionOrNull()
        assertEquals("$next", 0, (next as? no.brasscribe.play.engine.EngineException)?.status)
        assertEquals(listOf("GET /v1/health"), other.requests.toList())
        // On the screen: looking for the computer, never the update sentence.
        rule.runOnUiThread { vm.connection.retry(); vm.home() }
        waitUntil(15_000) { vm.connection.state.value is ConnectionState.Reconnecting }
        assertFalse(shows(R.string.conn_update_computer))
    }

    @Test
    fun aPhoneTheEngineNoLongerKnowsPairsAgainOnlyWithItsOwnEngineAtThisVersion() {
        val engine = engine(Wire.INTERFACE_VERSION)
        engine.deviceStatus = 401
        credentialFor(engine)
        // The paired engine, this app's version: pair again.
        assertEquals(Check.Unauthorized, check(engine))
        // The paired engine with another version: update first, nothing is paired again against it.
        engine.interfaceVersion = (Wire.INTERFACE_VERSION + 1).toString()
        assertEquals(Check.Mismatch(InterfaceMatch.UPDATE_APP), check(engine))
        engine.interfaceVersion = null
        assertEquals(Check.Mismatch(InterfaceMatch.UPDATE_COMPUTER), check(engine))
        // Its health cannot be read, or it gives none: not there, never "pair again" and never "connected".
        engine.interfaceVersion = Wire.INTERFACE_VERSION.toString()
        rule.runOnUiThread { (container.engine() as no.brasscribe.play.engine.KtorEngineApi).forget() }
        for (body in listOf("<html>Sign in</html>", "{}")) {
            engine.healthBody = body
            assertEquals(body, Check.Unreachable, check(engine))
        }
        engine.healthBody = null
        engine.healthStatus = 503
        assertEquals(Check.Unreachable, check(engine))
        // A newer engine whose health this app cannot read in full: still the paired one, and "update the app".
        engine.healthStatus = null
        engine.healthBody = """{"server_id":"${StubEngine.SERVER_ID}","interface_version":${Wire.INTERFACE_VERSION + 1},"shape":"new"}"""
        assertEquals(Check.Mismatch(InterfaceMatch.UPDATE_APP), check(engine))
    }

    @Test
    fun anAnswerThatIsNotThePhonesEntryIsConnectedOnlyForAClientLetInWithoutOne() {
        val engine = engine(Wire.INTERFACE_VERSION)
        credentialFor(engine)
        // 404: the engine lets this client in without a device entry. Its health says it is ours, at this version.
        engine.deviceStatus = 404
        assertTrue(check(engine) is Check.Ok)
        assertEquals(listOf("GET /v1/devices/me", "GET /v1/health"), engine.requests.toList())
        // The same answer from an engine with another version is "update", and from one that cannot answer, not connected.
        engine.interfaceVersion = null
        assertEquals(Check.Mismatch(InterfaceMatch.UPDATE_COMPUTER), check(engine))
        engine.interfaceVersion = Wire.INTERFACE_VERSION.toString()
        rule.runOnUiThread { (container.engine() as no.brasscribe.play.engine.KtorEngineApi).forget() }
        engine.deviceStatus = 500
        assertEquals(Check.Unreachable, check(engine))
    }

    @Test
    fun aTrustedAddressIsNotConnectedToAnEngineWithAnotherVersionAndNoCodeIsAskedFor() {
        val older = engine(null)
        onThePairingScreen()
        // No code typed: the sentence is "update", not "the code is needed".
        rule.runOnUiThread { vm.connect(older.url, "") }
        waitForState(R.string.conn_update_computer)
        assertFalse(container.settings.paired)
        assertEquals(listOf("GET /v1/health"), older.requests.toList())
        // And an app that is the one behind gets the way to its latest version under the sentence.
        val newer = engine(Wire.INTERFACE_VERSION + 1)
        rule.runOnUiThread { vm.companionState.value = null; vm.connect(newer.url, "") }
        waitForState(R.string.conn_update_app)
        waitUntil { shows(R.string.conn_get_app_update) }
    }

    @Test
    fun whatTheScreensSayWhenTheComputerNeedsAnUpdate() {
        val older = engine(Wire.INTERFACE_VERSION - 1)
        pairedWith(older.url)
        waitUntil(10_000) { vm.connection.state.value is ConnectionState.NeedsUpdate }
        // A finished score tapped in a notification: the update sentence, not "connect to it to open the score".
        rule.runOnUiThread { vm.openFinishedJob("0123456789abcdef") }
        waitUntil(10_000) { vm.status.value?.text == text(R.string.conn_update_computer) }
        // In the background, a job that was being followed: the notice says to update, not that the computer is away.
        val said = mutableListOf<InterfaceMatch>()
        val ended = runBlocking { JobFollow.untilEnded({ checkNotNull(container.engine()).job("j1") }, refused = { said += it }) }
        assertEquals(null, ended)
        assertEquals(listOf(InterfaceMatch.UPDATE_COMPUTER), said)
        assertEquals(emptySet<String>(), askedBesidesItsVersion(older))
    }
}
