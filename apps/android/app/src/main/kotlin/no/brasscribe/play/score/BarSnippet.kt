package no.brasscribe.play.score

import alphaTab.AlphaTabView
import alphaTab.LayoutMode
import alphaTab.PlayerMode
import alphaTab.collections.DoubleList
import alphaTab.core.ecmaScript.Uint8Array
import alphaTab.importer.ScoreLoader
import alphaTab.model.Beat
import alphaTab.model.Score
import android.content.Context

/**
 * One bar of one part, engraved by alphaTab without a player: the review's note card shows the note
 * on a staff, with its key and the notes around it, the uncertainty marks at the score's size and an
 * ink ring round the note being checked.
 */
class BarSnippet(context: Context) {
    /** Called with the bottom of the rendered staff system, in dp. */
    var onStaffBottom: (Float) -> Unit = {}
    val view: AlphaTabView = AlphaTabView(context, null)
    private val selection = NotationOverlay.attach(view, under = true)
    private val overlay = NotationOverlay.attach(view, under = false)
    private var score: Score? = null
    private var loadedXml: String? = null

    init {
        view.settings.apply {
            display.layoutMode = LayoutMode.Horizontal
            display.scale = 0.9
            player.playerMode = PlayerMode.Disabled
            player.enableCursor = false
            player.enableUserInteraction = false
            core.includeNoteBounds = true
        }
        view.api.updateSettings()
        view.importantForAccessibility = android.view.View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        view.api.postRenderFinished.on {
            selection.refresh(); overlay.refresh()
            // Where the staff system ends: the view is cut off there, below the notes and the dynamics,
            // so alphaTab's "rendered by alphaTab" line under it stays out of sight (credited in About).
            val lookup = view.api.boundsLookup
            val systems = lookup?.staffSystems
            if (systems != null && systems.length > 0) {
                val b = systems[systems.length.toInt() - 1].realBounds
                onStaffBottom((b.y + b.h).toFloat())
            }
        }
    }

    fun setPalette(p: ScorePalette) {
        overlay.palette = p
        selection.palette = p
        view.setBackgroundColor(p.paper)
        view.settings.display.resources.apply {
            mainGlyphColor = p.ink.toColor(); secondaryGlyphColor = p.ink.toColor(); scoreInfoColor = p.ink.toColor()
            staffLineColor = p.staff.toColor(); barSeparatorColor = p.staff.toColor(); barNumberColor = p.staff.toColor()
        }
        view.api.updateSettings()
    }

    /** Shows [bar] (1-based) of the single-part [musicXml], ringing the note [offsetQuarters] into the bar. */
    fun show(musicXml: String, bar: Int, offsetQuarters: Double, barCount: Int = 1) {
        val s = if (musicXml == loadedXml) score else runCatching {
            ScoreLoader.loadScoreFromBytes(Uint8Array(musicXml.toByteArray().asUByteArray()), view.settings)
        }.getOrNull()?.also { loaded ->
            score = loaded; loadedXml = musicXml
            overlay.marks = collectMarks(loaded).first
            colourMarks(loaded, overlay.marks, overlay.palette)
        }
        s ?: return
        val staff = s.tracks[0].staves[0]
        val b = (bar - 1).coerceIn(0, staff.bars.length.toInt() - 1)
        view.settings.display.startBar = (b + 1).toDouble()
        view.settings.display.barCount = barCount.coerceIn(1, 2).toDouble()
        view.api.updateSettings()
        val voice = staff.bars[b].voices[0]
        val notes = (0 until voice.beats.length.toInt()).map { voice.beats[it] }.filter { !it.isRest }
        overlay.ring = notes.minByOrNull { kotlin.math.abs(it.playbackStart / 960.0 - offsetQuarters) }
        selection.ring = overlay.ring
        view.api.renderScore(s, DoubleList(0.0))
    }

    private fun Int.toColor() = alphaTab.model.Color(((this shr 16) and 0xFF).toDouble(), ((this shr 8) and 0xFF).toDouble(),
        (this and 0xFF).toDouble(), ((this ushr 24) and 0xFF).toDouble())
}

/** Beats with a "?" (false) or boxed "?" (true), blanking their small text; and the free-time bars. */
internal fun collectMarks(s: Score): Pair<Map<Beat, Boolean>, Set<Int>> {
    val found = HashMap<Beat, Boolean>()
    val adLib = HashSet<Int>()
    for (t in 0 until s.tracks.length.toInt()) for (st in s.tracks[t].staves) {
        var free = false
        for (bar in st.bars) {
            for (voice in bar.voices) for (beat in voice.beats) {
                when (beat.text?.trim()?.lowercase()) {
                    "?" -> { found[beat] = false; beat.text = MARK_SPACE }
                    BOXED_QUESTION -> { found[beat] = true; beat.text = MARK_SPACE }
                    "ad lib.", "ad lib", "ad. lib." -> free = true
                    "a tempo" -> free = false
                }
            }
            if (free) adLib += bar.index.toInt()
        }
    }
    return found to adLib
}

/** Colours each marked note (head, stem, flags, accidentals): uncertain or very uncertain. */
internal fun colourMarks(s: Score, marks: Map<Beat, Boolean>, p: ScorePalette?) {
    p ?: return
    fun c(v: Int) = alphaTab.model.Color(((v shr 16) and 0xFF).toDouble(), ((v shr 8) and 0xFF).toDouble(), (v and 0xFF).toDouble(), ((v ushr 24) and 0xFF).toDouble())
    val uncertain = c(p.uncertain)
    val very = c(p.veryUncertain)
    for ((beat, isVery) in marks) {
        val colour = if (isVery) very else uncertain
        beat.style = alphaTab.model.BeatStyle().apply {
            for (e in listOf(alphaTab.model.BeatSubElement.Effects, alphaTab.model.BeatSubElement.StandardNotationEffects,
                alphaTab.model.BeatSubElement.StandardNotationStem, alphaTab.model.BeatSubElement.StandardNotationFlags)) colors.set(e, colour)
        }
        for (n in beat.notes) n.style = alphaTab.model.NoteStyle().apply {
            for (e in listOf(alphaTab.model.NoteSubElement.StandardNotationNoteHead, alphaTab.model.NoteSubElement.StandardNotationAccidentals,
                alphaTab.model.NoteSubElement.StandardNotationEffects)) colors.set(e, colour)
        }
    }
}
