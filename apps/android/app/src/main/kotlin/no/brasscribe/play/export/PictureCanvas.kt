package no.brasscribe.play.export

import alphaTab.Settings
import alphaTab.model.Color
import alphaTab.model.Font
import alphaTab.model.MusicFontSymbol
import alphaTab.platform.ICanvas
import alphaTab.platform.MeasuredText
import alphaTab.platform.TextAlign
import alphaTab.platform.TextBaseline
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Picture
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.Typeface

/**
 * What alphaTab engraves, kept as drawing commands in an [android.graphics.Picture] rather than as pixels: drawn into
 * a PDF page it stays lines, curves and text (the music font's glyphs), sharp at any size. Each system alphaTab lays
 * out is one Picture ([endRender]).
 *
 * It draws as alphaTab's own Android canvas does (the same font sizes, the same text baselines), with the music font
 * from alphaTab's assets ([musicFont]).
 */
internal class PictureCanvas(private val musicFont: Typeface) : ICanvas {
    override lateinit var settings: Settings
    override var color: Color = Color(0.0, 0.0, 0.0, 255.0)
    override var lineWidth: Double = 1.0
    override var font: Font = Font("Arial", 10.0)
    override var textAlign: TextAlign = TextAlign.Left
    override var textBaseline: TextBaseline = TextBaseline.Top

    private var picture: Picture? = null
    private var canvas: Canvas? = null
    private val path = Path().apply { fillType = Path.FillType.WINDING }
    private var faceKey = ""
    private var face: Typeface = Typeface.DEFAULT

    override fun beginRender(width: Double, height: Double) {
        val p = Picture()
        canvas = p.beginRecording(kotlin.math.ceil(width).toInt().coerceAtLeast(1), kotlin.math.ceil(height).toInt().coerceAtLeast(1))
        picture = p
        path.reset()
        textBaseline = TextBaseline.Top
    }

    override fun endRender(): Any? {
        val p = picture ?: return null
        p.endRecording()
        picture = null
        canvas = null
        return p
    }

    override fun onRenderFinished(): Any? = null
    override fun destroy() { picture?.endRecording(); picture = null; canvas = null }

    private fun paint(style: Paint.Style): Paint {
        val c = color
        return Paint(Paint.ANTI_ALIAS_FLAG).apply {
            this.style = style
            setARGB(c.a.toInt(), c.r.toInt(), c.g.toInt(), c.b.toInt())
        }
    }

    override fun fillRect(x: Double, y: Double, w: Double, h: Double) {
        canvas?.drawRect(RectF(x.toFloat(), y.toFloat(), (x + w).toFloat(), (y + h).toFloat()), paint(Paint.Style.FILL))
    }

    override fun strokeRect(x: Double, y: Double, w: Double, h: Double) {
        canvas?.drawRect(RectF(x.toFloat(), y.toFloat(), (x + w).toFloat(), (y + h).toFloat()),
            paint(Paint.Style.STROKE).apply { strokeWidth = lineWidth.toFloat() })
    }

    override fun beginPath() = path.reset()
    override fun closePath() = path.close()
    override fun moveTo(x: Double, y: Double) = path.moveTo(x.toFloat(), y.toFloat())
    override fun lineTo(x: Double, y: Double) = path.lineTo(x.toFloat(), y.toFloat())
    override fun quadraticCurveTo(cpx: Double, cpy: Double, x: Double, y: Double) =
        path.quadTo(cpx.toFloat(), cpy.toFloat(), x.toFloat(), y.toFloat())
    override fun bezierCurveTo(cp1X: Double, cp1Y: Double, cp2X: Double, cp2Y: Double, x: Double, y: Double) =
        path.cubicTo(cp1X.toFloat(), cp1Y.toFloat(), cp2X.toFloat(), cp2Y.toFloat(), x.toFloat(), y.toFloat())

    override fun fillCircle(x: Double, y: Double, radius: Double) {
        path.reset(); path.addCircle(x.toFloat(), y.toFloat(), radius.toFloat(), Path.Direction.CW); fill()
    }

    override fun strokeCircle(x: Double, y: Double, radius: Double) {
        path.reset(); path.addCircle(x.toFloat(), y.toFloat(), radius.toFloat(), Path.Direction.CW); stroke()
    }

    override fun fill() {
        canvas?.drawPath(path, paint(Paint.Style.FILL))
        path.reset()
    }

    override fun stroke() {
        canvas?.drawPath(path, paint(Paint.Style.STROKE).apply { strokeWidth = lineWidth.toFloat() })
        path.reset()
    }

    override fun beginGroup(identifier: String) = Unit
    override fun endGroup() = Unit

    private fun typeface(): Typeface {
        val key = "${font.family}|${font.isBold}|${font.isItalic}"
        if (key != faceKey) {
            faceKey = key
            val style = when {
                font.isBold && font.isItalic -> Typeface.BOLD_ITALIC
                font.isBold -> Typeface.BOLD
                font.isItalic -> Typeface.ITALIC
                else -> Typeface.NORMAL
            }
            face = Typeface.create(font.family, style)
        }
        return face
    }

    private fun textPaint(face: Typeface, size: Double) = paint(Paint.Style.FILL).apply {
        typeface = face
        textSize = size.toFloat()
        isSubpixelText = true
    }

    override fun fillText(text: String, x: Double, y: Double) {
        val p = textPaint(typeface(), font.size * settings.display.scale)
        p.textAlign = when (textAlign) {
            TextAlign.Left -> Paint.Align.LEFT
            TextAlign.Center -> Paint.Align.CENTER
            TextAlign.Right -> Paint.Align.RIGHT
        }
        val m = p.fontMetrics
        // The canvas baselines of a browser, as alphaTab lays text out for them ("top" is the hanging baseline).
        val shift = when (textBaseline) {
            TextBaseline.Top -> -m.ascent * 0.8f
            TextBaseline.Middle -> (-m.ascent - m.descent) / 2f
            TextBaseline.Alphabetic -> 0f
            TextBaseline.Bottom -> -m.descent
        }
        canvas?.drawText(text, x.toFloat(), y.toFloat() + shift, p)
    }

    override fun measureText(text: String): MeasuredText {
        if (text.isEmpty()) return MeasuredText(0.0, 0.0)
        val bounds = Rect()
        textPaint(typeface(), font.size).getTextBounds(text, 0, text.length, bounds)
        return MeasuredText(bounds.width().toDouble(), bounds.height().toDouble())
    }

    override fun fillMusicFontSymbol(x: Double, y: Double, relativeScale: Double, symbol: MusicFontSymbol, centerAtPosition: Boolean?) =
        fillMusicFontSymbols(x, y, relativeScale, alphaTab.collections.List(symbol), centerAtPosition)

    override fun fillMusicFontSymbols(x: Double, y: Double, relativeScale: Double, symbols: alphaTab.collections.List<MusicFontSymbol>, centerAtPosition: Boolean?) {
        val text = buildString { for (s in symbols) if (s != MusicFontSymbol.None) appendCodePoint(s.value.toInt()) }
        if (text.isEmpty()) return
        val p = textPaint(musicFont, MUSIC_FONT_SIZE * relativeScale)
        if (centerAtPosition == true) p.textAlign = Paint.Align.CENTER
        // On the alphabetic baseline, as SMuFL places its glyphs.
        canvas?.drawText(text, x.toFloat(), y.toFloat(), p)
    }

    override fun beginRotate(centerX: Double, centerY: Double, angle: Double) {
        canvas?.save()
        canvas?.translate(centerX.toFloat(), centerY.toFloat())
        canvas?.rotate(angle.toFloat())
    }

    override fun endRotate() { canvas?.restore() }

    companion object {
        /** The music font's size at scale 1, as alphaTab's canvases draw it. */
        const val MUSIC_FONT_SIZE = 34.0
    }
}
