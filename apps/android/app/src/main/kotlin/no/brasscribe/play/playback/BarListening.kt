package no.brasscribe.play.playback

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import no.brasscribe.play.audio.PcmAudio

/** Plays clips one after the other, once. */
interface ClipOutput {
    /** Starts playing and returns how long it lasts, in milliseconds (0 when there was nothing to play). */
    fun play(clips: List<PcmAudio>): Long
    fun stop()
}

/**
 * "Listen to this bar" as a toggle (contract: listen to this bar): [toggle] starts the bar, or stops it
 * when that bar is already playing; the bar returns to "Listen" by itself when it ends. [playing] is the
 * bar playing now. [load] gathers the clips (the recording's bar, then the score's, which may need a
 * download); stopping during the load means nothing plays afterwards.
 */
class BarListening(
    private val scope: CoroutineScope,
    private val output: ClipOutput,
    private val onEvent: (Event) -> Unit = {},
) {
    sealed interface Event {
        data class Started(val bar: Int, val withRecording: Boolean) : Event
        data class Stopped(val bar: Int) : Event
        data class Ended(val bar: Int) : Event
        data object Unavailable : Event
    }

    /** What [load] found for a bar: the clips in order, and whether the first is the recording. */
    data class Clips(val clips: List<PcmAudio>, val withRecording: Boolean)

    private val _playing = MutableStateFlow<Int?>(null)
    val playing: StateFlow<Int?> = _playing.asStateFlow()
    private var job: Job? = null

    fun toggle(bar: Int, load: suspend () -> Clips) {
        if (_playing.value == bar) stop() else start(bar, load)
    }

    fun start(bar: Int, load: suspend () -> Clips) {
        cancel()
        // The button turns to Stop at once, so a second press during a download stops it.
        _playing.value = bar
        job = scope.launch {
            // A clip that cannot be loaded or played (no audio output, a render that failed) says so; it never
            // takes the app down.
            val c = try { load() } catch (e: kotlinx.coroutines.CancellationException) { throw e } catch (e: Exception) { Clips(emptyList(), false) }
            val ms = if (c.clips.isEmpty()) 0L else try { output.play(c.clips) } catch (e: Exception) {
                runCatching { output.stop() }
                0L
            }
            if (ms <= 0L) {
                _playing.value = null
                onEvent(Event.Unavailable)
                return@launch
            }
            onEvent(Event.Started(bar, c.withRecording))
            delay(ms)
            output.stop()
            _playing.value = null
            onEvent(Event.Ended(bar))
        }
    }

    /**
     * Stops whatever plays: the user pressed Stop ([announce]d), or left the place (not announced: the new
     * place speaks). Silent when nothing plays.
     */
    fun stop(announce: Boolean = true) {
        val bar = _playing.value
        cancel()
        if (bar != null && announce) onEvent(Event.Stopped(bar))
    }

    private fun cancel() {
        job?.cancel()
        job = null
        output.stop()
        _playing.value = null
    }
}
