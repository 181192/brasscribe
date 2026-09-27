package no.brasscribe.play.score

import alphaTab.AlphaTabView
import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.view.View
import android.widget.RelativeLayout

/**
 * The right-hand page of the music stand's spread (a tablet on its side, design/music-stand.md §3):
 * a second window onto the same engraving, drawn from alphaTab's render wrapper (the notation, the
 * cursor and the overlays with the "?" marks), from [top] down. Only [from]..[to] of the window is
 * music; the rest is paper, so the page shows whole systems and never the title block. It is not an
 * accessibility element: the stand's score surface speaks for both pages.
 */
@SuppressLint("ViewConstructor")
class StandMirror(context: Context, tab: AlphaTabView) : View(context) {
    private val wrapper: RelativeLayout = tab.findViewById(net.alphatab.R.id.renderWrapper)
    var top = 0f
    var from = 0f
    var to = 0f
    var paper = 0
    private val fill = android.graphics.Paint()

    init {
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO
        isClickable = false
        isFocusable = false
    }

    /** Draws again every frame while [live] (the cursor moves while the music plays). */
    var live = false
        set(v) { field = v; if (v) postInvalidateOnAnimation() }

    fun show(top: Float, from: Float, to: Float, paper: Int) {
        this.top = top; this.from = from; this.to = to; this.paper = paper
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        // Only this view's bounds: the canvas is not clipped to them, so drawColor would paint the window.
        canvas.clipRect(0f, 0f, width.toFloat(), height.toFloat())
        fill.color = paper
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), fill)
        if (to > from) {
            canvas.save()
            canvas.clipRect(0f, from, width.toFloat(), to)
            canvas.translate(0f, -top)
            wrapper.draw(canvas)
            canvas.restore()
        }
        if (live) postInvalidateOnAnimation()
    }
}
