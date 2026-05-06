import { create } from 'zustand';
import api from '../services/api';
import { API_BASE_URL } from '../config/env';

export const useAlertStore = create((set, get) => ({
  alerts: [],
  isLoading: false,
  error: null,
  incomingCall: null, // { id, title, body, data }
  ws: null,
  activeFilter: 'active',

  fetchAlerts: async (filter = 'active') => {
    try {
      set({ isLoading: true, activeFilter: filter });
      const response = await api.get(`/mobile/alerts?filter=${filter}`);
      set({ alerts: response.data, isLoading: false });
    } catch (error) {
      set({ error: error.message, isLoading: false });
    }
  },

  setupWebSocket: () => {
    // Prevent duplicate connections
    if (get().ws) return;

    // Convert https://.../api/v1 to wss://.../ws/updates
    const wsUrl = API_BASE_URL.replace('https://', 'wss://')
                              .replace('http://', 'ws://')
                              .replace('/api/v1', '') + '/ws/updates';
    
    console.log(`📡 Connecting to WebSocket: ${wsUrl}`);
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('✅ WebSocket Connected');
    };

    ws.onmessage = (e) => {
      try {
        const message = JSON.parse(e.data);
        console.log('📬 WebSocket Message:', message.type);
        
        // Refresh UI if alert state changed
        if (['new_alert', 'alert_acknowledged', 'alerts_resolved'].includes(message.type)) {
           
           // SILENCE GHOST ALARMS: If the current incoming call was acknowledged or resolved by someone else,
           // stop the ringing and clear the UI immediately.
           const currentCall = get().incomingCall;
           if (currentCall && message.data && 
              (message.data.alert_id === parseInt(currentCall.id) || message.data.alert_id === currentCall.id)) {
               console.log('🛑 Alert handled by another user/system. Stopping ring.');
               const alertCallManager = require('../services/alertCallManager').default;
               const NativeAlarm = require('../services/NativeAlarm').default;
               if (alertCallManager && typeof alertCallManager.stopRinging === 'function') {
                 alertCallManager.stopRinging();
               }
               NativeAlarm.stopAlarm();
               set({ incomingCall: null });
           }

           // Wait a tiny bit for DB to settle
           setTimeout(() => {
             get().fetchAlerts(get().activeFilter);
           }, 500);
        }
      } catch (err) {
        console.warn('WS parse error:', err);
      }
    };

    ws.onclose = () => {
      console.log('❌ WebSocket Disconnected. Reconnecting in 5s...');
      set({ ws: null });
      setTimeout(() => get().setupWebSocket(), 5000);
    };

    ws.onerror = (e) => {
      console.warn('WebSocket error:', e.message);
    };

    set({ ws });
  },

  acknowledgeAlert: async (alert_id, ert_minutes = 2, justification = null) => {
    try {
      await api.post(`/mobile/alerts/${alert_id}/ack`, {
        ert_minutes,
        justification
      });
      // Update local state: mark as acknowledged
      // Handle both numeric and string IDs (test alerts)
      const idMatch = (aId, targetId) => {
        if (typeof targetId === 'string' && targetId.startsWith('test_')) return aId === targetId;
        return parseInt(aId) === parseInt(targetId);
      };

      const alerts = get().alerts.map(a => 
        idMatch(a.id, alert_id) ? { ...a, mobile_status: 'acknowledged' } : a
      );
      set({ alerts });
      return true;
    } catch (error) {
      console.error('Ack API error:', error);
      return false;
    }
  },

  syncAlerts: async () => {
    try {
      console.log('🔄 Syncing alerts with server...');
      const response = await api.get('/mobile/alerts?filter=active');
      const activeAlerts = response.data;
      
      // Update global alerts list (for feed)
      set({ alerts: activeAlerts });

      // Get current state
      const currentCall = get().incomingCall;

      // 1. FULL LOCK: If user is currently handling an alert, do not interrupt.
      if (currentCall) {
          console.log('🔒 Sync Locked: User is handling alert #', currentCall.id);
          
          // Check if it was resolved or acknowledged by someone else
          const serverMatch = activeAlerts.find(a => parseInt(a.id) === parseInt(currentCall.id));
          
          if (!serverMatch || serverMatch.mobile_status === 'acknowledged') {
              console.log('🛑 Alert #', currentCall.id, 'resolved or acknowledged remotely. Clearing UI.');
              const alertCallManager = require('../services/alertCallManager').default;
              const NativeAlarm = require('../services/NativeAlarm').default;
              if (alertCallManager && typeof alertCallManager.stopRinging === 'function') {
                alertCallManager.stopRinging();
              }
              NativeAlarm.stopAlarm();
              set({ incomingCall: null });
          }
          return; // STOP SYNC HERE to preserve user typing
      }

      // 2. NEW ALERT DETECTION
      if (activeAlerts && activeAlerts.length > 0) {
        const unackedAlert = activeAlerts.find(a => a.mobile_status === 'pending' || !a.mobile_status);
        if (unackedAlert) {
            console.log('🚀 Forcing Full-Screen UI for new alert:', unackedAlert.id);
            set({ incomingCall: {
                id: unackedAlert.id,
                title: unackedAlert.alert_type || unackedAlert.title || "SMC ALERT",
                body: unackedAlert.message || unackedAlert.body || "Critical Alert",
                severity: unackedAlert.severity || 'critical',
                site_name: unackedAlert.server_name || 'System',
                server_ip: unackedAlert.server_ip || '',
                hardware_details: unackedAlert.hardware_details || 'N/A',
                alert_type: unackedAlert.alert_type || 'Alert',
                voice_alert: unackedAlert.voice_alert || '' // ENSURE sync carries voice string
            }});
        }
      }
    } catch (error) {
      console.warn('⚠️ syncAlerts failed:', error.message);
    }
  },

  setIncomingCall: (callData) => set({ incomingCall: callData }),
  clearIncomingCall: () => set({ incomingCall: null }),
}));
