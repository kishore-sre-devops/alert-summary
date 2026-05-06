import React, { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Switch from '@mui/material/Switch';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import InputAdornment from '@mui/material/InputAdornment';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Grid from '@mui/material/Grid';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import Chip from '@mui/material/Chip';
import Container from '@mui/material/Container';
import Checkbox from '@mui/material/Checkbox';
import FormGroup from '@mui/material/FormGroup';
import Tooltip from '@mui/material/Tooltip';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import axios from '../utils/axiosConfig';
import { getCurrentEnvironment } from '../utils/api';
import { useEnvironment } from '../hooks/useEnvironment';
import PrometheusDiscovery from '../components/PrometheusDiscovery';
import AWSDiscovery from '../components/AWSDiscovery';

const ConfigWizard = () => {
  const { environment: currentEnvironment } = useEnvironment();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState({ prod: false, uat: false });
  const [message, setMessage] = useState({ prod: '', uat: '' });
  const [messageType, setMessageType] = useState({ prod: 'info', uat: 'info' });

  // Configuration state for both environments
  const [configs, setConfigs] = useState({
    prod: {
      enabled: false,
      credentials: {
        member_id: '',
        login_id: '',
        password: '',
        secret_key: '',
        lama_api_url: '',
      },
    },
    uat: {
      enabled: false,
      credentials: {
        member_id: '',
        login_id: '',
        password: '',
        secret_key: '',
        lama_api_url: '',
      },
    },
  });

  const [showPassword, setShowPassword] = useState({ prod: false, uat: false });
  const [showSecretKey, setShowSecretKey] = useState({ prod: false, uat: false });
  
  // Metric configuration state
  const [metricConfigs, setMetricConfigs] = useState({
    prod: {
      hardware: true,
      network: true,
      database: true,
      application: true,
    },
    uat: {
      hardware: true,
      network: true,
      database: true,
      application: true,
    },
  });
  const [savingMetricConfig, setSavingMetricConfig] = useState({ prod: false, uat: false });
  const [metricConfigMessage, setMetricConfigMessage] = useState({ prod: '', uat: '' });

  // Server selection state
  const [serverSelections, setServerSelections] = useState({ prod: [], uat: [] });
  const [loadingServers, setLoadingServers] = useState({ prod: false, uat: false });
  const [savingServers, setSavingServers] = useState({ prod: false, uat: false });
  const [serverSelectionMessage, setServerSelectionMessage] = useState({ prod: '', uat: '' });
  const [serverSelectionCount, setServerSelectionCount] = useState({ prod: { enabled: 0, total: 0 }, uat: { enabled: 0, total: 0 } });
  
  // Exchange status state
  const [exchangeStatus, setExchangeStatus] = useState({ prod: [], uat: [] });


  useEffect(() => {
    axios.defaults.baseURL = '/api';
    loadAllConfigurations();
    loadMetricConfigurations();
    loadServerSelections('prod');
    loadServerSelections('uat');
  }, []);

  // Reload configs when environment changes
  useEffect(() => {
    loadAllConfigurations();
    loadMetricConfigurations();
    loadServerSelections(currentEnvironment);
  }, [currentEnvironment]);

  // Sync server selection count when selections change (derived state pattern)
  useEffect(() => {
    // Update count for both environments when selections change
    ['prod', 'uat'].forEach(env => {
      setServerSelectionCount(prev => ({
        ...prev,
        [env]: {
          enabled: serverSelections[env]?.filter(s => s.enabled).length || 0,
          total: serverSelections[env]?.length || 0
        }
      }));
    });
  }, [serverSelections]);

  const loadExchangeStatus = async (env) => {
    try {
      axios.defaults.baseURL = '/api';
      
      
      const response = await axios.get(`/v1/lama-config/exchanges/${env}`, {
        headers: {  }
      });
      
      if (response.data.status === 'success') {
        setExchangeStatus(prev => ({
          ...prev,
          [env]: response.data.exchanges || []
        }));
      }
    } catch (error) {
      console.error(`Error loading exchange status for ${env}:`, error);
      // Set empty array on error
      setExchangeStatus(prev => ({
        ...prev,
        [env]: []
      }));
    }
  };

  const loadAllConfigurations = async () => {
    setLoading(true);
    try {
      axios.defaults.baseURL = '/api';
      
      
      // Load both PROD and UAT configurations explicitly
      // Note: environment parameter in URL specifies which config to get, not the current environment
      const [prodResponse, uatResponse] = await Promise.all([
        axios.get('/v1/lama-config/?environment=prod', {
          headers: {  }
        }).catch(() => ({ data: [] })),
        axios.get('/v1/lama-config/?environment=uat', {
          headers: {  }
        }).catch(() => ({ data: [] }))
      ]);

      // Process PROD config
      const prodData = Array.isArray(prodResponse.data) && prodResponse.data.length > 0
        ? prodResponse.data.find(c => c.environment === 'prod') || prodResponse.data[0]
        : null;
      
      // Process UAT config
      const uatData = Array.isArray(uatResponse.data) && uatResponse.data.length > 0
        ? uatResponse.data.find(c => c.environment === 'uat') || uatResponse.data[0]
        : null;

      setConfigs({
        prod: {
          enabled: prodData?.enabled || false,
          credentials: {
            member_id: prodData?.member_id || '',
            login_id: prodData?.login_id || '',
            password: prodData?.password || '',
            secret_key: prodData?.secret_key || '',
            lama_api_url: prodData?.lama_api_url || '',
          },
        },
        uat: {
          enabled: uatData?.enabled || false,
          credentials: {
            member_id: uatData?.member_id || '',
            login_id: uatData?.login_id || '',
            password: uatData?.password || '',
            secret_key: uatData?.secret_key || '',
            lama_api_url: uatData?.lama_api_url || '',
          },
        },
      });
      
      // Load exchange status for both environments
      await Promise.all([
        loadExchangeStatus('prod'),
        loadExchangeStatus('uat')
      ]);
    } catch (error) {
      console.error('Error loading configurations:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadMetricConfigurations = async () => {
    try {
      axios.defaults.baseURL = '/api';
      
      
      const response = await axios.get('/v1/lama-config/metric-config', {
        headers: {  }
      });
      
      if (response.data.status === 'success' && response.data.configs) {
        setMetricConfigs({
          prod: response.data.configs.prod || {
            hardware: true,
            network: true,
            database: true,
            application: true,
          },
          uat: response.data.configs.uat || {
            hardware: true,
            network: true,
            database: true,
            application: true,
          },
        });
      }
    } catch (error) {
      console.error('Error loading metric configurations:', error);
    }
  };

  const handleMetricConfigSave = async (env) => {
    setSavingMetricConfig({ ...savingMetricConfig, [env]: true });
    setMetricConfigMessage({ ...metricConfigMessage, [env]: '' });
    
    try {
      axios.defaults.baseURL = '/api';
      
      
      const response = await axios.put(
        `/v1/lama-config/metric-config/${env}`,
        metricConfigs[env],
        {
          headers: {  }
        }
      );
      
      if (response.data.status === 'success') {
        setMetricConfigMessage({
          ...metricConfigMessage,
          [env]: `${env.toUpperCase()} metric configuration saved successfully!`
        });
        setTimeout(() => {
          setMetricConfigMessage({ ...metricConfigMessage, [env]: '' });
        }, 3000);
      }
    } catch (error) {
      console.error(`Error saving ${env} metric configuration:`, error);
      setMetricConfigMessage({
        ...metricConfigMessage,
        [env]: `Error: ${error.response?.data?.detail || error.message}`
      });
    } finally {
      setSavingMetricConfig({ ...savingMetricConfig, [env]: false });
    }
  };

  const handleMetricToggle = (env, metricType) => {
    setMetricConfigs({
      ...metricConfigs,
      [env]: {
        ...metricConfigs[env],
        [metricType]: !metricConfigs[env][metricType],
      },
    });
  };

  // Server selection functions
  const loadServerSelections = async (env) => {
    // Use functional updates to avoid stale closure issues with concurrent calls
    setLoadingServers(prev => ({ ...prev, [env]: true }));
    // Clear any previous error messages at the start
    setServerSelectionMessage(prev => ({ ...prev, [env]: '' }));
    try {
      axios.defaults.baseURL = '/api';
      
      
      const response = await axios.get(`/v1/lama-config/server-selection/${env}`, {
        headers: {  }
      });
      
      if (response.data) {
        setServerSelections(prev => ({
          ...prev,
          [env]: response.data.servers || []
        }));
        setServerSelectionCount(prev => ({
          ...prev,
          [env]: {
            enabled: response.data.enabled_count || 0,
            total: response.data.total_count || 0
          }
        }));
        // Clear error message on successful load using functional update
        setServerSelectionMessage(prev => ({ ...prev, [env]: '' }));
      }
    } catch (error) {
      console.error(`Error loading server selections for ${env}:`, error);
      // Show error message to user - use functional update to prevent race conditions
      setServerSelectionMessage(prev => ({
        ...prev,
        [env]: `Error loading servers: ${error.response?.data?.detail || error.message || 'Unknown error'}`
      }));
      setServerSelections(prev => ({
        ...prev,
        [env]: []
      }));
      setServerSelectionCount(prev => ({
        ...prev,
        [env]: { enabled: 0, total: 0 }
      }));
    } finally {
      setLoadingServers(prev => ({ ...prev, [env]: false }));
    }
  };

  const handleServerToggle = (env, serverId) => {
    // Update server selections only - count syncs automatically via useEffect
    // This avoids nested setters and side effects in updater functions (React best practice)
    setServerSelections(prev => ({
      ...prev,
      [env]: prev[env].map(server =>
        server.server_id === serverId
          ? { ...server, enabled: !server.enabled }
          : server
      )
    }));
  };

  const handleMetricSourceChange = (env, serverId, newSource) => {
    setServerSelections(prev => ({
      ...prev,
      [env]: prev[env].map(server =>
        server.server_id === serverId
          ? { ...server, metric_source: newSource }
          : server
      )
    }));
  };

  const handleServerSelectionSave = async (env) => {
    const enabledCount = serverSelections[env].filter(s => s.enabled).length;
    
    // Validation: Warn if no servers selected
    if (enabledCount === 0) {
      const confirm = window.confirm(
        `Warning: No servers are selected for ${env.toUpperCase()}. ` +
        `Metrics will NOT be sent to LAMA Exchange until at least one server is selected. ` +
        `Do you want to continue?`
      );
      if (!confirm) {
        return;
      }
    }
    
    setSavingServers(prev => ({ ...prev, [env]: true }));
    setServerSelectionMessage(prev => ({ ...prev, [env]: '' }));
    
    try {
      axios.defaults.baseURL = '/api';
      
      
      const response = await axios.post(
        `/v1/lama-config/server-selection/${env}`,
        {
          environment: env,
          servers: serverSelections[env]
        },
        {
          headers: {  }
        }
      );
      
      if (response.data.status === 'success') {
        // Use functional updates to avoid stale closure issues
        setServerSelectionMessage(prev => ({
          ...prev,
          [env]: `${env.toUpperCase()} server selection saved successfully! ${enabledCount} server(s) enabled.`
        }));
        setTimeout(() => {
          setServerSelectionMessage(prev => ({ ...prev, [env]: '' }));
        }, 5000);
        
        // Update count with functional update
        setServerSelectionCount(prev => ({
          ...prev,
          [env]: {
            enabled: enabledCount,
            total: serverSelections[env].length
          }
        }));
      }
    } catch (error) {
      console.error(`Error saving server selection for ${env}:`, error);
      setServerSelectionMessage(prev => ({
        ...prev,
        [env]: `Error: ${error.response?.data?.detail || error.message}`
      }));
    } finally {
      setSavingServers(prev => ({ ...prev, [env]: false }));
    }
  };

  const handleSelectAllServers = (env) => {
    // Update server selections only - count syncs automatically via useEffect
    // This avoids nested setters and side effects in updater functions (React best practice)
    setServerSelections(prev => ({
      ...prev,
      [env]: prev[env].map(server => ({ ...server, enabled: true }))
    }));
  };

  const handleDeselectAllServers = (env) => {
    // Update server selections only - count syncs automatically via useEffect
    // This avoids nested setters and side effects in updater functions (React best practice)
    setServerSelections(prev => ({
      ...prev,
      [env]: prev[env].map(server => ({ ...server, enabled: false }))
    }));
  };


  const handleToggleChange = async (env, newEnabled) => {
    setSaving({ ...saving, [env]: true });
    setMessage({ ...message, [env]: '' });
    
    try {
      axios.defaults.baseURL = '/api';
      
      
      // Toggle endpoint uses environment in path, not query parameter
      const response = await axios.post(
        `/v1/lama-config/toggle/${env}`,
        { enabled: newEnabled },
        {
          headers: {  }
        }
      );

      if (response.data.status === 'success') {
        setConfigs(prev => ({
          ...prev,
          [env]: { ...prev[env], enabled: newEnabled }
        }));
        
        // Reload exchange status after toggle
        await loadExchangeStatus(env);
        
        const statusText = newEnabled ? 'enabled' : 'disabled';
        const exchangeStatusText = newEnabled 
          ? 'All exchanges (NSE, BSE, MCX, NCDEX) have been enabled.' 
          : 'All exchanges (NSE, BSE, MCX, NCDEX) have been disabled.';
        setMessage({ ...message, [env]: `${env.toUpperCase()} LAMA exchange ${statusText} successfully! ${exchangeStatusText}` });
        setMessageType({ ...messageType, [env]: 'success' });
      } else {
        setMessage({ ...message, [env]: 'Failed to toggle configuration. Please try again.' });
        setMessageType({ ...messageType, [env]: 'error' });
      }
    } catch (error) {
      if (error.response?.status === 404) {
        // Config doesn't exist yet, need to save with credentials
        const config = configs[env];
        if (!config.credentials.member_id || !config.credentials.login_id || 
            !config.credentials.password || !config.credentials.secret_key) {
          setMessage({ ...message, [env]: `Please fill all required fields before enabling ${env.toUpperCase()}` });
          setMessageType({ ...messageType, [env]: 'error' });
          setSaving({ ...saving, [env]: false });
          return;
        }
        await handleSave(env, newEnabled);
        return;
      }
      
      setMessage({ ...message, [env]: error.response?.data?.detail || `Error toggling ${env.toUpperCase()} configuration` });
      setMessageType({ ...messageType, [env]: 'error' });
    } finally {
      setSaving({ ...saving, [env]: false });
    }
  };

  const handleSave = async (env, newEnabled = null) => {
    const config = configs[env];
    const enabledToSave = newEnabled !== null ? newEnabled : config.enabled;
    
    // Validation
    if (enabledToSave && (!config.credentials.member_id || !config.credentials.login_id || 
        !config.credentials.password || !config.credentials.secret_key || !config.credentials.lama_api_url)) {
      setMessage({ ...message, [env]: `Please fill all required fields for ${env.toUpperCase()} before enabling` });
      setMessageType({ ...messageType, [env]: 'error' });
      return;
    }

    setSaving({ ...saving, [env]: true });
    setMessage({ ...message, [env]: '' });

    try {
      axios.defaults.baseURL = '/api';
      
      
      // Save configuration - environment is specified in request body
      // No API test - only saves credentials to database
      const response = await axios.post(
        '/v1/lama-config/',
        {
          environment: env,
          enabled: enabledToSave,
          credentials: {
            member_id: config.credentials.member_id || '',
            login_id: config.credentials.login_id || '',
            password: config.credentials.password || '',
            secret_key: config.credentials.secret_key || '',
            lama_api_url: config.credentials.lama_api_url || '',
          },
        },
        {
          headers: {  },
          timeout: 10000 // 10 seconds - save operation only (no API test)
        }
      );

      if (response.data.status === 'success') {
        const statusText = enabledToSave ? 'enabled' : 'disabled';
        let msg = `${env.toUpperCase()} configuration saved successfully!`;
        setMessageType({ ...messageType, [env]: 'success' });
        
        setMessage({ ...message, [env]: msg });
        await loadAllConfigurations();
      } else {
        setMessage({ ...message, [env]: 'Failed to save configuration. Please try again.' });
        setMessageType({ ...messageType, [env]: 'error' });
      }
    } catch (error) {
      // Handle timeout and network errors gracefully
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout') || error.response?.status === 504) {
        // Request timed out, but config might have been saved
        // Check if we can verify the save by reloading config
        try {
          await loadAllConfigurations();
          setMessage({ 
            ...message, 
            [env]: `Request timed out. Please check your network connection and try again.` 
          });
          setMessageType({ ...messageType, [env]: 'error' });
        } catch (reloadError) {
          setMessage({ 
            ...message, 
            [env]: `Request timed out. Please check your network connection and try again.` 
          });
          setMessageType({ ...messageType, [env]: 'error' });
        }
      } else {
        // Other errors
        setMessage({ 
          ...message, 
          [env]: error.response?.data?.detail || `Error saving ${env.toUpperCase()} configuration: ${error.message || 'Unknown error'}` 
        });
        setMessageType({ ...messageType, [env]: 'error' });
      }
    } finally {
      setSaving({ ...saving, [env]: false });
    }
  };

  const handleCredentialChange = (env, field, value) => {
    setConfigs(prev => ({
      ...prev,
      [env]: {
        ...prev[env],
        credentials: {
          ...prev[env].credentials,
          [field]: value
        }
      }
    }));
  };


  const renderConfigTab = (env) => {
    const config = configs[env];
    const envName = env.toUpperCase();
    const envColor = env === 'uat' ? '#FF9800' : '#4CAF50';

        return (
      <Box sx={{ mt: 3 }}>
        {message[env] && (
          <Alert 
            severity={messageType[env]} 
            sx={{ mb: 3, whiteSpace: 'pre-wrap' }} 
            onClose={() => setMessage({ ...message, [env]: '' })}
          >
            <Box component="div" sx={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>
              {message[env].split(' | ').map((line, idx) => (
                <Box key={idx} component="div" sx={{ marginBottom: idx > 0 ? '4px' : '0' }}>
                  {line}
                </Box>
              ))}
            </Box>
          </Alert>
        )}

        <Paper
          sx={{
            p: 3,
            mb: 3,
            border: `2px solid ${envColor}`,
            borderRadius: 2,
            backgroundColor: '#ffffff',
          }}
        >
          {/* Service Toggle Section */}
          <Box sx={{ mb: 3, p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                  {envName} LAMA SERVICE
                </Typography>
                <Typography variant="body2" sx={{ 
                  color: config.enabled ? '#4CAF50' : '#999',
                  fontWeight: config.enabled ? 600 : 400
                }}>
                  {config.enabled 
                    ? `✓ LAMA ${envName} exchange is ENABLED - Data will be sent to ${envName} exchange APIs.`
                    : `⚠ LAMA ${envName} exchange is DISABLED - Data will NOT be sent to ${envName} exchange APIs.`
                  }
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="body2" color={config.enabled ? 'textSecondary' : 'textPrimary'}>
                  Disable
                </Typography>
                <Switch
                  checked={config.enabled}
                  onChange={(e) => handleToggleChange(env, e.target.checked)}
                  color="primary"
                  disabled={saving[env]}
                />
                <Typography variant="body2" color={config.enabled ? 'textPrimary' : 'textSecondary'}>
                  Enable
                </Typography>
              </Box>
            </Box>
          </Box>

          {/* Exchange Status Section */}
          {config.enabled && exchangeStatus[env] && exchangeStatus[env].length > 0 && (
            <Box sx={{ mt: 2, mb: 2, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                Exchange Status:
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {exchangeStatus[env].map((exchange) => (
                  <Chip
                    key={exchange.exchange_id}
                    label={`${exchange.name}: ${exchange.enabled ? 'Enabled' : 'Disabled'}`}
                    color={exchange.enabled ? 'success' : 'default'}
                    size="small"
                    sx={{
                      fontWeight: exchange.enabled ? 600 : 400,
                    }}
                  />
                ))}
              </Box>
            </Box>
          )}
          {config.enabled && (!exchangeStatus[env] || exchangeStatus[env].length === 0) && (
            <Box sx={{ mt: 2, mb: 2, p: 2, bgcolor: '#fff3cd', borderRadius: 1 }}>
              <Typography variant="body2" color="textSecondary">
                ⚠ Exchange status loading...
              </Typography>
            </Box>
          )}
          {!config.enabled && (
            <Box sx={{ mt: 2, mb: 2, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
              <Typography variant="body2" color="textSecondary">
                All exchanges (NSE, BSE, MCX, NCDEX) are disabled when {envName} is disabled.
              </Typography>
            </Box>
          )}

          {/* Exchange Credentials Section */}
          <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2 }}>
            Exchange Credentials
          </Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
            These credentials will be used to authenticate with {envName} LAMA exchange APIs.
          </Typography>

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              fullWidth
              label="Member ID *"
              value={config.credentials.member_id}
              onChange={(e) => handleCredentialChange(env, 'member_id', e.target.value)}
              variant="outlined"
              size="small"
              required
            />

            <TextField
              fullWidth
              label="Login ID *"
              value={config.credentials.login_id}
              onChange={(e) => handleCredentialChange(env, 'login_id', e.target.value)}
              variant="outlined"
              size="small"
              required
            />

            <TextField
              fullWidth
              label="Password *"
              type={showPassword[env] ? 'text' : 'password'}
              value={config.credentials.password}
              onChange={(e) => handleCredentialChange(env, 'password', e.target.value)}
              variant="outlined"
              size="small"
              required
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label="toggle password visibility"
                      onClick={() => setShowPassword({ ...showPassword, [env]: !showPassword[env] })}
                      onMouseDown={(e) => e.preventDefault()}
                      edge="end"
                      size="small"
                    >
                      {showPassword[env] ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />

            <TextField
              fullWidth
              label="Secret Key *"
              type={showSecretKey[env] ? 'text' : 'password'}
              value={config.credentials.secret_key}
              onChange={(e) => handleCredentialChange(env, 'secret_key', e.target.value)}
              variant="outlined"
              size="small"
              required
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label="toggle secret key visibility"
                      onClick={() => setShowSecretKey({ ...showSecretKey, [env]: !showSecretKey[env] })}
                      onMouseDown={(e) => e.preventDefault()}
                      edge="end"
                      size="small"
                    >
                      {showSecretKey[env] ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />

            <TextField
              fullWidth
              label="LAMA API URL *"
              placeholder="e.g. https://lama.uat.nseindia.com/api/V1"
              value={config.credentials.lama_api_url}
              onChange={(e) => handleCredentialChange(env, 'lama_api_url', e.target.value)}
              variant="outlined"
              size="small"
              required
              helperText="Base URL including version (e.g., /api/V1)"
            />
          </Box>
        </Paper>

        {/* Action Buttons */}
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2, mb: 4 }}>
          <Button
            variant="contained"
            onClick={() => handleSave(env)}
            disabled={saving[env]}
            sx={{
              minWidth: 120,
              background: `linear-gradient(135deg, ${envColor} 0%, ${envColor}dd 100%)`,
            }}
          >
            {saving[env] ? <CircularProgress size={24} sx={{ color: 'white' }} /> : `SAVE ${envName}`}
          </Button>
        </Box>
          </Box>
        );
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 1.5, sm: 2, md: 2.5 }, px: { xs: 1, sm: 1.5, md: 2 } }}>
      <Typography
        variant="h4"
        sx={{
          fontWeight: 'bold',
          fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.75rem', lg: '2rem' },
          mb: { xs: 2, md: 2.5 }
        }}
      >
        Configuration
      </Typography>

      {/* Environment indicator and tip */}
      <Alert 
        severity="info" 
        sx={{ mb: 3 }}
        icon={false}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Chip 
            label={currentEnvironment.toUpperCase()} 
            size="small" 
            sx={{ 
              backgroundColor: currentEnvironment === 'uat' ? '#FF9800' : '#4CAF50',
              color: 'white',
              fontWeight: 'bold',
              height: 24
            }}
          />
          <Typography variant="body2">
            Currently configuring <strong>{currentEnvironment.toUpperCase()}</strong> environment.
            {currentEnvironment === 'prod' 
              ? ' Switch to UAT in the sidebar to configure UAT environment.'
              : ' Switch to PROD in the sidebar to configure PROD environment.'
            }
          </Typography>
        </Box>
      </Alert>

      {renderConfigTab(currentEnvironment)}
      
      {/* Metric Configuration Section - Environment Specific */}
      <Box sx={{ mt: 4 }}>
        <Typography
          variant="h5"
          sx={{
            fontWeight: 'bold',
            fontSize: '1.5rem',
            mb: 3
          }}
        >
          LAMA Exchange Metrics Configuration
        </Typography>
        <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
          Control which metric types are sent to LAMA Exchange for {currentEnvironment.toUpperCase()} environment
        </Typography>
        
        {/* Show Metric Configuration for current environment */}
        {currentEnvironment === 'prod' && (
          <Paper sx={{ maxWidth: 800, mx: 'auto', p: 3, border: '2px solid #4CAF50', borderRadius: 2 }}>
            <Box sx={{ mb: 2 }}>
              <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 0.5, color: '#4CAF50' }}>
                PROD Environment
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                https://lama.nseindia.com/api/V1
              </Typography>
            </Box>
            
            {metricConfigMessage.prod && (
              <Alert 
                severity={metricConfigMessage.prod.includes('Error') ? 'error' : 'success'} 
                sx={{ mb: 2 }}
                onClose={() => setMetricConfigMessage({ ...metricConfigMessage, prod: '' })}
              >
                {metricConfigMessage.prod}
              </Alert>
            )}
            
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={metricConfigs.prod.hardware}
                    onChange={() => handleMetricToggle('prod', 'hardware')}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      Hardware Metrics
                    </Typography>
                    <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                      → /metrics/hardware
                    </Typography>
                  </Box>
                }
              />
              
              <FormControlLabel
                control={
                  <Switch
                    checked={metricConfigs.prod.network}
                    onChange={() => handleMetricToggle('prod', 'network')}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      Network Metrics
                    </Typography>
                    <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                      → /metrics/network
                    </Typography>
                  </Box>
                }
              />
              
              <FormControlLabel
                control={
                  <Switch
                    checked={metricConfigs.prod.database}
                    onChange={() => handleMetricToggle('prod', 'database')}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      Database Metrics
                    </Typography>
                    <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                      → /metrics/database
                    </Typography>
                  </Box>
                }
              />
              
              <FormControlLabel
                control={
                  <Switch
                    checked={metricConfigs.prod.application}
                    onChange={() => handleMetricToggle('prod', 'application')}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      Application Metrics
                    </Typography>
                    <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                      → /metrics/application
                    </Typography>
                  </Box>
                }
              />
            </Box>
            
            <Box sx={{ display: 'flex', gap: 2, mt: 3 }}>
              <Button
                variant="contained"
                onClick={() => handleMetricConfigSave('prod')}
                disabled={savingMetricConfig.prod}
                sx={{
                  flex: 1,
                  background: 'linear-gradient(135deg, #4CAF50 0%, #388E3C 100%)',
                }}
              >
                {savingMetricConfig.prod ? <CircularProgress size={24} sx={{ color: 'white' }} /> : 'Save PROD Configuration'}
              </Button>
            </Box>
          </Paper>
        )}
        
        {/* Show Metric Configuration for current environment */}
        {currentEnvironment === 'uat' && (
          <Paper sx={{ maxWidth: 800, mx: 'auto', p: 3, border: '2px solid #FF9800', borderRadius: 2 }}>
            <Box sx={{ mb: 2 }}>
              <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 0.5, color: '#FF9800' }}>
                UAT Environment
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                https://lama.uat.nseindia.com/api/V1
              </Typography>
            </Box>
            
            {metricConfigMessage.uat && (
              <Alert 
                severity={metricConfigMessage.uat.includes('Error') ? 'error' : 'success'} 
                sx={{ mb: 2 }}
                onClose={() => setMetricConfigMessage({ ...metricConfigMessage, uat: '' })}
              >
                {metricConfigMessage.uat}
              </Alert>
            )}
            
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={metricConfigs.uat.hardware}
                    onChange={() => handleMetricToggle('uat', 'hardware')}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      Hardware Metrics
                    </Typography>
                    <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                      → /metrics/hardware
                    </Typography>
                  </Box>
                }
              />
              
              <FormControlLabel
                control={
                  <Switch
                    checked={metricConfigs.uat.network}
                    onChange={() => handleMetricToggle('uat', 'network')}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      Network Metrics
                    </Typography>
                    <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                      → /metrics/network
                    </Typography>
                  </Box>
                }
              />
              
              <FormControlLabel
                control={
                  <Switch
                    checked={metricConfigs.uat.database}
                    onChange={() => handleMetricToggle('uat', 'database')}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      Database Metrics
                    </Typography>
                    <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                      → /metrics/database
                    </Typography>
                  </Box>
                }
              />
              
              <FormControlLabel
                control={
                  <Switch
                    checked={metricConfigs.uat.application}
                    onChange={() => handleMetricToggle('uat', 'application')}
                    color="primary"
                  />
                }
                label={
                  <Box>
                    <Typography variant="body1" sx={{ fontWeight: 600 }}>
                      Application Metrics
                    </Typography>
                    <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                      → /metrics/application
                    </Typography>
                  </Box>
                }
              />
            </Box>
            
            <Box sx={{ display: 'flex', gap: 2, mt: 3 }}>
              <Button
                variant="contained"
                onClick={() => handleMetricConfigSave('uat')}
                disabled={savingMetricConfig.uat}
                sx={{
                  flex: 1,
                  background: 'linear-gradient(135deg, #FF9800 0%, #F57C00 100%)',
                }}
              >
                {savingMetricConfig.uat ? <CircularProgress size={24} sx={{ color: 'white' }} /> : 'Save UAT Configuration'}
              </Button>
            </Box>
          </Paper>
        )}

        {/* Server Selection Section */}
        <Paper sx={{ maxWidth: 800, mx: 'auto', p: 3, mt: 4, border: `2px solid ${currentEnvironment === 'uat' ? '#FF9800' : '#4CAF50'}`, borderRadius: 2 }}>
          <Box sx={{ mb: 2 }}>
            <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 0.5, color: currentEnvironment === 'uat' ? '#FF9800' : '#4CAF50' }}>
              Server Selection - {currentEnvironment.toUpperCase()} Environment
            </Typography>
            <Typography variant="body2" color="textSecondary">
              Select which servers should send metrics to LAMA Exchange
            </Typography>
          </Box>

          {serverSelectionMessage[currentEnvironment] && (
            <Alert 
              severity={serverSelectionMessage[currentEnvironment].includes('Error') ? 'error' : 'success'} 
              sx={{ mb: 2 }}
              onClose={() => setServerSelectionMessage({ ...serverSelectionMessage, [currentEnvironment]: '' })}
            >
              {serverSelectionMessage[currentEnvironment]}
            </Alert>
          )}

          {/* Warning if no servers selected */}
          {serverSelectionCount[currentEnvironment].enabled === 0 && serverSelectionCount[currentEnvironment].total > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                No servers selected for LAMA Exchange. Metrics will NOT be sent until at least one server is selected.
              </Typography>
            </Alert>
          )}

          {/* Server count status */}
          <Box sx={{ mb: 2, p: 1.5, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
            <Typography variant="body2">
              <strong>{serverSelectionCount[currentEnvironment].enabled}</strong> of{' '}
              <strong>{serverSelectionCount[currentEnvironment].total}</strong> server(s) selected for LAMA Exchange
            </Typography>
          </Box>

          {loadingServers[currentEnvironment] ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : serverSelections[currentEnvironment].length === 0 ? (
            <Alert severity="info">
              No servers found in {currentEnvironment.toUpperCase()} environment. Please add servers first.
            </Alert>
          ) : (
            <>
              {/* Select All / Deselect All buttons */}
              <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => handleSelectAllServers(currentEnvironment)}
                  disabled={savingServers[currentEnvironment]}
                >
                  Select All
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => handleDeselectAllServers(currentEnvironment)}
                  disabled={savingServers[currentEnvironment]}
                >
                  Deselect All
                </Button>
              </Box>

              {/* Server checkboxes */}
              <Box sx={{ maxHeight: 500, overflowY: 'auto', mb: 2 }}>
                <FormGroup>
                  {serverSelections[currentEnvironment].map((server) => (
                    <Box 
                      key={server.server_id} 
                      sx={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        justifyContent: 'space-between',
                        p: 1,
                        borderBottom: '1px solid #eee',
                        '&:hover': { bgcolor: '#fafafa' }
                      }}
                    >
                      <FormControlLabel
                        sx={{ flexGrow: 1 }}
                        control={
                          <Checkbox
                            checked={server.enabled}
                            onChange={() => handleServerToggle(currentEnvironment, server.server_id)}
                            disabled={savingServers[currentEnvironment]}
                          />
                        }
                        label={
                          <Box>
                            <Typography variant="body1" sx={{ fontWeight: 600 }}>
                              {server.server_name}
                            </Typography>
                            <Typography variant="caption" color="textSecondary" sx={{ fontFamily: 'monospace' }}>
                              {server.server_ip}
                            </Typography>
                          </Box>
                        }
                      />
                      
                      {server.enabled && (
                        <FormControl size="small" sx={{ minWidth: 130 }}>
                          <InputLabel id={`source-label-${server.server_id}`}>Metric Source</InputLabel>
                          <Select
                            labelId={`source-label-${server.server_id}`}
                            value={server.metric_source || 'auto'}
                            label="Metric Source"
                            onChange={(e) => handleMetricSourceChange(currentEnvironment, server.server_id, e.target.value)}
                            disabled={savingServers[currentEnvironment]}
                          >
                            <MenuItem value="auto">Auto Discover</MenuItem>
                            <MenuItem value="onprem">On-Prem Account</MenuItem>
                            <MenuItem value="aws">AWS Account</MenuItem>
                          </Select>
                        </FormControl>
                      )}
                    </Box>
                  ))}
                </FormGroup>
              </Box>

              {/* Save button */}
              <Box sx={{ display: 'flex', gap: 2 }}>
                <Button
                  variant="contained"
                  onClick={() => handleServerSelectionSave(currentEnvironment)}
                  disabled={savingServers[currentEnvironment]}
                  sx={{
                    flex: 1,
                    background: currentEnvironment === 'uat' 
                      ? 'linear-gradient(135deg, #FF9800 0%, #F57C00 100%)'
                      : 'linear-gradient(135deg, #4CAF50 0%, #388E3C 100%)',
                  }}
                >
                  {savingServers[currentEnvironment] ? (
                    <CircularProgress size={24} sx={{ color: 'white' }} />
                  ) : (
                    `Save ${currentEnvironment.toUpperCase()} Server Selection`
                  )}
                </Button>
              </Box>
            </>
          )}
        </Paper>

        {/* Clone All Sources to Other Environment */}
        <Paper sx={{ p: 2, mt: 4, mb: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px dashed #90caf9', bgcolor: '#f5f9ff' }}>
          <Box>
            <Typography variant="body1" sx={{ fontWeight: 600 }}>
              Environment Promotion
            </Typography>
            <Typography variant="body2" color="textSecondary">
              Clone all data sources (Prometheus, AWS, Apps) from {currentEnvironment.toUpperCase()} → {currentEnvironment === 'uat' ? 'PROD' : 'UAT'}. Existing sources in target are skipped.
            </Typography>
          </Box>
          <Button
            variant="outlined"
            onClick={async () => {
              const target = currentEnvironment === 'uat' ? 'prod' : 'uat';
              if (!window.confirm(`Clone ALL data sources from ${currentEnvironment.toUpperCase()} → ${target.toUpperCase()}?\n\nThis includes Prometheus endpoints, AWS accounts, and application sources.\nExisting sources in ${target.toUpperCase()} will NOT be affected.`)) return;
              try {
                const res = await axios.post('/v1/metric-sources/promote', { target_environment: target });
                const { cloned, skipped } = res.data;
                alert(`✅ Cloned ${cloned.length} source(s) to ${target.toUpperCase()}.\n${skipped.length ? `Skipped (already exist): ${skipped.join(', ')}` : 'No duplicates.'}`);
              } catch (e) {
                alert('Failed to promote sources: ' + (e.response?.data?.detail || e.message));
              }
            }}
          >
            Clone All → {currentEnvironment === 'uat' ? 'PROD' : 'UAT'}
          </Button>
        </Paper>

        {/* New Prometheus Discovery Section */}
        <PrometheusDiscovery environment={currentEnvironment} />

        {/* New AWS CloudWatch Discovery Section */}
        <AWSDiscovery environment={currentEnvironment} />
      </Box>
    </Container>
  );
};

export default ConfigWizard;
