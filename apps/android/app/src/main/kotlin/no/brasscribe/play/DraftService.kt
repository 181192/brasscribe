package no.brasscribe.play

import android.app.NotificationChannel
import android.app.NotificationManager
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
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .build()
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.VANILLA_ICE_CREAM) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROCESSING
        else ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type)
        return START_NOT_STICKY
    }

    /** The system's time limit for the type ran out: the draft goes on only while the app is in front. */
    override fun onTimeout(startId: Int, fgsType: Int) {
        stopSelf()
    }

    companion object {
        private const val CHANNEL = "draft"
        private const val NOTIFICATION_ID = 2

        /** Started when a draft starts; a start the system refuses (the app is not in front) leaves the draft running. */
        fun start(context: Context) {
            runCatching { context.startForegroundService(Intent(context, DraftService::class.java)) }
                .onFailure { android.util.Log.w("BrasscribePlay", "draft service not started", it) }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, DraftService::class.java))
        }
    }
}
