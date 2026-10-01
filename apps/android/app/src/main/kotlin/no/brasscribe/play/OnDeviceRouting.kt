package no.brasscribe.play

import androidx.annotation.StringRes
import no.brasscribe.play.connection.ConnectionState
import no.brasscribe.play.engine.Profile

/**
 * Where a recording is written down, and the words for it (design/system.md §3, "A band draft on the
 * device"). A solo is made on the phone whenever it can be; a brass band goes to the computer when it is
 * there, and is otherwise made on the phone as a quick draft. The other band choices need the computer.
 */
object OnDeviceRouting {
    /** The computer is there: paired, and its connection is Connected or Reconnecting. */
    fun computerThere(state: ConnectionState): Boolean =
        state is ConnectionState.Connected || state is ConnectionState.Reconnecting

    /** The phone can make this score: its models are bundled and the recording is held in memory. */
    fun canRunOnDevice(profile: Profile?, hasPitchModel: Boolean, hasBandModels: Boolean, audioInMemory: Boolean): Boolean =
        audioInMemory && when (profile) {
            Profile.SOLO -> hasPitchModel
            Profile.BRASS_BAND -> hasBandModels
            else -> false
        }

    /** Where a new choice in What is this? goes by default. */
    fun defaultWhere(profile: Profile?, onDevice: Boolean, computerThere: Boolean): Where = when {
        !onDevice -> Where.COMPANION
        profile == Profile.BRASS_BAND && computerThere -> Where.COMPANION
        else -> Where.DEVICE
    }

    /** A score made on the phone for a band recording is a draft. */
    fun isDraft(profile: Profile?, where: Where): Boolean = profile == Profile.BRASS_BAND && where == Where.DEVICE

    /** The where-it-runs row's title in What is this?. */
    @StringRes
    fun whereTitle(profile: Profile?, where: Where): Int = when {
        where == Where.COMPANION -> R.string.where_companion
        isDraft(profile, where) -> R.string.where_device_draft
        else -> R.string.where_device
    }

    /** The row's subtitle when the phone makes it (the computer's subtitle names the computer). */
    @StringRes
    fun deviceSubtitle(profile: Profile?): Int =
        if (profile == Profile.BRASS_BAND) R.string.where_device_draft_desc else R.string.where_device_desc

    /**
     * The phone's card in the Change sheet: why it can't make this score, or what it makes. Null when the
     * recording is too long to hold in memory (the sheet then says how many minutes fit).
     */
    @StringRes
    fun deviceCard(profile: Profile?, hasPitchModel: Boolean, hasBandModels: Boolean, audioInMemory: Boolean): Int? = when {
        profile != Profile.SOLO && profile != Profile.BRASS_BAND -> R.string.where_device_solo_only
        !(if (profile == Profile.BRASS_BAND) hasBandModels else hasPitchModel) -> R.string.where_device_unavailable
        !audioInMemory -> null
        profile == Profile.BRASS_BAND -> R.string.where_device_draft_card
        else -> R.string.where_device_desc
    }

    /** Where it runs, on the transcribing screen. */
    @StringRes
    fun transcribingWhere(draft: Boolean): Int = if (draft) R.string.transcribe_where_device_draft else R.string.transcribe_where_device
}
