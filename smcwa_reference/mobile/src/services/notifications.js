import messaging from '@react-native-firebase/messaging';
import * as Device from 'expo-device';
import { Platform, PermissionsAndroid } from 'react-native';

export async function registerForPushNotificationsAsync() {
  let token;

  if (Platform.OS === 'android') {
    // Request permission for Android 13+
    if (Platform.Version >= 33) {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS
      );
      if (granted !== PermissionsAndroid.RESULTS.GRANTED) {
        console.log('Notification permission denied');
      }
    }
  }

  if (Device.isDevice) {
    try {
      // 1. Check/Request permission
      const authStatus = await messaging().requestPermission();
      const enabled =
        authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
        authStatus === messaging.AuthorizationStatus.PROVISIONAL;

      if (enabled) {
        // 2. Get FCM token
        token = await messaging().getToken();
        console.log('Direct FCM Token:', token);
      } else {
        console.log('Failed to get FCM permission');
      }
    } catch (e) {
      console.error('Error getting FCM token:', e);
    }
  } else {
    console.log("Not a physical device");
  }

  return token;
}
