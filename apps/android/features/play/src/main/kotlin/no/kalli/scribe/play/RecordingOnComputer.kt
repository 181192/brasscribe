package no.kalli.scribe.play

import no.kalli.scribe.engine.EngineException

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
suspend fun <T> jobFromRecording(
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

/**
 * A take the computer holds and would not write down yet: it answered that something is left to set up there
 * (`band_writer_not_set_up`). The recording itself arrived and stays on the computer, so when the player tries the
 * same take again it is named by its id and not sent a second time. One take is remembered, the last one refused,
 * for as long as the app is open; a take the computer has let go of since is sent again ([jobFromRecording]).
 */
class RefusedTake {
    private var take: Pair<String, String>? = null

    /** The id of [source] on the computer, when it is the take that was refused. */
    fun on(source: String): String? = take?.takeIf { it.first == source }?.second

    /** [create] for the recording [audioId] of [source]: a refusal for unfinished setup is remembered and thrown on. */
    suspend fun <T> noting(source: String, audioId: String, create: suspend (String) -> T): T =
        try {
            create(audioId).also { if (take?.first == source) take = null }
        } catch (e: EngineException) {
            if (e.code == "band_writer_not_set_up") take = source to audioId
            throw e
        }
}
