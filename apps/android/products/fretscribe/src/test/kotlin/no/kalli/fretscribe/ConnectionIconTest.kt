package no.kalli.fretscribe

import no.kalli.scribe.tab.*

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import no.kalli.scribe.design.R as DesignR

import no.kalli.scribe.connection.ConnectionState
import no.kalli.scribe.play.ui.connectionIcon
import org.junit.Assert.assertEquals
import org.junit.Test

/** Fretscribe writes a tab on the computer only: without it, "Not connected" keeps its warning. */
class ConnectionIconTest {
    @Test
    fun notConnectedIsAWarning() {
        assertEquals(DesignR.drawable.ic_bc_attention, connectionIcon(ConnectionState.Offline(paired = false), Fretscribe.makesScoresOnThePhone))
        assertEquals(DesignR.drawable.ic_bc_attention, connectionIcon(ConnectionState.Offline(paired = true), Fretscribe.makesScoresOnThePhone))
    }
}
