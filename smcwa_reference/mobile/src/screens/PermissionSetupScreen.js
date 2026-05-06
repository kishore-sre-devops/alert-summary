import React, { useState, useEffect } from 'react';
import { 
  View, 
  Text, 
  StyleSheet, 
  TouchableOpacity, 
  ScrollView, 
  Linking, 
  Platform, 
  Alert, 
  Image, 
  AppState, 
  BackHandler, 
  NativeModules,
  ActivityIndicator
} from 'react-native';
import messaging from '@react-native-firebase/messaging';
import EncryptedStorage from 'react-native-encrypted-storage';

const PermissionSetupScreen = ({ navigation }) => {
  const [permissionStatus, setPermissionStatus] = useState({
    notifications: false,
    overlay: false,
    battery: false,
  });
  const [checking, setChecking] = useState(false);

  // Check permissions on mount and when returning from settings
  useEffect(() => {
    checkAllPermissions();

    const subscription = AppState.addEventListener('change', async (state) => {
      if (state === 'active') {
        setChecking(true);
        await checkAllPermissions();
        setChecking(false);
      }
    });

    const backHandler = BackHandler.addEventListener('hardwareBackPress', () => {
      showSkipConfirmation();
      return true;
    });

    return () => {
      subscription.remove();
      backHandler.remove();
    };
  }, []);

  const checkAllPermissions = async () => {
    try {
      // 1. Notification
      const notifStatus = await messaging().hasPermission();
      const notifGranted = notifStatus === messaging.AuthorizationStatus.AUTHORIZED || 
                           notifStatus === messaging.AuthorizationStatus.PROVISIONAL;

      // 2. Overlay - check via Settings (using a safer check if native module not ready)
      let overlayGranted = false;
      if (Platform.OS === 'android') {
        try {
          // In a real production app, we would have a custom NativeModule for this
          // For now, if we can't check, we maintain previous state or assume false
          overlayGranted = await NativeModules.PermissionModule?.checkOverlay() || permissionStatus.overlay;
        } catch (e) {
          console.log('Overlay check error:', e);
          overlayGranted = permissionStatus.overlay;
        }
      }

      // 3. Battery - cannot programmatically check easily in JS
      // We keep existing state if already marked done
      const batteryGranted = permissionStatus.battery;

      setPermissionStatus({
        notifications: notifGranted,
        overlay: overlayGranted,
        battery: batteryGranted,
      });
    } catch (error) {
      console.log('Permission check error:', error);
    }
  };

  const showSkipConfirmation = () => {
    Alert.alert(
      '⚠️ Skip Permission Setup?',
      'Without permissions you will NOT receive voice alerts on locked screen. Are you sure?',
      [
        { text: 'Continue Setup', style: 'cancel' },
        { text: 'Skip', style: 'destructive', onPress: finishSetup }
      ]
    );
  };

  const finishSetup = async () => {
    try {
      await EncryptedStorage.setItem('permissions_setup_done', 'true');
      if (navigation && navigation.reset) {
        navigation.reset({
          index: 0,
          routes: [{ name: 'Main' }],
        });
      }
    } catch (e) {
      console.error("Finish setup error:", e);
    }
  };

  const openOverlaySettings = async () => {
    try {
      if (Platform.OS === 'android') {
        // Direct intent for overlay
        await Linking.sendIntent('android.settings.action.MANAGE_OVERLAY_PERMISSION', [
          { key: 'package', value: 'com.smc.lama.alerts' }
        ]);
      }
    } catch (e) {
      await Linking.openSettings();
    }
  };

  const openBatterySettings = async () => {
    try {
      if (Platform.OS === 'android') {
        await Linking.sendIntent('android.settings.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS', [
          { key: 'package', value: 'com.smc.lama.alerts' }
        ]);
      }
    } catch (e) {
      await Linking.openSettings();
    }
    // Mark battery as done since user went to settings
    setPermissionStatus(prev => ({ ...prev, battery: true }));
  };

  const requestNotifications = async () => {
    const status = await messaging().requestPermission();
    const granted = status === messaging.AuthorizationStatus.AUTHORIZED || 
                    status === messaging.AuthorizationStatus.PROVISIONAL;
    setPermissionStatus(prev => ({ ...prev, notifications: granted }));
  };

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerEmoji}>🚨</Text>
        <Text style={styles.title}>Alert Permissions</Text>
        <Text style={styles.subtitle}>
          Required for call-like alert experience
        </Text>
      </View>

      <ScrollView style={styles.content}>
        {/* Step 1 - Notifications */}
        <View style={styles.step}>
          <View style={styles.stepLeft}>
            <Text style={styles.stepNumber}>1</Text>
          </View>
          <View style={styles.stepContent}>
            <Text style={styles.stepTitle}>🔔 Notifications</Text>
            <Text style={styles.stepDesc}>To receive alert notifications</Text>
            {!permissionStatus.notifications ? (
              <TouchableOpacity style={styles.enableButton} onPress={requestNotifications}>
                <Text style={styles.enableButtonText}>Enable Notifications</Text>
              </TouchableOpacity>
            ) : (
              <Text style={styles.doneText}>✅ Enabled</Text>
            )}
          </View>
        </View>

        {/* Step 2 - Display Over Apps */}
        <View style={styles.step}>
          <View style={styles.stepLeft}>
            <Text style={styles.stepNumber}>2</Text>
          </View>
          <View style={styles.stepContent}>
            <Text style={styles.stepTitle}>📱 Display Over Other Apps</Text>
            <Text style={styles.stepDesc}>
              To show alerts on lock screen.{'\n'}
              After opening settings:{'\n'}
              Find "SMC Lama" → Toggle ON
            </Text>
            <TouchableOpacity 
              style={[styles.enableButton, permissionStatus.overlay && styles.doneButton]} 
              onPress={openOverlaySettings}
            >
              <Text style={styles.enableButtonText}>
                {permissionStatus.overlay ? '✅ Open Settings Again' : 'Open Settings →'}
              </Text>
            </TouchableOpacity>
            {permissionStatus.overlay && (
              <Text style={styles.doneText}>✅ Enabled</Text>
            )}
          </View>
        </View>

        {/* Step 3 - Battery */}
        <View style={styles.step}>
          <View style={styles.stepLeft}>
            <Text style={styles.stepNumber}>3</Text>
          </View>
          <View style={styles.stepContent}>
            <Text style={styles.stepTitle}>🔋 Battery Optimization</Text>
            <Text style={styles.stepDesc}>
              To receive alerts when phone is idle.{'\n'}
              After opening settings:{'\n'}
              Select "Unrestricted"
            </Text>
            <TouchableOpacity 
              style={[styles.enableButton, permissionStatus.battery && styles.doneButton]} 
              onPress={openBatterySettings}
            >
              <Text style={styles.enableButtonText}>
                {permissionStatus.battery ? '✅ Done' : 'Open Settings →'}
              </Text>
            </TouchableOpacity>
            {permissionStatus.battery && (
              <Text style={styles.doneText}>✅ Enabled</Text>
            )}
          </View>
        </View>
      </ScrollView>

      {/* Finish Button - always enabled */}
      <View style={styles.footer}>
        {checking && (
          <Text style={styles.checkingText}>Checking permissions...</Text>
        )}
        <TouchableOpacity style={styles.finishButton} onPress={finishSetup}>
          <Text style={styles.finishButtonText}>I've Enabled All - Continue →</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.skipLink} onPress={showSkipConfirmation}>
          <Text style={styles.skipLinkText}>Skip (not recommended)</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f0f4ff' },
  header: { 
    backgroundColor: '#1a237e', 
    padding: 30, 
    alignItems: 'center', 
    paddingTop: 50,
  },
  headerEmoji: { fontSize: 40, marginBottom: 10 },
  title: { fontSize: 24, fontWeight: 'bold', color: 'white', marginBottom: 5 },
  subtitle: { fontSize: 13, color: '#c5cae9', textAlign: 'center' },
  content: { flex: 1, padding: 15 },
  step: { 
    flexDirection: 'row', 
    backgroundColor: 'white', 
    borderRadius: 12, 
    padding: 15, 
    marginBottom: 12,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
  },
  stepLeft: { 
    width: 35, 
    height: 35, 
    borderRadius: 18, 
    backgroundColor: '#1a237e', 
    justifyContent: 'center', 
    alignItems: 'center', 
    marginRight: 12,
    marginTop: 3,
  },
  stepNumber: { color: 'white', fontWeight: 'bold', fontSize: 16 },
  stepContent: { flex: 1 },
  stepTitle: { fontSize: 16, fontWeight: 'bold', marginBottom: 5, color: '#1a237e' },
  stepDesc: { fontSize: 13, color: '#666', lineHeight: 20, marginBottom: 10 },
  enableButton: { 
    backgroundColor: '#1a237e', 
    padding: 10, 
    borderRadius: 8, 
    alignItems: 'center', 
    marginTop: 5,
  },
  doneButton: { backgroundColor: '#2e7d32' },
  enableButtonText: { color: 'white', fontWeight: 'bold', fontSize: 13 },
  doneText: { color: '#2e7d32', fontWeight: 'bold', marginTop: 8, fontSize: 14 },
  footer: { 
    padding: 15, 
    backgroundColor: 'white', 
    elevation: 8,
    borderTopWidth: 1,
    borderTopColor: '#eee'
  },
  checkingText: { textAlign: 'center', color: '#666', fontSize: 12, marginBottom: 5 },
  finishButton: { 
    backgroundColor: '#2e7d32', 
    padding: 16, 
    borderRadius: 10, 
    alignItems: 'center', 
    marginBottom: 10,
  },
  finishButtonText: { color: 'white', fontSize: 16, fontWeight: 'bold' },
  skipLink: { alignItems: 'center', padding: 8 },
  skipLinkText: { color: '#999', fontSize: 12 },
});

export default PermissionSetupScreen;
