package no.brasscribe.play.audio

import java.io.File

/**
 * A finished recording: always the WAV on disk, and the samples in memory too when the take was
 * short enough ([TakeSink.maxInMemory]); a longer take is null here and goes to the engine as the file.
 */
class CapturedTake(val file: File, val sampleRate: Int, val samples: Long, val audio: PcmAudio?) {
    val seconds: Double get() = samples.toDouble() / sampleRate
}

/**
 * Where a recorder's samples go as they arrive: straight into a 16-bit WAV on disk ([WavWriter]), and
 * into memory only up to [maxInMemory] samples, the same budget an imported file has
 * ([AudioDecoder.maxSamplesInMemory]). Past it the memory copy is dropped at once, so a long take
 * costs a 64 KB buffer, not 11.5 MB a minute. Nothing is kept past [maxSamples] ([full] turns true):
 * the recorder stops there.
 */
class TakeSink(
    val file: File,
    val sampleRate: Int,
    val maxInMemory: Int = AudioDecoder.maxSamplesInMemory,
    val maxSamples: Long = MAX_TAKE_SECONDS * sampleRate,
) {
    private val wav = WavWriter(file, sampleRate)
    private var pcm: FloatBuilder? = FloatBuilder(minOf(maxInMemory, 1 shl 16).coerceAtLeast(1))

    @Volatile var samples = 0L
        private set

    /** Writing the WAV failed (the disk is full): the take ends with what was written. */
    @Volatile var failed = false
        private set

    /** The take reached [maxSamples], or the disk took no more; later samples are dropped. */
    val full: Boolean get() = failed || samples >= maxSamples

    /** The samples are still held in memory (the take is under [maxInMemory]). */
    val inMemory: Boolean get() = pcm != null

    /** Takes the first [n] samples of [buf]; returns how many were kept (fewer once [full]). */
    fun add(buf: FloatArray, n: Int): Int {
        if (failed) return 0
        val keep = minOf(n.toLong(), maxSamples - samples).toInt().coerceAtLeast(0)
        if (keep == 0) return 0
        // A full disk ends the take (the recorder stops as at the length limit) instead of crashing the service.
        try { for (i in 0 until keep) wav.write(buf[i]) } catch (e: java.io.IOException) { failed = true; return 0 }
        pcm?.let { if (it.size + keep > maxInMemory) pcm = null else it.addAll(buf, keep) }
        samples += keep
        return keep
    }

    /** Closes the WAV (its header gets the sizes) and hands the take over. */
    fun finish(): CapturedTake {
        runCatching { wav.close() }.onFailure { failed = true }
        val audio = pcm?.let { PcmAudio(it.toArray(), sampleRate) }
        pcm = null
        return CapturedTake(file, sampleRate, samples, audio)
    }

    /** Closes and deletes the file (a take thrown away). */
    fun discard() {
        runCatching { wav.close() }
        pcm = null
        file.delete()
    }

    companion object {
        /**
         * The longest take: 3 hours, a 1 GB WAV at 48 kHz. A 16-bit WAV cannot pass 4 GB (about 12 hours
         * of mono at 48 kHz); well before that the engine's stages take far longer than anyone waits.
         */
        const val MAX_TAKE_SECONDS = 3L * 60 * 60
    }
}
