package no.kalli.scribe.play

import no.kalli.scribe.connection.LocalNetworkClosedException

import androidx.annotation.StringRes
import no.kalli.scribe.engine.EngineException
import no.kalli.scribe.engine.InterfaceMatch
import no.kalli.scribe.engine.InterfaceMismatchException

/** A job on the computer ended without a score; [message] is the engine's own (English) words. */
class EngineJobFailedException(message: String) : Exception(message)

/** The app has no computer to send the job to. */
class NoCompanionException : Exception("no computer paired")

/** The computer offers no profile that reads printed music: its Bandroom is from before that, or has no reader of it installed. */
class PagesNotReadException : Exception("the computer's Bandroom does not read pages")

/** The computer no longer holds the pages a tab is to be written from again; the phone let go of them when the tab was made. */
class PagesGoneException : Exception("the computer no longer holds the pages")

/** The take is longer than the phone's free memory holds for a band draft. */
class DraftTooLongException(detail: String) : Exception(detail)

/**
 * The player's words for what went wrong: the engine's refusal codes, the connection, the core's
 * refusals. The engine's and the core's own text is English; it stays in the problem screen's details
 * and the log, never in the status line or the reasons.
 */
object ErrorWords {
    /** The core's refusal of a drummer's solo take (instruments.rs PERCUSSION_SOLO). */
    private const val CORE_PERCUSSION_SOLO = "percussion can't be written down from a solo take"

    /** The request was never sent: the phone has the local network closed to the app (also when another exception wraps it). */
    fun networkClosed(e: Throwable): Boolean = generateSequence(e) { it.cause }.take(8)
        .any { it is LocalNetworkClosedException || it.message?.contains(LocalNetworkClosedException.MESSAGE) == true }

    /** Which of the two to update when the computer's interface version is not this app's. */
    @StringRes
    fun update(which: InterfaceMatch): Int = if (which == InterfaceMatch.UPDATE_APP) R.string.conn_update_app else R.string.conn_update_computer

    // The fixed words a job that reads pages fails with, at the end of its error (the engine's sheet.py).
    const val NO_NOTES_ON_PAGE = "no notes were found on the page"
    const val ONLY_TAB_ON_PAGE = "no staff of notes was found on the page: a tab staff is not read"
    const val PAGE_TOO_LARGE = "a page is too large to read"
    const val PAGES_NOT_READ = "the pages could not be read"
    private val TOO_MANY_PAGES = Regex("""there are more than \d+ pages$""")

    /** The app's words for why a job read no pages, from the engine's own at the end of [error]; null for any other failure. */
    @StringRes
    fun pagesNotRead(error: String?): Int? = error?.trim()?.let { said ->
        when {
            said.endsWith(ONLY_TAB_ON_PAGE) -> R.string.error_only_tab_on_page
            said.endsWith(PAGE_TOO_LARGE) -> R.string.error_page_too_large
            TOO_MANY_PAGES.containsMatchIn(said) -> R.string.error_too_many_pages
            else -> null
        }
    }

    @StringRes
    fun of(e: Throwable): Int = if (networkClosed(e)) R.string.pair_network_refused else when (e) {
        is QuartetNeedsGroupException -> R.string.lineup_quartet_needs_group
        is LeadSeatRefusedException -> R.string.lead_seat_refused
        is NoCompanionException -> R.string.where_companion_missing
        is InterfaceMismatchException -> update(e.update)
        is EngineJobFailedException -> pagesNotRead(e.message) ?: R.string.error_engine_failed
        is RecordingGoneException -> R.string.error_recording_gone
        is PagesNotReadException -> R.string.error_pages_not_read
        is PagesGoneException -> R.string.error_pages_gone
        is EngineException -> when (e.code) {
            "quartet_needs_group" -> R.string.lineup_quartet_needs_group
            "percussion_solo" -> R.string.percussion_solo_refused
            "seat_no_tune" -> R.string.lead_seat_refused
            "reads_not_offered" -> R.string.error_reads_not_offered
            "invalid_options" -> R.string.error_invalid_options
            "core_missing" -> R.string.error_core_missing
            // not taken: the computer has not been set up for a full band yet (the band writer and its key)
            "band_writer_not_set_up" -> R.string.error_band_writer_not_set_up
            no.kalli.scribe.engine.InputRefusal.NOT_A_PAGE -> R.string.error_not_a_page
            no.kalli.scribe.engine.InputRefusal.PAGE_TOO_LARGE -> R.string.error_page_too_large
            no.kalli.scribe.engine.InputRefusal.READER_MISSING -> R.string.error_reader_missing
            else -> when (e.status) {
                0 -> R.string.error_unreachable
                401, 403 -> R.string.error_pair_again
                408, 504 -> R.string.error_timeout
                413 -> R.string.error_too_large_for_computer
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
