import './shim-zlib'; 
import { registerRootComponent } from 'expo';
import messaging from '@react-native-firebase/messaging';
import { NativeModules, Platform } from 'react-native';
import App from './App';

// Register background handler
messaging().setBackgroundMessageHandler(async (remoteMessage) => {
  console.log('--- BACKGROUND FCM RECEIVED ---', remoteMessage);
  
  const { data } = remoteMessage;
  if (data && (data.severity === 'critical' || data.type === 'alert' || data.severity === 'warning')) {
    const title = data.title || `🚨 ${data.severity?.toUpperCase() || 'CRITICAL'} ALERT`;
    const message = data.message || data.body || 'New alert received';
    const alertId = data.alertId || data.alert_id || Date.now().toString();
    const severity = data.severity || 'critical';
    
    // Trigger native alarm service ONLY on non-Android (or if we really want JS to handle it)
    // On Android, SMCFirebaseMessagingService.java already does this more reliably.
    if (Platform.OS !== 'android' && NativeModules.AlertingModule) {
      NativeModules.AlertingModule.triggerAlarm(title, message, alertId, severity);
    } else {
      console.log('Skipping JS triggerAlarm on Android (Java handles it)');
    }
  }
});

registerRootComponent(App);
