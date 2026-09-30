package no.brasscribe.play.audio

import android.Manifest
import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import android.os.Handler
import android.os.Looper
import androidx.annotation.RequiresPermission
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import kotlin.math.abs

/** Live state of a capture, for the level meter and the silence notice. */
data class CaptureState(
    val recording: Boolean = false,
    val seconds: Double = 0.0,
    /** Peak of the last buffer, 0..1. */
    val level: Float = 0f,
    /** Seconds since the input was last above the silence threshold. */
    val silentFor: Double = 0.0,
    /** The take is still short enough to keep in memory, so the phone itself can make the score. */
    val fitsPhone: Boolean = true,
    /** The take reached [TakeSink.MAX_TAKE_SECONDS]: nothing more is recorded. */
    val full: Boolean = false,
    /** The input went away (the microphone lost, or "Stop sharing"): the take ends with what it has. */
    val interrupted: Boolean = false,
)

/** Something that records mono float audio into a WAV file until stopped. */
interface AudioCapture {
    /** The WAV the take is written to. */
    val file: File
    val state: StateFlow<CaptureState>
    fun start(scope: CoroutineScope): Boolean
    suspend fun stop(): CapturedTake
    /** Stops and deletes the take. */
    suspend fun discard()
}

private const val SILENCE = 1e-3f

/** The live state after [sink] took a buffer whose peak was [level]; [lastSound] is the sample count at the last sound. */
private fun TakeSink.state(level: Float, lastSound: Long) = CaptureState(
    recording = true, seconds = samples.toDouble() / sampleRate, level = level,
    silentFor = (samples - lastSound).toDouble() / sampleRate, fitsPhone = inMemory, full = full,
)

/** Peak of the first [n] samples. */
private fun peak(buf: FloatArray, n: Int): Float { var p = 0f; for (i in 0 until n) p = maxOf(p, abs(buf[i])); return p }

/**
 * Microphone capture through Oboe/AAudio (native, low latency), written to [file] as it is recorded
 * ([TakeSink]): memory holds a 4096-sample buffer and, while the take is short enough, its samples.
 */
class MicRecorder(override val file: File, private val requestedRate: Int = 48000) : AudioCapture {
    private val _state = MutableStateFlow(CaptureState())
    override val state: StateFlow<CaptureState> = _state
    private var sink: TakeSink? = null
    private var job: Job? = null

    @RequiresPermission(Manifest.permission.RECORD_AUDIO)
    override fun start(scope: CoroutineScope): Boolean {
        if (!NativeAudio.recorderStart(requestedRate)) return false
        val take = runCatching { TakeSink(file, NativeAudio.recorderSampleRate()) }.getOrElse { NativeAudio.recorderStop(); return false }
        sink = take
        job = scope.launch(Dispatchers.Default) {
            val buf = FloatArray(4096)
            var lastSound = 0L
            while (isActive) {
                val n = NativeAudio.recorderRead(buf)
                if (n > 0) {
                    take.add(buf, n)
                    if (peak(buf, n) > SILENCE) lastSound = take.samples
                    _state.value = take.state(NativeAudio.recorderLevel(), lastSound)
                } else if (NativeAudio.recorderLost()) {
                    // The microphone went away and could not be opened again: the take ends here.
                    _state.value = _state.value.copy(interrupted = true)
                    break
                } else delay(10)
            }
        }
        _state.value = CaptureState(recording = true)
        return true
    }

    /** Ends the take whatever happens to the caller: the stream, the read loop and the file are always let go. */
    private suspend fun end() = withContext(NonCancellable) {
        job?.cancel()
        job?.join()
        NativeAudio.recorderStop()
        _state.value = _state.value.copy(recording = false)
    }

    override suspend fun stop(): CapturedTake {
        end()
        val take = sink!!
        return withContext(NonCancellable + Dispatchers.IO) {
            // Drain what the callback wrote after the last read.
            val buf = FloatArray(4096)
            while (true) {
                val n = NativeAudio.recorderRead(buf)
                if (n <= 0) break
                take.add(buf, n)
            }
            take.finish()
        }
    }

    override suspend fun discard() { end(); withContext(NonCancellable + Dispatchers.IO) { sink?.discard() } }
}

/**
 * Records what other apps play (Android 10+ AudioPlaybackCapture) through a MediaProjection the user
 * consented to. Apps can opt out, and DRM playback is never captured: both give silence, which
 * [CaptureState.silentFor] exposes so the UI can say so instead of recording nothing. Written to
 * [file] as it is recorded, as [MicRecorder] does.
 */
class PlaybackCaptureRecorder(
    private val projection: MediaProjection, override val file: File, private val sampleRate: Int = 48000,
) : AudioCapture {
    private val _state = MutableStateFlow(CaptureState())
    override val state: StateFlow<CaptureState> = _state
    private var sink: TakeSink? = null
    private var record: AudioRecord? = null
    private var job: Job? = null

    @SuppressLint("MissingPermission") // RECORD_AUDIO is checked by the caller before consent is asked.
    override fun start(scope: CoroutineScope): Boolean {
        val config = AudioPlaybackCaptureConfiguration.Builder(projection)
            .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
            .addMatchingUsage(AudioAttributes.USAGE_GAME)
            .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
            .build()
        val format = AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
            .setSampleRate(sampleRate)
            .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
            .build()
        val minBuf = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_FLOAT)
        val rec = runCatching {
            AudioRecord.Builder().setAudioFormat(format).setBufferSizeInBytes(maxOf(minBuf, sampleRate)).setAudioPlaybackCaptureConfig(config).build()
        }.getOrNull() ?: return false
        if (rec.state != AudioRecord.STATE_INITIALIZED) { rec.release(); return false }
        val take = runCatching { TakeSink(file, sampleRate) }.getOrElse { rec.release(); return false }
        sink = take
        record = rec
        // "Stop sharing" in the system UI (or another app taking the projection) ends the take here.
        projection.registerCallback(stopped, Handler(Looper.getMainLooper()))
        rec.startRecording()
        job = scope.launch(Dispatchers.IO) {
            val buf = FloatArray(4096)
            var lastSound = 0L
            while (isActive) {
                val n = rec.read(buf, 0, buf.size, AudioRecord.READ_BLOCKING)
                if (n < 0) {
                    // An error code: the recording was stopped under it. Reading again would only spin.
                    _state.value = _state.value.copy(interrupted = true)
                    break
                }
                if (n == 0) continue
                take.add(buf, n)
                val p = peak(buf, n)
                if (p > SILENCE) lastSound = take.samples
                _state.value = take.state(p, lastSound).copy(interrupted = projectionStopped)
            }
        }
        _state.value = CaptureState(recording = true)
        return true
    }

    @Volatile private var projectionStopped = false
    private val stopped = object : MediaProjection.Callback() {
        override fun onStop() {
            projectionStopped = true
            if (_state.value.recording) _state.value = _state.value.copy(interrupted = true)
        }
    }

    /** Ends the take whatever happens to the caller: the recording, the read loop and the projection are always let go. */
    private suspend fun end() = withContext(NonCancellable) {
        job?.cancel()
        runCatching { record?.stop() }
        job?.join()
        record?.release()
        record = null
        runCatching { projection.unregisterCallback(stopped) }
        projection.stop()
        _state.value = _state.value.copy(recording = false)
    }

    override suspend fun stop(): CapturedTake {
        end()
        val take = sink!!
        return withContext(NonCancellable + Dispatchers.IO) { take.finish() }
    }

    override suspend fun discard() { end(); withContext(NonCancellable + Dispatchers.IO) { sink?.discard() } }
}
