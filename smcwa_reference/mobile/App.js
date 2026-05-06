import React, { useEffect, useState, useRef } from 'react';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet, View, ActivityIndicator, AppState } from 'react-native';
import * as SplashScreen from 'expo-splash-screen';
import { NavigationContainer, createNavigationContainerRef } from '@react-navigation/native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import messaging from '@react-native-firebase/messaging';
import * as Device from 'expo-device';
import { Platform, Linking, Alert } from 'react-native';
import Constants from 'expo-constants';
import appConfig from './app.json';
import AppNavigator from './src/navigation/AppNavigator';
import { useAuthStore } from './src/store/authStore';
import { useAlertStore } from './src/store/alertStore';
import { registerForPushNotificationsAsync } from './src/services/notifications';
import api from './src/services/api';
import EncryptedStorage from 'react-native-encrypted-storage';
import alertCallManager from './src/services/alertCallManager';

// Keep splash screen visible while loading
SplashScreen.preventAutoHideAsync().catch(() => {});

export const navigationRef = createNavigationContainerRef();

export default function App() {
  const [isReady, setIsReady] = useState(false);
  const { restoreToken, user } = useAuthStore();
  const { incomingCall, setIncomingCall, syncAlerts } = useAlertStore();
  const appState = useRef(AppState.currentState);

  // Auto-navigate to IncomingAlert when state changes
  useEffect(() => {
    if (incomingCall && navigationRef.isReady()) {
        const currentRoute = navigationRef.getCurrentRoute();
        
        // Scenario 1 & 2 Implementation: 
        // Use RESET to clear any previous alert screens and ensure we only have ONE active screen.
        if (currentRoute?.name !== 'IncomingAlert' || parseInt(currentRoute?.params?.id) !== parseInt(incomingCall.id)) {
            console.log('🚀 Journey Start: Resetting navigation for Alert #', incomingCall.id);
            navigationRef.reset({
                index: 0,
                routes: [{ 
                    name: 'IncomingAlert', 
                    params: { 
                        id: incomingCall.id, 
                        autoAck: incomingCall.autoAck // Scenario 1: true, Scenario 2: false
                    } 
                }],
            });
        }
    }
  }, [incomingCall, isReady]);

  // Helper function to register/refresh device status on backend
  const registerDevice = async () => {
    if (user && isReady) {
      try {
        const token = await messaging().getToken();
        if (token) {
          await api.post('/mobile/register', {
            push_token: token,
            device_os: Platform.OS,
            device_name: Device.modelName || 'Mobile Device',
            app_version: '1.0.53'
          });
        }
      } catch (error) {
        console.warn('❌ Device registration failed:', error.message);
      }
    }
  };

  // Handle deep links
  const handleDeepLink = ({ url }) => {
    if (url && url.includes('com.smc.lama.alerts://alert/')) {
        console.log('🔗 Deep link received:', url);
        
        const pathPart = url.split('://')[1].split('?')[0];
        const alertId = pathPart.split('/').pop();
        const queryPart = url.split('?')[1] || '';
        const params = {};
        
        // FIX: Handle Android's '+' encoding and URL decoding in one go
        queryPart.split('&').forEach(pair => {
            const [key, value] = pair.split('=');
            if (key && value) {
                params[key] = decodeURIComponent(value.replace(/\+/g, ' '));
            }
        });

        const { alerts } = useAlertStore.getState();
        const existing = alerts.find(a => parseInt(a.id) === parseInt(alertId));
        
        setIncomingCall({ 
            id: alertId, 
            title: params.alert_type || existing?.alert_type || "CRITICAL ALERT", 
            body: params.message || existing?.message || "Critical Alert",
            severity: params.severity || existing?.severity || 'critical',
            site_name: params.site_name || existing?.server_name || 'System',
            server_ip: params.server_ip || existing?.server_ip || '',
            hardware_details: params.hardware_details || existing?.hardware_details || 'N/A',
            alert_type: params.alert_type || existing?.alert_type || 'Alert',
            metric_value: params.metric_value || existing?.metric_value || '',
            threshold_value: params.threshold_value || existing?.threshold_value || '',
            voice_alert: params.voice_alert || params.message || existing?.voice_alert || '',
            autoAck: params.auto_ack === 'true'
        });
    }
  };

  useEffect(() => {
    const subscription = AppState.addEventListener('change', nextAppState => {
      if (appState.current.match(/inactive|background/) && nextAppState === 'active') {
        if (user) syncAlerts();
        registerDevice();
      }
      appState.current = nextAppState;
    });

    Linking.getInitialURL().then(url => { if (url) handleDeepLink({ url }); });
    const linkingSubscription = Linking.addEventListener('url', handleDeepLink);

    async function loadApp() {
      try {
        if (Platform.OS === 'android') {
          const hasPrompted = await EncryptedStorage.getItem('overlay_prompted');
          if (!hasPrompted) {
            Alert.alert(
              "Permissions Required",
              "SMC LAMA requires 'Display over other apps' to alert you during emergencies.",
              [{ text: "Open Settings", onPress: () => {
                  EncryptedStorage.setItem('overlay_prompted', 'true');
                  Linking.openSettings();
              }}]
            );
          }
        }
        await restoreToken();
        await registerForPushNotificationsAsync();
      } catch (e) {
        console.error('App load error:', e);
      } finally {
        setIsReady(true);
        SplashScreen.hideAsync().catch(() => {});
      }
    }

    loadApp();
    return () => {
      subscription.remove();
      linkingSubscription.remove();
    };
  }, []);

  useEffect(() => { if (isReady) registerDevice(); }, [user, isReady]);

  if (!isReady) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#fff' }}>
        <ActivityIndicator size="large" color="#1a237e" />
      </View>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <NavigationContainer ref={navigationRef}>
        <AppNavigator />
        <StatusBar style="auto" />
      </NavigationContainer>
    </GestureHandlerRootView>
  );
}
