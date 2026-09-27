package no.brasscribe.play.connection

import org.junit.Assert.assertEquals
import org.junit.Test

class ServerNamesTest {
    private fun nb(name: String) = ServerNames.display(name, { "Brasscribe på $it" }, "Brasscribe på datamaskinen")
    private fun en(name: String) = ServerNames.display(name, { "Brasscribe on $it" }, "Brasscribe on your computer")

    @Test
    fun norwegianBuildsItsOwnPhraseFromTheComputerName() {
        assertEquals("Brasscribe på Kallis MacBook", nb("Brasscribe on Kallis MacBook"))
        assertEquals("Brasscribe på Kallis MacBook", nb("Brasscribe on Kallis MacBook (2)"))
        assertEquals("Brasscribe on Kallis MacBook", en("Brasscribe on Kallis MacBook"))
    }

    @Test
    fun otherNamesStayAsTheyAreAndNothingFallsBackToAGenericName() {
        assertEquals("Studio", nb("Studio"))
        assertEquals("Brasscribe på datamaskinen", nb(""))
        assertEquals("Brasscribe på datamaskinen", nb("Brasscribe on "))
    }
}
