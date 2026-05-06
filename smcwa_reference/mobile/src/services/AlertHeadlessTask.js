import { AppRegistry, NativeModules } from 'react-native';
import messaging from '@react-native-firebase/messaging';

const { AlertingModule } = NativeModules;

// This function runs in background even when app is closed
const AlertHeadlessTask = async (remoteMessage) => {
    console.log('Headless task received alert:', remoteMessage);
    
    // Check if it's a critical alert payload
    if (remoteMessage && remoteMessage.data) {
        const { data } = remoteMessage;
        const severity = data.severity || 'critical';
        
        if (['critical', 'error', 'warning'].includes(severity.toLowerCase())) {
            const title = data.title || (severity.toLowerCase() === 'warning' ? "⚠️ WARNING ALERT" : "🚨 CRITICAL ALERT");
            const siteName = data.site_name || "Unknown Site";
            const alertType = data.alert_type || "System";
            const metricValue = data.metric_value !== undefined ? data.metric_value : "Unknown";
            const threshold = data.threshold_value !== undefined ? data.threshold_value : "Unknown";
            const time = data.alert_time || "";
            const body = data.message || data.body || `Site: ${siteName} - ${alertType}`;
            const alertId = data.alertId || data.alert_id || Date.now().toString();
            const hardware = data.hardware_details || 'N/A';
            const status = data.status || 'active';
            
            // PRIORITIZE backend voice alert string if available, else fallback to legacy construction
            const profMessage = data.voice_alert || `${severity.toUpperCase()} Alert for ${siteName}. Metric: ${alertType}. Value: ${metricValue} (Threshold: ${threshold}). ${time ? "Time: " + time : ""}`;
            
            if (AlertingModule && AlertingModule.triggerAlarm) {
                console.log('Triggering native alarm from Headless JS...');
                AlertingModule.triggerAlarm(
                    title, 
                    profMessage, 
                    alertId, 
                    severity,
                    siteName,
                    alertType,
                    hardware,
                    threshold,
                    status
                );
            } else {
                console.warn('AlertingModule is not available in Headless JS.');
            }
        }
    }
};

// Register headless task
AppRegistry.registerHeadlessTask(
    'ReactNativeFirebaseMessagingHeadlessTask',
    () => AlertHeadlessTask
);

export default AlertHeadlessTask;
