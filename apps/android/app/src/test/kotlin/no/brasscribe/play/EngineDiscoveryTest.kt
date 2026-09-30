package no.brasscribe.play

import java.net.InetAddress
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class EngineDiscoveryTest {
    private fun ip(s: String) = InetAddress.getByName(s)

    @Test
    fun overlappingFindsShareOneSession() {
        val calls = mutableListOf<String>()
        val s = EngineDiscovery.SharedSession({ calls += "start" }, { calls += "stop" })
        s.acquire()
        s.acquire()
        s.release()
        assertEquals("the second find keeps it going", listOf("start"), calls)
        s.release()
        assertEquals(listOf("start", "stop"), calls)
        s.release()
        s.acquire()
        assertEquals(listOf("start", "stop", "start"), calls)
    }

    @Test
    fun prefersPrivateIpv4() {
        assertEquals("http://192.168.0.2:8765", EngineDiscovery.engineUrl(listOf(ip("fe80::1"), ip("100.64.0.1"), ip("192.168.0.2")), 8765))
        assertEquals("http://100.64.0.1:8765", EngineDiscovery.engineUrl(listOf(ip("fe80::1"), ip("100.64.0.1")), 8765))
    }

    @Test
    fun usesRoutableIpv6WhenThereIsNoIpv4() {
        assertEquals("http://[2001:db8:0:0:0:0:0:1]:8765", EngineDiscovery.engineUrl(listOf(ip("2001:db8::1")), 8765))
    }

    @Test
    fun skipsLinkLocalOnlyAndMissingPort() {
        assertNull(EngineDiscovery.engineUrl(listOf(ip("fe80::1")), 8765))
        assertNull(EngineDiscovery.engineUrl(listOf(ip("192.168.0.2")), 0))
        assertNull(EngineDiscovery.engineUrl(emptyList(), 8765))
    }
}
