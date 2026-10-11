package no.brasscribe.play.engine

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

/** The app is built for one interface version; the engine says its own in its health answer. */
class InterfaceMatchTest {
    private val json = Json { ignoreUnknownKeys = true }
    private fun health(extra: String) = json.decodeFromString(Health.serializer(),
        """{"status":"ok","version":"1.0.0","device":"cpu","auth_required":true,"server_id":"s","server_name":"n"$extra}""")

    @Test
    fun theSameNumberMatches() {
        assertEquals(InterfaceMatch.MATCH, InterfaceMatch.of(Wire.INTERFACE_VERSION))
        health(""","interface_version":${Wire.INTERFACE_VERSION}""").requireSameInterface()
    }

    @Test
    fun aNewerEngineMeansUpdateTheApp() {
        assertEquals(InterfaceMatch.UPDATE_APP, InterfaceMatch.of(Wire.INTERFACE_VERSION + 1))
        val e = assertThrows(InterfaceMismatchException::class.java) { health(""","interface_version":${Wire.INTERFACE_VERSION + 1}""").requireSameInterface() }
        assertEquals(InterfaceMatch.UPDATE_APP, e.update)
    }

    @Test
    fun anOlderEngineMeansUpdateBandroom() {
        assertEquals(InterfaceMatch.UPDATE_COMPUTER, InterfaceMatch.of(Wire.INTERFACE_VERSION - 1))
        assertEquals(InterfaceMatch.UPDATE_COMPUTER, InterfaceMatch.of(3, app = 4))
    }

    @Test
    fun anEngineWithoutTheNumberMeansUpdateBandroom() {
        assertEquals(InterfaceMatch.UPDATE_COMPUTER, InterfaceMatch.of(null))
        val e = assertThrows(InterfaceMismatchException::class.java) { health("").requireSameInterface() }
        assertEquals(InterfaceMatch.UPDATE_COMPUTER, e.update)
    }

    @Test
    fun thisReleaseIsInterfaceVersionOne() {
        assertEquals(1, Wire.INTERFACE_VERSION)
        assertEquals("scribe", Wire.PAIR_SCHEME)
        assertEquals("_scribe._tcp", Wire.SERVICE_TYPE)
    }
}
