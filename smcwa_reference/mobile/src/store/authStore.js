import { create } from 'zustand';
import EncryptedStorage from 'react-native-encrypted-storage';
import messaging from '@react-native-firebase/messaging';
import api, { setAuthToken } from '../services/api';

export const useAuthStore = create((set) => ({
  user: null,
  isLoading: true,
  error: null,
  
  signIn: async (email, password) => {
    try {
      set({ isLoading: true, error: null });
      const response = await api.post('/auth/login', { email, password });
      
      // Backend returns flat structure: { token, user_email, user_id, role, group_name, ... }
      const { token, user_email, user_id, role, group_name, user } = response.data;
      
      await setAuthToken(token);
      
      // Construct user object from flat fields, fallback to nested user if present (backward compat)
      const userData = { 
        email: user?.email || user_email || email,
        id: user?.id || user_id,
        role: user?.role || role,
        group_name: user?.group_name || group_name // Fix: Check both top-level and nested user object
      };
      
      // Note: We don't set user in store here, we return it so LoginScreen can show success message
      set({ isLoading: false });
      return userData;
    } catch (error) {
      console.error(error);
      set({ error: error.response?.data?.detail || 'Login failed', isLoading: false });
      return null;
    }
  },
  
  setUser: async (user) => {
    if (user) {
      await EncryptedStorage.setItem('userData', JSON.stringify(user));
    } else {
      await EncryptedStorage.removeItem('userData');
    }
    set({ user });
  },
  
  signOut: async () => {
    try {
      // 1. Get FCM token to tell backend which device to logout
      const token = await messaging().getToken();
      if (token) {
        // 2. Notify backend to stop sending alerts to this device
        await api.post('/mobile/logout', { push_token: token });
      }
    } catch (e) {
      console.warn('Backend logout failed, proceeding with local cleanup:', e);
    } finally {
      // 3. Local cleanup always happens
      await setAuthToken(null);
      await EncryptedStorage.removeItem('userData');
      set({ user: null });
    }
  },

  restoreToken: async () => {
      try {
        const [token, userData] = await Promise.all([
          EncryptedStorage.getItem('userToken'),
          EncryptedStorage.getItem('userData')
        ]);

        if (token && userData) {
            set({ user: JSON.parse(userData), isLoading: false });
        } else if (token) {
            // Fallback if token exists but no user data (shouldn't happen with new logic)
            set({ user: { email: 'Restored User', role: 'user' }, isLoading: false });
        } else {
            set({ isLoading: false });
        }
      } catch (e) {
          set({ isLoading: false });
      }
  }
}));

// Auto restore on mount logic should be in App.js or similar
