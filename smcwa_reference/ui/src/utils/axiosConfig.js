// Axios configuration with automatic token expiration handling
import axios from 'axios';

// Set default baseURL
axios.defaults.baseURL = '/api';
// VAPT FIX: Enable withCredentials to send httpOnly cookies automatically
axios.defaults.withCredentials = true;

// Add request interceptor
axios.interceptors.request.use(
  (config) => {
    // Add active environment to headers
    const environment = localStorage.getItem('lama_environment') || 'prod';
    config.headers['X-Environment'] = environment;
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor to handle token expiration
axios.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // Handle 401 Unauthorized (token expired or invalid)
    if (error.response?.status === 401) {
      const errorMessage = error.response?.data?.detail || error.message || '';
      
      // Check if it's a token expiration error
      if (errorMessage.includes('expired') || errorMessage.includes('Invalid or expired token') || errorMessage.includes('Not authenticated')) {
        // Clear all authentication data from localStorage and sessionStorage
        const keysToRemove = [
          'lama_jwt', 'lama_token', 'lama_user_email', 'lama_user_id', 
          'lama_user_role', 'lama_user_name', 'lama_user_mobile'
        ];
        
        keysToRemove.forEach(key => {
          localStorage.removeItem(key);
          sessionStorage.removeItem(key);
        });
        
        // Redirect to login page
        if (window.location.pathname !== '/login') {
          window.location.href = '/login?expired=true';
        }
      }
    }
    
    return Promise.reject(error);
  }
);

export default axios;

