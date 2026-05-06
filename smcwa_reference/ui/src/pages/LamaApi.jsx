import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Radio,
  RadioGroup,
  FormControlLabel,
  FormControl,
  FormLabel,
  Button,
  Alert,
  Chip,
} from '@mui/material';
import { CheckCircle, Cloud, Storage } from '@mui/icons-material';

const LamaApi = () => {
  const [environment, setEnvironment] = useState('prod');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    // Load saved environment from localStorage
    const savedEnv = localStorage.getItem('lama_environment') || localStorage.getItem('api_endpoint');
    if (savedEnv) {
      if (savedEnv.includes('uat')) {
        setEnvironment('uat');
      } else if (savedEnv.includes('prod')) {
        setEnvironment('prod');
      } else {
        setEnvironment('prod'); // Default to prod
      }
    }
  }, []);

  const handleEnvironmentChange = (event) => {
    setEnvironment(event.target.value);
    setSaved(false);
  };

  const handleSave = () => {
    // Save environment selection - single /api/ endpoint (environment passed as query parameter)
    const apiEndpoint = '/api';
    localStorage.setItem('lama_environment', environment);
    localStorage.setItem('api_endpoint', apiEndpoint);
    
    // Update axios base URL immediately
    const axios = require('axios').default;
    axios.defaults.baseURL = apiEndpoint;
    
    setSaved(true);
    
    // Show success message and reload after a short delay
    setTimeout(() => {
      window.location.reload();
    }, 1500);
  };

  return (
    <Box sx={{ width: '100%', boxSizing: 'border-box' }}>
      <Typography variant="h5" sx={{ fontWeight: 'bold', mb: 3, fontSize: '1.5rem' }}>
        LAMA API Configuration
      </Typography>

      <Paper sx={{ p: 3, md: 4, maxWidth: 800, mx: 'auto' }}>
        <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold' }}>
          Select API Environment
        </Typography>
        
        <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
          Choose the environment you want to connect to. This will be used for all API calls throughout the application.
        </Typography>

        {saved && (
          <Alert severity="success" sx={{ mb: 3 }}>
            Environment saved successfully! The page will reload to apply changes.
          </Alert>
        )}

        <FormControl component="fieldset" sx={{ width: '100%', mb: 3 }}>
          <FormLabel component="legend" sx={{ mb: 2, fontWeight: 'bold' }}>
            Available Environments
          </FormLabel>
          <RadioGroup
            value={environment}
            onChange={handleEnvironmentChange}
            sx={{ gap: 2 }}
          >
            <Paper
              sx={{
                p: 2,
                border: environment === 'prod' ? '2px solid #1976d2' : '2px solid #e0e0e0',
                borderRadius: 2,
                backgroundColor: environment === 'prod' ? '#e3f2fd' : 'white',
                cursor: 'pointer',
                '&:hover': {
                  backgroundColor: environment === 'prod' ? '#e3f2fd' : '#f5f5f5',
                },
              }}
              onClick={() => setEnvironment('prod')}
            >
              <FormControlLabel
                value="prod"
                control={<Radio />}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
                    <Cloud sx={{ fontSize: 32, color: '#1976d2' }} />
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                        Production (PROD)
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        Production environment with live data
                      </Typography>
                    </Box>
                    {environment === 'prod' && (
                      <Chip
                        icon={<CheckCircle />}
                        label="Active"
                        color="primary"
                        sx={{ fontWeight: 'bold' }}
                      />
                    )}
                  </Box>
                }
                sx={{ m: 0, width: '100%' }}
              />
            </Paper>

            <Paper
              sx={{
                p: 2,
                border: environment === 'uat' ? '2px solid #1976d2' : '2px solid #e0e0e0',
                borderRadius: 2,
                backgroundColor: environment === 'uat' ? '#e3f2fd' : 'white',
                cursor: 'pointer',
                '&:hover': {
                  backgroundColor: environment === 'uat' ? '#e3f2fd' : '#f5f5f5',
                },
              }}
              onClick={() => setEnvironment('uat')}
            >
              <FormControlLabel
                value="uat"
                control={<Radio />}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
                    <Storage sx={{ fontSize: 32, color: '#1976d2' }} />
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                        User Acceptance Testing (UAT)
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        Testing environment for validation and QA
                      </Typography>
                    </Box>
                    {environment === 'uat' && (
                      <Chip
                        icon={<CheckCircle />}
                        label="Active"
                        color="primary"
                        sx={{ fontWeight: 'bold' }}
                      />
                    )}
                  </Box>
                }
                sx={{ m: 0, width: '100%' }}
              />
            </Paper>
          </RadioGroup>
        </FormControl>

        <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', mt: 4 }}>
          <Button
            variant="outlined"
            onClick={() => {
              setEnvironment(localStorage.getItem('lama_environment') || 'prod');
              setSaved(false);
            }}
            sx={{ minWidth: 120 }}
          >
            Reset
          </Button>
          <Button
            variant="contained"
            onClick={handleSave}
            sx={{
              minWidth: 120,
              background: 'linear-gradient(135deg, #2196F3 0%, #1976D2 100%)',
            }}
          >
            Save & Apply
          </Button>
        </Box>

        <Box sx={{ mt: 4, p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
            Current Configuration
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Selected Environment: <strong>{environment.toUpperCase()}</strong>
          </Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mt: 0.5 }}>
            API Endpoint: <strong>/api</strong> (Environment: {environment.toUpperCase()} passed as query parameter)
          </Typography>
        </Box>
      </Paper>
    </Box>
  );
};

export default LamaApi;

