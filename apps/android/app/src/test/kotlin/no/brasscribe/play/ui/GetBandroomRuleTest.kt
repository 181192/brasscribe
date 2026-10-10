package no.brasscribe.play.ui

import no.brasscribe.play.connection.ConnectionState
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The pairing screen offers Get Bandroom only while nothing is paired or the paired computer can't be found. */
class GetBandroomRuleTest {
    @Test
    fun onlyWithoutAComputerToReach() {
        assertTrue(showsGetBandroom(paired = false, ConnectionState.Offline(paired = false)))
        assertTrue(showsGetBandroom(paired = true, ConnectionState.Offline(paired = true)))
        assertFalse(showsGetBandroom(paired = true, ConnectionState.Connected("Kari's Mac")))
        assertFalse(showsGetBandroom(paired = true, ConnectionState.Reconnecting("Kari's Mac")))
    }
}
