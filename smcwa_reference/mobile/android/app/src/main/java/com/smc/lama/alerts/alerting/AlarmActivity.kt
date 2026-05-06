package com.smc.lama.alerts.alerting

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.smc.lama.alerts.R
import android.util.Log

class AlarmActivity : AppCompatActivity() {

    private val TAG = "AlarmActivity"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Ensure the activity is shown above the lock screen and turns the screen on
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
            val keyguardManager = getSystemService(android.content.Context.KEYGUARD_SERVICE) as android.app.KeyguardManager
            keyguardManager.requestDismissKeyguard(this, null)
        } else {
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                        or WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
                        or WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
                        or WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            )
        }
        
        // Increase brightness for better visibility during alert
        val params = window.attributes
        params.screenBrightness = WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_FULL
        window.attributes = params

        setContentView(R.layout.activity_alarm)

        val title = intent.getStringExtra(AlarmService.EXTRA_TITLE) ?: "🚨 CRITICAL ALERT"
        val message = intent.getStringExtra(AlarmService.EXTRA_MESSAGE) ?: "New alert received."
        val alertId = intent.getStringExtra(AlarmService.EXTRA_ALERT_ID)
        var siteName = intent.getStringExtra(AlarmService.EXTRA_SITE_NAME) ?: "Unknown Site"
        val serverIp = intent.getStringExtra(AlarmService.EXTRA_SERVER_IP) ?: ""
        if (serverIp.isNotEmpty()) {
            siteName = "$siteName ($serverIp)"
        }
        val alertType = intent.getStringExtra(AlarmService.EXTRA_ALERT_TYPE) ?: "System Alert"
        val hardware = intent.getStringExtra(AlarmService.EXTRA_HARDWARE) ?: "N/A"
        val threshold = intent.getStringExtra(AlarmService.EXTRA_THRESHOLD) ?: "N/A"
        val metricValue = intent.getStringExtra(AlarmService.EXTRA_METRIC_VALUE) ?: "Unknown"
        val severity = intent.getStringExtra(AlarmService.EXTRA_SEVERITY) ?: "critical"
        val status = intent.getStringExtra(AlarmService.EXTRA_STATUS) ?: "active"

        Log.d(TAG, "Displaying Alarm Activity for alertId: $alertId, site: $siteName, status: $status")

        findViewById<TextView>(R.id.tvTitle).text = title
        findViewById<TextView>(R.id.tvMessage).text = message
        findViewById<TextView>(R.id.tvSiteValue).text = siteName
        findViewById<TextView>(R.id.tvMetricValue).text = alertType
        findViewById<TextView>(R.id.tvHardwareValue).text = hardware
        findViewById<TextView>(R.id.tvThresholdValue).text = "$metricValue > $threshold"

        val ackBtn = findViewById<Button>(R.id.btnAcknowledge)
        if (status.lowercase() == "acknowledged") {
            ackBtn.text = "ALREADY ACKNOWLEDGED"
            ackBtn.setBackgroundColor(android.graphics.Color.GRAY)
        }

        // Dynamic background color based on severity
        if (severity.lowercase() == "warning") {
            findViewById<android.view.View>(R.id.rootLayout).setBackgroundColor(android.graphics.Color.parseColor("#FF9800"))
            ackBtn.setTextColor(android.graphics.Color.parseColor("#FF9800"))
        }

        findViewById<android.view.View>(R.id.btnAcknowledge).setOnClickListener {
            viewDetails(alertId, true)
        }

        findViewById<android.view.View>(R.id.btnViewDetails).setOnClickListener {
            viewDetails(alertId, false)
        }
    }

    private fun viewDetails(alertId: String?, autoAck: Boolean) {
        Log.d(TAG, "Opening App for alert: $alertId, autoAck: $autoAck")
        
        // 1. Stop the alarm sound locally so the user can talk/think
        val stopIntent = Intent(this, AlarmService::class.java).apply {
            action = AlarmService.ACTION_STOP
            putExtra(AlarmService.EXTRA_ALERT_ID, alertId)
        }
        startService(stopIntent)

        // 2. Open the React Native App to the IncomingAlertScreen
        // Pass full details in the URI so the App can show them immediately
        val siteName = intent.getStringExtra(AlarmService.EXTRA_SITE_NAME) ?: ""
        val serverIp = intent.getStringExtra(AlarmService.EXTRA_SERVER_IP) ?: ""
        val alertType = intent.getStringExtra(AlarmService.EXTRA_ALERT_TYPE) ?: ""
        val hardware = intent.getStringExtra(AlarmService.EXTRA_HARDWARE) ?: ""
        val mValue = intent.getStringExtra(AlarmService.EXTRA_METRIC_VALUE) ?: ""
        val tValue = intent.getStringExtra(AlarmService.EXTRA_THRESHOLD) ?: ""
        val severity = intent.getStringExtra(AlarmService.EXTRA_SEVERITY) ?: ""
        val message = intent.getStringExtra(AlarmService.EXTRA_MESSAGE) ?: ""
        val voiceAlert = intent.getStringExtra(AlarmService.EXTRA_VOICE_ALERT) ?: message

        val encodedSite = java.net.URLEncoder.encode(siteName, "UTF-8")
        val encodedIp = java.net.URLEncoder.encode(serverIp, "UTF-8")
        val encodedType = java.net.URLEncoder.encode(alertType, "UTF-8")
        val encodedHardware = java.net.URLEncoder.encode(hardware, "UTF-8")
        val encodedMValue = java.net.URLEncoder.encode(mValue, "UTF-8")
        val encodedTValue = java.net.URLEncoder.encode(tValue, "UTF-8")
        val encodedMsg = java.net.URLEncoder.encode(message, "UTF-8")
        val encodedVoice = java.net.URLEncoder.encode(voiceAlert, "UTF-8")

        val uriStr = "com.smc.lama.alerts://alert/$alertId?site_name=$encodedSite&server_ip=$encodedIp&alert_type=$encodedType&hardware_details=$encodedHardware&metric_value=$encodedMValue&threshold_value=$encodedTValue&severity=$severity&message=$encodedMsg&voice_alert=$encodedVoice&auto_ack=$autoAck"
        
        try {
            val deepLinkUri = android.net.Uri.parse(uriStr)
            val deepLinkIntent = Intent(Intent.ACTION_VIEW, deepLinkUri).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            startActivity(deepLinkIntent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to launch deep link: ${e.message}")
            launchMainApp()
        }
        
        finish()
    }

    private fun launchMainApp() {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        if (launchIntent != null) {
            launchIntent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            startActivity(launchIntent)
        }
    }

    override fun onBackPressed() {
        // Prevent dismissal via back button to force intentional acknowledgement
        Log.d(TAG, "Back pressed - ignoring to force acknowledgement")
    }
}
