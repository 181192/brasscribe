package no.brasscribe.play.engine

import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/** The app is built for one interface version; the engine says its own, and one with another is asked for its health only. */
class InterfaceMatchTest {
    private val json = Json { ignoreUnknownKeys = true }
    private val jsonType = headersOf(HttpHeaders.ContentType, "application/json")

    private fun healthBody(extra: String) =
        """{"status":"ok","version":"1.0.0","device":"cpu","auth_required":true,"server_id":"s","server_name":"n"$extra}"""

    private fun health(extra: String) = json.decodeFromString(Health.serializer(), healthBody(extra))

    @Test
    fun theSameNumberMatches() {
        assertEquals(InterfaceMatch.MATCH, InterfaceMatch.of(Wire.INTERFACE_VERSION))
        assertEquals(InterfaceMatch.MATCH, InterfaceMatch.of(health(""","interface_version":${Wire.INTERFACE_VERSION}""").interfaceVersion))
    }

    @Test
    fun aNewerEngineMeansUpdateTheApp() {
        assertEquals(InterfaceMatch.UPDATE_APP, InterfaceMatch.of(Wire.INTERFACE_VERSION + 1))
        assertEquals(InterfaceMatch.UPDATE_APP, InterfaceMatch.of(health(""","interface_version":${Wire.INTERFACE_VERSION + 1}""").interfaceVersion))
    }

    @Test
    fun anOlderEngineMeansUpdateBandroom() {
        assertEquals(InterfaceMatch.UPDATE_COMPUTER, InterfaceMatch.of(Wire.INTERFACE_VERSION - 1))
        assertEquals(InterfaceMatch.UPDATE_COMPUTER, InterfaceMatch.of(3, app = 4))
    }

    @Test
    fun anEngineWithoutTheNumberMeansUpdateBandroom() {
        assertEquals(InterfaceMatch.UPDATE_COMPUTER, InterfaceMatch.of(null))
        assertNull(health("").interfaceVersion)
    }

    @Test
    fun aNumberThatIsNoWholeNumberIsNoNumberAndTheRestIsStillRead() {
        for (odd in listOf("1.5", "1.0", "true", "\"1\"", "99999999999", "null", "[1]", "{}")) {
            val h = health(""","interface_version":$odd""")
            assertNull(odd, h.interfaceVersion)
            assertEquals(odd, "s", h.serverId)
            assertEquals(odd, InterfaceMatch.UPDATE_COMPUTER, InterfaceMatch.of(h.interfaceVersion))
        }
        // The phone's own entry carries the number too, read the same way.
        val me = """{"device_id":"d","name":"Phone","platform":"android","paired_at":"a","last_seen":"b","online":true,"server_id":"s",""" +
            """"rotate_after":"c","expires_if_idle_after":"d","interface_version":"""
        assertEquals(1, json.decodeFromString(DeviceSelf.serializer(), "${me}1}").interfaceVersion)
        assertNull(json.decodeFromString(DeviceSelf.serializer(), "${me}1.5}").interfaceVersion)
    }

    /** An engine that answers health with [health] and remembers what it was asked. */
    private fun engine(asked: MutableList<String>, health: () -> String?) = MockEngine { req ->
        asked += "${req.method.value} ${req.url.encodedPath}"
        when (req.url.encodedPath) {
            "/v1/health" -> health()?.let { respond(it, HttpStatusCode.OK, jsonType) } ?: throw java.io.IOException("not there")
            "/v1/jobs" -> respond("[]", HttpStatusCode.OK, jsonType)
            "/v1/devices/me" -> respond(
                """{"device_id":"d","name":"Phone","platform":"android","paired_at":"a","last_seen":"b","online":true,"server_id":"s",""" +
                    """"rotate_after":"c","expires_if_idle_after":"d","interface_version":2}""", HttpStatusCode.OK, jsonType)
            else -> respond("{}", HttpStatusCode.OK, jsonType)
        }
    }

    @Test
    fun theFirstRequestAsksTheEnginesHealthFirst() = runTest {
        val asked = mutableListOf<String>()
        val api = KtorEngineApi("http://host", engine(asked) { healthBody(""","interface_version":${Wire.INTERFACE_VERSION}""") })
        assertNull(api.interfaceMatch)
        api.jobs()
        api.jobs()
        assertEquals(listOf("GET /v1/health", "GET /v1/jobs", "GET /v1/jobs"), asked)
        assertEquals(InterfaceMatch.MATCH, api.interfaceMatch)
    }

    @Test
    fun anEngineWithAnotherNumberIsAskedForItsHealthOnly() = runTest {
        for ((body, update) in listOf(
            healthBody(""","interface_version":${Wire.INTERFACE_VERSION + 1}""") to InterfaceMatch.UPDATE_APP,
            healthBody(""","interface_version":${Wire.INTERFACE_VERSION - 1}""") to InterfaceMatch.UPDATE_COMPUTER,
            healthBody("") to InterfaceMatch.UPDATE_COMPUTER,
            healthBody(""","interface_version":"one"""") to InterfaceMatch.UPDATE_COMPUTER,
            // An answer this app cannot read in full is still that engine's, not one that cannot be reached.
            """{"interface_version":7}""" to InterfaceMatch.UPDATE_APP,
            """{"status":"ok"}""" to InterfaceMatch.UPDATE_COMPUTER,
        )) {
            val asked = mutableListOf<String>()
            val api = KtorEngineApi("http://host", engine(asked) { body }, token = "t")
            val calls: List<suspend () -> Any?> = listOf(
                { api.jobs() }, { api.pair("123456", "Pixel") }, { api.requestPairing("Pixel") }, { api.unpairThisDevice() },
                { api.rotateToken() }, { api.cancel("j") }, { api.renameRun("j", "t") }, { api.deleteRun("j") }, { api.musicXml("j") },
                { api.events("j").toList() }, { api.thisDevice() },
            )
            for (call in calls) {
                val refused = runCatching { call() }.exceptionOrNull()
                assertEquals(body, update, (refused as? InterfaceMismatchException)?.update)
            }
            assertEquals(body, listOf("GET /v1/health"), asked)
        }
    }

    @Test
    fun aPairedPhonesOwnEntryMayBeTheFirstThingAskedAndSaysTheNumber() = runTest {
        val asked = mutableListOf<String>()
        val api = KtorEngineApi("http://host", engine(asked) { healthBody("") }, token = "t")
        assertEquals(2, api.thisDevice().interfaceVersion)
        assertEquals(InterfaceMatch.UPDATE_APP, api.interfaceMatch)
        assertTrue(runCatching { api.jobs() }.exceptionOrNull() is InterfaceMismatchException)
        // Known to be another version: the heartbeat is health from now on.
        assertTrue(runCatching { api.thisDevice() }.exceptionOrNull() is InterfaceMismatchException)
        assertEquals(listOf("GET /v1/devices/me"), asked)
    }

    @Test
    fun afterARequestThatDidNotGetThroughTheEngineIsAskedAgain() = runTest {
        val asked = mutableListOf<String>()
        var body: String? = healthBody(""","interface_version":${Wire.INTERFACE_VERSION}""")
        val api = KtorEngineApi("http://host", engine(asked) { body })
        api.jobs()
        // The computer goes away (its update), and comes back as another version.
        body = null
        assertTrue(runCatching { api.health() }.exceptionOrNull() is java.io.IOException)
        assertNull(api.interfaceMatch)
        body = healthBody(""","interface_version":${Wire.INTERFACE_VERSION + 1}""")
        asked.clear()
        assertEquals(InterfaceMatch.UPDATE_APP, (runCatching { api.jobs() }.exceptionOrNull() as? InterfaceMismatchException)?.update)
        assertEquals(listOf("GET /v1/health"), asked)
        // And once both are up to date, it works again without anything else being done.
        body = healthBody(""","interface_version":${Wire.INTERFACE_VERSION}""")
        api.health()
        api.jobs()
        assertEquals(InterfaceMatch.MATCH, api.interfaceMatch)
    }

    /** The engine's own file says the same names and number as this app's. */
    @Test
    fun theNamesAndTheNumberAreTheEngines() {
        val wire = File(System.getProperty("brasscribe.engine") ?: "", "wire.py")
        assumeTrue("the engine's wire.py is in this checkout", wire.isFile)
        val text = wire.readText()
        fun value(name: String) = Regex("""^$name\s*=\s*"?([^"\n]+?)"?\s*$""", RegexOption.MULTILINE).find(text)?.groupValues?.get(1)
        assertEquals(Wire.INTERFACE_VERSION.toString(), value("INTERFACE_VERSION"))
        assertEquals(Wire.PAIR_SCHEME, value("PAIRING_SCHEME"))
        assertEquals(Wire.SERVICE_TYPE, value("SERVICE_TYPE"))
    }
}
