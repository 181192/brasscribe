package no.brasscribe.play.audio

import java.io.File

/**
 * The realistic playback tier: SFZ instruments (VSCO 2 CE, Iowa MIS, own recordings) played by sfizz
 * through an Oboe output stream, one instrument per MIDI channel.
 *
 * [available] is false when the app was built without a sfizz checkout; the app then keeps the
 * alphaTab synth (baseline tier) for everything.
 */
object RealisticSynth {
    val available: Boolean by lazy { runCatching { NativeAudio.sfizzAvailable() }.getOrDefault(false) }

    /** Opens the output at the shared output stage's gain (the limiter follows it, in C++). */
    fun start(sampleRate: Int = 48000): Boolean = available && NativeAudio.sfizzStart(sampleRate).also {
        if (it) NativeAudio.sfizzSetOutputGain(PlaybackLevels.factor(PlaybackLevels.SFIZZ_GAIN_DB))
    }
    fun stop() { if (available) NativeAudio.sfizzStop() }

    /** Loads an .sfz file; its samples are resolved relative to it. */
    fun load(channel: Int, sfz: File): Boolean = available && NativeAudio.sfizzLoadFile(channel, sfz.absolutePath)

    /** A sine instrument with no samples: for engine tests only; the app never plays it for a part. */
    fun loadTestTone(channel: Int): Boolean =
        available && NativeAudio.sfizzLoadString(channel, "<region> sample=*sine ampeg_attack=0.005 ampeg_release=0.2", "/virtual/test-tone.sfz")

    fun regions(channel: Int): Int = if (available) NativeAudio.sfizzRegions(channel) else 0
    fun noteOn(channel: Int, note: Int, velocity: Int) { if (available) NativeAudio.sfizzNoteOn(channel, note, velocity) }
    fun noteOff(channel: Int, note: Int) { if (available) NativeAudio.sfizzNoteOff(channel, note) }
    /** Note on (velocity > 0) or off (0) [delaySeconds] from now, placed sample-accurately in the output. */
    fun noteAt(channel: Int, note: Int, velocity: Int, delaySeconds: Double) {
        if (available) NativeAudio.sfizzNoteAt(channel, note, velocity, delaySeconds)
    }

    /** Hard cut of every voice: only when the tier is torn down. Stop uses [fadeOut], seek [releaseAll]. */
    fun allOff() { if (available) NativeAudio.sfizzAllOff() }

    /** Drops notes not yet played and releases every sounding note, so it fades with its release. */
    fun releaseAll() { if (available) NativeAudio.sfizzReleaseAll() }

    /** Stop: silence within [STOP_FADE_S] without a click, instead of letting the releases ring on. */
    fun fadeOut(seconds: Double = STOP_FADE_S) { if (available) NativeAudio.sfizzFadeOut(seconds) }

    const val STOP_FADE_S = 0.08
    fun setGain(channel: Int, gain: Float) { if (available) NativeAudio.sfizzSetGain(channel, gain) }
    /** The C++ limiter curve (cpp/output_stage.h), built with or without sfizz; for tests. */
    fun limit(x: Float): Float = NativeAudio.outputStageLimit(x)
    fun activeVoices(): Int = if (available) NativeAudio.sfizzActiveVoices() else 0

    /** Renders [frames] of interleaved stereo without the audio device (tests, audio export). */
    fun renderOffline(frames: Int): FloatArray {
        val out = FloatArray(frames * 2)
        if (available) NativeAudio.sfizzRenderOffline(out)
        return out
    }
}
