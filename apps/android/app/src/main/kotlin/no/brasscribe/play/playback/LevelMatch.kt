package no.brasscribe.play.playback

import no.brasscribe.play.audio.LoudnessMeter
import no.brasscribe.play.audio.PcmAudio
import no.brasscribe.play.audio.PlaybackLevels
import no.brasscribe.play.audio.leveled

/**
 * Brings a whole recording to the band's loudness (sounds/playback-levels.json): measured once
 * (EBU R128 integrated, as dual mono, the way a mono clip plays from both speakers), then every
 * slice of it plays with that one gain, so a quiet bar stays quieter than a loud one. Holds the
 * last recording only.
 */
class LevelMatch {
    private var audio: PcmAudio? = null
    private var gain = 0.0

    /** The gain for [whole], measured the first time it is asked for. */
    @Synchronized
    fun gainDb(whole: PcmAudio): Double {
        if (audio !== whole) {
            gain = PlaybackLevels.recordingGainDb(LoudnessMeter.dualMono(whole))
            audio = whole
        }
        return gain
    }

    /** [slice] of [whole] at the whole recording's level-matching gain, limited. */
    fun slice(whole: PcmAudio, fromS: Double, toS: Double): PcmAudio = whole.slice(fromS, toS).leveled(gainDb(whole))
}
