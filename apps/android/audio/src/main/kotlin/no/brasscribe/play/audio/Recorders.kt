package no.brasscribe.play.audio

import android.Manifest
import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import androidx.annotation.RequiresPermission
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.math.abs

/** Live state of a capture, for the level meter and the silence notice. */
data class CaptureState(
    val recording: Boolean = false,
    val seconds: Double = 0.0,
    /** Peak of the last buffer, 0..1. */
    val level: Float = 0f,
    /** Seconds since the input was last above the silence threshold. */
    val silentFor: Double = 0.0,
)

/** Something that records mono float audio until stopped. */
interface AudioCapture {
    val state: StateFlow<CaptureState>
    fun start(scope: CoroutineScope): Boolean
    suspend fun stop(): PcmAudio
}

private const val SILENCE = 1e-3f

/** Microphone capture through Oboe/AAudio (native, low latency). */
class MicRecorder(private val requestedRate: Int = 48000) : AudioCapture {
    private val _state = MutableStateFlow(CaptureState())
    override val state: StateFlow<CaptureState> = _state
    private val pcm = FloatBuilder()
    private var job: Job? = null

    @RequiresPermission(Manifest.permission.RECORD_AUDIO)
    override fun start(scope: CoroutineScope): Boolean {
        if (!NativeAudio.recorderStart(requestedRate)) return false
        val rate = NativeAudio.recorderSampleRate()
        job = scope.launch(Dispatchers.Default) {
            val buf = FloatArray(4096)
            var lastSound = 0
            while (isActive) {
                val n = NativeAudio.recorderRead(buf)
                if (n > 0) {
                    pcm.addAll(buf, n)
                    var peak = 0f
                    for (i in 0 until n) peak = maxOf(peak, abs(buf[i]))
                    if (peak > SILENCE) lastSound = pcm.size
                    _state.value = CaptureState(true, pcm.size.toDouble() / rate, NativeAudio.recorderLevel(),
                        (pcm.size - lastSound).toDouble() / rate)
                } else delay(10)
            }
        }
        _state.value = CaptureState(recording = true)
        return true
    }

    override suspend fun stop(): PcmAudio {
        val rate = NativeAudio.recorderSampleRate()
        NativeAudio.recorderStop()
        job?.cancel()
        job?.join()
        // Drain what the callback wrote after the last read.
        val buf = FloatArray(4096)
        while (true) {
            val n = NativeAudio.recorderRead(buf)
            if (n <= 0) break
            pcm.addAll(buf, n)
        }
        _state.value = _state.value.copy(recording = false)
        return PcmAudio(pcm.toArray(), rate)
    }
}

/**
 * Records what other apps play (Android 10+ AudioPlaybackCapture) through a MediaProjection the user
 * consented to. Apps can opt out, and DRM playback is never captured: both give silence, which
 * [CaptureState.silentFor] exposes so the UI can say so instead of recording nothing.
 */
class PlaybackCaptureRecorder(private val projection: MediaProjection, private val sampleRate: Int = 48000) : AudioCapture {
    private val _state = MutableStateFlow(CaptureState())
    override val state: StateFlow<CaptureState> = _state
    private val pcm = FloatBuilder()
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
        record = rec
        rec.startRecording()
        job = scope.launch(Dispatchers.IO) {
            val buf = FloatArray(4096)
            var lastSound = 0
            while (isActive) {
                val n = rec.read(buf, 0, buf.size, AudioRecord.READ_BLOCKING)
                if (n <= 0) continue
                pcm.addAll(buf, n)
                var peak = 0f
                for (i in 0 until n) peak = maxOf(peak, abs(buf[i]))
                if (peak > SILENCE) lastSound = pcm.size
                _state.value = CaptureState(true, pcm.size.toDouble() / sampleRate, peak, (pcm.size - lastSound).toDouble() / sampleRate)
            }
        }
        _state.value = CaptureState(recording = true)
        return true
    }

    override suspend fun stop(): PcmAudio {
        job?.cancel()
        record?.stop()
        job?.join()
        record?.release()
        record = null
        projection.stop()
        _state.value = _state.value.copy(recording = false)
        return PcmAudio(pcm.toArray(), sampleRate)
    }
}
