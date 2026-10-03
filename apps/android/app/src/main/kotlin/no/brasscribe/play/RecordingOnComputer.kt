package no.brasscribe.play

import no.brasscribe.play.engine.EngineException

/** The computer no longer holds the recording to write down again, and the phone has no copy of it to send. */
class RecordingGoneException : Exception("the computer no longer holds the recording, and the phone has no copy of it")

/**
 * A job on the computer, made from the recording the computer already holds when the product names one ([held]),
 * else from the recording [send] sends. The computer can have let go of what it held (its uploads were cleared, or
 * the song was deleted there): it answers 404, and then the phone's copy is sent when there is one ([canSend];
 * [resent] is told first), and [RecordingGoneException] says so when there is none.
 *
 * Returns the id of the recording on the computer, and what [create] made from it.
 */
internal suspend fun <T> jobFromRecording(
    held: suspend () -> String?,
    canSend: Boolean,
    send: suspend () -> String,
    resent: () -> Unit,
    create: suspend (audioId: String) -> T,
): Pair<String, T> {
    var lost = false
    val named = try { held() } catch (e: EngineException) { if (e.status != 404) throw e; lost = true; null }
    if (named != null) {
        try { return named to create(named) } catch (e: EngineException) { if (e.status != 404) throw e }
        lost = true
    }
    if (lost) {
        if (!canSend) throw RecordingGoneException()
        resent()
    }
    val sent = send()
    return sent to create(sent)
}
