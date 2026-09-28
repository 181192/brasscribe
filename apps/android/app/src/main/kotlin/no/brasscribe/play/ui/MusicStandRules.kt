package no.brasscribe.play.ui

import android.accessibilityservice.AccessibilityServiceInfo
import android.view.KeyEvent

/** What a key does on the music stand (design/music-stand.md §7). */
enum class StandCommand { NEXT_PAGE, PREVIOUS_PAGE, FIRST_PAGE, LAST_PAGE, NEXT_BAR, PREVIOUS_BAR, PLAY_PAUSE, LEAVE, SHOW_CONTROLS }

/** The music stand's rules that do not need a screen: keys, auto-hide, layout and "your part". */
object MusicStandRules {
    /** The layer hides itself this long after the last touch, and only while the music plays. */
    const val HIDE_AFTER_MS = 4_000L
    /** Swipes that start this close to a screen edge belong to the system (back, the edge gestures). */
    const val EDGE_DP = 24
    /** Speed steppers: 5 % a step, 25 % to 150 %. */
    const val SPEED_STEP = 5

    /**
     * Arrows and Page Up/Down turn pages (what Bluetooth page turners send), Space plays, Home/End go
     * to the first and last page, Ctrl+↓/↑ move a bar, F and Esc leave, and Tab shows the layer (and
     * still moves focus). Anything else is left alone.
     */
    fun command(keyCode: Int, ctrl: Boolean = false, alt: Boolean = false, shift: Boolean = false): StandCommand? {
        if (alt) return null
        return when (keyCode) {
            KeyEvent.KEYCODE_DPAD_DOWN -> if (ctrl) StandCommand.NEXT_BAR else StandCommand.NEXT_PAGE
            KeyEvent.KEYCODE_DPAD_UP -> if (ctrl) StandCommand.PREVIOUS_BAR else StandCommand.PREVIOUS_PAGE
            KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_PAGE_DOWN -> if (ctrl) null else StandCommand.NEXT_PAGE
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_PAGE_UP -> if (ctrl) null else StandCommand.PREVIOUS_PAGE
            KeyEvent.KEYCODE_MOVE_HOME -> StandCommand.FIRST_PAGE
            KeyEvent.KEYCODE_MOVE_END -> StandCommand.LAST_PAGE
            KeyEvent.KEYCODE_SPACE -> if (ctrl || shift) null else StandCommand.PLAY_PAUSE
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> StandCommand.PLAY_PAUSE
            KeyEvent.KEYCODE_F -> if (ctrl || shift) null else StandCommand.LEAVE
            KeyEvent.KEYCODE_ESCAPE -> StandCommand.LEAVE
            KeyEvent.KEYCODE_TAB -> StandCommand.SHOW_CONTROLS
            else -> null
        }
    }

    /**
     * Only Tab and Space show the control layer and keep it up (§4.2). A Bluetooth page turner is a
     * keyboard that sends arrows or Page Up/Down, so those turn the page and leave the layer as it is,
     * and a keyboard being attached keeps nothing on screen by itself.
     */
    fun showsControls(keyCode: Int) = keyCode == KeyEvent.KEYCODE_TAB || keyCode == KeyEvent.KEYCODE_SPACE

    /** F on the score (with the score focused) opens the stand; a single-key shortcut, so no modifiers. */
    fun opensStand(keyCode: Int, ctrl: Boolean, alt: Boolean, shift: Boolean) =
        keyCode == KeyEvent.KEYCODE_F && !ctrl && !alt && !shift

    /**
     * Whether the control layer may hide by itself (§4.2): only while the music plays, and never with
     * a screen reader or switch access, with focus in the layer, after Tab or Space ([keyboard]; until
     * the next touch), or with Settings → Keep the stand controls visible.
     */
    fun autoHides(playing: Boolean, assistive: Boolean, focusInLayer: Boolean, keyboard: Boolean, keepVisible: Boolean) =
        playing && !assistive && !focusInLayer && !keyboard && !keepVisible

    /**
     * Assistive technology that keeps the controls on screen: touch exploration (TalkBack), any
     * service that speaks, or Switch Access. [services] are (service id, feedback type flags) of the
     * enabled services. Other services (UiAutomation in tests, password managers) do not count.
     */
    fun assistive(touchExploration: Boolean, services: List<Pair<String, Int>>): Boolean =
        touchExploration || services.any { (id, feedback) ->
            feedback and AccessibilityServiceInfo.FEEDBACK_SPOKEN != 0 || id.contains("switchaccess", ignoreCase = true)
        }

    /** Bars per system (the §3 sizing table): 3 on a phone held upright, 4 on its side and on tablets. */
    fun barsPerSystem(smallestWidthDp: Int, portrait: Boolean) = if (smallestWidthDp < 600 && portrait) 3 else 4

    /**
     * The width one bar needs at 100 % so its notes never collide (a phone held upright fits three).
     * The staff size stays the player's own; a narrow screen, or zoom,
     * takes fewer bars per system instead of squeezing them (§3: drop bars per system first).
     */
    const val BAR_DP = 120f

    /** Bars per system for a column [columnDp] wide at [scale]: the §3 number, or fewer, at least 1. */
    fun barsFitting(wanted: Int, columnDp: Float, scale: Float): Int =
        (columnDp / (BAR_DP * scale)).toInt().coerceIn(1, wanted)

    /** Phones only: Android 16 ignores an app's orientation on displays of 600 dp and wider (§4.4). */
    fun lockAvailable(smallestWidthDp: Int) = smallestWidthDp < 600

    /** A swipe turns a page when it is mostly sideways, long enough, and started clear of the edges. */
    fun swipe(startX: Float, dx: Float, dy: Float, width: Float, edgePx: Float, minPx: Float): Int {
        if (startX < edgePx || startX > width - edgePx) return 0
        if (kotlin.math.abs(dx) < minPx || kotlin.math.abs(dx) < 1.5f * kotlin.math.abs(dy)) return 0
        return if (dx < 0) 1 else -1
    }

    /**
     * "Your part" for the stand: the seat's part will come from Settings (my-instrument §2.3); until
     * then it is the lineup's lead. Null when there is no part to name (none of the known leads, as in
     * a pop score): the stand then says no "(you)".
     */
    fun yourPart(parts: List<String>, lineup: no.brasscribe.play.Lineup?): Int? {
        val clean = parts.map { it.replace('\u00A0', ' ').trim() }
        val wanted = listOfNotNull(lineup?.lead) + no.brasscribe.play.Lineup.LEADS
        return wanted.firstNotNullOfOrNull { lead -> clean.indexOfFirst { it.equals(lead, ignoreCase = true) }.takeIf { it >= 0 } }
    }

    /** "Only my part" is shown when there is a part to name and something else to hide. */
    fun offersOnlyMine(parts: List<String>, yours: Int?) = yours != null && parts.size > 1
}
