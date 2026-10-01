package no.brasscribe.play

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat

/**
 * Keeps the app in the foreground, with a notification, while a band draft is made on the phone, so it
 * keeps going when the player leaves the app. The work itself runs in the view model; this service only
 * holds the process. Type `dataSync` below Android 15, `mediaProcessing` from 15 (its own time limit).
 */
class DraftService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, getString(R.string.notif_draft_channel), NotificationManager.IMPORTANCE_LOW))
        val notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(getString(R.string.notif_draft))
            .setOngoing(true)
            .setContentIntent(openApp())
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .build()
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.VANILLA_ICE_CREAM) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROCESSING
        else ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        // Always before anything else: a service started with startForegroundService that stops without
        // reaching the foreground ends the app. The platform call, not ServiceCompat's: that one masks the type
        // with the types it knows, which leaves mediaProcessing as none, and the system refuses none.
        runCatching { startForeground(NOTIFICATION_ID, notification, type) }
            .onFailure { android.util.Log.w("BrasscribePlay", "draft service not in the foreground", it) }
        starting = false
        // The draft ended (refused, failed or cancelled) before the service got here.
        if (stopWhenStarted) {
            stopWhenStarted = false
            ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
        return START_NOT_STICKY
    }

    /** Tapping the notification brings the app back as it is: the transcribing screen while a draft is made. */
    private fun openApp(): PendingIntent {
        val intent = Intent(this, MainActivity::class.java)
            .setAction(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        return PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    /** The system's time limit for the type ran out: the draft goes on only while the app is in front. */
    override fun onTimeout(startId: Int, fgsType: Int) {
        stopSelf()
    }

    companion object {
        private const val CHANNEL = "draft"
        private const val NOTIFICATION_ID = 2

        /** Asked to start, and not yet in the foreground: it may not be stopped until it is. */
        @Volatile private var starting = false
        /** The draft ended while the service was starting: it stops itself once it is in the foreground. */
        @Volatile private var stopWhenStarted = false

        /** Started when a draft starts; a start the system refuses (the app is not in front) leaves the draft running. */
        fun start(context: Context) {
            stopWhenStarted = false
            runCatching { context.startForegroundService(Intent(context, DraftService::class.java)) }
                .onSuccess { starting = true }
                .onFailure { android.util.Log.w("BrasscribePlay", "draft service not started", it) }
        }

        /** Stops it when the draft ends. One that is still starting stops itself once it is in the foreground. */
        fun stop(context: Context) {
            if (starting) stopWhenStarted = true
            else context.stopService(Intent(context, DraftService::class.java))
        }
    }
}
