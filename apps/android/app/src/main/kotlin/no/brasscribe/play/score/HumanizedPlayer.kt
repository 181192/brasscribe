package no.brasscribe.play.score

import alphaTab.model.Score
import no.brasscribe.play.audio.RealisticSynth
import no.brasscribe.play.model.CoreBridge
import no.brasscribe.play.model.PlayedNote
import no.brasscribe.play.model.ScoreNote
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * The realistic tier with humanization: every pitched part's notes are humanized by the Rust core
 * (sounds/README.md "Humanization": per-player lag, timing and velocity, soloist leads, band follows
 * the ensemble deviation) and scheduled into sfizz sample-accurately, following alphaTab's playback
 * position. Percussion stays on alphaTab's kit, identical in both tiers.
 */
class HumanizedPlayer(private val core: CoreBridge) {
    private class Part(val channel: Int, val notes: List<PlayedNote>)

    private var parts: List<Part> = emptyList()
    private var tickSeconds: (Double) -> Double = { it / 960.0 * 0.5 }
    private val exec = Executors.newSingleThreadScheduledExecutor { Thread(it, "humanized-player").apply { isDaemon = true } }
    private var task: ScheduledFuture<*>? = null

    // Playback position from alphaTab: score seconds at a wall-clock instant, and the speed.
    @Volatile private var anchorScoreS = 0.0
    @Volatile private var anchorNanos = 0L
    @Volatile private var speed = 1.0
    @Volatile private var playing = false
    private var sentUntil = 0.0
    private val next = HashMap<Int, Int>()

    /** Humanizes [score]'s pitched tracks; [channels] and [audible] come from the score controller. */
    fun prepare(score: Score, channels: IntArray, percussion: List<Boolean>, compositionJson: String?): Int {
        tickSeconds = tempoMap(score)
        parts = (0 until score.tracks.length.toInt()).mapNotNull { i ->
            if (percussion[i]) return@mapNotNull null
            val track = score.tracks[i]
            val name = track.name.replace(' ', ' ').trim()
            val notes = ArrayList<ScoreNote>()
            for (staff in track.staves) for (bar in staff.bars) for (voice in bar.voices) for (beat in voice.beats) {
                for (n in beat.notes) {
                    if (n.isTieDestination) continue
                    var dur = beat.playbackDuration
                    var t = n.tieDestination
                    while (t != null) { dur += t.beat.playbackDuration; t = t.tieDestination }
                    val start = beat.absolutePlaybackStart
                    notes += ScoreNote(
                        tick = Math.round(start / 960.0 * 24), durTicks = Math.round(dur / 960.0 * 24),
                        startS = tickSeconds(start), endS = tickSeconds(start + dur), pitch = n.realValue.toInt(), velocity = 80,
                    )
                }
            }
            // One sfizz instrument per part plays the part's first desk (player 0 in mapping.json).
            val player = 0
            val played = core.humanize(notes.sortedWith(compareBy({ it.tick }, { it.pitch })), name, player, compositionJson) ?: return@mapNotNull null
            Part(channels[i], trimSamePitch(played).sortedBy { it.startS })
        }
        return parts.sumOf { it.notes.size }
    }

    fun secondsAt(tick: Double): Double = tickSeconds(tick)

    /** Humanized notes whose note-off would end the next note of the same pitch are trimmed (see [SamePitchTrim]). */
    private fun trimSamePitch(played: List<PlayedNote>): List<PlayedNote> {
        val trimmed = SamePitchTrim.trim(played.map { TimedNote(it.startS, it.endS, it.pitch) })
        return played.indices.mapNotNull { i -> trimmed[i]?.let { played[i].copy(endS = it.end) } }
    }

    /** alphaTab reported [scoreSeconds] now; a jump backwards (seek, loop) re-arms the schedule. */
    fun position(scoreSeconds: Double, playbackSpeed: Double) {
        val predicted = predictedScoreSeconds()
        anchorScoreS = scoreSeconds
        anchorNanos = System.nanoTime()
        speed = playbackSpeed
        if (scoreSeconds < predicted - 0.3 || scoreSeconds > predicted + 1.0) rewind(scoreSeconds)
    }

    private fun predictedScoreSeconds(): Double =
        if (!playing) anchorScoreS else anchorScoreS + (System.nanoTime() - anchorNanos) / 1e9 * speed

    private fun rewind(from: Double) {
        RealisticSynth.releaseAll()
        sentUntil = from
        parts.forEachIndexed { i, p -> next[i] = p.notes.indexOfFirst { it.startS >= from }.let { if (it < 0) p.notes.size else it } }
    }

    fun start(audible: (Int) -> Boolean) {
        playing = true
        sent = 0
        anchorNanos = System.nanoTime()
        rewind(anchorScoreS)
        task?.cancel(false)
        task = exec.scheduleAtFixedRate({ tick(audible) }, 0, 10, TimeUnit.MILLISECONDS)
    }

    /** Notes handed to sfizz since the last start (for the log). */
    @Volatile var sent = 0
        private set

    fun stop() {
        if (playing) android.util.Log.i("BrasscribePlay", "humanized playback: $sent notes sent to sfizz, ${RealisticSynth.activeVoices()} voices sounding at stop")
        playing = false
        task?.cancel(false)
        task = null
        // The user asked for silence: a short fade, no click and no release ringing on.
        RealisticSynth.fadeOut()
    }

    /** Sends every note starting in the next [LOOKAHEAD_S] of score time, with its delay in real time. */
    private fun tick(audible: (Int) -> Boolean) {
        val now = predictedScoreSeconds()
        val until = now + LOOKAHEAD_S * speed
        if (until <= sentUntil) return
        parts.forEachIndexed { i, p ->
            var k = next[i] ?: 0
            while (k < p.notes.size && p.notes[k].startS < until) {
                val n = p.notes[k]
                if (n.startS >= sentUntil - 1e-9 && audible(p.channel)) {
                    val on = ((n.startS - now) / speed).coerceAtLeast(0.0)
                    val off = ((n.endS - now) / speed).coerceAtLeast(on + MIN_NOTE_S)
                    RealisticSynth.noteAt(p.channel, n.pitch, n.velocity.coerceIn(1, 127), on)
                    RealisticSynth.noteAt(p.channel, n.pitch, 0, off)
                    sent++
                }
                k++
            }
            next[i] = k
        }
        sentUntil = until
    }

    fun release() {
        stop()
        exec.shutdownNow()
    }

    companion object {
        const val LOOKAHEAD_S = 0.25
        const val MIN_NOTE_S = 0.01

        /** Score ticks (960 per quarter) to seconds, following the master bars' tempo changes. */
        fun tempoMap(score: Score): (Double) -> Double {
            data class Seg(val tick: Double, val seconds: Double, val bpm: Double)
            val segs = ArrayList<Seg>()
            var bpm = score.tempo.takeIf { it > 0 } ?: 120.0
            var seconds = 0.0
            var lastTick = 0.0
            for (mb in score.masterBars) {
                val auto = mb.tempoAutomations.firstOrNull()
                val tick = mb.start + (auto?.ratioPosition ?: 0.0) * mb.calculateDuration()
                seconds += (tick - lastTick) / 960.0 * 60.0 / bpm
                lastTick = tick
                if (auto != null && auto.value > 0) bpm = auto.value
                segs += Seg(tick, seconds, bpm)
            }
            if (segs.isEmpty()) segs += Seg(0.0, 0.0, bpm)
            return { t ->
                val s = segs.lastOrNull { it.tick <= t } ?: segs.first()
                s.seconds + (t - s.tick) / 960.0 * 60.0 / s.bpm
            }
        }
    }
}
