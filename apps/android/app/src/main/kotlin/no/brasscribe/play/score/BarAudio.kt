package no.brasscribe.play.score

import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.importer.ScoreLoader
import alphaTab.midi.AlphaSynthMidiFileHandler
import alphaTab.midi.MidiFile
import alphaTab.midi.MidiFileGenerator
import alphaTab.synth.AlphaSynthAudioExporter
import alphaTab.synth.AudioExportOptions
import alphaTab.synth.PlaybackRange
import android.content.Context
import no.brasscribe.play.audio.OutputStage
import no.brasscribe.play.audio.PcmAudio

/**
 * Bars of a score rendered on the phone, off the audio device: alphaTab's own synth with its General
 * MIDI SoundFont (the basic tier, 1.3 MB), through the shared output stage. "Listen to this bar" in
 * Review plays this once a note has been changed here, since the engine's render still has the old
 * note. Call it off the main thread: a band score's MusicXML takes a moment to parse.
 */
object BarAudio {
    const val SAMPLE_RATE = 44100
    private const val SOUNDFONT = "sonivox.sf2"

    @Volatile private var soundFont: ByteArray? = null

    private fun soundFont(context: Context): ByteArray =
        soundFont ?: context.assets.open(SOUNDFONT).use { it.readBytes() }.also { soundFont = it }

    /**
     * Bars [first]..[last] of [musicXml], mono at [SAMPLE_RATE]; null when there is no such bar. Bars
     * are numbered as Review numbers them: bar 1 is the first full bar, a pickup is bar 0.
     */
    fun render(context: Context, musicXml: String, first: Int, last: Int = first): PcmAudio? {
        val settings = alphaTab.Settings()
        val score = ScoreLoader.loadScoreFromBytes(Uint8Array(musicXml.toByteArray().asUByteArray()), settings)
        val bars = score.masterBars
        val count = bars.length.toInt()
        val pickup = count > 0 && bars[0].isAnacrusis
        // index + 1 of the bars in alphaTab's list
        val from = if (pickup) first + 1 else first
        val to = if (pickup) last + 1 else last
        if (from < 1 || from > count) return null
        // One channel per part (drums on 10), as the score screen plays it.
        val percussion = (0 until score.tracks.length.toInt()).map { i -> score.tracks[i].staves.any { it.isPercussion } }
        ChannelPlan.forPlayback(percussion).forEachIndexed { i, ch ->
            score.tracks[i].playbackInfo.primaryChannel = ch.toDouble()
            score.tracks[i].playbackInfo.secondaryChannel = ch.toDouble()
        }
        val midi = MidiFile()
        MidiFileGenerator(score, settings, AlphaSynthMidiFileHandler(midi, true)).generate()
        val end = bars[minOf(maxOf(from, to), count) - 1]
        val range = PlaybackRange().apply {
            startTick = bars[from - 1].start
            endTick = end.start + end.calculateDuration(false)
        }
        val options = AudioExportOptions().apply {
            sampleRate = SAMPLE_RATE.toDouble()
            metronomeVolume = 0.0
            playbackRange = range
        }
        val exporter = AlphaSynthAudioExporter(options)
        // The MIDI first: the SoundFont loads the samples of the programs it uses only.
        exporter.loadMidiFile(midi)
        exporter.loadSoundFont(Uint8Array(soundFont(context).asUByteArray()))
        exporter.setup()
        exporter.limitExport(range)
        var out = FloatArray(SAMPLE_RATE * 4)
        var n = 0
        while (true) {
            val chunk = exporter.render(500.0) ?: break
            val s = chunk.samples
            val frames = s.length.toInt() / 2
            if (frames == 0) break
            if (n + frames > out.size) out = out.copyOf(maxOf(out.size * 2, n + frames))
            // interleaved stereo to mono
            for (f in 0 until frames) out[n + f] = ((s[2 * f] + s[2 * f + 1]) * 0.5).toFloat()
            n += frames
        }
        if (n == 0) return null
        val mono = out.copyOf(n)
        OutputStage.process(mono, StagedSynthOutput.BAND_GAIN)
        return PcmAudio(mono, SAMPLE_RATE)
    }
}
