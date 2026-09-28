package no.brasscribe.play.audio

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.double
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.roundToInt
import kotlin.math.sin

/** The shared output stage against sounds/output-stage-vectors.json (sounds/playback_levels.py), as Apple and Windows. */
class OutputStageTest {
    private val vectors: JsonObject? = System.getProperty("brasscribe.sounds")?.let { File(it, "output-stage-vectors.json") }
        ?.takeIf { it.isFile }?.let { Json.parseToJsonElement(it.readText()).jsonObject }

    private fun v(): JsonObject { assumeTrue("sounds/output-stage-vectors.json not found", vectors != null); return vectors!! }

    @Test fun constantsMatchPlaybackLevels() {
        val levels = v().getValue("levels").jsonObject
        val lim = levels.getValue("limiter").jsonObject
        assertEquals(lim.getValue("threshold").jsonPrimitive.double, OutputStage.THRESHOLD.toDouble(), 1e-6)
        assertEquals(lim.getValue("ceiling").jsonPrimitive.double, OutputStage.CEILING.toDouble(), 1e-6)
        val band = levels.getValue("band").jsonObject
        assertEquals(band.getValue("phrase_lufs").jsonPrimitive.double, PlaybackLevels.BAND_PHRASE_LUFS, 0.0)
        val gains = band.getValue("gain_db").jsonObject
        assertEquals(gains.getValue("android_alphatab").jsonPrimitive.double, PlaybackLevels.ALPHATAB_GAIN_DB, 0.0)
        assertEquals(gains.getValue("android_sfizz").jsonPrimitive.double, PlaybackLevels.SFIZZ_GAIN_DB, 0.0)
        val rec = levels.getValue("recording").jsonObject
        assertEquals(rec.getValue("fallback_lufs").jsonPrimitive.double, PlaybackLevels.RECORDING_FALLBACK_LUFS, 0.0)
        assertEquals(rec.getValue("min_target_lufs").jsonPrimitive.double, PlaybackLevels.RECORDING_MIN_TARGET_LUFS, 0.0)
        assertEquals(rec.getValue("max_target_lufs").jsonPrimitive.double, PlaybackLevels.RECORDING_MAX_TARGET_LUFS, 0.0)
        assertEquals(rec.getValue("band_estimate").jsonObject.getValue("offset_db").jsonPrimitive.double, PlaybackLevels.BAND_ESTIMATE_OFFSET_DB, 0.0)
        val knots = levels.getValue("dynamics").jsonObject.getValue("sampler_velocity").jsonObject.getValue("alphatab_lufs").jsonObject
            .map { (k, x) -> k.toInt() to x.jsonPrimitive.double }.sortedBy { it.first }
        assertEquals(knots, PlaybackLevels.VELOCITY_LUFS)
        val dyn = levels.getValue("dynamics").jsonObject
        assertEquals(dyn.getValue("step").jsonPrimitive.int, PlaybackLevels.DYNAMIC_STEP)
        assertEquals(dyn.getValue("velocity").jsonObject.mapValues { it.value.jsonPrimitive.int }, PlaybackLevels.DYNAMIC_VELOCITY)
        assertEquals(rec.getValue("max_boost_db").jsonPrimitive.double, PlaybackLevels.RECORDING_MAX_BOOST_DB, 0.0)
        assertEquals(rec.getValue("max_cut_db").jsonPrimitive.double, PlaybackLevels.RECORDING_MAX_CUT_DB, 0.0)
        val met = levels.getValue("metronome").jsonObject
        assertEquals(met.getValue("click_peak_dbfs").jsonPrimitive.double, PlaybackLevels.METRONOME_CLICK_PEAK_DBFS, 0.0)
        assertEquals(met.getValue("gain_db").jsonObject.getValue("android_alphatab").jsonPrimitive.double, PlaybackLevels.METRONOME_GAIN_DB, 0.0)
    }

    @Test fun limiterMatchesTheSharedCurve() {
        val rows = v().getValue("limiter").jsonArray
        assertTrue(rows.size > 10)
        for (r in rows) {
            val o = r.jsonObject
            val x = o.getValue("in").jsonPrimitive.double.toFloat()
            assertEquals("limit($x)", o.getValue("out").jsonPrimitive.double, OutputStage.limit(x).toDouble(), 1e-6)
        }
    }

    /** Linear below the threshold (mute and solo keep the balance), monotonic, never at the ceiling: no pumping, no clipping. */
    @Test fun limiterIsLinearBelowTheThresholdMonotonicAndBounded() {
        for (x in listOf(0f, 0.1f, -0.5f, 0.79f, 0.8f)) assertEquals(x, OutputStage.limit(x), 0f)
        var last = 0f
        for (i in 0..400) { val y = OutputStage.limit(i / 100f); assertTrue(y >= last); last = y }
        assertTrue(OutputStage.limit(50f) <= OutputStage.CEILING && OutputStage.limit(-50f) >= -OutputStage.CEILING)
    }

    @Test fun recordingGainMatchesTheSharedRule() {
        for (r in v().getValue("recording_gain").jsonArray) {
            val o = r.jsonObject
            val lufs = o.getValue("lufs").jsonPrimitive.doubleOrNull ?: Double.NEGATIVE_INFINITY
            assertEquals("$lufs", o.getValue("gain_db").jsonPrimitive.double, PlaybackLevels.recordingGainDb(lufs), 1e-6)
        }
    }

    @Test fun recordingGainForATargetMatchesTheSharedRule() {
        val rows = v().getValue("recording_gain_for_target").jsonArray
        assertTrue(rows.isNotEmpty())
        for (r in rows) {
            val o = r.jsonObject
            val lufs = o.getValue("lufs").jsonPrimitive.doubleOrNull ?: Double.NEGATIVE_INFINITY
            val target = o.getValue("target_lufs").jsonPrimitive.double
            assertEquals("$lufs -> $target", o.getValue("gain_db").jsonPrimitive.double, PlaybackLevels.recordingGainDb(lufs, target), 1e-6)
        }
    }

    @Test fun bandEstimateAndRecordingTargetMatchTheSharedRule() {
        val rows = v().getValue("band_estimate").jsonArray
        assertTrue(rows.size > 5)
        for (c in rows.map { it.jsonObject }) {
            val name = c.getValue("name").jsonPrimitive.content
            val notes = c.getValue("notes").jsonArray.map { n ->
                n.jsonArray.let { BandNote(it[0].jsonPrimitive.double, it[1].jsonPrimitive.double, it[2].jsonPrimitive.double) }
            }
            val e = PlaybackLevels.bandEstimateLufs(notes)
            val want = c.getValue("estimate_lufs").jsonPrimitive.doubleOrNull
            if (want == null) assertEquals(name, null, e) else assertEquals(name, want, e!!, 1e-6)
            assertEquals(name, c.getValue("target_lufs").jsonPrimitive.double, PlaybackLevels.recordingTargetLufs(e), 1e-6)
        }
    }

    @Test fun meterMatchesPyloudnorm() {
        for (c in v().getValue("loudness").jsonArray.map { it.jsonObject }) {
            val rate = c.getValue("rate").jsonPrimitive.double
            val ch = c.getValue("channels").jsonPrimitive.int
            val tones = c.getValue("tones").jsonArray.map { it.jsonArray.let { t -> t[0].jsonPrimitive.double to t[1].jsonPrimitive.double } }
            val x = ArrayList<Float>()
            var t0 = 0
            for (seg in c.getValue("segments").jsonArray.map { it.jsonArray }) {
                val n = (seg[0].jsonPrimitive.double * rate).roundToInt()
                val scale = seg[1].jsonPrimitive.double
                for (i in 0 until n) {
                    val t = (t0 + i) / rate
                    val s = (tones.sumOf { (f, a) -> a * sin(2 * PI * f * t) } * scale).toFloat()
                    repeat(ch) { x += s }
                }
                t0 += n
            }
            val all = x.toFloatArray()
            val m = LoudnessMeter(rate, ch)
            var at = 0
            var k = 0
            while (at < all.size) {
                val frames = minOf(intArrayOf(1000, 4096, 333)[k++ % 3], (all.size - at) / ch)
                m.process(all, at, frames)
                at += frames * ch
            }
            val want = c.getValue("lufs")
            val name = c.getValue("name").jsonPrimitive.content
            if (want is JsonNull) assertEquals(name, Double.NEGATIVE_INFINITY, m.integratedLufs, 0.0)
            else assertTrue("$name: ${m.integratedLufs} vs $want", abs(m.integratedLufs - want.jsonPrimitive.double) < 0.1)
        }
    }

    /** A mono clip is measured as it plays from two speakers, and leveled audio is gained then limited. */
    @Test fun dualMonoAndLeveling() {
        val rate = 22050
        val tone = PcmAudio(FloatArray(rate * 3) { (0.1 * sin(2 * PI * 1000 * it / rate)).toFloat() }, rate)
        assertEquals(-20.0, LoudnessMeter.dualMono(tone), 0.2)
        val up = tone.leveled(20.0)
        // +20 dB takes the sine to full scale: the limiter holds it under the ceiling
        assertTrue(up.peak() > OutputStage.THRESHOLD && up.peak() <= OutputStage.CEILING)
        assertEquals(tone.samples[100] * 0.5f, tone.leveled(20 * log10(0.5)).samples[100], 1e-6f)
    }
}
