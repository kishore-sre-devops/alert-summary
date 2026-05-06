package com.smc.lama.alerts.alerting

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.Vibrator
import android.speech.tts.TextToSpeech
import android.util.Log
import androidx.core.app.NotificationCompat
import com.smc.lama.alerts.R
import java.util.Locale

class AlarmService : Service(), TextToSpeech.OnInitListener {

    private val TAG = "AlarmService"
    private val NOTIFICATION_ID = 1
    private val CHANNEL_ID = "SMC_ALARM_CHANNEL_V5"

    private var wakeLock: PowerManager.WakeLock? = null
    private var mediaPlayer: MediaPlayer? = null
    private var tts: TextToSpeech? = null
    private var vibrator: Vibrator? = null
    private var alertMessage: String? = null
    private var currentAlertId: String? = null
    private var currentSiteName: String? = null
    private var currentAlertType: String? = null
    private var currentHardware: String? = null
    private var currentThreshold: String? = null
    private var currentMetricValue: String? = null
    private var currentStatus: String? = null
    private var currentServerIp: String? = null
    private var currentSeverity: String = "critical"
    private var voiceAlertText: String? = null
    private var isTtsReady = false
    private val mainHandler = Handler(Looper.getMainLooper())
    private var isActive = false
    private var isLoopRunning = false

    companion object {
        const val ACTION_START = "com.smc.lama.alerts.START"
        const val ACTION_STOP = "com.smc.lama.alerts.STOP"
        const val ACTION_ACK = "com.smc.lama.alerts.ACK"

        const val EXTRA_TITLE = "EXTRA_TITLE"
        const val EXTRA_MESSAGE = "EXTRA_MESSAGE"
        const val EXTRA_VOICE_ALERT = "EXTRA_VOICE_ALERT"
        const val EXTRA_ALERT_ID = "EXTRA_ALERT_ID"
        const val EXTRA_SEVERITY = "EXTRA_SEVERITY"
        const val EXTRA_SITE_NAME = "EXTRA_SITE_NAME"
        const val EXTRA_ALERT_TYPE = "EXTRA_ALERT_TYPE"
        const val EXTRA_HARDWARE = "EXTRA_HARDWARE"
        const val EXTRA_METRIC_VALUE = "EXTRA_METRIC_VALUE"
        const val EXTRA_THRESHOLD = "EXTRA_THRESHOLD"
        const val EXTRA_STATUS = "EXTRA_STATUS"
        const val EXTRA_SERVER_IP = "EXTRA_SERVER_IP"
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: return START_NOT_STICKY
        Log.d(TAG, "onStartCommand: $action")

        when (action) {
            ACTION_START -> {
                val title = intent.getStringExtra(EXTRA_TITLE) ?: "Critical Alert"
                val message = intent.getStringExtra(EXTRA_MESSAGE) ?: "No message."
                val voiceAlert = intent.getStringExtra(EXTRA_VOICE_ALERT) ?: message
                val alertId = intent.getStringExtra(EXTRA_ALERT_ID)
                val severity = intent.getStringExtra(EXTRA_SEVERITY) ?: "critical"
                val siteName = intent.getStringExtra(EXTRA_SITE_NAME) ?: "System"
                val serverIp = intent.getStringExtra(EXTRA_SERVER_IP) ?: ""
                val alertType = intent.getStringExtra(EXTRA_ALERT_TYPE) ?: "Alert"
                val hardware = intent.getStringExtra(EXTRA_HARDWARE) ?: "N/A"
                val metricValue = intent.getStringExtra(EXTRA_METRIC_VALUE) ?: "N/A"
                val threshold = intent.getStringExtra(EXTRA_THRESHOLD) ?: "N/A"
                val status = intent.getStringExtra(EXTRA_STATUS) ?: "Active"
                handleStartAlarm(title, message, voiceAlert, alertId, severity, siteName, serverIp, alertType, hardware, metricValue, threshold, status)
            }
            ACTION_ACK, ACTION_STOP -> {
                Log.d(TAG, "Stopping service via $action")
                cleanupAndStop()
            }
        }
        return START_STICKY
    }

    private fun cleanupAndStop() {
        isActive = false
        isLoopRunning = false
        
        stopNokiaTune()
        try { tts?.stop() } catch (e: Exception) {}
        try { vibrator?.cancel() } catch (e: Exception) {}
        
        mainHandler.removeCallbacksAndMessages(null)
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.cancel(NOTIFICATION_ID)
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    private fun handleStartAlarm(title: String, message: String, voiceAlert: String, alertId: String?, severity: String, siteName: String?, serverIp: String?, alertType: String?, hardware: String?, metricValue: String?, threshold: String?, status: String?) {
        alertMessage = message
        voiceAlertText = voiceAlert
        currentAlertId = alertId
        currentSeverity = severity
        currentSiteName = siteName
        currentServerIp = serverIp
        currentAlertType = alertType
        currentHardware = hardware
        currentMetricValue = metricValue
        currentThreshold = threshold
        currentStatus = status

        if (isActive) {
            val notification = createNotification(title, message)
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.notify(NOTIFICATION_ID, notification)
            return
        }

        isActive = true
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        // Aggressive WakeLock to force screen ON and keep CPU alive
        wakeLock = pm.newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK or 
            PowerManager.ACQUIRE_CAUSES_WAKEUP or 
            PowerManager.ON_AFTER_RELEASE, 
            "SMC::AlarmWakeLock"
        ).apply {
            acquire(10 * 60 * 1000L)
        }

        // Direct Activity Launch to bypass notification downgrading
        launchAlarmActivity(title, message)

        // Start Vibration manually
        vibrator = getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        val pattern = longArrayOf(0, 1000, 500, 1000)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator?.vibrate(VibrationEffect.createWaveform(pattern, 0))
        } else {
            vibrator?.vibrate(pattern, 0)
        }

        createNotificationChannel()
        startForeground(NOTIFICATION_ID, createNotification(title, message))

        if (tts == null) { tts = TextToSpeech(this, this) }
        if (!isLoopRunning) { startSequentialLoop() }
    }

    private fun launchAlarmActivity(title: String, message: String) {
        val launchIntent = Intent(this, AlarmActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or 
                    Intent.FLAG_ACTIVITY_NO_USER_ACTION or 
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
            putExtra(EXTRA_TITLE, title)
            putExtra(EXTRA_MESSAGE, alertMessage)
            putExtra(EXTRA_VOICE_ALERT, voiceAlertText)
            putExtra(EXTRA_ALERT_ID, currentAlertId)
            putExtra(EXTRA_SITE_NAME, currentSiteName)
            putExtra(EXTRA_SERVER_IP, currentServerIp)
            putExtra(EXTRA_ALERT_TYPE, currentAlertType)
            putExtra(EXTRA_SEVERITY, currentSeverity)
            putExtra(EXTRA_HARDWARE, currentHardware)
            putExtra(EXTRA_METRIC_VALUE, currentMetricValue)
            putExtra(EXTRA_THRESHOLD, currentThreshold)
            putExtra(EXTRA_STATUS, currentStatus)
        }

        // Try to launch immediately and also after a delay to ensure it catches the OS window
        try {
            startActivity(launchIntent)
            Log.d(TAG, "Direct Activity Launch attempted immediately")
        } catch (e: Exception) {
            Log.e(TAG, "Immediate launch failed: ${e.message}")
        }

        mainHandler.postDelayed({
            if (isActive) {
                try {
                    startActivity(launchIntent)
                    Log.d(TAG, "Delayed Direct Activity Launch attempted")
                } catch (e: Exception) {
                    Log.e(TAG, "Delayed Direct Launch failed: ${e.message}")
                }
            }
        }, 800)
    }

    private fun startSequentialLoop() {
        if (!isActive) return
        isLoopRunning = true
        playNokiaTune()
        mainHandler.postDelayed({
            if (isActive) {
                stopNokiaTune()
                mainHandler.postDelayed({
                    if (isActive) {
                        speakProfessionalMessage()
                        mainHandler.postDelayed({
                            if (isActive) startSequentialLoop()
                        }, 20000)
                    }
                }, 1000)
            }
        }, 10000)
    }

    private fun playNokiaTune() {
        val res = when (currentSeverity.lowercase()) {
            "warning" -> R.raw.assets_alert_warning
            "info" -> R.raw.assets_alert_info
            else -> R.raw.assets_alert_critical
        }
        val uri = Uri.parse("android.resource://${packageName}/${res}")
        try {
            mediaPlayer?.release()
            mediaPlayer = MediaPlayer().apply {
                setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build())
                setDataSource(applicationContext, uri)
                isLooping = true
                prepare()
                start()
            }
        } catch (e: Exception) { Log.e(TAG, "Media Error: ${e.message}") }
    }

    private fun stopNokiaTune() {
        try { mediaPlayer?.stop(); mediaPlayer?.release() } catch (e: Exception) {}
        mediaPlayer = null
    }

    private fun speakProfessionalMessage() {
        if (isTtsReady) {
            val textToSpeak = voiceAlertText ?: alertMessage
            if (textToSpeak != null) {
                tts?.speak(textToSpeak, TextToSpeech.QUEUE_FLUSH, null, "SMC")
                Log.d(TAG, "Speaking professional message: $textToSpeak")
            }
        }
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            val result = tts?.setLanguage(Locale("en", "IN"))
            if (result == TextToSpeech.LANG_MISSING_DATA || result == TextToSpeech.LANG_NOT_SUPPORTED) {
                tts?.language = Locale.US
            }
            isTtsReady = true
            Log.d(TAG, "TTS Initialized successfully with language: ${tts?.language}")
        } else {
            Log.e(TAG, "TTS Initialization failed!")
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, "SMC Critical Alerts", NotificationManager.IMPORTANCE_HIGH).apply {
                setSound(null, null)
                enableVibration(true)
                setBypassDnd(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(channel)
        }
    }

    private fun createNotification(title: String, message: String): Notification {
        val fullScreenIntent = Intent(this, AlarmActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_USER_ACTION
            putExtra(EXTRA_TITLE, title)
            putExtra(EXTRA_MESSAGE, alertMessage)
            putExtra(EXTRA_VOICE_ALERT, voiceAlertText)
            putExtra(EXTRA_ALERT_ID, currentAlertId)

            putExtra(EXTRA_SITE_NAME, currentSiteName)
            putExtra(EXTRA_SERVER_IP, currentServerIp)
            putExtra(EXTRA_ALERT_TYPE, currentAlertType)
            putExtra(EXTRA_SEVERITY, currentSeverity)
            putExtra(EXTRA_HARDWARE, currentHardware)
            putExtra(EXTRA_METRIC_VALUE, currentMetricValue)
            putExtra(EXTRA_THRESHOLD, currentThreshold)
            putExtra(EXTRA_STATUS, currentStatus)
        }
        
        val pendingIntentFlags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        
        val fullScreenPendingIntent = PendingIntent.getActivity(this, 0, fullScreenIntent, pendingIntentFlags)

        val stopIntent = Intent(this, AlarmActionReceiver::class.java).apply {
            action = ACTION_STOP
            putExtra(EXTRA_ALERT_ID, currentAlertId)
        }
        val stopPendingIntent = PendingIntent.getBroadcast(this, 2, stopIntent, pendingIntentFlags)

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_CALL) // Treat as incoming call
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setOngoing(true)
            .setAutoCancel(false)
            .setFullScreenIntent(fullScreenPendingIntent, true)
            .setDeleteIntent(stopPendingIntent)
            .build()
    }

    override fun onDestroy() {
        cleanupAndStop()
        wakeLock?.let { if (it.isHeld) it.release() }
        super.onDestroy()
    }

    override fun onBind(intent: Intent): IBinder? = null
}
