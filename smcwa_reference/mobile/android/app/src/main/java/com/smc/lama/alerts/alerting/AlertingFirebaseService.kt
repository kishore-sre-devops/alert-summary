package com.smc.lama.alerts.alerting

import android.os.Build
import android.content.Intent
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import android.util.Log

class AlertingFirebaseService : FirebaseMessagingService() {

    private val TAG = "AlertingFirebaseService"

    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        Log.d(TAG, "FCM Message Received from: ${remoteMessage.from}")

        // Check if message contains a data payload.
        if (remoteMessage.data.isNotEmpty()) {
            val data = remoteMessage.data
            Log.d(TAG, "Message data payload: $data")

            // Extract data
            val title = data["title"] ?: "SMC LAMA Alert"
            val body = data["message"] ?: data["body"] ?: "You have a new critical alert."
            val alertId = data["alertId"] ?: data["alert_id"] ?: System.currentTimeMillis().toString()
            val severity = data["severity"] ?: "critical"
            val siteName = data["site_name"] ?: "Unknown Site"
            val serverIp = data["server_ip"] ?: ""
            val alertType = data["alert_type"] ?: "System"
            val mValue = data["metric_value"] ?: "Unknown"
            val tValue = data["threshold_value"] ?: "Unknown"
            val time = data["alert_time"] ?: ""
            val hardware = data["hardware_details"] ?: "N/A"
            val status = data["status"] ?: "active"
            val voiceAlert = data["voice_alert"]

            // Construction: Prioritize backend voice alert, fallback to legacy professional string
            val profMessage = voiceAlert ?: "$severity Alert for $siteName. Metric Name $alertType. Value $mValue. ${if (time.isNotEmpty()) "Time $time" else ""}"

            // Create an intent for the AlarmService
            val serviceIntent = Intent(this, AlarmService::class.java).apply {
                putExtra(AlarmService.EXTRA_TITLE, title)
                putExtra(AlarmService.EXTRA_MESSAGE, body) // THIS IS FOR UI
                putExtra(AlarmService.EXTRA_VOICE_ALERT, profMessage) // THIS IS FOR TTS
                putExtra(AlarmService.EXTRA_ALERT_ID, alertId)
                putExtra(AlarmService.EXTRA_SEVERITY, severity.lowercase())
                putExtra(AlarmService.EXTRA_SITE_NAME, siteName)
                putExtra(AlarmService.EXTRA_SERVER_IP, serverIp)
                putExtra(AlarmService.EXTRA_ALERT_TYPE, alertType)
                putExtra(AlarmService.EXTRA_HARDWARE, hardware)
                putExtra(AlarmService.EXTRA_METRIC_VALUE, mValue)
                putExtra(AlarmService.EXTRA_THRESHOLD, tValue)
                putExtra(AlarmService.EXTRA_STATUS, status)
                action = AlarmService.ACTION_START
            }

            // Android O+ requires startForegroundService.
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(serviceIntent)
                } else {
                    startService(serviceIntent)
                }
                Log.d(TAG, "AlarmService started for alert: $alertId")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start AlarmService: ${e.message}")
            }
        }
    }

    override fun onNewToken(token: String) {
        Log.d(TAG, "Refreshed token: $token")
    }
}
