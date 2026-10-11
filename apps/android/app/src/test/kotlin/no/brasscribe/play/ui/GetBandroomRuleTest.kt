package no.brasscribe.play.ui

import no.brasscribe.play.connection.ConnectionState
import no.brasscribe.play.engine.InterfaceMatch
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The pairing screen offers Get Bandroom while nothing is paired, the paired computer can't be found, or its Bandroom needs an update. */
class GetBandroomRuleTest {
    @Test
    fun onlyWithoutAComputerToReach() {
        assertTrue(showsGetBandroom(paired = false, ConnectionState.Offline(paired = false)))
        assertTrue(showsGetBandroom(paired = true, ConnectionState.Offline(paired = true)))
        assertFalse(showsGetBandroom(paired = true, ConnectionState.Connected("Kari's Mac")))
        assertFalse(showsGetBandroom(paired = true, ConnectionState.Reconnecting("Kari's Mac")))
        // Bandroom there is older than this app: the same address has the latest one. An older app is updated on the phone.
        assertTrue(showsGetBandroom(paired = true, ConnectionState.NeedsUpdate("Kari's Mac", InterfaceMatch.UPDATE_COMPUTER)))
        assertFalse(showsGetBandroom(paired = true, ConnectionState.NeedsUpdate("Kari's Mac", InterfaceMatch.UPDATE_APP)))
    }
}
