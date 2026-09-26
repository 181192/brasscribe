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

    fun start(sampleRate: Int = 48000): Boolean = available && NativeAudio.sfizzStart(sampleRate)
    fun stop() { if (available) NativeAudio.sfizzStop() }

    /** Loads an .sfz file; its samples are resolved relative to it. */
    fun load(channel: Int, sfz: File): Boolean = available && NativeAudio.sfizzLoadFile(channel, sfz.absolutePath)

    /** A sine instrument with no samples: proves the engine runs when no sound pack is installed. */
    fun loadTestTone(channel: Int): Boolean =
        available && NativeAudio.sfizzLoadString(channel, "<region> sample=*sine ampeg_attack=0.005 ampeg_release=0.2", "/virtual/test-tone.sfz")

    fun regions(channel: Int): Int = if (available) NativeAudio.sfizzRegions(channel) else 0
    fun noteOn(channel: Int, note: Int, velocity: Int) { if (available) NativeAudio.sfizzNoteOn(channel, note, velocity) }
    fun noteOff(channel: Int, note: Int) { if (available) NativeAudio.sfizzNoteOff(channel, note) }
    /** Note on (velocity > 0) or off (0) [delaySeconds] from now, placed sample-accurately in the output. */
    fun noteAt(channel: Int, note: Int, velocity: Int, delaySeconds: Double) {
        if (available) NativeAudio.sfizzNoteAt(channel, note, velocity, delaySeconds)
    }

    fun allOff() { if (available) NativeAudio.sfizzAllOff() }
    fun setGain(channel: Int, gain: Float) { if (available) NativeAudio.sfizzSetGain(channel, gain) }
    fun activeVoices(): Int = if (available) NativeAudio.sfizzActiveVoices() else 0

    /** Renders [frames] of interleaved stereo without the audio device (tests, audio export). */
    fun renderOffline(frames: Int): FloatArray {
        val out = FloatArray(frames * 2)
        if (available) NativeAudio.sfizzRenderOffline(out)
        return out
    }
}
