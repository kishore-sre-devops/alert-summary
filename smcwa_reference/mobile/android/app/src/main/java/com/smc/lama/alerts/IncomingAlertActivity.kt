package com.smc.lama.alerts

import android.os.Build
import android.os.Bundle
import android.content.Intent
import com.facebook.react.ReactActivity

class IncomingAlertActivity : ReactActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.AppTheme)
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        }
        
        super.onCreate(null)
    }

    override fun getMainComponentName(): String = "main"

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
    }
}
