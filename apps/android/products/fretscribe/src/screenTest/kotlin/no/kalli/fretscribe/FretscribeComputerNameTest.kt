package no.kalli.fretscribe

import no.kalli.scribe.tab.*

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import androidx.test.ext.junit.runners.AndroidJUnit4
import no.kalli.scribe.play.screen.ScreenTest
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/** The computer calls itself "Brasscribe on Kari's Mac"; Fretscribe names it by the program on it, as it calls that program everywhere: "Bandroom on Kari's Mac". */
@RunWith(AndroidJUnit4::class)
class FretscribeComputerNameTest : ScreenTest() {
    @Test
    fun theComputerIsBandroomOnItsName() {
        assertEquals("Bandroom on Kari's Mac", vm.serverDisplayName("Brasscribe on Kari's Mac"))
        language("nb")
        assertEquals("Bandroom på Kari's Mac", vm.serverDisplayName("Brasscribe on Kari's Mac"))
    }
}
