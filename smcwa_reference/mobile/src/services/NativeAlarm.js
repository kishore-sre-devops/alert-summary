import { NativeModules, Platform } from 'react-native';

const { AlertingModule } = NativeModules;

/**
 * NativeAlarm Service
 * 
 * Provides an interface to the native Android alerting engine.
 * Use this to acknowledge critical alerts and stop the native alarm loop.
 */
export const NativeAlarm = {
  /**
   * Acknowledges a critical alert, stopping the sound and dismissing the native lock screen UI.
   * @param {string} alertId - The unique ID of the alert to acknowledge.
   */
  acknowledge: (alertId) => {
    if (Platform.OS === 'android') {
      if (AlertingModule && AlertingModule.acknowledge) {
        console.log(`[NativeAlarm] Acknowledging alert: ${alertId}`);
        AlertingModule.acknowledge(alertId);
      } else {
        console.warn('[NativeAlarm] AlertingModule is not available. Native alerting may not be linked correctly.');
      }
    } else {
      console.log('[NativeAlarm] Native alerting is Android-only.');
    }
  },

  /**
   * Stops any currently playing native alarm.
   */
  stopAlarm: () => {
    if (Platform.OS === 'android') {
      if (AlertingModule && AlertingModule.stopAlarm) {
        console.log(`[NativeAlarm] Stopping native alarm`);
        AlertingModule.stopAlarm();
      }
    }
  }
};

export default NativeAlarm;
