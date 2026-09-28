package no.brasscribe.play

import androidx.annotation.StringRes
import no.brasscribe.play.engine.EngineException

/** A job on the computer ended without a score; [message] is the engine's own (English) words. */
class EngineJobFailedException(message: String) : Exception(message)

/** The app has no computer to send the job to. */
class NoCompanionException : Exception("no computer paired")

/**
 * The player's words for what went wrong: the engine's refusal codes, the connection, the core's
 * refusals. The engine's and the core's own text is English; it stays in the problem screen's details
 * and the log, never in the status line or the reasons.
 */
object ErrorWords {
    /** The core's refusal of a drummer's solo take (instruments.rs PERCUSSION_SOLO). */
    private const val CORE_PERCUSSION_SOLO = "percussion can't be written down from a solo take"

    @StringRes
    fun of(e: Throwable): Int = when (e) {
        is QuartetNeedsGroupException -> R.string.lineup_quartet_needs_group
        is LeadSeatRefusedException -> R.string.lead_seat_refused
        is NoCompanionException -> R.string.where_companion_missing
        is EngineJobFailedException -> R.string.error_engine_failed
        is EngineException -> when (e.code) {
            "quartet_needs_group" -> R.string.lineup_quartet_needs_group
            "percussion_solo" -> R.string.percussion_solo_refused
            "seat_no_tune" -> R.string.lead_seat_refused
            "reads_not_offered" -> R.string.error_reads_not_offered
            "invalid_options" -> R.string.error_invalid_options
            else -> when (e.status) {
                0 -> R.string.error_unreachable
                401, 403 -> R.string.error_pair_again
                408, 504 -> R.string.error_timeout
                422 -> R.string.error_invalid_options
                in 500..599 -> R.string.error_engine_failed
                else -> R.string.error_generic
            }
        }
        is java.net.SocketTimeoutException, is kotlinx.coroutines.TimeoutCancellationException -> R.string.error_timeout
        is java.io.IOException -> if (e.javaClass.simpleName.contains("Timeout")) R.string.error_timeout else R.string.error_unreachable
        else -> when {
            e.message?.contains(CORE_PERCUSSION_SOLO) == true -> R.string.percussion_solo_refused
            e.javaClass.simpleName.contains("Timeout") -> R.string.error_timeout
            else -> R.string.error_generic
        }
    }
}
