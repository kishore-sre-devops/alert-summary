/**
 * Get API endpoint - now uses single /api/ endpoint
 * @returns {string} API endpoint URL
 */
export const getApiEndpoint = () => {
  // Single API endpoint
  return '/api';
};

/**
 * Get API base URL for axios calls
 * Now uses single /api/ endpoint
 */
export const getApiBaseURL = () => {
  // Single API endpoint
  return '/api';
};

/**
 * Get current environment from localStorage
 * @returns {string} 'prod' or 'uat'
 */
export const getCurrentEnvironment = () => {
  return localStorage.getItem('lama_environment') || 'prod';
};

/**
 * Add environment parameter to API calls
 * @param {string} url - API endpoint URL
 * @returns {string} URL with environment parameter
 */
export const addEnvironmentParam = (url) => {
  const env = getCurrentEnvironment();
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}environment=${env}`;
};

