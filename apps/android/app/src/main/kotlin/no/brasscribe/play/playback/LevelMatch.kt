package no.brasscribe.play.playback

import no.brasscribe.play.audio.LoudnessMeter
import no.brasscribe.play.audio.PcmAudio
import no.brasscribe.play.audio.PlaybackLevels
import no.brasscribe.play.audio.leveled

/**
 * Brings a whole recording to the loudness the band plays the score at (sounds/playback-levels.json):
 * the recording is measured once (EBU R128 integrated, as dual mono, the way a mono clip plays from
 * both speakers), the score's band loudness is estimated once ([BandEstimate]), and every slice
 * plays with that one gain, so a quiet bar stays quieter than a loud one. Holds the last recording
 * and the last score only.
 */
class LevelMatch(private val targetOf: (String?) -> Double = BandEstimate::targetLufs) {
    private var audio: PcmAudio? = null
    private var measured = Double.NEGATIVE_INFINITY
    private var score: String? = null
    private var target = PlaybackLevels.RECORDING_FALLBACK_LUFS
    private var targetKnown = false

    /** The target for [musicXml] (the fallback for none), estimated the first time it is asked for. */
    @Synchronized
    fun targetLufs(musicXml: String?): Double {
        if (!targetKnown || score !== musicXml) {
            target = targetOf(musicXml)
            score = musicXml
            targetKnown = true
        }
        return target
    }

    /** The gain for [whole] against the score [musicXml], each measured the first time it is asked for. */
    @Synchronized
    fun gainDb(whole: PcmAudio, musicXml: String? = null): Double {
        if (audio !== whole) {
            measured = LoudnessMeter.dualMono(whole)
            audio = whole
        }
        return PlaybackLevels.recordingGainDb(measured, targetLufs(musicXml))
    }

    /** [slice] of [whole] at the whole recording's level-matching gain for the score [musicXml], limited. */
    fun slice(whole: PcmAudio, fromS: Double, toS: Double, musicXml: String? = null): PcmAudio =
        whole.slice(fromS, toS).leveled(gainDb(whole, musicXml))
}
