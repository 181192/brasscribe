package no.brasscribe.play

import no.brasscribe.play.engine.EngineException
import org.junit.Assert.assertEquals
import org.junit.Test

/** Engine and core failures in the player's words: never the engine's own English text. */
class ErrorWordsTest {
    @Test
    fun engineCodesHaveTheirOwnWords() {
        assertEquals(R.string.lineup_quartet_needs_group, ErrorWords.of(EngineException(422, "x", "quartet_needs_group")))
        assertEquals(R.string.percussion_solo_refused, ErrorWords.of(EngineException(422, "x", "percussion_solo")))
        assertEquals(R.string.lead_seat_refused, ErrorWords.of(EngineException(422, "x", "seat_no_tune")))
        assertEquals(R.string.error_reads_not_offered, ErrorWords.of(EngineException(422, "x", "reads_not_offered")))
        assertEquals(R.string.error_invalid_options, ErrorWords.of(EngineException(422, "x", "invalid_options")))
        // a tab asked of a computer that cannot write one is not "these choices"
        assertEquals(R.string.error_core_missing, ErrorWords.of(EngineException(422, "x", "core_missing")))
        // an engine too old to send a code
        assertEquals(R.string.error_invalid_options, ErrorWords.of(EngineException(422, "x")))
    }

    @Test
    fun theConnectionAndTheCore() {
        assertEquals(R.string.error_unreachable, ErrorWords.of(EngineException(0, "event stream lost")))
        assertEquals(R.string.error_unreachable, ErrorWords.of(java.net.ConnectException("refused")))
        assertEquals(R.string.error_timeout, ErrorWords.of(java.net.SocketTimeoutException("slow")))
        assertEquals(R.string.error_pair_again, ErrorWords.of(EngineException(401, "x")))
        assertEquals(R.string.error_engine_failed, ErrorWords.of(EngineException(500, "x")))
        assertEquals(R.string.error_engine_failed, ErrorWords.of(EngineJobFailedException("MuseScore did not write brass-band.pdf")))
        assertEquals(R.string.where_companion_missing, ErrorWords.of(NoCompanionException()))
        assertEquals(R.string.percussion_solo_refused,
            ErrorWords.of(RuntimeException("invalid input: percussion can't be written down from a solo take yet: record the band")))
        assertEquals(R.string.error_generic, ErrorWords.of(IllegalStateException("anything")))
    }
}
