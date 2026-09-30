package no.brasscribe.play.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PairLinkTest {
    @Test
    fun parsesTheComputersPayload() {
        val l = PairLink.parse("brasscribe://pair?v=1&id=srv-7f3a&name=Brasscribe%20on%20Kalli%E2%80%99s%20Mac&h=192.168.1.20:8765,[fd00::5]:8765&code=482913")!!
        assertEquals("srv-7f3a", l.serverId)
        assertEquals("Brasscribe on Kalli’s Mac", l.serverName)
        assertEquals(listOf("192.168.1.20:8765", "[fd00::5]:8765"), l.hosts)
        assertEquals(listOf("http://192.168.1.20:8765", "http://[fd00::5]:8765"), l.urls)
        assertEquals("482913", l.code)
        assertNull(l.fingerprint)
    }

    @Test
    fun keepsFingerprintAndPlusSpaces() {
        val l = PairLink.parse("brasscribe://pair?v=1&id=a&name=Brasscribe+on+studio&h=10.0.0.2:8765&code=1&fp=abc_-DEF")!!
        assertEquals("Brasscribe on studio", l.serverName)
        assertEquals("abc_-DEF", l.fingerprint)
    }

    @Test
    fun dropsBadHostsButKeepsGoodOnes() {
        val l = PairLink.parse("brasscribe://pair?v=1&id=a&h=nope,10.0.0.2,1.2.3.4:0,evil@x:1,10.0.0.3:8765&code=1")!!
        assertEquals(listOf("10.0.0.3:8765"), l.hosts)
        assertEquals("", l.serverName)
    }

    @Test
    fun keepsOnlyAddressesOnTheLocalNetwork() {
        val l = PairLink.parse("brasscribe://pair?v=1&id=a&h=203.0.113.9:8765,8.8.8.8:80,[2001:db8::1]:8765,example.com:8765," +
            "192.168.1.20:8765,172.20.0.5:8765,172.32.0.5:8765,169.254.3.4:8765,[fe80::1]:8765,[fd00::5]:8765,studio.local:8765,100.64.0.1:8765&code=1")!!
        assertEquals(listOf("192.168.1.20:8765", "172.20.0.5:8765", "169.254.3.4:8765", "[fe80::1]:8765", "[fd00::5]:8765", "studio.local:8765"), l.hosts)
    }

    @Test
    fun validHostNeedsAPortAndALocalAddress() {
        listOf("10.0.2.2:8765", "127.0.0.1:1", "[::1]:8765", "localhost:8765", "10.255.255.255:65535").forEach { assertTrue(it, PairLink.validHost(it)) }
        listOf("10.0.0.2", "10.0.0.2:0", "10.0.0.2:70000", "1.2.3.4:8765", "256.1.1.1:80", "10.0.0:80", "evil.com:8765",
            "local:8765", ".local:8765", "a b.local:8765", "[2001:db8::1]:8765", "[fd00::5]", "user@10.0.0.2:80").forEach { assertFalse(it, PairLink.validHost(it)) }
    }

    @Test
    fun onlyThisPhoneAndTheEmulatorsHostAreTrustedWithoutPairing() {
        listOf("127.0.0.1", "localhost", "::1", "[::1]", "10.0.2.2").forEach { assertTrue(it, LocalHosts.isTrusted(it)) }
        listOf("192.168.1.20", "10.0.2.3", "fd00::5", "studio.local", "example.com").forEach { assertFalse(it, LocalHosts.isTrusted(it)) }
        assertEquals("fd00::5", LocalHosts.hostOf("http://[fd00::5]:8765"))
        assertEquals("192.168.1.20", LocalHosts.hostOf("http://192.168.1.20:8765/"))
        assertNull(LocalHosts.hostOf("not a url"))
    }

    @Test
    fun addressesAndCodeAreOptional() {
        val l = PairLink.parse("brasscribe://pair?v=1&id=abc&name=Brasscribe%20on%20mac&future=1")!!
        assertEquals(emptyList<String>(), l.hosts)
        assertNull(l.code)
        assertEquals("482913", PairLink.parse("brasscribe://pair?v=1&id=abc&code=482%20913")!!.code)
    }

    @Test
    fun rejectsWhatIsNotAPairingLink() {
        listOf(
            "https://pair?v=1&id=a&h=1.2.3.4:1&code=1",
            "brasscribe://other?v=1&id=a&h=1.2.3.4:1&code=1",
            "brasscribe://pair?v=2&id=a&h=1.2.3.4:1&code=1",
            "brasscribe://pair?id=a&h=1.2.3.4:1&code=1",
            "brasscribe://pair?v=1&h=1.2.3.4:1&code=1",
            "brasscribe://pair?v=1&id=&h=1.2.3.4:1&code=1",
            "not a uri at all",
            "",
        ).forEach { assertNull(it, PairLink.parse(it)) }
    }
}
