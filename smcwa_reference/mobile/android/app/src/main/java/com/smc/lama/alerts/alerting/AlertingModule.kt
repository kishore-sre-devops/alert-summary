package com.smc.lama.alerts.alerting

import android.content.Intent
import android.os.Build
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.module.annotations.ReactModule

@ReactModule(name = AlertingModule.NAME)
class AlertingModule(reactContext: ReactApplicationContext) : ReactContextBaseJavaModule(reactContext) {

    companion object {
        const val NAME = "AlertingModule"
    }

    override fun getName() = NAME

    @ReactMethod
    fun triggerAlarm(title: String, message: String, alertId: String, severity: String?, siteName: String?, alertType: String?, hardware: String?, threshold: String?, status: String?) {
        val context = reactApplicationContext
        val serviceIntent = Intent(context, AlarmService::class.java).apply {
            putExtra(AlarmService.EXTRA_TITLE, title)
            putExtra(AlarmService.EXTRA_MESSAGE, message)
            putExtra(AlarmService.EXTRA_ALERT_ID, alertId)
            putExtra(AlarmService.EXTRA_SEVERITY, severity ?: "critical")
            putExtra(AlarmService.EXTRA_SITE_NAME, siteName)
            putExtra(AlarmService.EXTRA_ALERT_TYPE, alertType)
            putExtra(AlarmService.EXTRA_HARDWARE, hardware)
            putExtra(AlarmService.EXTRA_THRESHOLD, threshold)
            putExtra(AlarmService.EXTRA_STATUS, status)
            action = AlarmService.ACTION_START
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }

    @ReactMethod
    fun stopAlarm() {
        val context = reactApplicationContext
        val serviceIntent = Intent(context, AlarmService::class.java).apply {
            action = AlarmService.ACTION_STOP
        }
        context.startService(serviceIntent)
    }

    @ReactMethod
    fun acknowledge(alertId: String?) {
        val context = reactApplicationContext
        val serviceIntent = Intent(context, AlarmService::class.java).apply {
            action = AlarmService.ACTION_ACK
            putExtra(AlarmService.EXTRA_ALERT_ID, alertId)
        }
        context.startService(serviceIntent)
    }

    @ReactMethod
    fun addListener(eventName: String) {}

    @ReactMethod
    fun removeListeners(count: Int) {}
}
