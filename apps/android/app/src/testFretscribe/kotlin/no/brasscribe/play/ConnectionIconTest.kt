package no.brasscribe.play

import no.brasscribe.play.connection.ConnectionState
import no.brasscribe.play.ui.connectionIcon
import org.junit.Assert.assertEquals
import org.junit.Test

/** Fretscribe writes a tab on the computer only: without it, "Not connected" keeps its warning. */
class ConnectionIconTest {
    @Test
    fun notConnectedIsAWarning() {
        assertEquals(R.drawable.ic_bc_attention, connectionIcon(ConnectionState.Offline(paired = false)))
        assertEquals(R.drawable.ic_bc_attention, connectionIcon(ConnectionState.Offline(paired = true)))
    }
}
