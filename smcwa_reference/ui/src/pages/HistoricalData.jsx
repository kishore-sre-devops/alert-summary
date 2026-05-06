import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  CircularProgress,
  Card,
  CardContent,
  Tabs,
  Tab,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Menu,
  Container,
} from '@mui/material';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import DownloadIcon from '@mui/icons-material/Download';
import RefreshIcon from '@mui/icons-material/Refresh';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';

const HistoricalData = () => {
  const { environment, withEnvironment } = useEnvironment();
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  // Date and time range (combined)
  const [startDateTime, setStartDateTime] = useState(null);
  const [endDateTime, setEndDateTime] = useState(null);
  
  // Filters
  const [metricType, setMetricType] = useState('');
  const [status, setStatus] = useState('');
  const [exchangeFilter, setExchangeFilter] = useState('ALL');
  const [sequenceIdSearch, setSequenceIdSearch] = useState('');
  const [interval, setInterval] = useState('1440'); // Default: Last 24 hours
  const [viewType, setViewType] = useState('activity'); // 'activity' or 'transactions'
  
  // Data
  const [exchangeTransactions, setExchangeTransactions] = useState([]);
  const [serverMetrics, setServerMetrics] = useState([]);
  
  // Details modal state
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [selectedTransaction, setSelectedTransaction] = useState(null);
  const [serverDetails, setServerDetails] = useState([]);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState(null);
  const [selectedRowId, setSelectedRowId] = useState(null);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [selectedJsonData, setSelectedJsonData] = useState(null);
  useEffect(() => {
    // Initial data load
    fetchExchangeTransactions();
  }, []);

  // Auto-fetch when interval changes (for Exchange Activity tab)
  useEffect(() => {
    if (interval && tabValue === 0) {
      // Clear data immediately to show loading state
      setExchangeTransactions([]);
      // Fetch with new interval - use a small delay to ensure state is updated
      const timer = setTimeout(() => {
        fetchExchangeTransactions();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [interval, tabValue]);

  // Auto-fetch when tab changes or environment changes
  useEffect(() => {
    if (tabValue === 0) {
      fetchExchangeTransactions();
    } else if (tabValue === 1) {
      fetchServerMetrics();
    }
  }, [tabValue, environment]); // Reload when environment changes from sidebar

  const fetchExchangeTransactions = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {};
      
      // Unified date/time selection: Use interval OR custom date/time
      // CRITICAL: Use UTC dates/times for API calls since database stores UTC
      if (interval && interval !== 'custom') {
        // Use predefined interval (5 mins, 15 mins, etc.)
        const now = new Date();
        const intervalMinutes = parseInt(interval, 10);
        if (isNaN(intervalMinutes)) {
          console.error('Invalid interval:', interval);
          // Default to 15 minutes if invalid
          const minutesAgo = new Date(now.getTime() - 15 * 60 * 1000);
          params.start_date = formatDateUTC(minutesAgo);
          params.end_date = formatDateUTC(now);
          params.start_time = formatTimeFromDateUTC(minutesAgo);
          params.end_time = formatTimeFromDateUTC(now);
        } else {
          const minutesAgo = new Date(now.getTime() - intervalMinutes * 60 * 1000);
          params.start_date = formatDateUTC(minutesAgo);
          params.end_date = formatDateUTC(now);
          // Include time for precise filtering
          params.start_time = formatTimeFromDateUTC(minutesAgo);
          params.end_time = formatTimeFromDateUTC(now);
      
        }
      } else if (interval === 'custom' && startDateTime && endDateTime) {
        // Use custom DateTimePicker values
        params.start_date = formatDateUTC(startDateTime);
        params.start_time = formatTimeFromDateUTC(startDateTime);
        params.end_date = formatDateUTC(endDateTime);
        params.end_time = formatTimeFromDateUTC(endDateTime);
      } else {
        // Default: Last 15 minutes if nothing is selected
        const now = new Date();
        const minutesAgo = new Date(now.getTime() - 15 * 60 * 1000);
        params.start_date = formatDateUTC(minutesAgo);
        params.end_date = formatDateUTC(now);
        params.start_time = formatTimeFromDateUTC(minutesAgo);
        params.end_time = formatTimeFromDateUTC(now);
      }
      
      // Always include environment from sidebar selector
      params = { ...params, ...withEnvironment() };
      if (metricType) params.metric_type = metricType;
      if (status) params.status = status;
      
      const response = await axios.get('/v1/historical/exchange-transactions', { params });
      setExchangeTransactions(response.data.transactions || []);
      setSuccess(`Loaded ${response.data.count} exchange transactions`);
    } catch (error) {
      console.error('Error fetching exchange transactions:', error);
      setError('Failed to load exchange transactions');
    } finally {
      setLoading(false);
    }
  };
  
  // Removed handleIntervalChange, handleStartDateTimeChange, handleEndDateTimeChange
  // Now handled directly in the onChange handlers above
  
  const formatTimeFromDate = (dateValue) => {
    if (!dateValue) return '';
    const d = new Date(dateValue);
    // Validate date object
    if (isNaN(d.getTime())) {
      console.error('Invalid date in formatTimeFromDate:', dateValue);
      return '';
    }
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const seconds = String(d.getSeconds()).padStart(2, '0');
    return `${hours}:${minutes}:${seconds}`;
  };

  // Format date/time in UTC for API calls (database stores UTC)
  const formatDateUTC = (date) => {
    if (!date) return '';
    const d = new Date(date);
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
  };

  const formatTimeFromDateUTC = (dateValue) => {
    if (!dateValue) return '';
    const d = new Date(dateValue);
    // Validate date object
    if (isNaN(d.getTime())) {
      console.error('Invalid date in formatTimeFromDateUTC:', dateValue);
      return '';
    }
    // Use UTC methods to get UTC time
    const hours = String(d.getUTCHours()).padStart(2, '0');
    const minutes = String(d.getUTCMinutes()).padStart(2, '0');
    const seconds = String(d.getUTCSeconds()).padStart(2, '0');
    return `${hours}:${minutes}:${seconds}`;
  };

  const fetchServerMetrics = async () => {
    setLoading(true);
    setError('');
    try {
      const params = {};
      // CRITICAL: Use UTC dates/times for API calls since database stores UTC
      if (startDateTime) {
        params.start_date = formatDateUTC(startDateTime);
        params.start_time = formatTimeFromDateUTC(startDateTime);
      }
      if (endDateTime) {
        params.end_date = formatDateUTC(endDateTime);
        params.end_time = formatTimeFromDateUTC(endDateTime);
      }
      
      // Always include environment from sidebar selector
      const response = await axios.get('/v1/historical/server-metrics', { 
        params: { ...params, ...withEnvironment() } 
      });
      setServerMetrics(response.data.metrics || []);
      setSuccess(`Loaded ${response.data.count} server metrics`);
    } catch (error) {
      console.error('Error fetching server metrics:', error);
      setError('Failed to load server metrics');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    setError('');
    try {
      const params = {
        data_type: tabValue === 0 ? 'exchange' : 'both'
      };
      
      // Unified date/time selection: Use interval OR custom date/time
      // CRITICAL: Use UTC dates/times for API calls since database stores UTC
      if (interval && interval !== 'custom') {
        const now = new Date();
        const minutesAgo = new Date(now.getTime() - parseInt(interval) * 60 * 1000);
        params.start_date = formatDateUTC(minutesAgo);
        params.end_date = formatDateUTC(now);
        params.start_time = formatTimeFromDateUTC(minutesAgo);
        params.end_time = formatTimeFromDateUTC(now);
      } else if (interval === 'custom' && startDateTime && endDateTime) {
        params.start_date = formatDateUTC(startDateTime);
        params.start_time = formatTimeFromDateUTC(startDateTime);
        params.end_date = formatDateUTC(endDateTime);
        params.end_time = formatTimeFromDateUTC(endDateTime);
      } else {
        // Default: Last 15 minutes
        const now = new Date();
        const minutesAgo = new Date(now.getTime() - 15 * 60 * 1000);
        params.start_date = formatDateUTC(minutesAgo);
        params.end_date = formatDateUTC(now);
        params.start_time = formatTimeFromDateUTC(minutesAgo);
        params.end_time = formatTimeFromDateUTC(now);
      }
      
      // Always include environment from sidebar selector
      params = { ...params, ...withEnvironment() };
      
      const response = await axios.get('/v1/historical/export/excel', {
        params,
        responseType: 'blob'
      });
      
      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      
      // Generate filename with date and time
      let filename = 'lama_historical_data';
      if (startDateTime) {
        filename += `_${formatDate(startDateTime)}`;
        filename += `_${formatTimeFromDate(startDateTime).replace(/:/g, '-')}`;
      }
      if (endDateTime) {
        filename += `_to_${formatDate(endDateTime)}`;
        filename += `_${formatTimeFromDate(endDateTime).replace(/:/g, '-')}`;
      }
      filename += '.xlsx';
      
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      
      setSuccess('Excel file downloaded successfully');
    } catch (error) {
      console.error('Error exporting data:', error);
      setError('Failed to export data to Excel: ' + (error.response?.data?.detail || error.message));
    } finally {
      setExporting(false);
    }
  };

  const formatDate = (date) => {
    if (!date) return '';
    const d = new Date(date);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };

  const formatTimeString = (timeString) => {
    // Convert HH:MM to HH:MM:SS format
    if (!timeString) return '';
    if (typeof timeString === 'string' && timeString.length === 5) {
      return timeString + ':00'; // Add seconds if missing
    }
    return timeString;
  };

  const formatDateTime = (isoString) => {
    if (!isoString) return '';
    // Database stores IST (PostgreSQL timezone=Asia/Kolkata).
    const date = new Date(isoString);
    return date.toLocaleString('en-IN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
    if (newValue === 0) {
      // Exchange Activity - fetch with interval filter
      fetchExchangeTransactions();
    } else {
      // Server Metrics (was index 2, now index 1)
      fetchServerMetrics();
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'success': return 'success';
      case 'failed': return 'error';
      case 'error': return 'warning';
      case 'timeout': return 'warning';
      case 'protocol_error': return 'warning';
      case 'request_error': return 'warning';
      case 'connection_error': return 'warning';
      default: return 'default';
    }
  };
  
  // Determine display status based on transaction status and error type
  // CRITICAL: Per LAMA Exchange API specification, ONLY responseCode 601 = SUCCESS
  // All other response codes (602, 603, 704, 708, 801, etc.) are treated as UNSUCCESSFUL
  // This logic applies to ALL metric types (Hardware/System, Network, Database, Application)
  // and BOTH environments (PROD and UAT)
  const getDisplayStatus = (tx) => {
    const status = tx.status?.toLowerCase() || '';
    const responseCode = tx.exchange_response?.responseCode || tx.exchange_response?.response_code;
    
    // Check if responseCode is 601 (ONLY code considered as SUCCESS per LAMA Exchange spec)
    if (responseCode === 601 || responseCode === '601') {
      return 'SUCCESS';
    }
    
    // If we got a response from exchange but not 601, it's FAILED
    if (responseCode) {
      return 'FAILED';
    }
    
    // If no response from exchange (timeout, connection errors), it's NOT FOUND
    if (['error', 'timeout', 'protocol_error', 'request_error', 'connection_error'].includes(status)) {
      return 'NOT FOUND';
    }
    
    // Fallback: use status from database
    if (status === 'success') {
      // Legacy: if status is 'success' but responseCode is not 601, treat as FAILED
      // This handles old records that might have been marked as success incorrectly
      return 'FAILED';
    }
    
    return status.toUpperCase();
  };
  
  // Determine if sequence ID should be shown
  // CRITICAL: Always show sequence ID if it exists - needed for matching exchange alerts
  const shouldShowSequenceId = (tx) => {
    // Show sequence ID if:
    // 1. It exists in the transaction (from metrics_sent payload or sequence_id field)
    // 2. OR if we have a response code (meaning exchange responded)
    const sequenceId = tx.sequence_id || tx.metrics_sent?.lama_v1_2_payload?.sequenceId;
    const responseCode = tx.exchange_response?.responseCode || tx.exchange_response?.response_code;
    
    // Always show if sequence ID exists, or if we got a response from exchange
    return (sequenceId !== undefined && sequenceId !== null && sequenceId !== '') || 
           (responseCode !== undefined && responseCode !== null);
  };
  
  // Get error message for display
  const getErrorMessage = (tx) => {
    const status = tx.status?.toLowerCase() || '';
    const responseCode = tx.exchange_response?.responseCode || tx.exchange_response?.response_code;
    const responseDesc = tx.exchange_response?.responseDesc || tx.exchange_response?.response_desc || tx.exchange_response?.message;
    const errorMsg = tx.error_message;
    
    // For NOT FOUND (timeout, connection errors), show actual error
    if (['error', 'timeout', 'protocol_error', 'request_error', 'connection_error'].includes(status)) {
      return errorMsg || 'Data Not Found';
    }
    
    // For FAILED with exchange response, show response description
    if (status === 'failed' && responseDesc) {
      return responseDesc;
    }
    
    // Fallback to error_message
    return errorMsg || 'Unknown error';
  };

  const getMetricTypeColor = (type) => {
    switch (type) {
      case 'hardware': return 'primary';
      case 'network': return 'info';
      case 'database': return 'secondary';
      case 'application': return 'success';
      default: return 'default';
    }
  };

  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Container maxWidth="xl" sx={{ py: { xs: 1.5, sm: 2, md: 2.5 }, px: { xs: 1, sm: 1.5, md: 2 } }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: { xs: 2, md: 2.5 } }}>
        <Typography variant="h4" sx={{ 
          fontWeight: 'bold', 
          fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.75rem', lg: '2rem' }
        }}>
          Historical Data
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title="Refresh">
            <IconButton onClick={() => {
              if (tabValue === 0) fetchExchangeTransactions();
              else fetchServerMetrics();
            }}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
          <Button
            variant="contained"
            startIcon={<DownloadIcon />}
            onClick={handleExport}
            disabled={exporting}
            sx={{ background: 'linear-gradient(135deg, #1976d2 0%, #1565c0 100%)' }}
          >
            {exporting ? <CircularProgress size={20} sx={{ color: 'white' }} /> : 'Export Excel'}
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess('')}>
          {success}
        </Alert>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Time Range</InputLabel>
                <Select
                  value={interval || '1440'}
                  onChange={(e) => {
                    const value = e.target.value;
                    setInterval(value);
                    if (value === 'custom') {
                      // Don't clear date/time when switching to custom
                    } else {
                      setStartDateTime(null);
                      setEndDateTime(null);
                    }
                    // Data will be fetched automatically via useEffect when interval state updates
                  }}
                  label="Time Range"
                >
                  <MenuItem value="5">Last 5 minutes</MenuItem>
                  <MenuItem value="15">Last 15 minutes</MenuItem>
                  <MenuItem value="30">Last 30 minutes</MenuItem>
                  <MenuItem value="60">Last 1 hour</MenuItem>
                  <MenuItem value="1440">Last 24 hours</MenuItem>
                  <MenuItem value="custom">Custom Date & Time</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            {interval === 'custom' && (
              <>
                <Grid item xs={12} sm={6} md={3}>
                  <DateTimePicker
                    label="Start Date & Time"
                    value={startDateTime}
                    onChange={(newValue) => {
                      setStartDateTime(newValue);
                      if (startDateTime && endDateTime) {
                        setTimeout(() => {
                          if (tabValue === 0) fetchExchangeTransactions();
                          else fetchServerMetrics();
                        }, 500);
                      }
                    }}
                    slotProps={{
                      textField: {
                        fullWidth: true,
                        size: 'small'
                      }
                    }}
                  />
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <DateTimePicker
                    label="End Date & Time"
                    value={endDateTime}
                    onChange={(newValue) => {
                      setEndDateTime(newValue);
                      if (startDateTime && endDateTime) {
                        setTimeout(() => {
                          if (tabValue === 0) fetchExchangeTransactions();
                          else fetchServerMetrics();
                        }, 500);
                      }
                    }}
                    slotProps={{
                      textField: {
                        fullWidth: true,
                        size: 'small'
                      }
                    }}
                  />
                </Grid>
              </>
            )}
            <Grid item xs={12} sm={6} md={interval === 'custom' ? 2 : 2}>
              <FormControl fullWidth size="small">
                <InputLabel>Metric Type</InputLabel>
                <Select
                  value={metricType || ''}
                  onChange={(e) => {
                    setMetricType(e.target.value);
                    // Auto-load when metric type changes
                    setTimeout(() => {
                      if (tabValue === 0) fetchExchangeTransactions();
                      else fetchServerMetrics();
                    }, 100);
                  }}
                  label="Metric Type"
                >
                  <MenuItem value="">All</MenuItem>
                  <MenuItem value="hardware">Hardware</MenuItem>
                  <MenuItem value="network">Network</MenuItem>
                  <MenuItem value="database">Database</MenuItem>
                  <MenuItem value="application">Application</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={interval === 'custom' ? 2 : 2}>
              <FormControl fullWidth size="small">
                <InputLabel>Status</InputLabel>
                <Select
                  value={status || ''}
                  onChange={(e) => {
                    setStatus(e.target.value);
                    // Auto-load when status changes
                    setTimeout(() => {
                      if (tabValue === 0) fetchExchangeTransactions();
                      else fetchServerMetrics();
                    }, 100);
                  }}
                  label="Status"
                >
                  <MenuItem value="">All</MenuItem>
                  <MenuItem value="success">Success</MenuItem>
                  <MenuItem value="failed">Failed</MenuItem>
                  <MenuItem value="error">Error</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            {tabValue === 0 && (
              <>
                <Grid item xs={12} sm={6} md={interval === 'custom' ? 2 : 2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Exchange</InputLabel>
                    <Select
                      value={exchangeFilter}
                      onChange={(e) => {
                        setExchangeFilter(e.target.value);
                        // Exchange filter is client-side only, no need to reload
                      }}
                      label="Exchange"
                    >
                      <MenuItem value="ALL">ALL</MenuItem>
                      <MenuItem value="1">NSE</MenuItem>
                      <MenuItem value="2">BSE</MenuItem>
                      <MenuItem value="3">MSE</MenuItem>
                      <MenuItem value="4">MCX</MenuItem>
                      <MenuItem value="5">NCDEX</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={interval === 'custom' ? 2 : 2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>View Type</InputLabel>
                    <Select
                      value={viewType}
                      onChange={(e) => {
                        setViewType(e.target.value);
                        // Data is already loaded, just change view
                      }}
                      label="View Type"
                    >
                      <MenuItem value="activity">Activity View</MenuItem>
                      <MenuItem value="transactions">Transactions View</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
              </>
            )}
          </Grid>
        </CardContent>
      </Card>

      <Paper>
        <Tabs value={tabValue} onChange={handleTabChange} sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tab label="Exchange Activity" />
          <Tab label="Server Metrics" />
        </Tabs>

        {tabValue === 0 && (
          <>
            {viewType === 'activity' && (
              <Box sx={{ p: 2 }}>
                {/* Exchange Activity Filters - Only unique filters for this tab */}
                <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
                  <TextField
                    size="small"
                    label="Search for Sequence ID's"
                    value={sequenceIdSearch}
                    onChange={(e) => setSequenceIdSearch(e.target.value)}
                    sx={{ minWidth: 200 }}
                    InputProps={{
                      startAdornment: <IconButton size="small" sx={{ mr: 1 }}>🔍</IconButton>
                    }}
                  />
                  
                  {/* Note: Exchange filter moved to top filter bar */}
                </Box>
                
                {/* Exchange Activity Table */}
            {loading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
              </Box>
            ) : (
              <Box>
                <Alert severity="info" sx={{ mb: 2 }}>
                  <Typography variant="body2">
                    <strong>Time Display:</strong> The "Time" column shows the <strong>actual timestamp</strong> when each transaction was sent to LAMA Exchange (historical data in IST), not the current viewing time. To see recent transactions, use the <strong>"Time Range"</strong> filter in the filter panel above.
                  </Typography>
                </Alert>
                <TableContainer sx={{ maxHeight: 600 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Time (IST - When Sent)</TableCell>
                        <TableCell>
                          Seq No
                          <IconButton size="small" sx={{ ml: 0.5, p: 0 }}>
                            ↑
                          </IconButton>
                        </TableCell>
                        <TableCell>Exchange</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell sx={{ minWidth: 500 }}>Detail</TableCell>
                        <TableCell>Action</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                    {exchangeTransactions.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} align="center">No transactions found</TableCell>
                      </TableRow>
                    ) : (
                      exchangeTransactions
                        .filter(tx => {
                          // Apply filters
                          if (status && tx.status !== status) return false;
                          if (sequenceIdSearch && !tx.sequence_id?.includes(sequenceIdSearch)) return false;
                          if (exchangeFilter !== 'ALL') {
                            const exchangeId = tx.metrics_sent?.lama_v1_2_payload?.exchangeId;
                            if (String(exchangeId) !== exchangeFilter) return false;
                          }
                          if (metricType && tx.metric_type !== metricType) return false;
                          return true;
                        })
                        .map((tx) => {
                          // Extract exchangeId from various possible locations
                          const metricsSent = tx.metrics_sent || {};
                          const lamaPayload = metricsSent.lama_v1_2_payload || {};
                          let exchangeId = lamaPayload.exchangeId;
                          
                          // Fallback: try to get from top level if not found
                          if (exchangeId === undefined || exchangeId === null) {
                            exchangeId = metricsSent.exchangeId || tx.exchange_response?.exchangeId;
                          }
                          
                          // Extract payload array from V1.2 structure
                          const payload = lamaPayload.payload || [];
                          
                          // Fallback: if no payload, try to get from original_metrics
                          const originalMetrics = metricsSent.original_metrics || [];
                          
                          const exchangeResponse = tx.exchange_response || {};
                          
                          // Get Exchange name
                          const getExchangeName = (id) => {
                            if (id === undefined || id === null || id === '') {
                              return 'N/A';
                            }
                            const map = { '1': 'NSE', '2': 'BSE', '3': 'MSE', '4': 'MCX', '5': 'NCDEX' };
                            return map[String(id)] || `ID: ${id}`;
                          };
                          
                          // Format Detail string to match exact LAMA Exchange format
                          // Format: SUCCESS | response Code : 601 | Lama : V1 | response Desc : success ,cpu : min: 0.3 ,max: 0.3 ,avg: 0.3 ,med: 0.3 ...
                          const formatDetail = () => {
                            const displayStatus = getDisplayStatus(tx);
                            const mainParts = [];
                            mainParts.push(displayStatus);
                            
                            // For NOT FOUND, show error message instead of response details
                            if (displayStatus === 'NOT FOUND') {
                              const errorMsg = getErrorMessage(tx);
                              return errorMsg || 'Data Not Found';
                            }
                            
                            // For SUCCESS (601) and FAILED (other codes), show response details
                            // CRITICAL: Always show responseCode for audit purposes (per LAMA Exchange requirement)
                            const responseCode = exchangeResponse.responseCode || exchangeResponse.response_code || tx.status_code || '';
                            if (responseCode) {
                              mainParts.push(`response Code : ${responseCode}`);
                            }
                            mainParts.push('Lama : V1');
                            const responseDesc = exchangeResponse.responseDesc || exchangeResponse.response_desc || exchangeResponse.message || '';
                            if (responseDesc) {
                              // Convert to lowercase to match sample format
                              const descLower = responseDesc.toLowerCase();
                              mainParts.push(`response Desc : ${descLower}`);
                            } else if (displayStatus === 'SUCCESS') {
                              mainParts.push(`response Desc : success`);
                            } else {
                              // For FAILED, show the actual error description
                              const errorDesc = getErrorMessage(tx).toLowerCase() || 'unsuccessful';
                              mainParts.push(`response Desc : ${errorDesc}`);
                            }
                            
                            // Group metrics by applicationId from V1.2 payload
                            const metricsByAppId = {};
                            
                            if (payload && payload.length > 0) {
                              // Use V1.2 payload structure
                              payload.forEach((appPayload) => {
                                const appId = appPayload.applicationId;
                                if (!metricsByAppId[appId]) {
                                  metricsByAppId[appId] = [];
                                }
                                (appPayload.metricData || []).forEach((metric) => {
                                  metricsByAppId[appId].push({
                                    key: metric.key,
                                    value: metric.value
                                  });
                                });
                              });
                            } else if (originalMetrics && originalMetrics.length > 0) {
                              // Fallback to original_metrics format
                              // Group by applicationId if available, otherwise use default
                              const defaultAppId = lamaPayload.payload?.[0]?.applicationId || '-1';
                              if (!metricsByAppId[defaultAppId]) {
                                metricsByAppId[defaultAppId] = [];
                              }
                              originalMetrics.forEach((metric) => {
                                metricsByAppId[defaultAppId].push({
                                  key: metric.name || metric.key,
                                  value: {
                                    min: metric.min,
                                    max: metric.max,
                                    avg: metric.avg,
                                    med: metric.med
                                  }
                                });
                              });
                            }
                            
                            // Format metrics with exact spacing as per sample
                            // Sample shows: first appId group uses spaces between metrics, subsequent groups use commas
                            const appIdGroups = [];
                            
                            Object.keys(metricsByAppId).sort((a, b) => {
                              // Sort applicationIds numerically if possible
                              const aNum = parseInt(a);
                              const bNum = parseInt(b);
                              if (!isNaN(aNum) && !isNaN(bNum)) {
                                return aNum - bNum;
                              }
                              return String(a).localeCompare(String(b));
                            }).forEach((appId, appIndex) => {
                              const metrics = metricsByAppId[appId];
                              const metricStrings = [];
                              
                              metrics.forEach((metric) => {
                                const value = metric.value;
                                // Handle both object format {min, max, avg, med} and simple numeric values
                                if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                                  const { min, max, avg, med } = value;
                                  // Format values
                                  const minVal = min !== null && min !== undefined ? (typeof min === 'number' ? min.toFixed(2) : min) : 0;
                                  const maxVal = max !== null && max !== undefined ? (typeof max === 'number' ? max.toFixed(2) : max) : 0;
                                  const avgVal = avg !== null && avg !== undefined ? (typeof avg === 'number' ? avg.toFixed(2) : avg) : 0;
                                  const medVal = med !== null && med !== undefined ? (typeof med === 'number' ? med.toFixed(2) : med) : 0;
                                  
                                  if (appIndex === 0) {
                                    // First applicationId group: "metricName : min: X ,max: Y ,avg: Z ,med: W" (spaces around commas)
                                    metricStrings.push(`${metric.key} : min: ${minVal} ,max: ${maxVal} ,avg: ${avgVal} ,med: ${medVal}`);
                                  } else {
                                    // Subsequent groups: "metricName : min: X,max: Y,avg: Z,med: W," (no spaces, ends with comma)
                                    metricStrings.push(`${metric.key} : min: ${minVal},max: ${maxVal},avg: ${avgVal},med: ${medVal},`);
                                  }
                                } else {
                                  // Simple numeric value (for packetCount, lookupCount)
                                  if (appIndex === 0) {
                                    metricStrings.push(`${metric.key} : ${value || 0}`);
                                  } else {
                                    metricStrings.push(`${metric.key} : ${value || 0},`);
                                  }
                                }
                              });
                              
                              // Add applicationId marker
                              if (appIndex === 0) {
                                // First group: metrics separated by spaces, then space + "applicationId - X,"
                                appIdGroups.push(metricStrings.join(' ') + ` applicationId - ${appId},`);
                              } else {
                                // Subsequent groups: metrics separated by spaces (each metric already ends with comma), then "applicationId - X,"
                                appIdGroups.push(metricStrings.join(' ') + `applicationId - ${appId},`);
                              }
                            });
                            
                            // Combine: main parts with | separator (with spaces), then metrics
                            let result = mainParts.join(' | ');
                            if (appIdGroups.length > 0) {
                              result += ' ,' + appIdGroups.join('');
                            }
                            
                            return result;
                          };
                          
                          return (
                            <TableRow key={tx.id}>
                              <TableCell>
                                {formatDateTime(tx.sent_at)}
                              </TableCell>
                              <TableCell>
                                {(() => {
                                  // Get sequence ID from multiple possible locations
                                  const seqId = tx.sequence_id || 
                                               tx.metrics_sent?.lama_v1_2_payload?.sequenceId ||
                                               tx.metrics_sent?.sequenceId;
                                  return seqId ? String(seqId) : '-';
                                })()}
                              </TableCell>
                              <TableCell>
                                <Chip 
                                  label={getExchangeName(exchangeId)} 
                                  size="small" 
                                  color={exchangeId ? "primary" : "default"}
                                />
                              </TableCell>
                              <TableCell>
                                <Chip 
                                  label={getDisplayStatus(tx)} 
                                  size="small" 
                                  color={getStatusColor(tx.status)}
                                  sx={{ 
                                    color: getDisplayStatus(tx) === 'SUCCESS' ? 'white' : 'inherit',
                                    fontWeight: 'bold'
                                  }}
                                />
                              </TableCell>
                              <TableCell>
                                <Typography 
                                  variant="body2" 
                                  sx={{ 
                                    fontFamily: 'monospace', 
                                    fontSize: '0.75rem',
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    maxWidth: 500
                                  }}
                                >
                                  {formatDetail()}
                                </Typography>
                              </TableCell>
                              <TableCell>
                                <IconButton 
                                  size="small"
                                  onClick={(e) => {
                                    setMenuAnchor(e.currentTarget);
                                    setSelectedRowId(tx.id);
                                    setSelectedTransaction(tx);
                                  }}
                                >
                                  <Typography>⋯</Typography>
                                </IconButton>
                              </TableCell>
                            </TableRow>
                          );
                        })
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
              </Box>
            )}
              </Box>
            )}
            
            {viewType === 'transactions' && (
              <Box sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="h6">Exchange Transactions - LAMA v1.2 Payload</Typography>
              <Button variant="outlined" onClick={fetchExchangeTransactions} disabled={loading}>
                Load Data
              </Button>
            </Box>
            {loading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
              </Box>
            ) : (
              <TableContainer sx={{ maxHeight: 600 }}>
                <Table stickyHeader size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Sent At</TableCell>
                      <TableCell>Environment</TableCell>
                      <TableCell>Metric Type</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell sx={{ minWidth: 600 }}>LAMA v1.2 Payload</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {exchangeTransactions.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} align="center">No transactions found</TableCell>
                      </TableRow>
                    ) : (
                      exchangeTransactions.map((tx) => {
                        // Get the full LAMA v1.2 payload structure
                        const lamaPayload = tx.metrics_sent?.lama_v1_2_payload || {};
                        
                        // Construct the payload in the exact format as per LAMA API v1.2
                        const payloadStructure = {
                          memberId: lamaPayload.memberId || tx.member_id || '',
                          exchangeId: lamaPayload.exchangeId || null,
                          sequenceId: lamaPayload.sequenceId || tx.sequence_id || null,
                          timestamp: lamaPayload.timestamp || null,
                          payload: lamaPayload.payload || []
                        };
                        
                        // Format the payload as JSON string with proper indentation
                        const formatPayloadJSON = () => {
                          try {
                            return JSON.stringify(payloadStructure, null, 2);
                          } catch (e) {
                            return JSON.stringify(payloadStructure);
                          }
                        };
                        
                        return (
                          <TableRow key={tx.id}>
                            <TableCell>{formatDateTime(tx.sent_at)}</TableCell>
                            <TableCell>
                              <Chip label={tx.environment?.toUpperCase() || ''} size="small" />
                            </TableCell>
                            <TableCell>
                              <Chip label={tx.metric_type} size="small" color={getMetricTypeColor(tx.metric_type)} />
                            </TableCell>
                            <TableCell>
                              <Box>
                                <Chip label={tx.status} size="small" color={getStatusColor(tx.status)} />
                                {tx.status_code && (
                                  <Typography variant="caption" display="block" color="text.secondary" sx={{ mt: 0.5 }}>
                                    Code: {tx.status_code}
                                  </Typography>
                                )}
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Box
                                sx={{
                                  fontFamily: 'monospace',
                                  fontSize: '0.75rem',
                                  backgroundColor: '#f5f5f5',
                                  p: 1,
                                  borderRadius: 1,
                                  maxHeight: 400,
                                  overflow: 'auto',
                                  whiteSpace: 'pre-wrap',
                                  wordBreak: 'break-word'
                                }}
                              >
                                {formatPayloadJSON()}
                              </Box>
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
              </Box>
            )}
          </>
        )}
        
        {tabValue === 1 && (
          <Box sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="h6">Server Metrics</Typography>
              <Button variant="outlined" onClick={fetchServerMetrics} disabled={loading}>
                Load Data
              </Button>
            </Box>
            {loading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
              </Box>
            ) : (
              <TableContainer sx={{ maxHeight: 600 }}>
                <Table stickyHeader size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Timestamp</TableCell>
                      <TableCell>Server</TableCell>
                      <TableCell>Metric Name</TableCell>
                      <TableCell>Value</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {serverMetrics.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} align="center">No metrics found</TableCell>
                      </TableRow>
                    ) : (
                      serverMetrics.map((metric) => (
                        <TableRow key={metric.id}>
                          <TableCell>{formatDateTime(metric.timestamp)}</TableCell>
                          <TableCell>{metric.server_name || metric.server_ip || '-'}</TableCell>
                          <TableCell>{metric.metric_name}</TableCell>
                          <TableCell>{metric.value.toFixed(2)}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Box>
        )}
      </Paper>
      </Container>
      
      {/* Action Menu */}
      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor)}
        onClose={() => {
          setMenuAnchor(null);
          setSelectedRowId(null);
        }}
      >
        <MenuItem
          onClick={async () => {
            if (selectedTransaction) {
              setLoadingDetails(true);
              setDetailsModalOpen(true);
              try {
                const response = await axios.get(`/v1/historical/exchange-transactions/${selectedTransaction.id}/servers`);
                setServerDetails(response.data.servers || []);
              } catch (error) {
                console.error('Error fetching server details:', error);
                setError('Failed to load server details');
                setServerDetails([]);
              } finally {
                setLoadingDetails(false);
                setMenuAnchor(null);
              }
            }
          }}
        >
          Details
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (selectedTransaction) {
              setSelectedJsonData(selectedTransaction.metrics_sent?.lama_v1_2_payload || {});
              setJsonModalOpen(true);
              setMenuAnchor(null);
            }
          }}
        >
          JSON
        </MenuItem>
      </Menu>
      
      {/* Server Details Modal */}
      <Dialog
        open={detailsModalOpen}
        onClose={() => setDetailsModalOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          {selectedTransaction && (() => {
            const exchangeId = selectedTransaction.metrics_sent?.lama_v1_2_payload?.exchangeId;
            const exchangeName = {1: "NSE", 2: "BSE", 3: "MSE", 4: "MCX", 5: "NCDEX"}[exchangeId] || `Exchange ${exchangeId}`;
            const metricType = selectedTransaction.metric_type || 'system';
            const timestamp = formatDateTime(selectedTransaction.sent_at);
            return `${exchangeName} - ${metricType.charAt(0).toUpperCase() + metricType.slice(1)} - ${timestamp}`;
          })()}
        </DialogTitle>
        <DialogContent>
          {loadingDetails ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : serverDetails.length === 0 ? (
            <Typography>No server details found</Typography>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Time</TableCell>
                    <TableCell>Server Name</TableCell>
                    <TableCell>Server IP</TableCell>
                    <TableCell>Details</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {serverDetails.map((server, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{formatDateTime(server.time)}</TableCell>
                      <TableCell>{server.server_name || 'Unknown'}</TableCell>
                      <TableCell>{server.ip || 'N/A'}</TableCell>
                      <TableCell>
                        <Typography 
                          variant="body2" 
                          sx={{ 
                            fontFamily: 'monospace', 
                            fontSize: '0.75rem',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word'
                          }}
                        >
                          {server.details}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailsModalOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
      
      {/* JSON Modal */}
      <Dialog
        open={jsonModalOpen}
        onClose={() => setJsonModalOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>LAMA v1.2 Payload (JSON)</DialogTitle>
        <DialogContent>
          <Box
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              backgroundColor: '#f5f5f5',
              p: 2,
              borderRadius: 1,
              maxHeight: 500,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }}
          >
            {selectedJsonData ? JSON.stringify(selectedJsonData, null, 2) : 'No data available'}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setJsonModalOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </LocalizationProvider>
  );
};

export default HistoricalData;

