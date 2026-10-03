package no.brasscribe.play

import kotlinx.coroutines.runBlocking
import no.brasscribe.play.engine.EngineException
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

/** A job made from the recording the computer holds, and the phone's copy sent when it no longer has it ([jobFromRecording]). */
class RecordingOnComputerTest {
    private val said = mutableListOf<String>()

    private fun run(held: () -> String?, canSend: Boolean = true, refuse: Map<String, Int> = emptyMap()): Pair<String, String> = runBlocking {
        jobFromRecording(
            held = { held() },
            canSend = canSend,
            send = { said += "send"; "sent" },
            resent = { said += "resent" },
        ) { audio ->
            said += "create $audio"
            refuse[audio]?.let { throw EngineException(it, "/v1/jobs: $it") }
            "job of $audio"
        }
    }

    @Test
    fun aProductThatNamesNoRecordingSendsItAsBefore() {
        assertEquals("sent" to "job of sent", run({ null }))
        assertEquals(listOf("send", "create sent"), said)
    }

    @Test
    fun theRecordingTheComputerHoldsIsNotSentAgain() {
        assertEquals("held" to "job of held", run({ "held" }))
        assertEquals(listOf("create held"), said)
    }

    @Test
    fun whenTheComputerNoLongerHasItThePhonesCopyIsSentAndThatIsSaid() {
        assertEquals("sent" to "job of sent", run({ "held" }, refuse = mapOf("held" to 404)))
        assertEquals(listOf("create held", "resent", "send", "create sent"), said)
    }

    @Test
    fun whenTheComputerNoLongerHasTheSongTheRecordingCameFromThePhonesCopyIsSent() {
        assertEquals("sent" to "job of sent", run({ throw EngineException(404, "/v1/jobs/j: 404") }))
        assertEquals(listOf("resent", "send", "create sent"), said)
    }

    @Test
    fun withoutACopyOnThePhoneItSaysTheRecordingIsGone() {
        val e = assertThrows(RecordingGoneException::class.java) { run({ "held" }, canSend = false, refuse = mapOf("held" to 404)) }
        assertEquals(R.string.error_recording_gone, ErrorWords.of(e))
        assertEquals(listOf("create held"), said)
        assertThrows(RecordingGoneException::class.java) { run({ throw EngineException(404, "gone") }, canSend = false) }
    }

    @Test
    fun anyOtherAnswerIsTheComputersOwnAndNothingIsSent() {
        assertEquals(500, assertThrows(EngineException::class.java) { run({ "held" }, refuse = mapOf("held" to 500)) }.status)
        assertEquals(401, assertThrows(EngineException::class.java) { run({ throw EngineException(401, "pair again") }) }.status)
        // A job refused for a recording that was just sent is not sent again.
        assertEquals(404, assertThrows(EngineException::class.java) { run({ null }, refuse = mapOf("sent" to 404)) }.status)
        assertEquals(listOf("create held", "send", "create sent"), said)
    }
}
