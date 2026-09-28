package no.brasscribe.play

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.MediaMuxer
import android.net.Uri
import android.os.SystemClock
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import no.brasscribe.play.audio.MediaImport
import no.brasscribe.play.engine.FixtureEngineApi
import no.brasscribe.play.engine.UploadSource
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.PI
import kotlin.math.sin

/**
 * A video larger than the app's whole heap goes through import (its AAC track remuxed to .m4a,
 * the PCM decoded) and upload without running out of memory, and the Java heap stays far below
 * the file's size throughout. The video is made here with MediaMuxer: a real AAC tone, and video
 * samples of filler bytes behind a real H.264 codec config (nothing decodes the pictures).
 */
@RunWith(AndroidJUnit4::class)
class LargeVideoImportTest {
    @get:Rule
    val scenario = ActivityScenarioRule(MainActivity::class.java)

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private lateinit var activity: MainActivity
    private val vm get() = ViewModelProvider(activity)[PlayViewModel::class.java]
    private lateinit var video: File

    @Before
    fun setUp() {
        scenario.scenario.onActivity { activity = it }
        (activity.application as PlayApplication).container.firstRunDone = true
        video = File(activity.filesDir, "large-video-test.mp4")
    }

    @After
    fun tearDown() {
        video.delete()
        File(activity.cacheDir, "takes").listFiles()?.filter { it.name.startsWith("large-video-test") }?.forEach { it.delete() }
    }

    /** Samples the Java heap in use every 20 ms and keeps the highest value. */
    private class PeakHeap : AutoCloseable {
        val peak = AtomicLong(0)
        @Volatile private var running = true
        private val thread = Thread {
            val rt = Runtime.getRuntime()
            while (running) {
                peak.accumulateAndGet(rt.totalMemory() - rt.freeMemory(), ::maxOf)
                Thread.sleep(20)
            }
        }.apply { isDaemon = true; start() }

        override fun close() { running = false; thread.join() }
    }

    @Test
    fun videoLargerThanTheHeapImportsAndUploads() {
        val maxHeap = Runtime.getRuntime().maxMemory()
        val target = maxOf(400L shl 20, maxHeap + (64L shl 20))
        val seconds = makeVideo(video, target)
        assertTrue("video (${video.length() shr 20} MB) is larger than the heap (${maxHeap shr 20} MB)", video.length() > maxHeap)

        System.gc()
        val rt = Runtime.getRuntime()
        val before = rt.totalMemory() - rt.freeMemory()
        val t0 = SystemClock.uptimeMillis()
        PeakHeap().use { heap ->
            instrumentation.runOnMainSync { vm.importUri(Uri.fromFile(video)) }
            val end = SystemClock.uptimeMillis() + 180_000
            while (vm.source.value?.name != video.name && vm.problem.value == null) {
                assertTrue("import timed out", SystemClock.uptimeMillis() < end)
                Thread.sleep(100)
            }
            val importMs = SystemClock.uptimeMillis() - t0
            assertEquals("no problem screen (detail: ${vm.problemDetail})", null, vm.problem.value)
            val source = vm.source.value!!
            assertEquals(SourceKind.VIDEO, source.kind)
            val file = assertNotNull(source.file).let { source.file!! }
            assertEquals("m4a", file.extension)
            assertTrue("only the sound is kept (${file.length()} bytes)", file.length() < 8L shl 20)
            assertEquals(seconds, source.durationS, 0.5)
            assertNotNull("the PCM is decoded for on-device work", source.audio)
            assertEquals(seconds, source.audio!!.seconds, 0.5)

            // The whole video streamed through an upload too, a buffer at a time.
            val fixture = FixtureEngineApi({ null })
            var sent = 0L
            val ref = runBlocking { fixture.uploadAudio(UploadSource.of(video)) { done, _ -> sent = done } }
            assertEquals(video.length(), ref.bytes)
            assertEquals(video.length(), sent)

            val peak = heap.peak.get()
            android.util.Log.i("BrasscribePlay", "large video: %d MB, %.0f s; import %d ms; heap %d MB before, %d MB peak, %d MB max"
                .format(video.length() shr 20, seconds, importMs, before shr 20, peak shr 20, maxHeap shr 20))
            assertTrue("heap peak (${peak shr 20} MB) stays far below the file (${video.length() shr 20} MB)",
                peak - before < 96L shl 20)
        }
    }

    @Test
    fun aacTrackIsRemuxedWithoutReencoding() {
        val seconds = makeVideo(video, 8L shl 20)
        val out = File(activity.cacheDir, "large-video-test-remux.m4a")
        assertTrue(MediaImport.remuxAac(activity, Uri.fromFile(video), out))
        val (hasAudio, hasVideo) = MediaImport.probe(activity, Uri.fromFile(out))
        assertTrue(hasAudio)
        assertTrue("no picture in the .m4a", !hasVideo)
        val decoded = no.brasscribe.play.audio.AudioDecoder.decode(activity, Uri.fromFile(out))
        assertEquals(seconds, decoded.audio!!.seconds, 0.5)
        // A 440 Hz tone survives the copy: not silence.
        assertTrue(decoded.audio!!.peak() > 0.1f)
        out.delete()
    }

    @Test
    fun otherCodecsAreDecodedToAWav() {
        // AMR-NB: MPEG-4 holds it, but it is not AAC, so the sound is decoded once into a WAV.
        val seconds = makeVideo(video, 4L shl 20, amr = true)
        val imported = MediaImport.import(activity, Uri.fromFile(video), video.name, File(activity.cacheDir, "takes"))
        assertEquals("wav", imported.file.extension)
        assertTrue(imported.hasVideo)
        assertEquals(seconds, imported.durationS, 0.5)
        val pcm = assertNotNull(imported.audio).let { imported.audio!! }
        assertEquals(8000, pcm.sampleRate)
        assertEquals(seconds, pcm.seconds, 0.5)
        val wav = no.brasscribe.play.audio.WavFile.read(imported.file)
        assertEquals(pcm.samples.size, wav.samples.size)
        assertTrue("the tone is there", wav.peak() > 0.1f)
        imported.file.delete()
    }

    /**
     * Writes an MP4 of about [bytes]: 30 fps video samples of 1 MB filler behind a real H.264 config,
     * and a real tone for the same duration (44.1 kHz AAC, or 8 kHz AMR-NB with [amr]). Returns the duration in seconds.
     */
    private fun makeVideo(file: File, bytes: Long, amr: Boolean = false): Double {
        val aac = if (amr) encodeTone(MediaFormat.MIMETYPE_AUDIO_AMR_NB, 8000, 12_200, 160) else encodeTone(MediaFormat.MIMETYPE_AUDIO_AAC, 44100, 96_000, 1024)
        val videoFormat = avcFormat()
        val frameBytes = 1 shl 20
        val frames = (bytes / frameBytes).toInt().coerceAtLeast(10)
        val fps = 30
        val durationUs = frames * 1_000_000L / fps
        val muxer = MediaMuxer(file.path, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        val vTrack = muxer.addTrack(videoFormat)
        val aTrack = muxer.addTrack(aac.format)
        muxer.start()
        val filler = ByteBuffer.allocateDirect(frameBytes).apply {
            // Not start codes, so the writer copies the sample as it is.
            for (i in 0 until frameBytes) put(i, (i * 131 + 17).toByte())
        }
        val info = MediaCodec.BufferInfo()
        val aacFrameUs = aac.frameUs
        var audioUs = 0L
        var a = 0
        for (f in 0 until frames) {
            val vUs = f * 1_000_000L / fps
            while (audioUs <= vUs) {
                val frame = aac.frames[a++ % aac.frames.size]
                info.set(0, frame.size, audioUs, MediaCodec.BUFFER_FLAG_KEY_FRAME)
                muxer.writeSampleData(aTrack, ByteBuffer.wrap(frame), info)
                audioUs += aacFrameUs
            }
            filler.position(0).limit(frameBytes)
            info.set(0, frameBytes, vUs, if (f % fps == 0) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
            muxer.writeSampleData(vTrack, filler, info)
        }
        while (audioUs < durationUs) {
            val frame = aac.frames[a++ % aac.frames.size]
            info.set(0, frame.size, audioUs, MediaCodec.BUFFER_FLAG_KEY_FRAME)
            muxer.writeSampleData(aTrack, ByteBuffer.wrap(frame), info)
            audioUs += aacFrameUs
        }
        muxer.stop()
        muxer.release()
        return durationUs / 1e6
    }

    private class Aac(val format: MediaFormat, val frames: List<ByteArray>, val frameUs: Long)

    /** One second of a 440 Hz tone, mono, in [mime]; its frames are repeated for longer tracks. */
    private fun encodeTone(mime: String, rate: Int, bitRate: Int, samplesPerFrame: Int): Aac {
        val format = MediaFormat.createAudioFormat(mime, rate, 1).apply {
            if (mime == MediaFormat.MIMETYPE_AUDIO_AAC) setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
            setInteger(MediaFormat.KEY_BIT_RATE, bitRate)
        }
        val codec = MediaCodec.createEncoderByType(mime)
        codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        codec.start()
        val pcm = ByteBuffer.allocate(rate * 2).order(java.nio.ByteOrder.nativeOrder())
        for (i in 0 until rate) pcm.putShort((sin(2 * PI * 440 * i / rate) * 12000).toInt().toShort())
        pcm.flip()
        val frames = ArrayList<ByteArray>()
        var outFormat: MediaFormat? = null
        val info = MediaCodec.BufferInfo()
        var inputDone = false
        var pts = 0L
        while (true) {
            if (!inputDone) {
                val i = codec.dequeueInputBuffer(10_000)
                if (i >= 0) {
                    val buf = codec.getInputBuffer(i)!!
                    val n = minOf(buf.capacity(), pcm.remaining(), samplesPerFrame * 2)
                    if (n == 0) {
                        codec.queueInputBuffer(i, 0, 0, pts, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                        inputDone = true
                    } else {
                        val chunk = ByteArray(n).also { pcm.get(it) }
                        buf.clear(); buf.put(chunk)
                        codec.queueInputBuffer(i, 0, n, pts, 0)
                        pts += n / 2 * 1_000_000L / rate
                    }
                }
            }
            val o = codec.dequeueOutputBuffer(info, 10_000)
            if (o == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) outFormat = codec.outputFormat
            else if (o >= 0) {
                if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0 && info.size > 0) {
                    val buf = codec.getOutputBuffer(o)!!
                    buf.position(info.offset); buf.limit(info.offset + info.size)
                    frames += ByteArray(info.size).also { buf.get(it) }
                }
                codec.releaseOutputBuffer(o, false)
                if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
            }
        }
        codec.stop(); codec.release()
        return Aac(outFormat!!, frames, samplesPerFrame * 1_000_000L / rate)
    }

    /** A 320x240 H.264 format with the encoder's real SPS/PPS, taken from one encoded frame. */
    private fun avcFormat(): MediaFormat {
        val w = 320
        val h = 240
        val format = MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible)
            setInteger(MediaFormat.KEY_BIT_RATE, 1_000_000)
            setInteger(MediaFormat.KEY_FRAME_RATE, 30)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
        }
        val codec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_VIDEO_AVC)
        codec.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
        codec.start()
        val info = MediaCodec.BufferInfo()
        var queued = 0
        try {
            val end = SystemClock.uptimeMillis() + 20_000
            while (SystemClock.uptimeMillis() < end) {
                if (queued < 3) {
                    val i = codec.dequeueInputBuffer(10_000)
                    if (i >= 0) {
                        val size = w * h * 3 / 2
                        codec.getInputBuffer(i)!!.apply { clear(); put(ByteArray(minOf(size, capacity())) { 64 }) }
                        codec.queueInputBuffer(i, 0, minOf(size, codec.getInputBuffer(i)!!.capacity()), queued * 33_333L,
                            if (queued == 2) MediaCodec.BUFFER_FLAG_END_OF_STREAM else 0)
                        queued++
                    }
                }
                val o = codec.dequeueOutputBuffer(info, 10_000)
                if (o == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    val f = codec.outputFormat
                    return MediaFormat.createVideoFormat(MediaFormat.MIMETYPE_VIDEO_AVC, w, h).apply {
                        setByteBuffer("csd-0", f.getByteBuffer("csd-0"))
                        setByteBuffer("csd-1", f.getByteBuffer("csd-1"))
                    }
                } else if (o >= 0) codec.releaseOutputBuffer(o, false)
            }
            error("the H.264 encoder gave no format")
        } finally {
            codec.stop(); codec.release()
        }
    }
}
