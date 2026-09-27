package no.brasscribe.play.engine

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
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
