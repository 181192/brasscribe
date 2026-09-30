package no.brasscribe.play.connection

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EngineConnectionTest {
    @Test
    fun withoutACredentialOnlyATrustedHostCountsAsConnected() {
        // The emulator's host or loopback: the engine lets it in without pairing.
        assertTrue(EngineConnection.noCredential(authRequired = false, trustedHost = true, sameServer = true) is Check.Ok)
        // Restored from a backup, or the Keystore was reset: the paired engine wants a credential; pair again.
        assertEquals(Check.Unauthorized, EngineConnection.noCredential(authRequired = true, trustedHost = false, sameServer = true))
        assertEquals(Check.Unauthorized, EngineConnection.noCredential(authRequired = true, trustedHost = true, sameServer = true))
        // An address that is not trusted gets no pass for saying so.
        assertEquals(Check.Unauthorized, EngineConnection.noCredential(authRequired = false, trustedHost = false, sameServer = true))
        // Another engine now answers at the address: the paired one is not there.
        assertEquals(Check.Unreachable, EngineConnection.noCredential(authRequired = true, trustedHost = false, sameServer = false))
    }
}
