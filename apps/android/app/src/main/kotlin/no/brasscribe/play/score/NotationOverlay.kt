package no.brasscribe.play.score

import alphaTab.AlphaTabView
import alphaTab.model.Beat
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.view.View
import android.widget.RelativeLayout

/**
 * Draws what alphaTab cannot, from its layout (boundsLookup), inside alphaTab's scrolling render
 * wrapper so it scrolls with the notation:
 * - the uncertainty marks at the spec size (visual-design-tokens.md §2, system.md §6): a "?" 1.6 staff
 *   spaces tall above an uncertain note, and a boxed "?" of the same height, stroke at least 1.5 dp,
 *   above a very uncertain one, both in the note's colour;
 * - the ad-lib tint behind free-time bars (the loop tint replaces it inside a loop; high contrast has
 *   no tints);
 * - an ink ring around one note (the review's note card).
 * alphaTab still lays out a blank text band where the marks go, so nothing collides with them.
 */
@SuppressLint("ViewConstructor")
class NotationOverlay(context: Context, private val tab: AlphaTabView, private val under: Boolean) : View(context) {
    /** Marked beats: true when very uncertain. */
    var marks: Map<Beat, Boolean> = emptyMap()
    /** Master bar indexes (0-based) in free time. */
    var adLibBars: Set<Int> = emptySet()
    /** Loop range (1-based bars); the loop tint replaces the ad-lib tint there. */
    var loop: IntRange? = null
    var ring: Beat? = null
    var palette: ScorePalette? = null

    private val density = context.resources.displayMetrics.density
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        textAlign = Paint.Align.CENTER
    }
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val fill = Paint()
    private val rect = RectF()
    private val caret = android.graphics.Path()

    init {
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        isClickable = false
        setWillNotDraw(false)
    }

    /** One staff space in view pixels at the current zoom. */
    val staffSpacePx: Float
        get() {
            val ss = tab.settings.display.resources.engravingSettings.oneStaffSpace.takeIf { it > 0 } ?: 8.5
            return (ss * tab.settings.display.scale * density).toFloat()
        }

    /** alphaTab's high-DPI factor is the display density (AndroidEnvironment). */
    private val f get() = density

    override fun onDraw(canvas: Canvas) {
        val p = palette
        val lookup = tab.api.boundsLookup
        if (p == null || lookup == null) return
        val ss = staffSpacePx
        // Ad-lib tint over the whole system height of each free-time bar.
        if (under) {
            // The selected note: a selection-tint column behind it, the height of the staff (review 3, P2-A).
            ring?.let { beat ->
                val bb = lookup.findBeats(beat)?.let { if (it.length > 0) it[0] else null } ?: return@let
                val staff = bb.barBounds.visualBounds
                val notes = bb.notes
                val h = if (notes != null && notes.length > 0) notes[0].noteHeadBounds else bb.visualBounds
                val cx = ((h.x + h.w / 2) * f).toFloat()
                fill.color = if (p.highContrast) p.paper else p.selectionTint
                canvas.drawRect(cx - 0.9f * ss, (staff.y * f).toFloat() - 1.8f * ss, cx + 0.9f * ss, ((staff.y + staff.h) * f).toFloat() + 0.4f * ss, fill)
            }
            if (p.highContrast || adLibBars.isEmpty()) return
            fill.color = p.adlibTint
            for (i in adLibBars) {
                if (loop?.contains(i + 1) == true) continue
                val mb = lookup.findMasterBarByIndex(i.toDouble()) ?: continue
                val b = mb.visualBounds
                canvas.drawRect((b.x * f).toFloat(), (b.y * f).toFloat(), ((b.x + b.w) * f).toFloat(), ((b.y + b.h) * f).toFloat(), fill)
            }
            return
        }
        val markH = 1.6f * ss
        text.textSize = markH / 0.72f
        stroke.strokeWidth = maxOf(1.5f * density, 0.14f * ss)
        for ((beat, very) in marks) {
            val all = lookup.findBeats(beat) ?: continue
            for (i in 0 until all.length.toInt()) {
                val bb = all[i]
                val staffTop = (bb.barBounds.visualBounds.y * f).toFloat()
                val notes = bb.notes
                // Above the staff, the note heads and the stem.
                var top = minOf(staffTop, (bb.visualBounds.y * f).toFloat())
                var cx = ((bb.onNotesX.takeIf { it > 0 } ?: (bb.visualBounds.x + bb.visualBounds.w / 2)) * f).toFloat()
                if (notes != null && notes.length > 0) {
                    for (j in 0 until notes.length.toInt()) {
                        val h = notes[j].noteHeadBounds
                        top = minOf(top, (h.y * f).toFloat())
                        if (j == 0) cx = ((h.x + h.w / 2) * f).toFloat()
                    }
                }
                val bottom = top - 0.4f * ss
                val colour = if (very) p.veryUncertain else p.uncertain
                text.color = colour
                if (very) {
                    val w = markH * 0.8f
                    rect.set(cx - w / 2, bottom - markH, cx + w / 2, bottom)
                    stroke.color = colour
                    canvas.drawRoundRect(rect, 0.15f * ss, 0.15f * ss, stroke)
                    text.textSize = markH * 0.8f / 0.72f
                    canvas.drawText("?", cx, bottom - markH * 0.16f, text)
                    text.textSize = markH / 0.72f
                } else {
                    canvas.drawText("?", cx, bottom, text)
                }
            }
        }
        // The selected note's caret, under the staff (a box would read as the boxed "?").
        ring?.let { beat ->
            val bb = lookup.findBeats(beat)?.let { if (it.length > 0) it[0] else null } ?: return@let
            val notes = bb.notes
            val h = if (notes != null && notes.length > 0) notes[0].noteHeadBounds else bb.visualBounds
            val cx = ((h.x + h.w / 2) * f).toFloat()
            val staff = bb.barBounds.visualBounds
            val bottom = maxOf(((staff.y + staff.h) * f).toFloat(), ((h.y + h.h) * f).toFloat()) + 0.8f * ss
            fill.color = p.selectionEdge
            caret.reset()
            caret.moveTo(cx, bottom); caret.lineTo(cx - 0.7f * ss, bottom + 0.9f * ss); caret.lineTo(cx + 0.7f * ss, bottom + 0.9f * ss); caret.close()
            canvas.drawPath(caret, fill)
        }
    }

    private var surface: View? = null

    /** Matches the rendered surface's size (the wrapper wraps its content), then redraws. */
    fun refresh() {
        val sv = surface
        if (sv != null && (layoutParams.width != sv.width || layoutParams.height != sv.height) && sv.width > 0) {
            layoutParams = layoutParams.apply { width = sv.width; height = sv.height }
        }
        invalidate()
    }

    companion object {
        /**
         * Puts an overlay into [tab]'s render wrapper: [under] the rendered notation for tints (the
         * surface is transparent over the paper), or above it for the marks and the ring.
         */
        fun attach(tab: AlphaTabView, under: Boolean): NotationOverlay {
            val overlay = NotationOverlay(tab.context, tab, under)
            val wrapper = tab.findViewById<RelativeLayout>(net.alphatab.R.id.renderWrapper)
            val surface = tab.findViewById<View>(net.alphatab.R.id.renderSurface)
            val index = (0 until wrapper.childCount).firstOrNull { wrapper.getChildAt(it) === surface }?.plus(if (under) 0 else 1) ?: 0
            wrapper.addView(overlay, index, RelativeLayout.LayoutParams(0, 0))
            overlay.surface = surface
            surface.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> overlay.post { overlay.refresh() } }
            return overlay
        }
    }
}
