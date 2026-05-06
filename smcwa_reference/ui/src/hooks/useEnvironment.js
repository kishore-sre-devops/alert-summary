import { useContext, useCallback } from 'react';
import { useEnvironmentContext } from '../contexts/EnvironmentContext';

/**
 * Custom hook to access and manage environment state
 * 
 * @returns {Object} { environment, changeEnvironment, withEnvironment }
 * 
 * @example
 * // Get current environment
 * const { environment } = useEnvironment();
 * 
 * @example
 * // Change environment
 * const { changeEnvironment } = useEnvironment();
 * changeEnvironment('uat');
 * 
 * @example
 * // Add environment to API params
 * const { withEnvironment } = useEnvironment();
 * await axios.get('/v1/servers/', { params: withEnvironment() });
 * 
 * @example
 * // Add environment to existing params
 * const { withEnvironment } = useEnvironment();
 * await axios.get('/v1/data/', { params: withEnvironment({ filter: 'active' }) });
 */
export const useEnvironment = () => {
  const { environment, changeEnvironment } = useEnvironmentContext();

  /**
   * Helper function to add environment parameter to API request params
   * Memoized to prevent unnecessary recreations
   * @param {Object} params - Existing query parameters
   * @returns {Object} Params with environment added
   */
  const withEnvironment = useCallback((params = {}) => {
    return {
      ...params,
      environment,
    };
  }, [environment]);

  return {
    environment,
    changeEnvironment,
    withEnvironment,
  };
};

