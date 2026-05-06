import React, { useEffect, useRef, useState } from 'react';
import { 
  View, Text, StyleSheet, TouchableOpacity, Dimensions, 
  Image, Platform, Vibration, TextInput, ScrollView,
  KeyboardAvoidingView, Alert, Keyboard
} from 'react-native';
import { useAlertStore } from '../store/alertStore';
import { useAuthStore } from '../store/authStore';
import { Audio } from 'expo-av';
import Tts from 'react-native-tts';
import NativeAlarm from '../services/NativeAlarm';
import { Ionicons } from '@expo/vector-icons';

const { width, height } = Dimensions.get('window');

export default function IncomingAlertScreen({ navigation, route }) {
  const { incomingCall, clearIncomingCall, acknowledgeAlert, alerts } = useAlertStore();
  const { user } = useAuthStore();
  const [showTimePicker, setShowTimePicker] = useState(route.params?.autoAck || false);
  const [selectedTime, setSelectedTime] = useState(2);
  const [justification, setJustification] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [successState, setSuccessState] = useState(false);

  // Check if this specific alert is already acknowledged in the global state
  const isHandled = incomingCall && alerts.find(a => {
    if (typeof incomingCall.id === 'string' && incomingCall.id.startsWith('test_')) {
        return a.id === incomingCall.id && a.mobile_status === 'acknowledged';
    }
    return parseInt(a.id) === parseInt(incomingCall.id) && a.mobile_status === 'acknowledged';
  });
  
  const soundRef = useRef(null);
  const ttsIntervalRef = useRef(null);

  useEffect(() => {
    // ALARM SOUND and TTS Logic (Platform specific)
    const startAlarm = async () => {
      try {
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: false,
          playsInSilentModeIOS: true,
          staysActiveInBackground: true,
          shouldDuckAndroid: true,
          playThroughEarpieceAndroid: false,
        });

        let soundSource;
        const severity = incomingCall?.severity?.toLowerCase() || 'critical';
        
        if (severity === 'warning') soundSource = require('../../assets/alert_warning.mp3');
        else if (severity === 'info') soundSource = require('../../assets/alert_info.mp3');
        else soundSource = require('../../assets/alert_critical.mp3');

        const { sound } = await Audio.Sound.createAsync(
           soundSource,
           { isLooping: true, shouldPlay: true, volume: 0.4 }
        );
        soundRef.current = sound;
      } catch (error) {
        console.log('Failed to load sound', error);
      }
      Vibration.vibrate([0, 500, 200, 500], true);
    };

    const setupTTS = async () => {
      try {
        if (!Tts) return;
        if (typeof Tts.getInitStatus === 'function') await Tts.getInitStatus();
        if (typeof Tts.setDefaultLanguage === 'function') Tts.setDefaultLanguage('en-IN');
        if (typeof Tts.setDefaultRate === 'function') Tts.setDefaultRate(0.5);
        if (Platform.OS === 'android' && typeof Tts.setIgnoreSilentBadge === 'function') {
            Tts.setIgnoreSilentBadge(true);
        }
      } catch(e) { console.log('TTS Init error:', e); }
    };

    const announceAlert = () => {
      if (!incomingCall || !Tts || typeof Tts.speak !== 'function') return;
      
      // PRIORITIZE backend voice alert string if available
      if (incomingCall.voice_alert) {
          try {
              Tts.speak(incomingCall.voice_alert, {
                androidParams: { KEY_PARAM_PAN: 0, KEY_PARAM_VOLUME: 1.0, KEY_PARAM_STREAM: 'STREAM_ALARM' },
              });
              return;
          } catch (e) {}
      }

      // Legacy fallback construction
      const site = incomingCall.site_name || 'Unknown IP';
      const type = incomingCall.alert_type || 'System';
      const severity = incomingCall.severity || 'Critical';
      const msg = `${severity} Alert for ${site}. Metric Name ${type}. Please Acknowledge.`;
      try {
          Tts.speak(msg, {
            androidParams: { KEY_PARAM_PAN: 0, KEY_PARAM_VOLUME: 1.0, KEY_PARAM_STREAM: 'STREAM_ALARM' },
          });
      } catch (e) {}
    };

    if (incomingCall) {
      if (Platform.OS === 'android') {
        Vibration.vibrate([0, 500, 200, 500], true);
        // Start TTS on Android too, as the native alarm service is stopped when entering this screen
        setupTTS().then(() => {
            announceAlert();
            ttsIntervalRef.current = setInterval(announceAlert, 30000);
        });
      } else {
        startAlarm();
        setupTTS().then(() => {
            announceAlert();
            ttsIntervalRef.current = setInterval(announceAlert, 30000);
        });
      }
    }

    return () => {
      if (soundRef.current) { soundRef.current.unloadAsync(); soundRef.current = null; }
      if (ttsIntervalRef.current) clearInterval(ttsIntervalRef.current);
      Tts.stop();
      Vibration.cancel();
      // REMOVED: NativeAlarm.acknowledge(incomingCall.id); 
      // We want the native alarm to keep ringing or stay in status bar until explicitly handled
    };
  }, [incomingCall]);

  useEffect(() => {
    // SCENARIO 1: Direct Acknowledge from Native Screen
    if (route.params?.autoAck && incomingCall) {
        console.log('🎯 Scenario 1: Auto-opening acknowledgement popup...');
        stopAllRinging();
        setShowTimePicker(true);
    }
  }, [route.params?.autoAck, incomingCall]);
const stopAllRinging = async () => {
  console.log('🔇 Stopping all sound and vibration...');
  Vibration.cancel(); // Scenario 1 & 2: Kill vibration immediately
  if (soundRef.current) {
      try { await soundRef.current.stopAsync(); await soundRef.current.unloadAsync(); } catch(e) {}
      soundRef.current = null;
  }
  if (ttsIntervalRef.current) clearInterval(ttsIntervalRef.current);
  Tts.stop();
  NativeAlarm.stopAlarm(); // Force kill native side just in case
};

const handleManualAckClick = () => {
  // SCENARIO 2: Stop ringing when manual button clicked inside details
  stopAllRinging();
  setShowTimePicker(true);
};

const handleSubmit = async () => {
    if (selectedTime >= 10 && !justification.trim()) {
        Alert.alert("Justification Required", "Please provide a brief reason for requiring 10 minutes or more.");
        return;
    }

    setSubmitting(true);
    try {
        const success = await acknowledgeAlert(incomingCall.id, selectedTime, justification);
        if (success) {
            setSuccessState(true);
            // SCENARIO 1 & 2: Show confirmation for 2 seconds then end the journey
            setTimeout(() => {
                clearIncomingCall();
                if (navigation.canGoBack()) {
                    navigation.goBack();
                } else {
                    navigation.replace('Main');
                }
            }, 2000);
        } else {
            Alert.alert("Error", "Failed to acknowledge alert. Check your network.");
        }
    } catch (e) {
        console.error("Ack failed", e);
    } finally {
        setSubmitting(false);
    }
};
  if (!incomingCall) return null;

  const severityColor = 
    incomingCall.severity?.toLowerCase() === 'critical' ? '#FF3B30' :
    incomingCall.severity?.toLowerCase() === 'warning' ? '#FF9500' : '#007AFF';

  return (
    <KeyboardAvoidingView 
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={[styles.container, { backgroundColor: severityColor }]}
    >
      <ScrollView 
        contentContainerStyle={styles.scrollContent} 
        bounces={false}
        keyboardShouldPersistTaps="always"
      >
        <View style={styles.card}>
            {successState ? (
                <View style={{ alignItems: 'center', py: 40 }}>
                    <Ionicons name="checkmark-circle" size={80} color="#4CD964" />
                    <Text style={{ fontSize: 24, fontWeight: 'bold', color: '#1a237e', marginTop: 20 }}>SUCCESS!</Text>
                    <Text style={{ fontSize: 16, color: '#666', marginTop: 10, textAlign: 'center' }}>
                        Acknowledged by:{"\n"}
                        <Text style={{ fontWeight: 'bold', color: '#1a237e' }}>{user?.email || 'System Admin'}</Text>
                    </Text>
                </View>
            ) : !showTimePicker ? (
                <>
                    <View style={styles.header}>
                        <Text style={styles.headerTitle}>🚨 {incomingCall.severity?.toUpperCase() || 'CRITICAL'} ALERT 🚨</Text>
                    </View>
                    
                    <View style={styles.logoContainer}>
                        <Image source={require('../../assets/icon.png')} style={styles.logo} resizeMode="contain" />
                    </View>

                    <View style={styles.details}>
                        <View style={styles.row}><Text style={styles.label}>Site / IP:</Text><Text style={styles.value}>{incomingCall.site_name || 'System'}{incomingCall.server_ip ? ` (${incomingCall.server_ip})` : ''}</Text></View>
                        <View style={styles.row}><Text style={styles.label}>Metric:</Text><Text style={styles.value}>{incomingCall.alert_type || 'Alert'}</Text></View>
                        <View style={styles.row}><Text style={styles.label}>Hardware:</Text><Text style={styles.value}>{incomingCall.hardware_details || 'System'}</Text></View>
                        {incomingCall.metric_value ? <View style={styles.row}><Text style={styles.label}>Value:</Text><Text style={styles.value}>{incomingCall.metric_value}</Text></View> : null}
                        {incomingCall.threshold_value ? <View style={styles.row}><Text style={styles.label}>Threshold:</Text><Text style={styles.value}>{incomingCall.threshold_value}</Text></View> : null}
                        <View style={styles.row}><Text style={styles.label}>Severity:</Text><Text style={[styles.value, { color: severityColor, fontWeight: '900' }]}>{incomingCall.severity?.toUpperCase() || 'CRITICAL'}</Text></View>
                    </View>

                    <TouchableOpacity 
                        style={[styles.ackButton, isHandled && { backgroundColor: '#888' }]} 
                        onPress={() => {
                            if (isHandled) {
                                clearIncomingCall();
                                if (navigation.canGoBack()) navigation.goBack();
                                else navigation.replace('Main');
                                return;
                            }
                            stopAllRinging();
                            setShowTimePicker(true);
                        }}
                    >
                        <Text style={styles.ackButtonText}>
                            {isHandled ? 'ALREADY ACKNOWLEDGED' : '✅ ACKNOWLEDGE'}
                        </Text>
                    </TouchableOpacity>

                    <TouchableOpacity 
                        onPress={() => {
                            stopAllRinging();
                            const alertData = { ...incomingCall, server_ip: incomingCall.server_ip || incomingCall.site_name, message: incomingCall.body || incomingCall.message, created_at: incomingCall.alert_time || new Date().toISOString() };
                            // Replace so that IncomingAlert is removed from history, allowing a clean transition
                            navigation.replace('AlertDetail', { alert: alertData });
                            // Clear state after a safe delay
                            setTimeout(() => clearIncomingCall(), 500);
                        }} 
                        style={{ marginTop: 25 }}
                    >
                        <Text style={{ color: '#007AFF', fontSize: 16, fontWeight: 'bold' }}>[ VIEW DETAILS ] 📋</Text>
                    </TouchableOpacity>
                </>
            ) : (
                <View style={styles.pickerContainer}>
                    <View style={{ backgroundColor: '#f0f2f5', padding: 12, borderRadius: 12, width: '100%', marginBottom: 15, borderLeftWidth: 4, borderLeftColor: '#1a237e' }}>
                        <Text style={{ fontSize: 13, color: '#666', fontWeight: 'bold', marginBottom: 2 }}>SERVER / IP</Text>
                        <Text style={{ fontSize: 16, color: '#1a237e', fontWeight: 'bold' }}>{incomingCall.site_name || 'System'}{incomingCall.server_ip ? ` (${incomingCall.server_ip})` : ''}</Text>
                        <Text style={{ fontSize: 13, color: '#666', fontWeight: 'bold', marginTop: 8, marginBottom: 2 }}>METRIC / HARDWARE</Text>
                        <Text style={{ fontSize: 15, color: '#333' }}>{incomingCall.alert_type || 'Alert'}{incomingCall.hardware_details ? ` [${incomingCall.hardware_details}]` : ''}</Text>
                    </View>

                    <Text style={styles.pickerTitle}>Resolution Commitment</Text>
                    <Text style={styles.pickerSubtitle}>How much time do you need to fix this?</Text>
                    
                    <View style={styles.timeGrid}>
                        {[2, 5, 10, 15, 30, 60, 120, 180, 360, 720, 1440, 2880].map((mins) => {
                            let label = `${mins}m`;
                            if (mins === 60) label = '1h';
                            else if (mins === 120) label = '2h';
                            else if (mins === 180) label = '3h';
                            else if (mins === 360) label = '6h';
                            else if (mins === 720) label = '12h';
                            else if (mins === 1440) label = '24h';
                            else if (mins === 2880) label = '2d';

                            return (
                                <TouchableOpacity 
                                    key={mins} 
                                    style={[styles.timeBtn, selectedTime === mins && styles.timeBtnSelected]}
                                    onPress={() => setSelectedTime(mins)}
                                >
                                    <Text style={[styles.timeBtnText, selectedTime === mins && styles.timeBtnTextSelected]}>
                                        {label}
                                    </Text>
                                </TouchableOpacity>
                            );
                        })}
                    </View>

                    {selectedTime >= 10 && (
                        <View style={styles.justificationArea}>
                            <Text style={styles.justificationLabel}>Mandatory Justification (>=10m):</Text>
                            <TextInput 
                                style={styles.input}
                                placeholder="Explain why more time is needed..."
                                multiline
                                numberOfLines={3}
                                value={justification}
                                onChangeText={setJustification}
                            />
                        </View>
                    )}

                    <TouchableOpacity 
                        style={[styles.submitBtn, submitting && { opacity: 0.7 }]} 
                        onPress={handleSubmit}
                        disabled={submitting}
                    >
                        <Text style={styles.submitBtnText}>
                            {submitting ? 'SAVING...' : 'CONFIRM & STOP ALARM'}
                        </Text>
                    </TouchableOpacity>

                    <TouchableOpacity onPress={() => setShowTimePicker(false)} style={{ marginTop: 15 }}>
                        <Text style={{ color: '#666' }}>Cancel</Text>
                    </TouchableOpacity>
                </View>
            )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  scrollContent: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  card: {
    width: width * 0.9,
    backgroundColor: '#fff',
    borderRadius: 24,
    alignItems: 'center',
    paddingBottom: 30,
    elevation: 20,
    shadowColor: '#000',
    shadowOpacity: 0.4,
    shadowRadius: 15,
    overflow: 'hidden',
  },
  header: { width: '100%', padding: 20, backgroundColor: '#333', alignItems: 'center' },
  headerTitle: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  logoContainer: { marginVertical: 20, backgroundColor: '#f8f9fa', padding: 15, borderRadius: 60 },
  logo: { width: 180, height: 180 },
  details: { width: '100%', paddingHorizontal: 30, marginBottom: 20 },
  row: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12, borderBottomWidth: 1, borderBottomColor: '#eee', paddingBottom: 5 },
  label: { fontSize: 15, color: '#666', fontWeight: '600' },
  value: { fontSize: 15, color: '#333', fontWeight: 'bold', maxWidth: '65%', textAlign: 'right' },
  ackButton: { backgroundColor: '#4CAF50', paddingHorizontal: 40, paddingVertical: 15, borderRadius: 30, elevation: 5 },
  ackButtonText: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  
  // Picker Styles
  pickerContainer: { width: '100%', padding: 20, alignItems: 'center' },
  pickerTitle: { fontSize: 22, fontWeight: 'bold', color: '#1a237e', marginBottom: 5 },
  pickerSubtitle: { fontSize: 14, color: '#666', marginBottom: 20 },
  timeGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8, marginBottom: 20 },
  timeBtn: { width: 68, height: 45, borderRadius: 12, borderWidth: 2, borderColor: '#e0e0e0', justifyContent: 'center', alignItems: 'center' },
  timeBtnSelected: { borderColor: '#1a237e', backgroundColor: '#e8eaf6' },
  timeBtnText: { fontSize: 16, fontWeight: 'bold', color: '#666' },
  timeBtnTextSelected: { color: '#1a237e' },
  justificationArea: { width: '100%', marginBottom: 20 },
  justificationLabel: { fontSize: 14, fontWeight: 'bold', color: '#d32f2f', marginBottom: 8 },
  input: { width: '100%', borderWidth: 1, borderColor: '#ddd', borderRadius: 12, padding: 12, height: 80, textAlignVertical: 'top', backgroundColor: '#f9f9f9' },
  submitBtn: { backgroundColor: '#1a237e', width: '100%', paddingVertical: 15, borderRadius: 12, alignItems: 'center', elevation: 3 },
  submitBtnText: { color: '#fff', fontSize: 16, fontWeight: 'bold' }
});
