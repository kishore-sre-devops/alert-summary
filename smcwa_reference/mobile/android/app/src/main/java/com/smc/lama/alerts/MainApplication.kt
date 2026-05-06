package com.smc.lama.alerts

import android.app.Application
import android.content.res.Configuration

import com.facebook.react.PackageList
import com.facebook.react.ReactApplication
import com.facebook.react.ReactNativeHost
import com.facebook.react.ReactPackage
import com.facebook.react.ReactHost
import com.facebook.react.defaults.DefaultNewArchitectureEntryPoint.load
import com.facebook.react.defaults.DefaultReactNativeHost
import com.facebook.soloader.SoLoader

import expo.modules.ApplicationLifecycleDispatcher
import expo.modules.ReactNativeHostWrapper

import com.smc.lama.alerts.alerting.AlertingPackage

class MainApplication : Application(), ReactApplication {

  override val reactNativeHost: ReactNativeHost = ReactNativeHostWrapper(
        this,
        object : DefaultReactNativeHost(this) {
          override fun getPackages(): List<ReactPackage> {
            val packages = PackageList(this).packages.toMutableList()
            // Packages that cannot be autolinked yet can be added manually here
            packages.add(AlertingPackage())
            return packages
          }

          override fun getJSMainModuleName(): String = "index"

          override fun getUseDeveloperSupport(): Boolean = BuildConfig.DEBUG

          override val isNewArchEnabled: Boolean = BuildConfig.IS_NEW_ARCHITECTURE_ENABLED
          override val isHermesEnabled: Boolean = BuildConfig.IS_HERMES_ENABLED
      }
  )

  override val reactHost: ReactHost
    get() = ReactNativeHostWrapper.createReactHost(applicationContext, reactNativeHost)

  override fun onCreate() {
    super.onCreate()
    SoLoader.init(this, false)
    if (BuildConfig.IS_NEW_ARCHITECTURE_ENABLED) {
      // If you opted-in for the New Architecture, we load the native entry point for this app.
      load()
    }
    
    // Create Notification Channel for High Priority Alerts
    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
      val channel = android.app.NotificationChannel(
        "smc_critical_alerts",
        "SMC Critical Alerts",
        android.app.NotificationManager.IMPORTANCE_HIGH
      )
      channel.description = "Critical infrastructure alerts"
      channel.enableVibration(true)
      channel.vibrationPattern = longArrayOf(0, 500, 200, 500)
      channel.setShowBadge(true)
      channel.setBypassDnd(true)
      channel.lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
      val audioAttributes = android.media.AudioAttributes.Builder()
          .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SONIFICATION)
          .setUsage(android.media.AudioAttributes.USAGE_ALARM)
          .build()
      
      val soundUri = android.net.Uri.parse("android.resource://" + packageName + "/raw/alarm")
      channel.setSound(soundUri, audioAttributes)

      val manager = getSystemService(android.app.NotificationManager::class.java)
      manager?.createNotificationChannel(channel)
    }

    ApplicationLifecycleDispatcher.onApplicationCreate(this)
  }

  override fun onConfigurationChanged(newConfig: Configuration) {
    super.onConfigurationChanged(newConfig)
    ApplicationLifecycleDispatcher.onConfigurationChanged(this, newConfig)
  }
}
