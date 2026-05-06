import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardHeader from '@mui/material/CardHeader';
import CardContent from '@mui/material/CardContent';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import TextField from '@mui/material/TextField';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import Alert from '@mui/material/Alert';
import Typography from '@mui/material/Typography';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import Paper from '@mui/material/Paper';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Chip from '@mui/material/Chip';
import Autocomplete from '@mui/material/Autocomplete';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import ListItemSecondaryAction from '@mui/material/ListItemSecondaryAction';
import IconButton from '@mui/material/IconButton';
import Container from '@mui/material/Container';
import Add from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import Save from '@mui/icons-material/Save';
import Send from '@mui/icons-material/Send';
import axios from '../utils/axiosConfig';

const ALERT_CHANNELS = [
  { value: 'email', label: 'Email (SMTP)' },
  { value: 'slack', label: 'Slack (Webhook)' },
];

export default function AlertConfig() {
  const [configs, setConfigs] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('info');
  const [testResult, setTestResult] = useState(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [tabValue, setTabValue] = useState(0);
  const [formData, setFormData] = useState({
    alert_channel: 'email',
    enabled: false,
    // Email config
    smtp_host: '',
    smtp_port: 587,
    smtp_username: '',
    smtp_password: '',
    smtp_from_email: '',
    smtp_to_emails: [],
    smtp_to_user_ids: [],
    smtp_use_tls: true,
    // Slack config
    slack_webhook_url: '',
    slack_channel: '',
    slack_to_user_ids: [],
    // Mobile config
    sms_provider: 'twilio',
    sms_api_key: '',
    sms_api_secret: '',
    sms_from_number: '',
    sms_to_numbers: [],
    sms_to_user_ids: [],
    // Voice config
    voice_provider: 'c-zentrix',
    voice_api_url: '',
    voice_to_numbers: [],
    voice_to_user_ids: [],
    voice_campaign_name: '',
  });
  const [customEmail, setCustomEmail] = useState('');
  const [customMobile, setCustomMobile] = useState('');
  const [customVoice, setCustomVoice] = useState('');

  const location = useLocation();
  const currentUserRole = sessionStorage.getItem('lama_user_role') || 'user';
  const isAdmin = currentUserRole === 'admin';

  useEffect(() => {
    loadConfigs();
    loadUsers();
  }, [location.pathname]);

  const loadConfigs = async () => {
    try {
      setLoading(true);
      
      const response = await axios.get('/v1/alert-config/', {
        headers: {  },
      });
      setConfigs(response.data || []);
      setMessage('');
    } catch (error) {
      setMessage('Error loading alert configurations: ' + (error.response?.data?.detail || error.message));
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const loadUsers = async () => {
    try {
      
      const response = await axios.get('/v1/users/', {
        headers: {  },
      });
      setUsers(response.data || []);
    } catch (error) {
      console.error('Error loading users:', error);
    }
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
    const channel = ALERT_CHANNELS[newValue]?.value || 'email';
    loadConfigForChannel(channel);
  };

  const loadConfigForChannel = async (channel) => {
    try {
      
      const response = await axios.get(`/v1/alert-config/${channel}`, {
        headers: {  },
      });
      const config = response.data;
      
      if (config) {
        setFormData({
          alert_channel: channel,
          enabled: config.enabled || false,
          smtp_host: config.email_config?.smtp_host || '',
          smtp_port: config.email_config?.smtp_port || 587,
          smtp_username: config.email_config?.smtp_username || '',
          smtp_password: '', // Don't load password
          smtp_from_email: config.email_config?.smtp_from_email || '',
          smtp_to_emails: config.email_config?.smtp_to_emails || [],
          smtp_to_user_ids: config.email_config?.smtp_to_user_ids || [],
          smtp_use_tls: config.email_config?.smtp_use_tls !== false,
          slack_webhook_url: '', // Don't load webhook URL
          slack_channel: config.slack_config?.slack_channel || '',
          slack_to_user_ids: config.slack_config?.slack_to_user_ids || [],
          sms_provider: config.mobile_config?.sms_provider || 'twilio',
          sms_api_key: '', // Don't load API key
          sms_api_secret: '', // Don't load API secret
          sms_from_number: config.mobile_config?.sms_from_number || '',
          sms_to_numbers: config.mobile_config?.sms_to_numbers || [],
          sms_to_user_ids: config.mobile_config?.sms_to_user_ids || [],
          voice_provider: config.voice_config?.voice_provider || 'c-zentrix',
          voice_api_url: config.voice_config?.voice_api_url || '',
          voice_to_numbers: config.voice_config?.voice_to_numbers || [],
          voice_to_user_ids: config.voice_config?.voice_to_user_ids || [],
          voice_campaign_name: config.voice_config?.voice_campaign_name || '',
        });
      } else {
        // Reset form for new config
        resetFormForChannel(channel);
      }
    } catch (error) {
      if (error.response?.status === 404) {
        // Config doesn't exist, reset form
        resetFormForChannel(channel);
      } else {
        setMessage('Error loading configuration: ' + (error.response?.data?.detail || error.message));
        setMessageType('error');
      }
    }
  };

  const resetFormForChannel = (channel) => {
    setFormData({
      alert_channel: channel,
      enabled: false,
      smtp_host: '',
      smtp_port: 587,
      smtp_username: '',
      smtp_password: '',
      smtp_from_email: '',
      smtp_to_emails: [],
      smtp_to_user_ids: [],
      smtp_use_tls: true,
      slack_webhook_url: '',
      slack_channel: '',
      slack_to_user_ids: [],
      sms_provider: 'twilio',
      sms_api_key: '',
      sms_api_secret: '',
      sms_from_number: '',
      sms_to_numbers: [],
      sms_to_user_ids: [],
      voice_provider: 'c-zentrix',
      voice_api_url: '',
      voice_to_numbers: [],
      voice_to_user_ids: [],
      voice_campaign_name: '',
    });
    setCustomEmail('');
    setCustomMobile('');
    setCustomVoice('');
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      
      const channel = ALERT_CHANNELS[tabValue]?.value || 'email';
      
      let payload = {
        alert_channel: channel,
        enabled: formData.enabled,
      };

      if (channel === 'email') {
    
        const missingFields = [];
        if (!formData.smtp_host) missingFields.push('SMTP Host');
        if (!formData.smtp_port) missingFields.push('SMTP Port');
        if (!formData.smtp_username) missingFields.push('SMTP Username');
        if (!formData.smtp_from_email) missingFields.push('From Email');
        
        if (missingFields.length > 0) {
          setTestResult({
            success: false,
            message: `Please fill required fields: ${missingFields.join(', ')}`
          });
          setTesting(false);
          return;
        }
        payload.email_config = {
          smtp_host: formData.smtp_host,
          smtp_port: formData.smtp_port,
          smtp_username: formData.smtp_username,
          smtp_password: formData.smtp_password, // Empty is OK - backend will use saved password
          smtp_from_email: formData.smtp_from_email,
          smtp_to_emails: formData.smtp_to_emails,
          smtp_to_user_ids: formData.smtp_to_user_ids,
          smtp_use_tls: formData.smtp_use_tls,
        };
      } else if (channel === 'slack') {
        // Slack webhook can be empty - backend will use saved value
        payload.slack_config = {
          slack_webhook_url: formData.slack_webhook_url, // Empty is OK - backend will use saved URL
          slack_channel: formData.slack_channel,
          slack_to_user_ids: formData.slack_to_user_ids,
        };
      } else if (channel === 'mobile') {
        setTestResult({
          success: false,
          message: 'Mobile/SMS testing is not yet implemented'
        });
        setTesting(false);
        return;
      } else if (channel === 'voice') {
        if (!formData.voice_api_url || 
            !formData.voice_campaign_name) {
          setTestResult({
            success: false,
            message: 'Please fill API URL and Campaign Name'
          });
          setTesting(false);
          return;
        }
        payload.voice_config = {
          voice_provider: formData.voice_provider,
          voice_api_url: formData.voice_api_url,
          voice_to_numbers: formData.voice_to_numbers,
          voice_to_user_ids: formData.voice_to_user_ids,
          voice_campaign_name: formData.voice_campaign_name,
        };
      }

      const response = await axios.post(`/v1/alert-config/${channel}/test`, payload, {
        headers: {  },
      });

      setTestResult(response.data);
    } catch (error) {
      setTestResult({
        success: false,
        message: error.response?.data?.detail || error.message || 'Test failed'
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      
      const channel = ALERT_CHANNELS[tabValue]?.value || 'email';
      
      let payload = {
        alert_channel: channel,
        enabled: formData.enabled,
      };

      if (channel === 'email') {
    
        const missingFields = [];
        if (!formData.smtp_host) missingFields.push('SMTP Host');
        if (!formData.smtp_port) missingFields.push('SMTP Port');
        if (!formData.smtp_username) missingFields.push('SMTP Username');
        if (!formData.smtp_from_email) missingFields.push('From Email');
        
        if (missingFields.length > 0) {
          setMessage(`Please fill required fields: ${missingFields.join(', ')}`);
          setMessageType('error');
          setLoading(false);
          return;
        }
        payload.email_config = {
          smtp_host: formData.smtp_host,
          smtp_port: formData.smtp_port,
          smtp_username: formData.smtp_username,
          smtp_password: formData.smtp_password, // Empty is OK - backend will keep existing
          smtp_from_email: formData.smtp_from_email,
          smtp_to_emails: formData.smtp_to_emails,
          smtp_to_user_ids: formData.smtp_to_user_ids,
          smtp_use_tls: formData.smtp_use_tls,
        };
      } else if (channel === 'slack') {
        // Webhook URL is optional if already saved
        payload.slack_config = {
          slack_webhook_url: formData.slack_webhook_url, // Empty is OK - backend will keep existing
          slack_channel: formData.slack_channel,
          slack_to_user_ids: formData.slack_to_user_ids,
        };
      } else if (channel === 'mobile') {
        if (!formData.sms_provider || !formData.sms_api_key || !formData.sms_api_secret || 
            !formData.sms_from_number) {
          setMessage('Please fill all required mobile/SMS fields');
          setMessageType('error');
          setLoading(false);
          return;
        }
        payload.mobile_config = {
          sms_provider: formData.sms_provider,
          sms_api_key: formData.sms_api_key,
          sms_api_secret: formData.sms_api_secret,
          sms_from_number: formData.sms_from_number,
          sms_to_numbers: formData.sms_to_numbers,
          sms_to_user_ids: formData.sms_to_user_ids,
        };
      } else if (channel === 'voice') {
        if (!formData.voice_api_url ||
            !formData.voice_campaign_name) {
          setMessage('Please fill API URL and Campaign Name');
          setMessageType('error');
          setLoading(false);
          return;
        }
        payload.voice_config = {
          voice_provider: formData.voice_provider,
          voice_api_url: formData.voice_api_url,
          voice_to_numbers: formData.voice_to_numbers,
          voice_to_user_ids: formData.voice_to_user_ids,
          voice_campaign_name: formData.voice_campaign_name,
        };
      }

      await axios.post('/v1/alert-config/', payload, {
        headers: {  },
      });

      setMessage('Alert configuration saved successfully!');
      setMessageType('success');
      loadConfigs();
      loadConfigForChannel(channel);
    } catch (error) {
      setMessage('Error saving configuration: ' + (error.response?.data?.detail || error.message));
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const addCustomEmail = () => {
    if (customEmail && !formData.smtp_to_emails.includes(customEmail)) {
      setFormData({ ...formData, smtp_to_emails: [...formData.smtp_to_emails, customEmail] });
      setCustomEmail('');
    }
  };

  const removeCustomEmail = (email) => {
    setFormData({ ...formData, smtp_to_emails: formData.smtp_to_emails.filter(e => e !== email) });
  };

  const addCustomMobile = () => {
    if (customMobile && !formData.sms_to_numbers.includes(customMobile)) {
      setFormData({ ...formData, sms_to_numbers: [...formData.sms_to_numbers, customMobile] });
      setCustomMobile('');
    }
  };

  const removeCustomMobile = (number) => {
    setFormData({ ...formData, sms_to_numbers: formData.sms_to_numbers.filter(n => n !== number) });
  };

  const addCustomVoiceNumber = () => {
    if (customVoice && !formData.voice_to_numbers.includes(customVoice)) {
      setFormData({ ...formData, voice_to_numbers: [...formData.voice_to_numbers, customVoice] });
      setCustomVoice('');
    }
  };

  const removeCustomVoiceNumber = (number) => {
    setFormData({ ...formData, voice_to_numbers: formData.voice_to_numbers.filter(n => n !== number) });
  };

  const handleUserSelection = (userIds) => {
    const channel = ALERT_CHANNELS[tabValue]?.value || 'email';
    if (channel === 'email') {
      setFormData({ ...formData, smtp_to_user_ids: userIds });
    } else if (channel === 'slack') {
      setFormData({ ...formData, slack_to_user_ids: userIds });
    } else if (channel === 'mobile') {
      setFormData({ ...formData, sms_to_user_ids: userIds });
    } else if (channel === 'voice') {
      setFormData({ ...formData, voice_to_user_ids: userIds });
    }
  };

  const getSelectedUsers = () => {
    const channel = ALERT_CHANNELS[tabValue]?.value || 'email';
    if (channel === 'email') {
      return formData.smtp_to_user_ids || [];
    } else if (channel === 'slack') {
      return formData.slack_to_user_ids || [];
    } else if (channel === 'mobile') {
      return formData.sms_to_user_ids || [];
    } else if (channel === 'voice') {
      return formData.voice_to_user_ids || [];
    }
    return [];
  };

  const getSelectedUserEmails = () => {
    const selectedIds = getSelectedUsers();
    return users.filter(u => selectedIds.includes(u.id)).map(u => u.email).filter(Boolean);
  };

  const getSelectedUserMobiles = () => {
    const selectedIds = getSelectedUsers();
    return users.filter(u => selectedIds.includes(u.id)).map(u => u.mobile).filter(Boolean);
  };

  useEffect(() => {
    const channel = ALERT_CHANNELS[tabValue]?.value || 'email';
    loadConfigForChannel(channel);
  }, [tabValue]);

  const currentChannel = ALERT_CHANNELS[tabValue]?.value || 'email';
  const currentConfig = configs.find(c => c.alert_channel === currentChannel);

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 1.5, sm: 2, md: 2.5 }, px: { xs: 1, sm: 1.5, md: 2 } }}>
      <Box sx={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', mb: { xs: 2, md: 2.5 }, gap: 0 }}>
        <Typography variant="h4" sx={{ 
          fontWeight: 'bold', 
          fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.75rem', lg: '2rem' }
        }}>
          Alert Configuration
        </Typography>
        {isAdmin && (
          <Box sx={{ display: 'flex', gap: 1 }}>
            {(currentChannel === 'email' || currentChannel === 'slack') && (
              <Button
                variant="outlined"
                startIcon={<Send />}
                onClick={handleTest}
                disabled={testing || loading}
                size={window.innerWidth < 600 ? 'small' : 'medium'}
                color="primary"
              >
                {testing ? 'Testing...' : 'Test'}
              </Button>
            )}
            <Button
              variant="contained"
              startIcon={<Save />}
              onClick={handleSave}
              disabled={loading || testing}
              size={window.innerWidth < 600 ? 'small' : 'medium'}
            >
              Save Configuration
            </Button>
          </Box>
        )}
        {!isAdmin && (
          <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
            Read-only access - Admin required for modifications
          </Typography>
        )}
      </Box>

      {message && (
        <Alert severity={messageType} sx={{ mb: 3 }} onClose={() => setMessage('')}>
          {message}
        </Alert>
      )}

      {testResult && (
        <Alert 
          severity={testResult.success ? 'success' : 'error'} 
          sx={{ mb: 3 }} 
          onClose={() => setTestResult(null)}
        >
          <Typography variant="body1" sx={{ fontWeight: 'bold', mb: 0.5 }}>
            {testResult.success ? '✅ Test Successful' : '❌ Test Failed'}
          </Typography>
          <Typography variant="body2">
            {testResult.message}
          </Typography>
        </Alert>
      )}

      <Card sx={{ boxShadow: 2, ml: 0 }}>
        <CardHeader
          title="Alert Channel Configuration"
          subheader="Configure Email and Slack alert settings"
          sx={{
            '& .MuiCardHeader-title': {
              fontSize: '1.25rem'
            }
          }}
        />
        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
          <Tabs value={tabValue} onChange={handleTabChange} sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}>
            {ALERT_CHANNELS.map((channel, index) => (
              <Tab key={channel.value} label={channel.label} />
            ))}
          </Tabs>

          <FormControlLabel
            control={
              <Switch
                checked={formData.enabled}
                onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                disabled={!isAdmin}
              />
            }
            label={`Enable ${ALERT_CHANNELS[tabValue]?.label} Alerts`}
            sx={{ mb: 3 }}
          />

          {currentChannel === 'email' && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Typography variant="h6" sx={{ fontWeight: 'bold' }}>SMTP Configuration</Typography>
              
              <TextField
                fullWidth
                label="SMTP Host"
                value={formData.smtp_host}
                onChange={(e) => setFormData({ ...formData, smtp_host: e.target.value })}
                disabled={!isAdmin}
                required
              />

              <TextField
                fullWidth
                label="SMTP Port"
                type="number"
                value={formData.smtp_port}
                onChange={(e) => setFormData({ ...formData, smtp_port: e.target.value })}
                disabled={!isAdmin}
                required
              />

              <TextField
                fullWidth
                label="SMTP Username"
                value={formData.smtp_username}
                onChange={(e) => setFormData({ ...formData, smtp_username: e.target.value })}
                disabled={!isAdmin}
                required
              />

              <TextField
                fullWidth
                label="SMTP Password"
                type="password"
                value={formData.smtp_password}
                onChange={(e) => setFormData({ ...formData, smtp_password: e.target.value })}
                disabled={!isAdmin}
                required
              />

              <TextField
                fullWidth
                label="From Email"
                type="email"
                value={formData.smtp_from_email}
                onChange={(e) => setFormData({ ...formData, smtp_from_email: e.target.value })}
                disabled={!isAdmin}
                required
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={formData.smtp_use_tls}
                    onChange={(e) => setFormData({ ...formData, smtp_use_tls: e.target.checked })}
                    disabled={!isAdmin}
                  />
                }
                label="Use TLS/SSL"
              />

              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mt: 2 }}>Email Recipients</Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1 }}>
                Select users from the system or add custom email addresses
              </Typography>

              <Autocomplete
                multiple
                options={users.filter(u => u.email)}
                getOptionLabel={(option) => `${option.full_name || option.email} (${option.email})`}
                value={users.filter(u => getSelectedUsers().includes(u.id))}
                onChange={(event, newValue) => {
                  handleUserSelection(newValue.map(u => u.id));
                }}
                disabled={!isAdmin}
                renderInput={(params) => (
                  <TextField {...params} label="Select Users" placeholder="Choose users to receive alerts" />
                )}
              />

              <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                <TextField
                  fullWidth
                  label="Add Custom Email"
                  type="email"
                  value={customEmail}
                  onChange={(e) => setCustomEmail(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && addCustomEmail()}
                  disabled={!isAdmin}
                />
                <Button variant="outlined" onClick={addCustomEmail} disabled={!isAdmin || !customEmail}>
                  Add
                </Button>
              </Box>

              {formData.smtp_to_emails.length > 0 && (
                <Paper sx={{ p: 2, mt: 1 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>Custom Email Addresses:</Typography>
                  <List dense>
                    {formData.smtp_to_emails.map((email, index) => (
                      <ListItem key={index}>
                        <ListItemText primary={email} />
                        {isAdmin && (
                          <ListItemSecondaryAction>
                            <IconButton edge="end" onClick={() => removeCustomEmail(email)} size="small">
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </ListItemSecondaryAction>
                        )}
                      </ListItem>
                    ))}
                  </List>
                </Paper>
              )}

              {getSelectedUserEmails().length > 0 && (
                <Paper sx={{ p: 2, mt: 1 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>Selected User Emails:</Typography>
                  <List dense>
                    {getSelectedUserEmails().map((email, index) => (
                      <ListItem key={index}>
                        <ListItemText primary={email} />
                      </ListItem>
                    ))}
                  </List>
                </Paper>
              )}
            </Box>
          )}

          {currentChannel === 'slack' && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Typography variant="h6" sx={{ fontWeight: 'bold' }}>Slack Webhook Configuration</Typography>
              
              <TextField
                fullWidth
                label="Slack Webhook URL"
                type="password"
                value={formData.slack_webhook_url}
                onChange={(e) => setFormData({ ...formData, slack_webhook_url: e.target.value })}
                disabled={!isAdmin}
                required
                helperText="Enter your Slack webhook URL (will be encrypted)"
              />

              <TextField
                fullWidth
                label="Slack Channel (Optional)"
                value={formData.slack_channel}
                onChange={(e) => setFormData({ ...formData, slack_channel: e.target.value })}
                disabled={!isAdmin}
                helperText="Channel name (e.g., #alerts). Leave empty to use webhook default."
              />

              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mt: 2 }}>Slack Recipients</Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 1 }}>
                Select users (for future use if Slack user IDs are stored)
              </Typography>

              <Autocomplete
                multiple
                options={users}
                getOptionLabel={(option) => `${option.full_name || option.email || option.mobile} (${option.email || option.mobile})`}
                value={users.filter(u => getSelectedUsers().includes(u.id))}
                onChange={(event, newValue) => {
                  handleUserSelection(newValue.map(u => u.id));
                }}
                disabled={!isAdmin}
                renderInput={(params) => (
                  <TextField {...params} label="Select Users" placeholder="Choose users (optional)" />
                )}
              />
            </Box>
          )}
        </CardContent>
      </Card>
    </Container>
  );
}