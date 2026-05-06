import React, { useState } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert } from 'react-native';
import { useAuthStore } from '../store/authStore';
import { useAlertStore } from '../store/alertStore';
import { format } from 'date-fns';

export default function AlertDetailScreen({ route, navigation }) {
  const { alert: initialAlert } = route.params;
  const { user } = useAuthStore();
  const { alerts, setIncomingCall } = useAlertStore();
  const [isAcknowledging, setIsAcknowledging] = useState(false);

  // Find the live version of this alert in the global store to get updated status
  const alert = alerts.find(a => parseInt(a.id) === parseInt(initialAlert.id)) || initialAlert;

  const canAcknowledge = alert.can_acknowledge !== undefined ? 
                         alert.can_acknowledge : 
                         (user?.role === 'admin' || user?.role === 'operator');

  const handleAcknowledge = () => {
    if (!canAcknowledge) {
      Alert.alert("Permission Denied", "You are not authorized to acknowledge this alert.");
      return;
    }
    
    if (alert.mobile_status === 'acknowledged') {
      Alert.alert("Already Handled", `This alert was already acknowledged by ${alert.acknowledged_by_name || 'another user'}.`);
      return;
    }
    
    setIncomingCall({
      id: alert.id,
      title: alert.alert_type || "SMC ALERT",
      body: alert.message || "Critical Alert",
      severity: alert.severity || 'critical',
      site_name: alert.server_name || 'System',
      server_ip: alert.server_ip || '',
      alert_type: alert.alert_type || 'Alert'
    });
  };

  const getSeverityColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical': return '#dc3545';
      case 'warning': return '#ffc107';
      default: return '#007AFF';
    }
  };

  const renderDate = (dateString) => {
    if (!dateString) return 'Unknown Date';
    try {
      const d = new Date(dateString);
      if (isNaN(d.getTime())) return dateString;
      return format(d, 'PPpp');
    } catch (e) {
      return dateString;
    }
  };

  return (
    <ScrollView style={styles.container}>
      <View style={[styles.header, { borderLeftColor: getSeverityColor(alert.severity) }]}>
        <Text style={styles.title}>{alert.message || "Alert Details"}</Text>
        <Text style={styles.timestamp}>
          {renderDate(alert.created_at)}
        </Text>
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>Severity</Text>
        <View style={[styles.badge, { backgroundColor: getSeverityColor(alert.severity) }]}>
          <Text style={styles.badgeText}>{alert.severity?.toUpperCase() || 'INFO'}</Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.label}>Status</Text>
        <View style={styles.statusContainer}>
          <Text style={styles.value}>
            {alert.is_resolved ? 'Auto Resolved' : 
             alert.mobile_status === 'acknowledged' ? 'Acknowledged' : 'Active'}
          </Text>
        </View>
      </View>

      {alert.metric_value !== undefined && alert.metric_value !== null && (
        <View style={styles.section}>
          <Text style={styles.label}>Metric Value</Text>
          <Text style={[styles.value, { color: getSeverityColor(alert.severity) }]}>
            {typeof alert.metric_value === 'number' ? alert.metric_value.toFixed(2) : alert.metric_value}
          </Text>
        </View>
      )}

      {alert.threshold_value !== undefined && alert.threshold_value !== null && (
        <View style={styles.section}>
          <Text style={styles.label}>Threshold</Text>
          <Text style={styles.value}>
            {typeof alert.threshold_value === 'number' ? alert.threshold_value.toFixed(2) : alert.threshold_value}
          </Text>
        </View>
      )}

      {alert.mobile_status === 'acknowledged' && (
        <View style={styles.successBanner}>
           <Text style={styles.successText}>✅ Acknowledged by {alert.acknowledged_by_name || 'User'}</Text>
           {alert.ert_at && (
             <Text style={styles.ertText}>Expected resolution by: {renderDate(alert.ert_at)}</Text>
           )}
           {alert.ert_justification && (
             <Text style={styles.justificationText}>Reason: {alert.ert_justification}</Text>
           )}
        </View>
      )}

      <View style={styles.section}>
        <Text style={styles.label}>Location / Server</Text>
        <Text style={styles.value}>
          {alert.server_name || 'Unknown Server'}
        </Text>
        {alert.server_ip ? (
          <Text style={styles.subValue}>IP: {alert.server_ip}</Text>
        ) : null}
      </View>
      
      {!alert.is_resolved && alert.mobile_status !== 'acknowledged' && canAcknowledge && (
        <TouchableOpacity 
          style={styles.ackButton}
          onPress={handleAcknowledge}
          disabled={isAcknowledging}
        >
          <Text style={styles.ackButtonText}>
            {isAcknowledging ? 'Processing...' : 'Acknowledge Alert'}
          </Text>
        </TouchableOpacity>
      )}
      
      {!canAcknowledge && !alert.is_resolved && alert.mobile_status !== 'acknowledged' && (
        <View style={styles.viewerNotice}>
          <Text style={styles.viewerNoticeText}>You do not have permission to acknowledge this alert.</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  header: {
    padding: 20,
    backgroundColor: '#f8f9fa',
    borderLeftWidth: 5,
    marginBottom: 20,
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold',
    marginBottom: 5,
  },
  timestamp: {
    color: '#666',
    fontSize: 14,
  },
  section: {
    paddingHorizontal: 20,
    marginBottom: 20,
  },
  label: {
    fontSize: 14,
    color: '#888',
    marginBottom: 5,
    textTransform: 'uppercase',
  },
  value: {
    fontSize: 16,
    color: '#333',
    fontWeight: 'bold',
  },
  subValue: {
    fontSize: 14,
    color: '#666',
    marginTop: 2,
  },
  statusContainer: {
    flexDirection: 'column',
  },
  badge: {
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 4,
    alignSelf: 'flex-start',
  },
  badgeText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 12,
  },
  successBanner: {
    margin: 20,
    padding: 15,
    backgroundColor: '#e8f5e9',
    borderRadius: 12,
    borderLeftWidth: 5,
    borderLeftColor: '#2e7d32',
  },
  successText: {
    color: '#2e7d32',
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 5,
  },
  ertText: {
    color: '#1b5e20',
    fontSize: 14,
    fontStyle: 'italic',
  },
  justificationText: {
    color: '#1b5e20',
    fontSize: 14,
    marginTop: 5,
  },
  ackButton: {
    margin: 20,
    backgroundColor: '#28a745',
    padding: 15,
    borderRadius: 8,
    alignItems: 'center',
    elevation: 3,
  },
  ackButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  viewerNotice: {
    margin: 20,
    padding: 15,
    backgroundColor: '#f8f9fa',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#eee',
    alignItems: 'center',
  },
  viewerNoticeText: {
    color: '#666',
    fontStyle: 'italic',
  }
});
