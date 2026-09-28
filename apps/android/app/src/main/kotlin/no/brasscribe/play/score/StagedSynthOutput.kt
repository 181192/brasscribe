package no.brasscribe.play.score

import alphaTab.AlphaTabApiBase
import alphaTab.core.ecmaScript.Float32Array
import alphaTab.synth.ISynthOutput
import no.brasscribe.play.audio.OutputStage
import no.brasscribe.play.audio.PlaybackLevels

/**
 * alphaTab's synth output with the shared output stage in front of it: every buffer the synth
 * renders gets the make-up gain and the soft limiter before it reaches the device (docs/research/
 * 12-band-sound.md §11). The master volume stays alphaTab's, for the stop fade, which so runs
 * before the stage as on Apple.
 */
class StagedSynthOutput(private val inner: ISynthOutput, @Volatile var gain: Float = BAND_GAIN) : ISynthOutput by inner {
    override fun addSamples(samples: Float32Array) {
        OutputStage.process(samples.data, gain)
        inner.addSamples(samples)
    }

    companion object {
        val BAND_GAIN = PlaybackLevels.factor(PlaybackLevels.ALPHATAB_GAIN_DB)

        /**
         * Puts the stage in front of the view's synth output. alphaTab 1.8.4 builds its Android output
         * inside the view with no hook, so this swaps the worker API's private output field; the
         * worker's events stay subscribed to the original output, which still does all the work.
         * Idempotent; call again whenever alphaTab may have made a new player. False when the
         * player is not there yet or its shape is not the one this knows.
         */
        fun install(api: AlphaTabApiBase<*>): Boolean = runCatching {
            val (worker, field) = outputField(api) ?: return false
            val current = field.get(worker) as ISynthOutput
            if (current !is StagedSynthOutput) field.set(worker, StagedSynthOutput(current))
            true
        }.getOrElse {
            android.util.Log.w("BrasscribePlay", "output stage not installed on alphaTab's synth", it)
            false
        }

        /** Whether the view's synth plays through the stage now. */
        @androidx.annotation.VisibleForTesting
        fun isInstalled(api: AlphaTabApiBase<*>): Boolean =
            runCatching { outputField(api)?.let { (w, f) -> f.get(w) is StagedSynthOutput } == true }.getOrDefault(false)

        /** The worker API and its output field; both classes are internal to alphaTab, so reached by name (kept by proguard-rules.pro). */
        private fun outputField(api: AlphaTabApiBase<*>): Pair<Any, java.lang.reflect.Field>? {
            val wrapper = api.player ?: return null
            if (wrapper.javaClass.name != "alphaTab.synth.AlphaSynthWrapper") return null
            val worker = wrapper.javaClass.getMethod("getInstance").invoke(wrapper) ?: return null
            if (worker.javaClass.name != "alphaTab.platform.worker.AlphaSynthWebWorkerApi") return null
            return worker to worker.javaClass.getDeclaredField("_output").apply { isAccessible = true }
        }
    }
}
