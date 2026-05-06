package com.smc.lama.alerts;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import androidx.core.app.NotificationCompat;

public class AlertNotificationService {
    public static void showFullScreenAlert(Context context, String title, String body, String alertId) {
        NotificationManager notificationManager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);

        // Create high priority channel
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                "smc_critical_alerts",
                "SMC Critical Alerts",
                NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Critical infrastructure alerts");
            channel.enableVibration(true);
            channel.setVibrationPattern(new long[]{0, 500, 200, 500});
            channel.setBypassDnd(true);
            channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            notificationManager.createNotificationChannel(channel);
        }

        // Intent to open app when notification tapped
        Intent intent = new Intent(Intent.ACTION_VIEW, android.net.Uri.parse("com.smc.lama.alerts://alert/" + alertId));
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        intent.putExtra("alertId", alertId);
        intent.putExtra("screen", "IncomingAlert");

        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }

        PendingIntent pendingIntent = PendingIntent.getActivity(context, 0, intent, flags);

        // FULL SCREEN INTENT - wakes phone like a call
        PendingIntent fullScreenIntent = PendingIntent.getActivity(context, 1, intent, flags);

        Notification notification = new NotificationCompat.Builder(context, "smc_critical_alerts")
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(false)
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .setFullScreenIntent(fullScreenIntent, true) // THIS IS THE KEY LINE
            .setVibrate(new long[]{0, 500, 200, 500})
            .build();

        notificationManager.notify(1001, notification);
    }
}
