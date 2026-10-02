package no.brasscribe.play.fret

import alphaTab.AlphaTabView
import alphaTab.LayoutMode
import alphaTab.NotationElement
import alphaTab.PlayerMode
import alphaTab.ScrollMode
import alphaTab.TabRhythmMode
import alphaTab.collections.DoubleList
import alphaTab.model.Beat
import alphaTab.model.Font
import alphaTab.model.FontStyle
import alphaTab.model.FontWeight
import alphaTab.model.Note
import alphaTab.model.NoteStyle
import alphaTab.model.NoteSubElement
import alphaTab.model.Score
import alphaTab.alphaSkia.AlphaSkiaTypeface
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.view.View
import android.widget.RelativeLayout
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import no.brasscribe.play.PlayViewModel
import no.brasscribe.play.engine.TabLayout
import no.brasscribe.play.score.AlphaTabMusicXml

/** The tab's colours (Fretscribe's tokens, ARGB): ink numerals on paper, the lines in the string colour. */
data class TabPalette(
    val paper: Int, val ink: Int, val string: Int, val uncertain: Int,
    /** The wash behind a doubtful numeral; null in high contrast, which has shapes only. */
    val uncertainTint: Int?,
    /** The line where the recording is. */
    val cursor: Int,
    /** The wash behind the beat the recording is at; null in high contrast. */
    val cursorTint: Int?,
    /** The brackets at both ends of the bars being repeated. */
    val repeat: Int,
    /** The band behind the bars being repeated; null in high contrast. */
    val repeatBand: Int?,
)

/** Where the cursor stands for one beat: the beat's start in its bar ([TabIndex.TICKS]), and its column's left edge and width in the page's pixels. */
data class CursorStop(val tick: Int, val left: Float, val width: Float)

/** One bar of the page, in the page's pixels: its box, the top line of its first staff, and the cursor's stops in it, in time order. */
data class BarBox(val bar: Int, val left: Float, val right: Float, val top: Float, val bottom: Float, val stops: List<CursorStop>, val staffTop: Float = top) {
    /** The stop of the beat that is sounding at [tick] of the bar: the last that starts at or before it. */
    fun stopAt(tick: Int): CursorStop? = stops.lastOrNull { it.tick <= tick } ?: stops.firstOrNull()
}

/** Where a mark is drawn, in the page's pixels: the middle of its column, the mark itself, how far down the column's numerals go, and how wide the mark and the numerals are. */
data class MarkBox(val column: Int, val centre: Float, val top: Float, val bottom: Float, val columnBottom: Float, val width: Float)

/** One line of the page: where it is, in the page's pixels, and its bars (counted from 0). */
data class TabLine(val top: Int, val bottom: Int, val firstBar: Int, val lastBar: Int)

/**
 * One engraving of the tab, as alphaTab laid it out: the height of its page in pixels (the height alphaTab
 * scrolls, so a scroll over it ends where alphaTab's does), its lines, and where the marks are.
 */
data class TabEngraving(val height: Int, val lines: List<TabLine>, val boxes: List<MarkBox>, val bars: List<BarBox> = emptyList()) {
    private val byBar = bars.associateBy { it.bar }

    /** The box of [bar] (counted from 0). */
    fun bar(bar: Int): BarBox? = byBar[bar]

    /** The line [bar] is on. */
    fun lineOf(bar: Int): TabLine? = lines.firstOrNull { bar in it.firstBar..it.lastBar }

    val barsPerLine: List<Int> get() = lines.map { it.lastBar - it.firstBar + 1 }

    /** The first bar of the line that [y] pixels down the page is in: the last line that starts at or above it. */
    fun barAt(y: Int): Int? = (lines.lastOrNull { it.top <= y + 2 } ?: lines.firstOrNull())?.firstBar

    /** Where the line with [bar] starts. */
    fun topOfBar(bar: Int): Int? = lines.firstOrNull { bar in it.firstBar..it.lastBar }?.top
}

/**
 * Fret numbers in Fretscribe Tab. alphaTab draws with alphaSkia on Android, which finds a face by its
 * family name among the system's fonts and the faces registered with it: [AlphaSkiaTypeface.register]
 * (alphaSkia's own API) adds one from its bytes. alphaTab's wrapper around it (SkiaCanvas.registerFont)
 * is not public in the Android build, and does no more than this.
 */
object TabFont {
    /** The face in the app's assets (design/fretscribe/brand/fonts). */
    const val ASSET = "fonts/FretscribeTab-Regular.ttf"

    private var face: AlphaSkiaTypeface? = null
    private var tried = false

    /** The face, registered once and kept; null when the build does not carry it or Skia cannot read it. */
    @Synchronized
    private fun registered(context: Context): AlphaSkiaTypeface? {
        if (!tried) {
            tried = true
            face = runCatching {
                AlphaSkiaTypeface.register(context.applicationContext.assets.open(ASSET).use { it.readBytes() })
            }.onFailure { android.util.Log.w(PlayViewModel.TAG, "Fretscribe Tab could not be registered; fret numbers use the system's face", it) }.getOrNull()
        }
        return face
    }

    /** alphaTab's font for the face at [size], by the family name and weight the face has; null without the face. */
    fun at(context: Context, size: Double): Font? = registered(context)?.let { f ->
        Font(f.familyName, size, if (f.isItalic) FontStyle.Italic else FontStyle.Plain, if (f.weight > 400) FontWeight.Bold else FontWeight.Regular)
    }
}

/**
 * The tab, engraved by alphaTab from tab.musicxml without a player: a page as wide as the view, scrolled
 * up and down, with more lines of fewer bars the larger it is. The "?" and the boxed "!" are drawn over it
 * from the tab's data ([TabMarks]).
 *
 * A view has one [scale] and one [palette], and engraves its page once. Another size or other colours are
 * another view: alphaTab lays its page out in steps and keeps track of the lines in view by the scroll
 * steps it sees, and a page engraved again under a view that is scrolled, or while the last engraving is
 * still being laid out, can come out half laid out or blank.
 */
class TabView(
    context: Context,
    /** alphaTab's scale ([TabSize]). */
    val scale: Double,
    internal val palette: TabPalette,
    /** False sets the fret numbers in the system's monospace face: what a build without Fretscribe Tab shows. */
    ownFace: Boolean = true,
) {
    val view: AlphaTabView = AlphaTabView(context, null)
    // Under the engraving: the band of a repeat, on it the wash of the beat being played, on that the doubtful numerals' wash
    // (washes never stack: each covers the one under it). Over it: the marks and the repeat's brackets, then the cursor's line.
    private val band = TabOverlay.attach(this, TabLayer.BAND)
    private val beatWash = TabOverlay.attach(this, TabLayer.BEAT)
    private val washes = TabOverlay.attach(this, TabLayer.WASH)
    private val glyphs = TabOverlay.attach(this, TabLayer.MARKS)
    private val cursorLine = TabOverlay.attach(this, TabLayer.CURSOR)
    private val overlays = listOf(band, beatWash, washes, glyphs, cursorLine)
    private val density = context.resources.displayMetrics.density
    private var score: Score? = null
    private var columns: List<TabColumn> = emptyList()
    /** The staff the cursor stops on its beats: the one the marks stand on. */
    private var cursorStaff = 0

    /** The bar and the stop the cursor stands at; null when it is not shown. */
    internal var cursor: Pair<BarBox, CursorStop>? = null
        private set

    /** The bars being repeated (counted from 0), with brackets at both ends and a band behind them. */
    var repeat: IntRange? = null
        set(value) {
            if (field == value) return
            field = value
            band.invalidate(); glyphs.invalidate()
        }

    /**
     * Stands the cursor at the beat that sounds at [place]; null takes it away. It moves from beat to beat and
     * is still between them, so nothing is drawn while a note sounds. True when it moved.
     */
    fun cursorAt(place: TabPlace?): Boolean {
        val bar = place?.let { _engraving.value?.bar(it.bar) }
        val to = bar?.let { b -> b.stopAt(place.tick)?.let { b to it } }
        if (to == cursor) return false
        cursor = to
        beatWash.invalidate(); cursorLine.invalidate()
        return true
    }

    /** The beat each column's mark stands over, and the notes of it that are in doubt. */
    internal var placed: List<Placed> = emptyList()
        private set

    internal class Placed(val column: Int, val kind: MarkKind, val beat: Beat, val doubtful: List<Note>)

    private val _engraving = MutableStateFlow<TabEngraving?>(null)
    /** The engraving, once alphaTab has laid its page out; null until then. */
    val engraving: StateFlow<TabEngraving?> = _engraving

    /** alphaTab's own space under a band of text above a staff. */
    private val bandGap = view.settings.display.effectBandPaddingBottom

    /** Engravings alphaTab has finished. */
    @Volatile var engravings: Int = 0
        private set

    /** Marked notes the engraving has no beat for: a mismatch between the page and what alphaTab read from it. */
    var unmatched: Int = 0
        private set

    /** Whether the fret numbers are set in Fretscribe Tab. */
    val tabFont: Boolean

    init {
        // alphaTab's environment (and alphaSkia with it) is set up by the view above.
        val face = if (ownFace) TabFont.at(context, NUMERAL_UNITS) else null
        tabFont = face != null
        view.settings.apply {
            display.layoutMode = LayoutMode.Page
            display.scale = scale
            // Bars as wide as their notes need, so a line holds as many as fit; the last line is not pulled out to the margin.
            display.stretchForce = STRETCH
            display.justifyLastSystem = false
            player.playerMode = PlayerMode.Disabled
            player.enableCursor = false
            player.enableUserInteraction = false
            // alphaTab scrolls its page to the bar at its cursor after every engraving; here the screen's scroll says where the page is.
            player.scrollMode = ScrollMode.Off
            core.includeNoteBounds = true
            notation.rhythmMode = TabRhythmMode.ShowWithBars
            // The screen's header has the title, the tuning and the tempo; the page keeps the music.
            for (e in listOf(NotationElement.ScoreTitle, NotationElement.ScoreSubTitle, NotationElement.ScoreArtist, NotationElement.ScoreAlbum,
                NotationElement.ScoreWords, NotationElement.ScoreMusic, NotationElement.ScoreWordsAndMusic, NotationElement.ScoreCopyright,
                NotationElement.TrackNames, NotationElement.GuitarTuning, NotationElement.EffectTempo)) notation.elements.set(e, false)
            display.resources.apply {
                tablatureFont = face ?: Font("monospace", NUMERAL_UNITS, FontStyle.Plain, FontWeight.Bold)
                mainGlyphColor = palette.ink.toColor(); secondaryGlyphColor = palette.ink.toColor(); scoreInfoColor = palette.ink.toColor()
                staffLineColor = palette.string.toColor(); barSeparatorColor = palette.string.toColor(); barNumberColor = palette.string.toColor()
                // A marked beat gets blank text, and alphaTab keeps a band above the staff for a line's text: with the text as
                // tall as a mark, the band is the room the marks need, on the lines that have marks and on no others.
                elementFonts.get(NotationElement.EffectText)?.let { text ->
                    elementFonts.set(NotationElement.EffectText, Font(text.families[0], TabTokens.MARK_LINE_SPACES * engravingSettings.tabLineSpacing, text.style, text.weight))
                }
            }
        }
        view.api.updateSettings()
        // The paper is the screen's; the engraving is drawn on a clear ground so the wash under a numeral shows.
        view.setBackgroundColor(0)
        // The marks are elements of the screen, over this view; the engraving itself is described there once.
        view.importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        view.descendantFocusability = android.view.ViewGroup.FOCUS_BLOCK_DESCENDANTS
        // The page is measured once alphaTab has laid it out: its height is the height alphaTab scrolls.
        for (id in listOf(net.alphatab.R.id.renderWrapper, net.alphatab.R.id.renderSurface)) {
            view.findViewById<View>(id)?.addOnLayoutChangeListener { _, _, top, _, bottom, _, oldTop, _, oldBottom ->
                if (bottom - top != oldBottom - oldTop) view.post { publish() }
            }
        }
        view.addOnLayoutChangeListener { _, left, _, right, _, _, _, _, _ ->
            if (right > left) waiting?.let { engrave ->
                waiting = null
                view.post { if (!released) engrave() }
            }
        }
        view.api.postRenderFinished.on {
            hideCredit()
            overlays.forEach { it.refresh() }
            engravings++
            view.post { publish() }
        }
    }

    /** One tab line space in view pixels. */
    internal val lineSpace: Float
        get() = (view.settings.display.resources.engravingSettings.tabLineSpacing.takeIf { it > 0 } ?: 10.0).let { (it * scale * density).toFloat() }

    /**
     * Shows [musicXml] with [marks]. alphaTab gets the page without its "?" and "!" words and without the
     * doubt colour: the marks and the tint come from the data, in this theme's colours.
     */
    fun show(musicXml: String, layout: TabLayout?, index: TabIndex, marks: TabMarks) {
        val s = runCatching { AlphaTabMusicXml.parse(TabIndex.forRenderer(musicXml, index.header).toByteArray(), view.settings) }.getOrNull() ?: return
        score = s
        musicInTheFirstVoice(s)
        val staves = s.tracks[0].staves
        for (i in 0 until staves.length.toInt()) {
            val tab = index.tabStaff == i && layout != TabLayout.NOTATION
            staves[i].showTablature = tab
            staves[i].showStandardNotation = !tab
        }
        // With the notation staff above, the rhythm is read there; under the tab it would be drawn twice.
        val pair = staves.length.toInt() > 1 && layout != TabLayout.TAB
        val rhythm = if (pair) TabRhythmMode.Hidden else TabRhythmMode.ShowWithBars
        // The marks stand above the bar numbers, in the band alphaTab keeps for text: the band is lifted by a bar number,
        // and between two staves by a line space more, clear of the stems that come down from the notation.
        val res = view.settings.display.resources
        val band = bandGap + res.barNumberFont.size + if (pair) res.engravingSettings.tabLineSpacing else 0.0
        if (view.settings.notation.rhythmMode != rhythm || view.settings.display.effectBandPaddingBottom != band) {
            view.settings.notation.rhythmMode = rhythm
            view.settings.display.effectBandPaddingBottom = band
            view.api.updateSettings()
        }
        columns = marks.columns
        cursorStaff = index.markStaff
        place(s)
        tint(s)
        // alphaTab skips an engraving asked of a view that has no width yet, and does not always make it up when the
        // view gets one (a view made as the phone is turned): the page is engraved once the view has been laid out.
        val engrave = { view.api.renderScore(s, DoubleList(0.0)) }
        if (view.width > 0) engrave() else waiting = engrave
    }

    /**
     * alphaTab 1.8.4 reads the second staff of a pair into its fifth voice (MusicXML numbers a second staff's
     * voices from 5) and leaves the first four empty; it draws a rest for an empty first voice, over the
     * numbers. The voice with the bar's music is made the first of its bar.
     */
    private fun musicInTheFirstVoice(s: Score) {
        for (track in s.tracks) for (staff in track.staves) for (bar in staff.bars) {
            val voices = bar.voices
            val n = voices.length.toInt()
            if (n < 2 || !voices[0].isEmpty) continue
            val k = (1 until n).firstOrNull { !voices[it].isEmpty } ?: continue
            val empty = voices[0]
            val music = voices[k]
            voices.set(0, music)
            voices.set(k, empty)
            music.index = 0.0
            empty.index = k.toDouble()
        }
    }

    /** Finds each column's beat in alphaTab's score: the same staff and measure, and the same start. */
    private fun place(s: Score) {
        val staves = s.tracks[0].staves
        val found = ArrayList<Placed>()
        var missing = 0
        columns.forEachIndexed { i, column ->
            val staff = if (column.staff < staves.length.toInt()) staves[column.staff] else null
            val bar = staff?.bars?.let { if (column.bar < it.length.toInt()) it[column.bar] else null }
            val strings = staff?.tuning?.length?.toInt() ?: 0
            val wanted = column.notes.filter { it.kind == MarkKind.DOUBT }
            // The beats that start there, in any voice; the one that has the column's notes is its beat.
            var at: Beat? = null
            var doubtful: List<Note> = emptyList()
            if (bar != null) for (voice in bar.voices) for (b in voice.beats) {
                if (b.isEmpty || Math.abs(b.playbackStart - column.onset) >= 1.0) continue
                val hits = wanted.mapNotNull { n -> var hit: Note? = null; for (note in b.notes) if (hit == null && note.matches(n, strings)) hit = note; hit }
                if (at == null || hits.size > doubtful.size) { at = b; doubtful = hits }
            }
            if (at == null) { missing += column.notes.size; return@forEachIndexed }
            missing += wanted.size - doubtful.size
            // alphaTab keeps a band above the staff for a beat with text: the mark is drawn there, over blank text.
            if (at.text.isNullOrBlank()) at.text = MARK_SPACE
            found += Placed(i, column.kind, at, doubtful)
        }
        placed = found
        unmatched = missing
    }

    /** alphaTab counts strings from the lowest; the page and the data count from the highest. A notation staff has only the pitch. */
    private fun Note.matches(n: MarkedNote, strings: Int): Boolean =
        if (n.string != null && n.fret != null && isStringed) fret.toInt() == n.fret && strings - string.toInt() + 1 == n.string
        else n.step == null || realValue.toInt() % 12 == (STEPS.getValue(n.step) + n.alter + 12) % 12

    /** The doubtful numerals (or note heads) in the doubt colour; every other note in ink. */
    private fun tint(s: Score) {
        val colour = palette.uncertain.toColor()
        for (track in s.tracks) for (staff in track.staves) for (bar in staff.bars) for (voice in bar.voices) for (beat in voice.beats) for (n in beat.notes) n.style = null
        for (mark in placed) for (n in mark.doubtful) n.style = NoteStyle().apply {
            for (e in listOf(NoteSubElement.GuitarTabFretNumber, NoteSubElement.StandardNotationNoteHead, NoteSubElement.StandardNotationAccidentals)) colors.set(e, colour)
        }
    }

    /** alphaTab signs its engraving under the last line; the page ends with the music (alphaTab is credited in About). */
    private fun hideCredit() {
        val surface = view.findViewById<View>(net.alphatab.R.id.renderSurface) ?: return
        val bottom = musicBottom() ?: run { surface.clipBounds = null; return }
        surface.clipBounds = android.graphics.Rect(0, 0, Int.MAX_VALUE / 2, bottom)
    }

    private fun musicBottom(): Int? {
        val systems = view.api.boundsLookup?.staffSystems ?: return null
        if (systems.length.toInt() == 0) return null
        val b = systems[systems.length.toInt() - 1].visualBounds
        return Math.ceil((b.y + b.h) * density).toInt()
    }

    /** Where each mark goes in this engraving: above its column's numerals and above the staff. */
    internal fun boxes(): List<MarkBox> {
        val lookup = view.api.boundsLookup ?: return emptyList()
        val ls = lineSpace
        val height = TabTokens.MARK_LINE_SPACES * ls
        val barNumber = (view.settings.display.resources.barNumberFont.size * scale * density).toFloat()
        return placed.mapNotNull { mark ->
            val all = lookup.findBeats(mark.beat) ?: return@mapNotNull null
            if (all.length.toInt() == 0) return@mapNotNull null
            val bb = all[0]
            val staff = bb.barBounds.visualBounds
            var top = minOf(staff.y, bb.visualBounds.y)
            var columnBottom = staff.y + staff.h
            var centre = bb.onNotesX.takeIf { it > 0 } ?: (bb.visualBounds.x + bb.visualBounds.w / 2)
            var wide = 0.0
            val notes = bb.notes
            if (notes != null) for (j in 0 until notes.length.toInt()) {
                val h = notes[j].noteHeadBounds
                top = minOf(top, h.y)
                columnBottom = maxOf(columnBottom, h.y + h.h)
                if (j == 0) centre = h.x + h.w / 2
                wide = maxOf(wide, h.w)
            }
            // Above the numerals, and above the bar's number over the staff's first line.
            val bottom = minOf((top * density).toFloat() - 0.45f * ls, (staff.y * density).toFloat() - barNumber - 0.3f * ls)
            MarkBox(mark.column, (centre * density).toFloat(), bottom - height, bottom, (columnBottom * density).toFloat(),
                maxOf(height, (wide * density).toFloat() + 0.4f * ls))
        }
    }

    /** The engraving to make once the view has a width. */
    private var waiting: (() -> Unit)? = null

    private var tries = 0
    private var looking = false

    /**
     * Puts the page where the screen's scroll says, and tells the screen of the engraving. alphaTab says an
     * engraving is finished before its page has been laid out to it: until the page is as long as its music,
     * this looks again a twentieth of a second later, for five seconds after the last layout at most.
     */
    private fun publish() {
        tries = 0
        if (!looking) look()
    }

    private fun look() {
        looking = false
        val page = pageScroll?.getChildAt(0)?.height ?: 0
        val music = musicBottom()
        if (music != null && page < music) {
            if (tries++ < 100) {
                looking = true
                view.postDelayed({ if (!released) look() }, 50)
            }
            return
        }
        val engraving = measure() ?: return
        if (pageScroll?.scrollY != pageTop) pageScroll?.scrollTo(0, pageTop)
        if (seenFor != engravings) {
            seenFor = engravings
            seeAgain()
        }
        _engraving.value = engraving
        // The repeat's band and brackets are drawn from the bars of the engraving.
        if (repeat != null) { band.invalidate(); glyphs.invalidate() }
    }

    private var seenFor = -1
    private var released = false

    /**
     * Has alphaTab's surface work out afresh which lines are in view. It keeps track of them by the scroll steps
     * it sees, and does not see the ones made while a page is being laid out, so after an engraving or a jump
     * the lines in view can come out blank. It looks again where it really is when it is measured.
     */
    private fun seeAgain() {
        view.findViewById<View>(net.alphatab.R.id.renderSurface)?.requestLayout()
    }

    private fun measure(): TabEngraving? {
        val systems = view.api.boundsLookup?.staffSystems ?: return null
        val page = pageScroll?.getChildAt(0)?.height ?: 0
        if (page <= 0 || systems.length.toInt() == 0) return null
        val lines = (0 until systems.length.toInt()).mapNotNull { i ->
            val bars = systems[i].bars
            val n = bars.length.toInt()
            if (n == 0) return@mapNotNull null
            val b = systems[i].realBounds
            TabLine((b.y * density).toInt(), Math.ceil((b.y + b.h) * density).toInt(), bars[0].index.toInt(), bars[n - 1].index.toInt())
        }
        return TabEngraving(page, lines, boxes(), bars())
    }

    /** Every bar's box and the cursor's stops in it: the columns of the beats written on the staff the marks stand on. */
    private fun bars(): List<BarBox> {
        val systems = view.api.boundsLookup?.staffSystems ?: return emptyList()
        val ls = lineSpace
        val pad = 0.25f * ls
        val out = ArrayList<BarBox>()
        for (i in 0 until systems.length.toInt()) {
            val masters = systems[i].bars
            for (j in 0 until masters.length.toInt()) {
                val master = masters[j]
                val box = master.visualBounds
                val stops = java.util.TreeMap<Int, CursorStop>()
                val staves = master.bars
                var staffTop = box.y + box.h
                for (k in 0 until staves.length.toInt()) {
                    staffTop = minOf(staffTop, staves[k].visualBounds.y)
                    val beats = staves[k].beats
                    for (m in 0 until beats.length.toInt()) {
                        val bb = beats[m]
                        if (bb.beat.isEmpty || bb.beat.voice.bar.staff.index.toInt() != cursorStaff) continue
                        var from = bb.visualBounds.x
                        var to = bb.visualBounds.x + bb.visualBounds.w
                        val notes = bb.notes
                        if (notes != null && notes.length.toInt() > 0) {
                            from = Double.MAX_VALUE; to = -Double.MAX_VALUE
                            for (n in 0 until notes.length.toInt()) {
                                val h = notes[n].noteHeadBounds
                                from = minOf(from, h.x); to = maxOf(to, h.x + h.w)
                            }
                        }
                        val width = maxOf(ls, ((to - from) * density).toFloat() + 2 * pad)
                        val left = ((from + to) / 2 * density).toFloat() - width / 2
                        // Two voices that start a beat together share its column: the first one written stands.
                        stops.putIfAbsent(bb.beat.playbackStart.toInt(), CursorStop(bb.beat.playbackStart.toInt(), left, width))
                    }
                }
                val left = (box.x * density).toFloat()
                if (stops.isEmpty()) stops[0] = CursorStop(0, left + pad, ls)
                out += BarBox(master.index.toInt(), left, ((box.x + box.w) * density).toFloat(), (box.y * density).toFloat(), ((box.y + box.h) * density).toFloat(), stops.values.toList(),
                    (staffTop * density).toFloat())
            }
        }
        return out
    }

    private val pageScroll: android.widget.ScrollView? = view.findViewById(net.alphatab.R.id.innerScroll)
    private var pageTop = 0

    /** Shows the page from [y] view pixels down. The screen's scroll is the only one that moves the page. */
    fun scrollTo(y: Int) {
        pageTop = y.coerceAtLeast(0)
        val scroll = pageScroll ?: return
        val from = scroll.scrollY
        if (from == pageTop) return
        scroll.scrollTo(0, pageTop)
        // A jump (the page put at a bar, Home and End), not a drag.
        if (Math.abs(pageTop - from) > scroll.height / 2) seeAgain()
    }

    /** How far down the page alphaTab is showing it. */
    val pageScrolled: Int get() = pageScroll?.scrollY ?: 0

    /** How far alphaTab can scroll its page. */
    val pageScrollRange: Int get() = pageScroll?.let { s -> ((s.getChildAt(0)?.height ?: 0) - s.height).coerceAtLeast(0) } ?: 0

    fun release() {
        released = true
        runCatching { view.api.destroy() }
    }

    private fun Int.toColor() = alphaTab.model.Color(((this shr 16) and 0xFF).toDouble(), ((this shr 8) and 0xFF).toDouble(),
        (this and 0xFF).toDouble(), ((this ushr 24) and 0xFF).toDouble())

    companion object {
        /** Blank text in place of a mark: alphaTab keeps the band above the staff for it. */
        private const val MARK_SPACE = "  "
        /** The size of the fret numbers in alphaTab's units (dp at scale 1). */
        const val NUMERAL_UNITS = 14.0

        /** alphaTab's scale at which the numerals are [TabTokens.NUMERAL_SCALE] times body text: 100 %, before the text size and the zoom. */
        const val BASE_SCALE = TabTokens.NUMERAL_SCALE * TabTokens.BODY_SP / NUMERAL_UNITS

        /** alphaTab's spring force between notes: under 1 sets them closer than its default. */
        private const val STRETCH = 0.6
        private val STEPS = mapOf("C" to 0, "D" to 2, "E" to 4, "F" to 5, "G" to 7, "A" to 9, "B" to 11)
    }
}

/** What an overlay draws, and on which side of the engraving. */
internal enum class TabLayer(val under: Boolean) { BAND(true), BEAT(true), WASH(true), MARKS(false), CURSOR(false) }

/**
 * Draws the marks inside alphaTab's render wrapper, from its layout (boundsLookup): under the engraving
 * the wash behind each doubtful numeral, over it the "?" in the doubt colour and the boxed "!" in ink.
 * The glyph carries the meaning; the colour only goes with it.
 */
@SuppressLint("ViewConstructor")
internal class TabOverlay(context: Context, private val tab: TabView, private val layer: TabLayer) : View(context) {
    private val density = context.resources.displayMetrics.density
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        textAlign = Paint.Align.CENTER
    }
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val rect = RectF()
    private var surface: View? = null

    init {
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        isClickable = false
        setWillNotDraw(false)
    }

    override fun onDraw(canvas: Canvas) {
        val p = tab.palette
        val ls = tab.lineSpace
        // A band, a wash and the cursor reach half a line space past the staff's outer lines.
        val reach = 0.5f * ls
        when (layer) {
            TabLayer.BAND -> {
                fill.color = p.repeatBand ?: return
                val bars = tab.repeat ?: return
                for (b in tab.engraving.value?.bars.orEmpty()) if (b.bar in bars) canvas.drawRect(b.left, b.top - reach, b.right, b.bottom + reach, fill)
                return
            }
            TabLayer.BEAT -> {
                fill.color = p.cursorTint ?: return
                val (bar, stop) = tab.cursor ?: return
                canvas.drawRect(stop.left, bar.top - reach, stop.left + stop.width, bar.bottom + reach, fill)
                return
            }
            TabLayer.CURSOR -> {
                val (bar, stop) = tab.cursor ?: return
                fill.color = p.cursor
                // At the left edge of the beat's column, so the line never crosses a numeral.
                canvas.drawRect(stop.left - TabTokens.CURSOR_DP * density, bar.top - reach, stop.left, bar.bottom + reach, fill)
                return
            }
            else -> Unit
        }
        if (layer == TabLayer.WASH) {
            val wash = p.uncertainTint ?: return
            val lookup = tab.view.api.boundsLookup ?: return
            fill.color = wash
            val pad = 0.2f * ls
            for (mark in tab.placed) for (note in mark.doubtful) {
                val b = lookup.findBeats(mark.beat)?.takeIf { it.length.toInt() > 0 }?.get(0)?.notes ?: continue
                for (j in 0 until b.length.toInt()) {
                    if (b[j].note !== note) continue
                    val h = b[j].noteHeadBounds
                    rect.set((h.x * density).toFloat() - pad, (h.y * density).toFloat() - pad, ((h.x + h.w) * density).toFloat() + pad, ((h.y + h.h) * density).toFloat() + pad)
                    canvas.drawRoundRect(rect, pad, pad, fill)
                }
            }
            return
        }
        tab.repeat?.let { bars ->
            // A bracket at each end of the bars: "[" before the first, "]" after the last. It starts at the staff's top line, under the bar's number.
            stroke.color = p.repeat
            stroke.strokeWidth = TabTokens.CURSOR_DP * density
            val half = stroke.strokeWidth / 2
            val arm = 0.9f * ls
            val boxes = tab.engraving.value?.bars.orEmpty()
            // And a rail under the bars on every line they run over, so a line in the middle of a long repeat is marked too.
            for (b in boxes) if (b.bar in bars) canvas.drawLine(b.left, b.bottom + reach - half, b.right, b.bottom + reach - half, stroke)
            for (b in boxes) {
                if (b.bar != bars.first && b.bar != bars.last) continue
                val top = b.staffTop - half
                val bottom = b.bottom + reach
                if (b.bar == bars.first) {
                    val x = b.left + half
                    canvas.drawLine(x, top, x, bottom, stroke)
                    canvas.drawLine(x, top + half, x + arm, top + half, stroke)
                    canvas.drawLine(x, bottom - half, x + arm, bottom - half, stroke)
                }
                if (b.bar == bars.last) {
                    val x = b.right - half
                    canvas.drawLine(x, top, x, bottom, stroke)
                    canvas.drawLine(x, top + half, x - arm, top + half, stroke)
                    canvas.drawLine(x, bottom - half, x - arm, bottom - half, stroke)
                }
            }
        }
        val kinds = tab.placed.associate { it.column to it.kind }
        stroke.strokeWidth = maxOf(1.5f * density, 0.12f * ls)
        for (box in tab.boxes()) {
            val height = box.bottom - box.top
            if (kinds[box.column] == MarkKind.NO_PLACE) {
                val w = height * 0.9f
                rect.set(box.centre - w / 2, box.top, box.centre + w / 2, box.bottom)
                stroke.color = p.ink
                canvas.drawRoundRect(rect, 0.15f * ls, 0.15f * ls, stroke)
                text.color = p.ink
                text.textSize = height * 0.8f / CAP
                canvas.drawText("!", box.centre, box.bottom - height * 0.1f, text)
            } else {
                text.color = p.uncertain
                text.textSize = height / CAP
                canvas.drawText("?", box.centre, box.bottom, text)
            }
        }
    }

    /** Matches the rendered surface's size (the wrapper wraps its content), then redraws. */
    fun refresh() {
        val sv = surface
        if (sv != null && (layoutParams.width != sv.width || layoutParams.height != sv.height) && sv.width > 0) {
            layoutParams = layoutParams.apply { width = sv.width; height = sv.height }
        }
        invalidate()
    }

    companion object {
        /** A capital's height as a part of the text size, for the bold system face. */
        private const val CAP = 0.72f

        /** Each layer goes on top of the ones attached before it on its side of the engraving. */
        fun attach(tab: TabView, layer: TabLayer): TabOverlay {
            val overlay = TabOverlay(tab.view.context, tab, layer)
            val wrapper = tab.view.findViewById<RelativeLayout>(net.alphatab.R.id.renderWrapper)
            val surface = tab.view.findViewById<View>(net.alphatab.R.id.renderSurface)
            val at = (0 until wrapper.childCount).firstOrNull { wrapper.getChildAt(it) === surface } ?: 0
            wrapper.addView(overlay, if (layer.under) at else wrapper.childCount, RelativeLayout.LayoutParams(0, 0))
            overlay.surface = surface
            surface.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> overlay.post { overlay.refresh() } }
            return overlay
        }
    }
}
