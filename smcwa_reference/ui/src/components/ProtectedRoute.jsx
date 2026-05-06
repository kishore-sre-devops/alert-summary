import React, { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import CircularProgress from '@mui/material/CircularProgress';
import Box from '@mui/material/Box';

// Ensure axios baseURL is always synchronized - single /api/ endpoint
const syncApiEndpoint = () => {
  const apiEndpoint = '/api';
  axios.defaults.baseURL = apiEndpoint;
  // VAPT FIX: Remove api_endpoint from localStorage
};

export default function ProtectedRoute({ children }){
  const [isVerifying, setIsVerifying] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const location = useLocation();
  
  // Sync API endpoint on every route change
  useEffect(() => {
    syncApiEndpoint();
  }, [location.pathname]);

  useEffect(() => {
    const verifySession = async () => {
      try {
        // VAPT FIX: Verify session via httpOnly cookie using /auth/me
        const res = await axios.get('/auth/me');
        if (res.data && res.data.id) {
          // Restore user info to sessionStorage for display purposes
          sessionStorage.setItem('lama_user_email', res.data.email);
          sessionStorage.setItem('lama_user_id', res.data.id);
          sessionStorage.setItem('lama_user_role', res.data.role);
          setIsAuthenticated(true);
        } else {
          setIsAuthenticated(false);
        }
      } catch (err) {
        setIsAuthenticated(false);
      } finally {
        setIsVerifying(false);
      }
    };

    verifySession();
  }, [location.pathname]);
  
  if (isVerifying) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
