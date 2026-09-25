package no.brasscribe.play.capture

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.projection.MediaProjectionManager
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.IntentCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.SharingStarted
import no.brasscribe.play.R
import no.brasscribe.play.audio.AudioCapture
import no.brasscribe.play.audio.CaptureState
import no.brasscribe.play.audio.MicRecorder
import no.brasscribe.play.audio.PcmAudio
import no.brasscribe.play.audio.PlaybackCaptureRecorder

enum class CaptureKind { MICROPHONE, DEVICE }

/**
 * Hands recordings between the UI and [CaptureService]. The service owns the recorder so capture keeps
 * running with the screen off; the UI watches [state] and calls [stop].
 */
object CaptureController {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val current = MutableStateFlow<AudioCapture?>(null)
    val kind = MutableStateFlow<CaptureKind?>(null)
    val failed = MutableStateFlow(false)

    @OptIn(ExperimentalCoroutinesApi::class)
    val state: StateFlow<CaptureState> = current
        .flatMapLatest { it?.state ?: flowOf(CaptureState()) }
        .stateIn(scope, SharingStarted.Eagerly, CaptureState())

    internal fun attach(capture: AudioCapture, kind: CaptureKind) {
        failed.value = false
        this.kind.value = kind
        current.value = capture
    }

    internal fun fail() {
        failed.value = true
        current.value = null
        kind.value = null
    }

    fun startMicrophone(context: Context) {
        failed.value = false
        kind.value = CaptureKind.MICROPHONE
        context.startForegroundService(Intent(context, CaptureService::class.java).setAction(CaptureService.ACTION_MIC))
    }

    /** [resultCode] and [data] come from the MediaProjection consent dialog; they are single use. */
    fun startDevice(context: Context, resultCode: Int, data: Intent) {
        failed.value = false
        kind.value = CaptureKind.DEVICE
        context.startForegroundService(
            Intent(context, CaptureService::class.java).setAction(CaptureService.ACTION_DEVICE)
                .putExtra(CaptureService.EXTRA_CODE, resultCode).putExtra(CaptureService.EXTRA_DATA, data),
        )
    }

    suspend fun stop(context: Context): PcmAudio? {
        val capture = current.value ?: return null
        val audio = capture.stop()
        current.value = null
        kind.value = null
        context.stopService(Intent(context, CaptureService::class.java))
        return audio
    }
}

/**
 * Foreground service for recording: type `microphone` for the mic, `mediaProjection` for other apps'
 * playback. Android 14+ requires the service to be in the foreground with the matching type before the
 * projection is obtained, so the projection is created here, not in the activity.
 */
class CaptureService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val device = intent?.action == ACTION_DEVICE
        startInForeground(device)
        val capture: AudioCapture? = if (device) {
            val code = intent?.getIntExtra(EXTRA_CODE, 0) ?: 0
            val data = intent?.let { IntentCompat.getParcelableExtra(it, EXTRA_DATA, Intent::class.java) }
            val mpm = getSystemService(MediaProjectionManager::class.java)
            val projection = data?.let { runCatching { mpm.getMediaProjection(code, it) }.getOrNull() }
            projection?.let { PlaybackCaptureRecorder(it) }
        } else MicRecorder()

        @Suppress("MissingPermission") // The UI only starts the service after RECORD_AUDIO was granted.
        val started = capture?.start(scope) == true
        if (!started || capture == null) {
            CaptureController.fail()
            stopSelf()
        } else CaptureController.attach(capture, if (device) CaptureKind.DEVICE else CaptureKind.MICROPHONE)
        return START_NOT_STICKY
    }

    private fun startInForeground(device: Boolean) {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, getString(R.string.notif_channel), NotificationManager.IMPORTANCE_LOW))
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(getString(if (device) R.string.notif_recording_device else R.string.notif_recording_mic))
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
        val type = if (device) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION else ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type)
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        const val ACTION_MIC = "no.brasscribe.play.capture.MIC"
        const val ACTION_DEVICE = "no.brasscribe.play.capture.DEVICE"
        const val EXTRA_CODE = "code"
        const val EXTRA_DATA = "data"
        private const val CHANNEL = "recording"
        private const val NOTIFICATION_ID = 1
    }
}
