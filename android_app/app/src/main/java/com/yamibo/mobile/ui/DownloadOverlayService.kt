package com.yamibo.mobile.ui

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.core.app.NotificationCompat

class DownloadOverlayService : Service() {
    private val channelId = "yamibo_download_channel"
    private val notifyId = 4242

    private var windowManager: WindowManager? = null
    private var overlayRoot: LinearLayout? = null
    private var overlayTitle: TextView? = null
    private var overlayProgressText: TextView? = null
    private var overlayProgress: ProgressBar? = null
    private var overlayEnabled: Boolean = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return try {
            ensureChannel()

            when (intent?.action) {
                ACTION_START -> {
                    overlayEnabled = intent.getBooleanExtra(EXTRA_OVERLAY_ENABLED, false)
                    val title = intent.getStringExtra(EXTRA_TITLE) ?: "后台下载进行中"
                    val done = intent.getIntExtra(EXTRA_DONE, 0)
                    val total = intent.getIntExtra(EXTRA_TOTAL, 100)
                    val eta = intent.getStringExtra(EXTRA_ETA) ?: "--:--"

                    startForeground(notifyId, buildNotification(title, done, total, eta))
                    if (overlayEnabled) {
                        ensureOverlay()
                        updateOverlay(title, done, total, eta)
                    }
                }

                ACTION_UPDATE -> {
                    val title = intent.getStringExtra(EXTRA_TITLE) ?: "后台下载进行中"
                    val done = intent.getIntExtra(EXTRA_DONE, 0)
                    val total = intent.getIntExtra(EXTRA_TOTAL, 100)
                    val eta = intent.getStringExtra(EXTRA_ETA) ?: "--:--"

                    startForeground(notifyId, buildNotification(title, done, total, eta))
                    if (overlayEnabled) {
                        ensureOverlay()
                        updateOverlay(title, done, total, eta)
                    }
                }

                ACTION_STOP -> {
                    removeOverlay()
                    stopForeground(STOP_FOREGROUND_REMOVE)
                    stopSelf()
                }
            }

            START_NOT_STICKY
        } catch (e: Exception) {
            Log.e(TAG, "DownloadOverlayService onStartCommand failed", e)
            removeOverlay()
            runCatching { stopForeground(STOP_FOREGROUND_REMOVE) }
            stopSelf()
            START_NOT_STICKY
        }
    }

    override fun onDestroy() {
        removeOverlay()
        super.onDestroy()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val existing = manager.getNotificationChannel(channelId)
            if (existing == null) {
                val channel = NotificationChannel(
                    channelId,
                    "Yamibo 后台下载",
                    NotificationManager.IMPORTANCE_LOW
                )
                channel.description = "后台抓取进度通知"
                manager.createNotificationChannel(channel)
            }
        }
    }

    private fun buildNotification(title: String, done: Int, total: Int, eta: String): Notification {
        val appIntent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            appIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val safeTotal = if (total <= 0) 1 else total
        val safeDone = done.coerceIn(0, safeTotal)
        val progress = ((safeDone * 100.0) / safeTotal).toInt().coerceIn(0, 100)

        return NotificationCompat.Builder(this, channelId)
            .setContentTitle("Yamibo 后台下载")
            .setContentText("$title  [$safeDone/$safeTotal]  剩余: $eta")
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setProgress(100, progress, false)
            .setContentIntent(pendingIntent)
            .build()
    }

    private fun ensureOverlay() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            return
        }
        if (overlayRoot != null) {
            return
        }

        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(20, 16, 20, 16)
            setBackgroundColor(Color.parseColor("#CC7F1D1D"))
        }
        val titleView = TextView(this).apply {
            setTextColor(Color.WHITE)
            textSize = 13f
            text = "后台下载进行中"
        }
        val progressView = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            progress = 0
        }
        val progressTextView = TextView(this).apply {
            setTextColor(Color.parseColor("#FFE5E7EB"))
            textSize = 12f
            text = "0/0"
        }

        root.addView(titleView)
        root.addView(progressView)
        root.addView(progressTextView)

        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        val lp = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            x = 18
            y = 120
        }

        runCatching {
            windowManager?.addView(root, lp)
        }.onSuccess {
            overlayRoot = root
            overlayTitle = titleView
            overlayProgress = progressView
            overlayProgressText = progressTextView
        }.onFailure { e ->
            Log.e(TAG, "Failed to attach download overlay window", e)
        }
    }

    private fun updateOverlay(title: String, done: Int, total: Int, eta: String) {
        val safeTotal = if (total <= 0) 1 else total
        val safeDone = done.coerceIn(0, safeTotal)
        val progress = ((safeDone * 100.0) / safeTotal).toInt().coerceIn(0, 100)

        overlayTitle?.text = title
        overlayProgress?.progress = progress
        overlayProgressText?.text = "$safeDone/$safeTotal  剩余:$eta"
    }

    private fun removeOverlay() {
        overlayRoot?.let { view ->
            runCatching { windowManager?.removeView(view) }
        }
        overlayRoot = null
        overlayTitle = null
        overlayProgressText = null
        overlayProgress = null
    }

    companion object {
        private const val ACTION_START = "com.yamibo.mobile.action.START_DL_OVERLAY"
        private const val ACTION_UPDATE = "com.yamibo.mobile.action.UPDATE_DL_OVERLAY"
        private const val ACTION_STOP = "com.yamibo.mobile.action.STOP_DL_OVERLAY"

        private const val EXTRA_TITLE = "extra_title"
        private const val EXTRA_DONE = "extra_done"
        private const val EXTRA_TOTAL = "extra_total"
        private const val EXTRA_ETA = "extra_eta"
        private const val EXTRA_OVERLAY_ENABLED = "extra_overlay_enabled"
        private const val TAG = "DownloadOverlayService"

        fun start(context: Context, title: String, overlayEnabled: Boolean) {
            val intent = Intent(context, DownloadOverlayService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_TITLE, title)
                putExtra(EXTRA_DONE, 0)
                putExtra(EXTRA_TOTAL, 100)
                putExtra(EXTRA_ETA, "--:--")
                putExtra(EXTRA_OVERLAY_ENABLED, overlayEnabled)
            }
            runCatching {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            }.onFailure { e ->
                Log.e(TAG, "Failed to start foreground download service", e)
            }
        }

        fun update(context: Context, title: String, done: Int, total: Int, eta: String) {
            val intent = Intent(context, DownloadOverlayService::class.java).apply {
                action = ACTION_UPDATE
                putExtra(EXTRA_TITLE, title)
                putExtra(EXTRA_DONE, done)
                putExtra(EXTRA_TOTAL, total)
                putExtra(EXTRA_ETA, eta)
            }
            runCatching {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            }.onFailure { e ->
                Log.e(TAG, "Failed to send progress update to service", e)
            }
        }

        fun stop(context: Context) {
            val intent = Intent(context, DownloadOverlayService::class.java).apply {
                action = ACTION_STOP
            }
            runCatching {
                context.startService(intent)
            }.onFailure { e ->
                Log.e(TAG, "Failed to stop foreground download service", e)
            }
        }
    }
}
