package no.brasscribe.play.score

import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.importer.ScoreLoader
import alphaTab.midi.AlphaSynthMidiFileHandler
import alphaTab.midi.ControlChangeEvent
import alphaTab.midi.ControllerType
import alphaTab.midi.MidiFile
import alphaTab.midi.MidiFileGenerator
import alphaTab.midi.NoteOffEvent
import alphaTab.midi.NoteOnEvent
import alphaTab.midi.ProgramChangeEvent
import alphaTab.synth.AlphaSynthAudioExporter
import alphaTab.synth.AudioExportOptions
import alphaTab.synth.PlaybackRange
import android.content.Context
import no.brasscribe.play.audio.OutputStage
import no.brasscribe.play.audio.PcmAudio
import java.io.File

/**
 * Bars of a score rendered on the phone, off the audio device, as the score screen plays them: the
 * band SoundFont with each part's preset and balance ([BandPlan]), alphaTab's synth, the shared
 * output stage. Without a band SoundFont (a build without the sound pack) alphaTab's General MIDI
 * one plays, as the score screen's basic tier does. "Listen to this bar" in Review plays this once a
 * note has been changed here, since the engine's render still has the old note. Call it off the
 * main thread: a band score's MusicXML takes a moment to parse.
 *
 * The band SoundFont is not held: each render reads the samples its bars play from the file
 * ([SoundFontSubset]; 10-20 MB for a few bars of a full band) and lets them go with the exporter.
 */
object BarAudio {
    const val SAMPLE_RATE = 44100
    private const val GM_SOUNDFONT = "sonivox.sf2"

    @Volatile private var soundMap: BandSoundMap? = null

    private fun soundMap(context: Context): BandSoundMap? = soundMap ?: runCatching {
        BandSoundMap.parse(context.assets.open("sounds/mapping.json").use { String(it.readBytes()) })
    }.getOrNull()?.also { soundMap = it }

    /**
     * Bars [first]..[last] of [musicXml], mono at [SAMPLE_RATE]; null when there is no such bar. Bars
     * are numbered as Review numbers them: bar 1 is the first full bar, a pickup is bar 0.
     * [bandSoundFont] is the band SoundFont to play (by default the one the score screen plays), or
     * null for General MIDI.
     */
    fun render(
        context: Context, musicXml: String, first: Int, last: Int = first,
        bandSoundFont: File? = BandSoundFontFile.resolve(context),
    ): PcmAudio? = render(musicXml, first, last, soundMap(context), bandSoundFont) {
        context.assets.open(GM_SOUNDFONT).use { it.readBytes() }
    }

    /** [render] without a Context; [whole] loads the whole band SoundFont rather than the bars' subset (for the test that both sound the same). */
    internal fun render(
        musicXml: String, first: Int, last: Int, soundMap: BandSoundMap?, bandSoundFont: File?,
        whole: Boolean = false, generalMidi: () -> ByteArray,
    ): PcmAudio? {
        val settings = alphaTab.Settings()
        val score = ScoreLoader.loadScoreFromBytes(Uint8Array(musicXml.toByteArray().asUByteArray()), settings)
        val bars = score.masterBars
        val count = bars.length.toInt()
        val pickup = count > 0 && bars[0].isAnacrusis
        // index + 1 of the bars in alphaTab's list
        val from = if (pickup) first + 1 else first
        val to = if (pickup) last + 1 else last
        if (from < 1 || from > count) return null
        val plan = BandPlan.apply(score, BandPlan.partNames(score), soundMap, bandSoundFont != null)
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
        val soundFont = when {
            bandSoundFont == null -> generalMidi()
            whole -> bandSoundFont.readBytes()
            else -> uses(midi, range.startTick, range.endTick).let { (uses, programs) -> SoundFontSubset.build(bandSoundFont, uses, programs) }
        }
        // In alphaTab's own export order: MIDI, channel volumes, SoundFont (its samples are decoded
        // for the programs the MIDI uses), range, setup.
        val exporter = AlphaSynthAudioExporter(options)
        exporter.loadMidiFile(midi)
        // Each part's balance, as the score screen's changeTrackVolume sets it.
        plan.channels.forEachIndexed { i, ch -> exporter.channelSetMixVolume(ch.toDouble(), plan.gains[i]) }
        exporter.loadSoundFont(Uint8Array(soundFont.asUByteArray()))
        exporter.limitExport(range)
        exporter.setup()
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

    /**
     * The keys each channel's preset plays that can sound in [startTick]..[endTick] (notes that start
     * up to two beats before it, for their release), with the preset as alphaTab's synth selects it;
     * and every program the MIDI selects.
     */
    internal fun uses(midi: MidiFile, startTick: Double, endTick: Double): Pair<Set<SoundFontSubset.Use>, Set<Int>> {
        // the MIDI's events are shifted by tickShift (grace notes at the start)
        val from = startTick + midi.tickShift - 2 * midi.division
        val until = endTick + midi.tickShift
        // one channel per part: an 18-part band goes past channel 16
        val bank = IntArray(256)
        val program = IntArray(256)
        val presetBank = IntArray(256)
        val programs = HashSet<Int>()
        val open = HashMap<Int, SoundFontSubset.Use>() // channel shl 8 or key
        val uses = HashSet<SoundFontSubset.Use>()
        for (e in midi.events) {
            when (e) {
                is ControlChangeEvent -> {
                    val ch = e.channel.toInt().takeIf { it in bank.indices } ?: continue
                    // as alphaTab's synth reads bank select
                    when (e.controller) {
                        ControllerType.BankSelectCoarse -> bank[ch] = 0x8000 or e.value.toInt()
                        ControllerType.BankSelectFine -> bank[ch] =
                            (if ((bank[ch] and 0x8000) != 0) (bank[ch] and 127) shl 7 else 0) or e.value.toInt()
                        else -> {}
                    }
                }
                is ProgramChangeEvent -> {
                    val ch = e.channel.toInt().takeIf { it in program.indices } ?: continue
                    // the synth picks the preset here, with the bank selected so far
                    program[ch] = e.program.toInt()
                    presetBank[ch] = bank[ch] and 2047
                    programs += program[ch]
                }
                is NoteOnEvent -> {
                    val ch = e.channel.toInt().takeIf { it in bank.indices } ?: continue
                    if (e.tick > until) continue
                    val use = SoundFontSubset.Use(presetBank[ch], program[ch], e.noteKey.toInt(), ch == ChannelPlan.DRUMS)
                    if (e.tick >= from) uses += use else open[(ch shl 8) or use.key] = use
                }
                is NoteOffEvent -> {
                    val use = open.remove((e.channel.toInt() shl 8) or e.noteKey.toInt()) ?: continue
                    if (e.tick >= from) uses += use
                }
            }
        }
        // notes still sounding when the MIDI ends
        uses += open.values
        return uses to programs
    }
}
