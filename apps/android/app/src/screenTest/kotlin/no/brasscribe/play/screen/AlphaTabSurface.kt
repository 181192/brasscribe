package no.brasscribe.play.screen

import android.view.View
import android.view.ViewGroup

/**
 * What alphaTab's view has painted. A render lays the engraving out in parts; the view asks alphaTab's thread for the
 * picture of each part it shows when it lays itself out, and draws the part once the picture is back. Until then the
 * part is blank, though the render has finished. alphaTab has no public way to tell, so this reads its view's own state.
 *
 * The view can also hold parts of an engraving before the current one: when two renders follow each other closely,
 * alphaTab hands a part of the first to the view after it cleared the view for the second. Its thread no longer knows
 * those parts and never paints them, so only the current engraving's parts (by id) are looked at.
 */
internal object AlphaTabSurface {
    private const val SURFACE = "alphaTab.platform.android.AlphaTabRenderSurface"
    /** RenderPlaceholder.STATE_RENDER_REQUESTED: asked for, and the picture not back yet. */
    private const val REQUESTED = 1

    /** True when every part of the current engraving ([parts], by id) that [view] (an AlphaTabView) asked for is painted. Read on the main thread. */
    fun painted(view: View, parts: Set<String>): Boolean {
        val surface = find(view) ?: return false
        // (The view asks for the pictures of the parts it shows when it lays itself out.)
        if (surface.isLayoutRequested) return false
        return placeholders(surface).none { (id, state) -> id in parts && state == REQUESTED }
    }

    /** For a test's message: whether the view waits for a layout, and each part's state (0 laid out, 1 asked for, 2 painted; old: not the current engraving's). */
    fun describe(view: View, parts: Set<String>): String {
        val surface = find(view) ?: return "no surface"
        return "layout requested ${surface.isLayoutRequested}, states " +
            placeholders(surface).joinToString(", ", "[", "]") { (id, state) -> if (id in parts) "$state" else "old $state" }
    }

    /** The view's parts: the id of each and its state. */
    private fun placeholders(surface: View): List<Pair<String?, Any?>> = internals {
        val parts = surface.javaClass.getDeclaredField("_placeholders").apply { isAccessible = true }.get(surface) as List<*>
        parts.map { p ->
            val result = p!!.javaClass.getMethod("getResult").invoke(p)!!
            result.javaClass.getMethod("getId").invoke(result) as String? to p.javaClass.getMethod("getState").invoke(p)
        }
    }

    private fun find(v: View): View? = when {
        v.javaClass.name == SURFACE -> v
        v is ViewGroup -> (0 until v.childCount).firstNotNullOfOrNull { find(v.getChildAt(it)) }
        else -> null
    }

    private inline fun <T> internals(block: () -> T): T = try {
        block()
    } catch (e: ReflectiveOperationException) {
        throw IllegalStateException("the screen tests could not read which parts alphaTab has painted ($SURFACE._placeholders, RenderPlaceholder.state): " +
            "it is not public, and has moved or changed in this alphaTab; AlphaTabSurface (src/screenTest) has to follow it", e)
    }
}
