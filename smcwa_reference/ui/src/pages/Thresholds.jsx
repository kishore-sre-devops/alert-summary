import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Box,
  Card,
  CardHeader,
  CardContent,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  IconButton,
  Alert,
  Typography,
  Chip,
  Switch,
  FormControlLabel,
  Paper,
  Tabs,
  Tab,
  Container,
} from '@mui/material';
import { Add, Edit, Delete as DeleteIcon } from '@mui/icons-material';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';

const METRIC_TYPES = [
  { value: 'hardware', label: 'Hardware' },
  { value: 'network', label: 'Network' },
  { value: 'database', label: 'Database' },
  { value: 'application', label: 'Application' },
];

// Define all metrics based on the reference image
const METRICS = {
  hardware: [
    { key: 'cpu', label: 'CPU (%)' },
    { key: 'memory', label: 'Memory (%)' },
    { key: 'disk', label: 'Disk (%)' },
    { key: 'uptime', label: 'Uptime (minutes)' },
  ],
  network: [
    { key: 'bandwidth', label: 'Bandwidth (%)' },
    { key: 'packetCount', label: 'Packet Count' },
  ],
  database: [
    { key: 'status', label: 'Database Status (1=Up, 0=Down)' },
    { key: 'bandwidth', label: 'Bandwidth (%)' },
    { key: 'qSize', label: 'Queue Size' },
    { key: 'latency', label: 'Latency (milliseconds)' },
  ],
  application: [
    { key: 'throughput', label: 'Throughput (req/s)' },
    { key: 'latency', label: 'Latency (milliseconds)' },
    { key: 'failureTradeApi', label: 'Failure Trade API Count' },
    { key: 'failureAuthentication', label: 'Failure Auth Count' },
    { key: 'historicalThroughput', label: 'Historical Throughput (21d avg)' },
    { key: 'historicalLatency', label: 'Historical Latency (21d avg)' },
  ],
};

export default function Thresholds() {
  const { environment, withEnvironment } = useEnvironment();
  const [thresholds, setThresholds] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('info');
  const [openDialog, setOpenDialog] = useState(false);
  const [editingThreshold, setEditingThreshold] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const [formData, setFormData] = useState({
    metric_type: 'hardware',
    metric_key: '',
    warning_threshold: '',
    error_threshold: '',
    enabled: true,
    interface_name: '', // For per-interface network thresholds
  });

  const location = useLocation();
  const currentUserRole = sessionStorage.getItem('lama_user_role') || 'user';
  const isAdmin = currentUserRole === 'admin';

  useEffect(() => {
    loadThresholds();
  }, [location.pathname, tabValue, environment]); // Reload when environment changes

  const loadThresholds = async () => {
    try {
      setLoading(true);
      
      const metricType = METRIC_TYPES[tabValue]?.value || 'hardware';
      const response = await axios.get(`/v1/thresholds/${metricType}`, {
        headers: {  },
      });
      setThresholds(response.data || []);
      setMessage('');
    } catch (error) {
      setMessage('Error loading thresholds: ' + (error.response?.data?.detail || error.message));
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenDialog = (threshold = null) => {
    if (threshold) {
      setEditingThreshold(threshold);
      // Parse metric_key to extract interface name if present (format: "bandwidth.eth0")
      let metricKey = threshold.metric_key;
      let interfaceName = '';
      if (threshold.metric_type === 'network' && threshold.metric_key.includes('.')) {
        const parts = threshold.metric_key.split('.');
        if (parts.length >= 2) {
          metricKey = parts[0]; // "bandwidth"
          interfaceName = parts.slice(1).join('.'); // "eth0" or "eth0.1" (for complex names)
        }
      }
      setFormData({
        metric_type: threshold.metric_type,
        metric_key: metricKey,
        warning_threshold: threshold.warning_threshold.toString(),
        error_threshold: threshold.error_threshold.toString(),
        enabled: threshold.enabled,
        interface_name: interfaceName,
      });
    } else {
      setEditingThreshold(null);
      // When creating new threshold, use the metric type from the current tab
      const metricType = METRIC_TYPES[tabValue]?.value || 'hardware';
      setFormData({
        metric_type: metricType,
        metric_key: '',
        warning_threshold: '',
        error_threshold: '',
        enabled: true,
        interface_name: '',
      });
    }
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingThreshold(null);
    setFormData({
      metric_type: 'hardware',
      metric_key: '',
      warning_threshold: '',
      error_threshold: '',
      enabled: true,
      interface_name: '',
    });
  };

  const handleSave = async () => {
    if (!formData.metric_key) {
      setMessage('Please select a metric');
      setMessageType('error');
      return;
    }
    const isBinaryStatus = formData.metric_key === 'status' || formData.metric_key === 'db_status';
    
    if (!isBinaryStatus && !formData.warning_threshold) {
      setMessage('Please enter a warning threshold');
      setMessageType('error');
      return;
    }
    if (!formData.error_threshold) {
      setMessage('Please enter a critical threshold');
      setMessageType('error');
      return;
    }

    // For binary status, set warning to -1 to ensure it never triggers, only critical (0)
    const warning = isBinaryStatus ? -1 : parseFloat(formData.warning_threshold);
    const error = parseFloat(formData.error_threshold);

    if ((!isBinaryStatus && isNaN(warning)) || isNaN(error)) {
      setMessage('Thresholds must be valid numbers');
      setMessageType('error');
      return;
    }

    // Metrics where LOW values are bad (uptime, status)
    const lowIsBad = ['uptime', 'status', 'db_status'].includes(formData.metric_key);

    if (lowIsBad && !isBinaryStatus) {
      if (warning <= error) {
        setMessage('For Uptime, Warning threshold should be greater than Critical threshold (e.g., Warning=10, Critical=5)');
        setMessageType('error');
        return;
      }
    } else if (!isBinaryStatus) {
      if (warning >= error) {
        setMessage('Warning threshold must be less than error threshold');
        setMessageType('error');
        return;
      }
    }

    setLoading(true);
    try {
      
      
      // Format metric_key: if network bandwidth with interface, use "bandwidth.eth0" format
      let metricKey = formData.metric_key;
      if (formData.metric_type === 'network' && formData.metric_key === 'bandwidth' && formData.interface_name) {
        metricKey = `bandwidth.${formData.interface_name.trim()}`;
      }
      
      const payload = {
        metric_type: formData.metric_type,
        metric_key: metricKey,
        warning_threshold: warning,
        error_threshold: error,
        enabled: formData.enabled,
      };

      if (editingThreshold) {
        await axios.put(`/v1/thresholds/${editingThreshold.id}`, payload, {
          headers: {  },
        });
        setMessage('Threshold updated successfully!');
      } else {
        await axios.post('/v1/thresholds/', payload, {
          headers: {  },
        });
        setMessage('Threshold created successfully!');
      }

      setMessageType('success');
      handleCloseDialog();
      loadThresholds();
    } catch (error) {
      setMessage('Error saving threshold: ' + (error.response?.data?.detail || error.message));
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (thresholdId) => {
    if (!window.confirm('Are you sure you want to delete this threshold?')) {
      return;
    }

    setLoading(true);
    try {
      
      await axios.delete(`/v1/thresholds/${thresholdId}`, {
        headers: {  },
      });
      setMessage('Threshold deleted successfully!');
      setMessageType('success');
      loadThresholds();
    } catch (error) {
      setMessage('Error deleting threshold: ' + (error.response?.data?.detail || error.message));
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const getAvailableMetrics = () => {
    // Use formData.metric_type instead of tabValue to show correct metrics when user changes metric type in dialog
    const metricType = formData.metric_type || 'hardware';
    const existingKeys = thresholds
      .filter(t => t.metric_type === metricType) // Only filter by existing keys for the same metric type
      .map(t => {
        // For network bandwidth, check base key (without interface) to avoid duplicates
        if (metricType === 'network' && t.metric_key.includes('.')) {
          return t.metric_key.split('.')[0]; // Return "bandwidth" instead of "bandwidth.eth0"
        }
        return t.metric_key;
      });
    return METRICS[metricType]?.filter(m => 
      !existingKeys.includes(m.key) || (editingThreshold && (editingThreshold.metric_key === m.key || editingThreshold.metric_key.split('.')[0] === m.key))
    ) || [];
  };

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 1.5, sm: 2, md: 2.5 }, px: { xs: 1, sm: 1.5, md: 2 } }}>
      <Box sx={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', mb: { xs: 2, md: 2.5 }, gap: 0 }}>
        <Typography variant="h4" sx={{ 
          fontWeight: 'bold', 
          fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.75rem', lg: '2rem' }
        }}>
          Alert Thresholds Configuration
        </Typography>
        {isAdmin && (
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => handleOpenDialog()}
            size={window.innerWidth < 600 ? 'small' : 'medium'}
          >
            Add Threshold
          </Button>
        )}
        {!isAdmin && (
          <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
            Read-only access - Admin required for modifications
          </Typography>
        )}
      </Box>

      {message && (
        <Alert severity={messageType} sx={{ mb: { xs: 2, md: 2.5 } }} onClose={() => setMessage('')}>
          {message}
        </Alert>
      )}

      <Card sx={{ boxShadow: 2, ml: 0 }}>
        <CardHeader
          title="Metric Thresholds"
          subheader="Configure warning and critical thresholds for each metric"
          sx={{
            '& .MuiCardHeader-title': {
              fontSize: { xs: '1rem', sm: '1.125rem', md: '1.25rem' }
            }
          }}
        />
        <CardContent sx={{ p: { xs: 1.5, sm: 2, md: 2.5 }, '&:last-child': { pb: { xs: 1.5, sm: 2, md: 2.5 } } }}>
          <Tabs value={tabValue} onChange={handleTabChange} sx={{ mb: { xs: 1.5, md: 2 }, borderBottom: 1, borderColor: 'divider' }}>
            {METRIC_TYPES.map((type, index) => (
              <Tab key={type.value} label={type.label} />
            ))}
          </Tabs>

          <Box sx={{ overflowX: 'auto', width: '100%', WebkitOverflowScrolling: 'touch' }}>
            <Table sx={{ minWidth: 650 }}>
              <TableHead>
                <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>
                    Metric Key
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>
                    Warning Threshold
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>
                    Critical Threshold
                  </TableCell>
                  <TableCell align="center" sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>
                    Status
                  </TableCell>
                  {isAdmin && (
                    <TableCell align="center" sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>
                      Actions
                    </TableCell>
                  )}
                </TableRow>
              </TableHead>
              <TableBody>
                {thresholds.length > 0 ? (
                  thresholds.map((threshold) => {
                    // Parse metric_key to show interface name if present
                    let displayKey = threshold.metric_key;
                    if (threshold.metric_type === 'network' && threshold.metric_key.includes('.')) {
                      const parts = threshold.metric_key.split('.');
                      if (parts.length >= 2 && parts[0] === 'bandwidth') {
                        const interfaceName = parts.slice(1).join('.');
                        displayKey = `Bandwidth (${interfaceName})`;
                      }
                    } else {
                      const metric = METRICS[threshold.metric_type]?.find(m => m.key === threshold.metric_key);
                      if (metric) {
                        displayKey = metric.label;
                      }
                    }
                    return (
                      <TableRow key={threshold.id} sx={{ '&:hover': { backgroundColor: '#fafafa' } }}>
                        <TableCell sx={{ fontSize: '0.875rem', padding: '16px' }}>
                          {displayKey}
                        </TableCell>
                        <TableCell align="right" sx={{ fontSize: '0.875rem', padding: '16px' }}>
                          {(threshold.metric_key === 'status' || threshold.metric_key === 'db_status') ? 'N/A' : threshold.warning_threshold}
                        </TableCell>
                        <TableCell align="right" sx={{ fontSize: '0.875rem', padding: '16px' }}>
                          {threshold.error_threshold}
                        </TableCell>
                        <TableCell align="center" sx={{ padding: '16px' }}>
                          <Chip
                            label={threshold.enabled ? 'Enabled' : 'Disabled'}
                            color={threshold.enabled ? 'success' : 'default'}
                            size="small"
                            sx={{ fontSize: '0.75rem' }}
                          />
                        </TableCell>
                        {isAdmin && (
                          <TableCell align="center" sx={{ padding: '16px' }}>
                            <IconButton
                              size="small"
                              onClick={() => handleOpenDialog(threshold)}
                              color="primary"
                              sx={{ p: 1 }}
                            >
                              <Edit fontSize="small" />
                            </IconButton>
                            <IconButton
                              size="small"
                              onClick={() => handleDelete(threshold.id)}
                              color="error"
                              sx={{ p: 1 }}
                            >
                              <DeleteIcon fontSize="small" />
                            </IconButton>
                          </TableCell>
                        )}
                      </TableRow>
                    );
                  })
                ) : (
                  <TableRow>
                    <TableCell colSpan={isAdmin ? 5 : 4} sx={{ textAlign: 'center', py: 3, color: '#999' }}>
                      No thresholds configured. {isAdmin && 'Click "Add Threshold" to create one.'}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Box>
        </CardContent>
      </Card>

      {/* Create/Edit Threshold Dialog */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth sx={{ '& .MuiDialog-paper': { m: 2 } }}>
        <DialogTitle>{editingThreshold ? 'Edit Threshold' : 'Create New Threshold'}</DialogTitle>
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <FormControl fullWidth>
            <InputLabel>Metric Type</InputLabel>
            <Select
              value={formData.metric_type}
              label="Metric Type"
              onChange={(e) => setFormData({ ...formData, metric_type: e.target.value, metric_key: '' })}
              disabled={!!editingThreshold}
            >
              {METRIC_TYPES.map((type) => (
                <MenuItem key={type.value} value={type.value}>
                  {type.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth>
            <InputLabel>Metric Key</InputLabel>
            <Select
              value={formData.metric_key}
              label="Metric Key"
              onChange={(e) => setFormData({ ...formData, metric_key: e.target.value, interface_name: '' })}
              disabled={!!editingThreshold}
            >
              {getAvailableMetrics().map((metric) => (
                <MenuItem key={metric.key} value={metric.key}>
                  {metric.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* Interface Name field for network bandwidth thresholds */}
          {formData.metric_type === 'network' && formData.metric_key === 'bandwidth' && (
            <TextField
              fullWidth
              label="Network Interface (Optional)"
              value={formData.interface_name}
              onChange={(e) => setFormData({ ...formData, interface_name: e.target.value })}
              placeholder="e.g., eth0, eth1, wlan0 (leave empty for all interfaces)"
              helperText="Leave empty for aggregated threshold, or specify interface name (e.g., eth0) for per-interface threshold"
            />
          )}

          {/* Conditionally hide Warning Threshold for binary metrics like Status */}
          {formData.metric_key !== 'status' && formData.metric_key !== 'db_status' && (
            <TextField
              fullWidth
              label="Warning Threshold"
              type="number"
              value={formData.warning_threshold}
              onChange={(e) => setFormData({ ...formData, warning_threshold: e.target.value })}
              helperText={['uptime', 'db_status'].includes(formData.metric_key) 
                ? "Alert will trigger when metric value <= this threshold"
                : "Alert will trigger when metric value >= this threshold"
              }
            />
          )}

          <TextField
            fullWidth
            label="Critical Threshold"
            type="number"
            value={formData.error_threshold}
            onChange={(e) => setFormData({ ...formData, error_threshold: e.target.value })}
            helperText={['uptime', 'status', 'db_status'].includes(formData.metric_key)
              ? "Alert will trigger with ERROR severity when metric value <= this threshold"
              : "Alert will trigger with ERROR severity when metric value >= this threshold"
            }
          />

          <FormControlLabel
            control={
              <Switch
                checked={formData.enabled}
                onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
              />
            }
            label="Enable this threshold"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button onClick={handleSave} variant="contained" disabled={loading}>
            {editingThreshold ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}

