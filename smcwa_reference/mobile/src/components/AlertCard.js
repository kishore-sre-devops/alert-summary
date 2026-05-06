import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { formatDistanceToNow } from 'date-fns';

export default function AlertCard({ alert, onPress }) {
  const isCritical = alert.severity?.toLowerCase() === 'critical';
  const isWarning = alert.severity?.toLowerCase() === 'warning';
  const isActive = !alert.is_resolved && alert.mobile_status !== 'acknowledged';

  const getSeverityColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical': 
      case 'error':
        return '#dc3545'; // Red
      case 'warning': return '#ffc107'; // Yellow
      case 'info': return '#007AFF'; // Blue
      default: return '#6c757d'; // Gray
    }
  };

  const getBackgroundColor = () => {
    if (!isActive) return '#fff';
    if (isCritical) return '#ffebee'; // Light Red
    if (isWarning) return '#fff3e0'; // Light Orange
    return '#e3f2fd'; // Light Blue
  };

  const renderDate = (dateString) => {
    if (!dateString) return '';
    try {
      const dateStr = dateString.toString();
      // Handle custom DD/MM/YYYY, HH:MM:SS PM format returned by backend
      if (dateStr.includes('/')) {
         const parts = dateStr.split(', ');
         if (parts.length === 2) {
             const dateParts = parts[0].split('/');
             if (dateParts.length === 3) {
                 // Convert DD/MM/YYYY to YYYY-MM-DD
                 const isoDate = `${dateParts[2]}-${dateParts[1]}-${dateParts[0]} ${parts[1]}`;
                 const d = new Date(isoDate);
                 if (!isNaN(d.getTime())) return formatDistanceToNow(d, { addSuffix: true });
             }
         }
      }
      
      const d = new Date(dateString);
      if (isNaN(d.getTime())) return dateString;
      return formatDistanceToNow(d, { addSuffix: true });
    } catch (e) {
      return dateString;
    }
  };

  return (
    <TouchableOpacity 
      style={[styles.card, { backgroundColor: getBackgroundColor() }]} 
      onPress={onPress}
    >
      <View style={[styles.indicator, { backgroundColor: getSeverityColor(alert.severity) }]} />
      <View style={styles.content}>
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <Text style={styles.siteName} numberOfLines={1}>
              {alert.server_name || "Unknown Server"}
            </Text>
            {alert.server_ip ? (
              <Text style={styles.ipText}>{alert.server_ip}</Text>
            ) : null}
          </View>
          <Text style={styles.time}>
            {renderDate(alert.created_at)}
          </Text>
        </View>
        <View style={styles.typeRow}>
           <Text style={styles.alertType}>{alert.alert_type || "Alert"}</Text>
           <View style={[styles.severityBadge, { backgroundColor: getSeverityColor(alert.severity) }]}>
             <Text style={styles.severityText}>{alert.severity?.toUpperCase()}</Text>
           </View>
        </View>
        <Text style={styles.message} numberOfLines={2}>{alert.message}</Text>
        <View style={styles.footer}>
           {alert.mobile_status === 'acknowledged' ? (
             <View style={styles.badgeContainer}>
               <Text style={[styles.statusBadge, styles.ackBadge]}>
                 ✅ Ack by {alert.acknowledged_by_name || 'User'}
               </Text>
             </View>
           ) : alert.is_resolved ? (
             <View style={styles.badgeContainer}>
               <Text style={[styles.statusBadge, styles.resolvedBadge]}>
                 ⚪ Auto Resolved
               </Text>
             </View>
           ) : (
             <View style={styles.badgeContainer}>
               <Text style={[styles.statusBadge, styles.activeBadge]}>
                 🔴 Active
               </Text>
             </View>
           )}
        </View>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    borderRadius: 12,
    marginBottom: 12,
    overflow: 'hidden',
    elevation: 3,
    shadowColor: '#000',
    shadowOpacity: 0.1,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    minHeight: 110,
  },
  indicator: {
    width: 8,
    height: '100%',
  },
  content: {
    flex: 1,
    padding: 12,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  siteName: {
    fontWeight: 'bold',
    fontSize: 16,
    color: '#000',
  },
  ipText: {
    fontSize: 12,
    color: '#666',
  },
  time: {
    fontSize: 12,
    color: '#666',
    marginLeft: 8,
  },
  typeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 6,
  },
  alertType: {
    fontSize: 14,
    color: '#444',
    fontWeight: '600',
    marginRight: 8,
  },
  severityBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  severityText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: 'bold',
  },
  message: {
    fontSize: 14,
    color: '#555',
    marginBottom: 8,
  },
  footer: {
      flexDirection: 'row',
      justifyContent: 'flex-end',
      alignItems: 'center',
  },
  badgeContainer: {
    borderRadius: 4,
    overflow: 'hidden',
  },
  statusBadge: {
    fontSize: 11,
    fontWeight: 'bold',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
  },
  activeBadge: {
    backgroundColor: '#ffebee',
    color: '#c62828',
  },
  ackBadge: {
    backgroundColor: '#e8f5e9',
    color: '#2e7d32',
  },
  resolvedBadge: {
    backgroundColor: '#f5f5f5',
    color: '#616161',
  }
});
