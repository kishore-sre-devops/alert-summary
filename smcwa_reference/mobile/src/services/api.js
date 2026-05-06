import axios from 'axios';
import EncryptedStorage from 'react-native-encrypted-storage';
import { API_BASE_URL } from '../config/env';

// Use the environment variable, or fallback to a default dev address
// For Android Emulator use 10.0.2.2, for iOS use localhost or machine IP
const BASE_URL = API_BASE_URL || 'http://10.0.2.2:8000/api/v1';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    'X-Device-Type': 'mobile'
  },
});

api.interceptors.request.use(
  async (config) => {
    const token = await EncryptedStorage.getItem('userToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response && error.response.status === 401) {
      // Handle unauthorized (e.g. logout)
      await EncryptedStorage.removeItem('userToken');
    }
    return Promise.reject(error);
  }
);

export const setAuthToken = async (token) => {
    if (token) {
        await EncryptedStorage.setItem('userToken', token);
    } else {
        await EncryptedStorage.removeItem('userToken');
    }
};

export const getAuthToken = async () => {
    return await EncryptedStorage.getItem('userToken');
};

export default api;
