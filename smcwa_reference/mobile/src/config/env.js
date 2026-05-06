import Constants from 'expo-constants';

// Access variables defined in app.json "extra" or .env files loaded by Expo
// Fallback to production URL if configuration fails to load
export const API_BASE_URL = Constants.expoConfig?.extra?.apiUrl || 'https://smcalert.smcindiaonline.com:8000/api/v1';
