package no.brasscribe.play.connection

import kotlinx.coroutines.runBlocking
import no.brasscribe.play.ErrorWords
import no.brasscribe.play.LocalNetwork
import no.brasscribe.play.LocalNetworkClosedException
import no.brasscribe.play.R
import no.kalli.scribe.engine.EngineException
import no.kalli.scribe.engine.KtorEngineApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * While the phone has the local network closed to the app, a request to the computer is not sent: it fails at
 * once, and in the player's words it is the network that is closed, not a computer that can't be reached.
 */
class ClosedNetworkRequestTest {
    @Test
    fun aRequestFailsAtOnceAndSaysTheNetworkIsClosed() = runBlocking {
        // A documentation address (RFC 5737): a request that was sent there would wait for the connection to time out.
        val api = KtorEngineApi("http://192.0.2.1:8765", EngineHttp.engine { false })
        val started = System.currentTimeMillis()
        val failed = runCatching { api.health() }.exceptionOrNull()
        api.close()
        assertTrue("it failed: $failed", failed != null)
        assertTrue("at once, not after a timeout", System.currentTimeMillis() - started < 3_000)
        assertTrue("$failed", ErrorWords.networkClosed(failed!!))
        assertEquals(R.string.pair_network_refused, ErrorWords.of(failed))
    }

    @Test
    fun wrappedByAnotherErrorItIsStillTheNetwork() {
        val wrapped = EngineException(0, "event stream lost: ${LocalNetworkClosedException().message}")
        assertEquals(R.string.pair_network_refused, ErrorWords.of(wrapped))
        assertEquals(R.string.pair_network_refused, ErrorWords.of(RuntimeException("sending failed", LocalNetworkClosedException())))
        assertEquals(R.string.error_unreachable, ErrorWords.of(EngineException(0, "connection refused")))
    }

    @Test
    fun thePhoneItselfIsNeverClosed() {
        assertTrue(LocalNetwork.isThisPhone("127.0.0.1"))
        assertTrue(LocalNetwork.isThisPhone("localhost"))
        assertTrue(LocalNetwork.isThisPhone("::1"))
        assertFalse(LocalNetwork.isThisPhone("10.0.2.2"))
        assertFalse(LocalNetwork.isThisPhone("192.168.0.2"))
        assertFalse(LocalNetwork.isThisPhone("karis-mac.local"))
    }
}
