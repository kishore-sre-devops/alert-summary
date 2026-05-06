package com.smc.lama.alerts.alerting

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

class AlarmActionReceiver : BroadcastReceiver() {

    private val TAG = "AlarmActionReceiver"

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        Log.d(TAG, "Received broadcast with action: $action")

        if (action == AlarmService.ACTION_ACK || action == AlarmService.ACTION_STOP) {
            val alertId = intent.getStringExtra(AlarmService.EXTRA_ALERT_ID)

            // We delegate the actual logic to the service to ensure it runs with a wakelock
            // and can perform networking operations reliably.
            val serviceIntent = Intent(context, AlarmService::class.java).apply {
                this.action = action
                putExtra(AlarmService.EXTRA_ALERT_ID, alertId)
            }
            context.startService(serviceIntent)
        }
    }
}
