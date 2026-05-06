package com.smc.lama.alerts;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import android.os.PowerManager;
import android.content.Context;
import android.media.AudioAttributes;
import android.net.Uri;
import androidx.core.app.NotificationCompat;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;
import android.util.Log;
import java.util.Map;

public class SMCFirebaseMessagingService extends FirebaseMessagingService {

  private static final String TAG = "SMCFirebase";
  private static final String CHANNEL_ID = "smc_critical_alerts_v4";

  @Override
  public void onMessageReceived(RemoteMessage remoteMessage) {
    super.onMessageReceived(remoteMessage);
    Log.d(TAG, "FCM Message received!");

    Map<String, String> data = remoteMessage.getData();
    
    String title = "🚨 CRITICAL ALERT";
    String body = "New alert received - tap to view";
    String alertId = "0";
    String siteName = "Unknown Site";
    String severity = "CRITICAL";
    String alertType = "System Alert";

    if (data != null && !data.isEmpty()) {
      if (data.containsKey("severity")) 
        severity = data.get("severity");
      if (data.containsKey("site_name")) 
        siteName = data.get("site_name");
      if (data.containsKey("alert_type")) 
        alertType = data.get("alert_type");
      if (data.containsKey("alert_id")) 
        alertId = data.get("alert_id");
      
      title = "🚨 " + severity.toUpperCase() + " ALERT";
      body = "Site: " + siteName + " - " + alertType;
    }

    // Start the persistent alarm service with Nokia tune and TTS
    // This service handles the full screen notification itself
    startAlarmService(title, body, alertId, data);
  }

  private void wakeScreen() {
    try {
      PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
      PowerManager.WakeLock wakeLock = pm.newWakeLock(
        PowerManager.SCREEN_BRIGHT_WAKE_LOCK | 
        PowerManager.ACQUIRE_CAUSES_WAKEUP |
        PowerManager.ON_AFTER_RELEASE,
        "SMCLama:AlertWakeLock"
      );
      wakeLock.acquire(10 * 1000L); // 10 seconds
      Log.d(TAG, "Screen woken up!");
    } catch (Exception e) {
      Log.e(TAG, "Failed to wake screen: " + e.getMessage());
    }
  }

  private void showFullScreenNotification(
    String title, 
    String body,
    String alertId,
    Map<String, String> data
  ) {
    NotificationManager notificationManager =
      (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);

    // Create channel
    createNotificationChannel(notificationManager);

    // Intent to open app to IncomingAlert screen
    // Using deep link URL for React Native Linking compatibility
    Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse("com.smc.lama.alerts://alert/" + alertId));
    intent.setFlags(
      Intent.FLAG_ACTIVITY_NEW_TASK |
      Intent.FLAG_ACTIVITY_CLEAR_TOP |
      Intent.FLAG_ACTIVITY_SINGLE_TOP
    );
    intent.putExtra("screen", "IncomingAlert");
    intent.putExtra("alert_id", alertId);
    if (data != null) {
      for (Map.Entry<String, String> entry : data.entrySet()) {
        intent.putExtra(entry.getKey(), entry.getValue());
      }
    }

    int flags = PendingIntent.FLAG_UPDATE_CURRENT;
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
      flags |= PendingIntent.FLAG_IMMUTABLE;
    }

    PendingIntent pendingIntent = PendingIntent.getActivity(
      this, 0, intent, flags
    );

    // Full screen intent (same as pending intent)
    PendingIntent fullScreenPendingIntent = 
      PendingIntent.getActivity(
        this, 1, intent, flags
      );

    // Build notification
    NotificationCompat.Builder builder =
      new NotificationCompat.Builder(this, CHANNEL_ID)
        .setSmallIcon(R.mipmap.ic_launcher)
        .setContentTitle(title)
        .setContentText(body)
        .setPriority(NotificationCompat.PRIORITY_MAX)
        .setCategory(NotificationCompat.CATEGORY_CALL)
        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
        .setAutoCancel(false)
        .setOngoing(true)
        .setContentIntent(pendingIntent)
        // THIS WAKES THE SCREEN AND SHOWS FULL SCREEN
        .setFullScreenIntent(fullScreenPendingIntent, true)
        .setVibrate(new long[]{0, 500, 200, 500, 200, 500})
        .setLights(0xFFFF0000, 500, 500); // Red LED

    notificationManager.notify(1001, builder.build());
    Log.d(TAG, "Full screen notification shown!");
  }

  private void createNotificationChannel(NotificationManager manager) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      NotificationChannel channel = new NotificationChannel(
        CHANNEL_ID,
        "SMC Critical Alerts",
        NotificationManager.IMPORTANCE_HIGH
      );
      channel.setDescription("Critical infrastructure alerts");
      channel.enableVibration(true);
      channel.setVibrationPattern(new long[]{0, 500, 200, 500});
      channel.setShowBadge(true);
      channel.setBypassDnd(true);
      channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
      
      // Set alarm sound
      AudioAttributes audioAttributes = new AudioAttributes.Builder()
          .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
          .setUsage(AudioAttributes.USAGE_ALARM)
          .build();
      
      // Silence the system sound - our AlarmService will handle the Nokia Tune
      channel.setSound(null, null);
      
      manager.createNotificationChannel(channel);
      Log.d(TAG, "Notification channel created!");
    }
  }

  private void startAlarmService(String title, String body, String alertId, Map<String, String> data) {
    try {
      Intent serviceIntent = new Intent(this, com.smc.lama.alerts.alerting.AlarmService.class);
      serviceIntent.setAction(com.smc.lama.alerts.alerting.AlarmService.ACTION_START);
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_TITLE, title);
      
      // Construct professional message for TTS
      String severity = data.getOrDefault("severity", "Critical");
      String siteName = data.getOrDefault("site_name", "Unknown Site");
      String serverIp = data.getOrDefault("server_ip", "");
      if (!serverIp.isEmpty()) {
          siteName = siteName + " (" + serverIp + ")";
      }
      String alertType = data.getOrDefault("alert_type", "System");
      String value = data.getOrDefault("threshold_value", "Unknown");
      String time = data.getOrDefault("alert_time", "");
      String hardware = data.getOrDefault("hardware_details", "N/A");
      String status = data.getOrDefault("status", "Active");
      
      String profMessage = severity + " Alert for " + siteName + ". Metric Name " + alertType + ". Value " + value + ". " + (time.isEmpty() ? "" : "Time " + time);
      
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_MESSAGE, profMessage);
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_ALERT_ID, alertId);
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_SEVERITY, severity.toLowerCase());
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_SITE_NAME, siteName);
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_SERVER_IP, serverIp);
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_ALERT_TYPE, alertType);
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_HARDWARE, hardware);
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_THRESHOLD, value);
      serviceIntent.putExtra(com.smc.lama.alerts.alerting.AlarmService.EXTRA_STATUS, status);
      
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        startForegroundService(serviceIntent);
      } else {
        startService(serviceIntent);
      }
      Log.d(TAG, "AlarmService started for: " + alertId);
    } catch (Exception e) {
      Log.e(TAG, "Failed to start AlarmService: " + e.getMessage());
    }
  }

  @Override
  public void onNewToken(String token) {
    Log.d(TAG, "New FCM token: " + token);
  }
}
