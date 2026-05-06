import React, { createContext, useState, useEffect, useContext } from 'react';

const EnvironmentContext = createContext({
  environment: 'prod',
  loading: false,
  setEnvironment: () => {},
  changeEnvironment: () => {},
});

export const useEnvironmentContext = () => {
  const context = useContext(EnvironmentContext);
  if (!context) {
    throw new Error('useEnvironmentContext must be used within EnvironmentProvider');
  }
  return context;
};

export const EnvironmentProvider = ({ children }) => {
  const [environment, setEnvironment] = useState('prod');
  const [loading, setLoading] = useState(false);

  // Load saved environment on mount
  useEffect(() => {
    const savedEnv = localStorage.getItem('lama_environment') || 'prod';
    setEnvironment(savedEnv);
  }, []);

  // Change environment (updates state, localStorage, and dispatches event)
  const changeEnvironment = (newEnv) => {
    if (!['prod', 'uat'].includes(newEnv)) {
      console.warn(`Invalid environment: ${newEnv}. Using 'prod' instead.`);
      newEnv = 'prod';
    }

    setLoading(true);
    setEnvironment(newEnv);
    localStorage.setItem('lama_environment', newEnv);
    
    // Clear loading after a short delay to allow components to reset
    setTimeout(() => {
      setLoading(false);
    }, 300);
    
    // Dispatch custom event for backward compatibility (in case any components still listen)
    window.dispatchEvent(
      new CustomEvent('environmentChanged', { 
        detail: { environment: newEnv } 
      })
    );
  };

  // Listen for storage changes (cross-tab synchronization)
  useEffect(() => {
    const handleStorageChange = (e) => {
      if (e.key === 'lama_environment') {
        const newEnv = localStorage.getItem('lama_environment') || 'prod';
        if (newEnv !== environment) {
          setEnvironment(newEnv);
        }
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }, [environment]);

  const value = {
    environment,
    loading,
    setEnvironment: changeEnvironment, // Expose changeEnvironment as setEnvironment for consistency
    changeEnvironment,
  };

  return (
    <EnvironmentContext.Provider value={value}>
      {children}
    </EnvironmentContext.Provider>
  );
};

