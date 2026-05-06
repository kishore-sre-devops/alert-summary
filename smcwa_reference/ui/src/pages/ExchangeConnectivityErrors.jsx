import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
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
  Container,
  Button,
  IconButton,
  Tooltip,
  Collapse,
} from '@mui/material';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import DownloadIcon from '@mui/icons-material/Download';
import RefreshIcon from '@mui/icons-material/Refresh';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';

const ExchangeConnectivityErrors = () => {
  const { environment, withEnvironment } = useEnvironment();
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [connectivityErrors, setConnectivityErrors] = useState([]);
  
  // Filters
  const [timeRange, setTimeRange] = useState('1440'); // Last 24 hours
  const [errorType, setErrorType] = useState(''); // All, login, logout
  const [startDateTime, setStartDateTime] = useState(null);
  const [endDateTime, setEndDateTime] = useState(null);
  const [activeTimeRange, setActiveTimeRange] = useState('');
  const [rowLimit, setRowLimit] = useState(1000); // Number of rows to display
  
  // Expandable rows
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [detailsDialog, setDetailsDialog] = useState({ open: false, error: null });
  
  const intervalRef = useRef('1440');
  const fetchRef = useRef(null);
  
  useEffect(() => {
    intervalRef.current = timeRange;
  }, [timeRange]);
  
  const fetchConnectivityErrors = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    
    try {
      let params = {};
      
      // Convert to UTC for API
      const convertToUTC = (date) => {
        if (!date) return null;
        const utcYear = date.getUTCFullYear();
        const utcMonth = String(date.getUTCMonth() + 1).padStart(2, '0');
        const utcDay = String(date.getUTCDate()).padStart(2, '0');
        const utcHours = String(date.getUTCHours()).padStart(2, '0');
        const utcMinutes = String(date.getUTCMinutes()).padStart(2, '0');
        const utcSeconds = String(date.getUTCSeconds()).padStart(2, '0');
        return {
          date: `${utcYear}-${utcMonth}-${utcDay}`,
          time: `${utcHours}:${utcMinutes}:${utcSeconds}`
        };
      };
      
      const currentInterval = intervalRef.current || timeRange || '1440';
      if (currentInterval && currentInterval !== 'custom') {
        const now = new Date();
        const intervalMinutes = parseInt(currentInterval, 10) || 1440;
        const minutesAgo = new Date(now.getTime() - intervalMinutes * 60 * 1000);
        const startUTC = convertToUTC(minutesAgo);
        const endUTC = convertToUTC(now);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
        setActiveTimeRange(`${startUTC.date} ${startUTC.time} to ${endUTC.date} ${endUTC.time} UTC`);
      } else if (currentInterval === 'custom' && startDateTime && endDateTime) {
        const startUTC = convertToUTC(startDateTime);
        const endUTC = convertToUTC(endDateTime);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
        setActiveTimeRange(`${startUTC.date} ${startUTC.time} to ${endUTC.date} ${endUTC.time} UTC`);
      } else {
        // Default: Last 24 hours
        const now = new Date();
        const hoursAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        const startUTC = convertToUTC(hoursAgo);
        const endUTC = convertToUTC(now);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
        setActiveTimeRange(`${startUTC.date} ${startUTC.time} to ${endUTC.date} ${endUTC.time} UTC`);
      }
      
      params = { ...params, ...withEnvironment() };
      if (errorType) params.error_type = errorType;
      params.limit = rowLimit; // Add row limit parameter
      
      const response = await axios.get('/v1/exchange-connectivity-errors', { params });
      const errors = response.data.errors || [];
      setConnectivityErrors(errors);
      if (!silent) {
        setSuccess(`Loaded ${errors.length} connectivity error${errors.length !== 1 ? 's' : ''}`);
      }
    } catch (error) {
      console.error('Error fetching connectivity errors:', error);
      setError('Failed to load connectivity errors: ' + (error.response?.data?.detail || error.message));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [environment, timeRange, errorType, startDateTime, endDateTime, rowLimit, withEnvironment]);
  
  // Store fetch function in ref for auto-refresh
  useEffect(() => {
    fetchRef.current = fetchConnectivityErrors;
  }, [fetchConnectivityErrors]);
  
  // Initial data load and trigger on filter changes
  useEffect(() => {
    const timer = setTimeout(() => {
      if (timeRange !== 'custom' || (startDateTime && endDateTime)) {
        fetchConnectivityErrors();
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [fetchConnectivityErrors, timeRange, startDateTime, endDateTime, rowLimit]);
  
  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (fetchRef.current) {
        fetchRef.current(true); // silent refresh
      }
    }, 30000); // 30 seconds
    
    return () => clearInterval(interval);
  }, []);
  
  const handleExport = async () => {
    setExporting(true);
    setError('');
    
    try {
      let params = {};
      
      const convertToUTC = (date) => {
        if (!date) return null;
        const utcYear = date.getUTCFullYear();
        const utcMonth = String(date.getUTCMonth() + 1).padStart(2, '0');
        const utcDay = String(date.getUTCDate()).padStart(2, '0');
        const utcHours = String(date.getUTCHours()).padStart(2, '0');
        const utcMinutes = String(date.getUTCMinutes()).padStart(2, '0');
        const utcSeconds = String(date.getUTCSeconds()).padStart(2, '0');
        return {
          date: `${utcYear}-${utcMonth}-${utcDay}`,
          time: `${utcHours}:${utcMinutes}:${utcSeconds}`
        };
      };
      
      const currentInterval = intervalRef.current || timeRange || '1440';
      if (currentInterval && currentInterval !== 'custom') {
        const now = new Date();
        const intervalMinutes = parseInt(currentInterval, 10) || 1440;
        const minutesAgo = new Date(now.getTime() - intervalMinutes * 60 * 1000);
        const startUTC = convertToUTC(minutesAgo);
        const endUTC = convertToUTC(now);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
      } else if (currentInterval === 'custom' && startDateTime && endDateTime) {
        const startUTC = convertToUTC(startDateTime);
        const endUTC = convertToUTC(endDateTime);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
      } else {
        const now = new Date();
        const hoursAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        const startUTC = convertToUTC(hoursAgo);
        const endUTC = convertToUTC(now);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
      }
      
      params = { ...params, ...withEnvironment() };
      if (errorType) params.error_type = errorType;
      
      const response = await axios.get('/v1/exchange-connectivity-errors/export', {
        params,
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
      link.setAttribute('download', `exchange_connectivity_errors_${timestamp}.xlsx`);
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
  
  const formatDateTime = (isoString) => {
    if (!isoString) return '';
    let dateString = isoString;
    if (!dateString.includes('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
      dateString = dateString.endsWith('Z') ? dateString : dateString + 'Z';
    }
    const date = new Date(dateString);
    return date.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };
  
  const toggleRow = (errorId, event) => {
    // Prevent page scroll when expanding
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(errorId)) {
      newExpanded.delete(errorId);
    } else {
      newExpanded.add(errorId);
    }
    setExpandedRows(newExpanded);
  };
  
  const getStatusColor = (status) => {
    switch (status) {
      case 'failed': return 'error';
      case 'error': return 'warning';
      case 'timeout': return 'warning';
      case 'connection_error': return 'error';
      case 'request_error': return 'warning';
      case 'protocol_error': return 'warning';
      default: return 'default';
    }
  };
  
  const getIntervalDisplayText = (value) => {
    const intervals = {
      '30': 'Last 30 minutes',
      '60': 'Last 1 hour',
      '1440': 'Last 24 hours',
      '10080': 'Last 7 days',
      'custom': 'Custom Range'
    };
    return intervals[value] || value;
  };
  
  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Container maxWidth="xl" sx={{ py: { xs: 1.5, sm: 2, md: 2.5 }, px: { xs: 1, sm: 1.5, md: 2 } }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: { xs: 2, md: 2.5 } }}>
          <Typography variant="h4" sx={{ 
            fontWeight: 'bold', 
            fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.75rem', lg: '2rem' }
          }}>
            Exchange Connectivity Error Logs
          </Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Tooltip title="Refresh">
              <IconButton onClick={() => fetchConnectivityErrors(false)}>
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

        <Card sx={{ mb: { xs: 2, md: 2.5 } }}>
          <CardContent sx={{ p: { xs: 1.5, sm: 2, md: 2.5 } }}>
            <Grid container spacing={{ xs: 1.5, sm: 2, md: 2 }} alignItems="center">
              <Grid item xs={12} sm={6} md={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Time Range</InputLabel>
                  <Select
                    value={timeRange}
                    onChange={(e) => {
                      const value = e.target.value;
                      intervalRef.current = value;
                      setTimeRange(value);
                      if (value !== 'custom') {
                        setStartDateTime(null);
                        setEndDateTime(null);
                      }
                    }}
                    label="Time Range"
                  >
                    <MenuItem value="30">Last 30 minutes</MenuItem>
                    <MenuItem value="60">Last 1 hour</MenuItem>
                    <MenuItem value="1440">Last 24 hours</MenuItem>
                    <MenuItem value="10080">Last 7 days</MenuItem>
                    <MenuItem value="custom">Custom Range</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              {timeRange === 'custom' && (
                <>
                  <Grid item xs={12} sm={6} md={3}>
                    <DateTimePicker
                      label="Start Date & Time"
                      value={startDateTime}
                      onChange={setStartDateTime}
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
                      onChange={setEndDateTime}
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
              
              <Grid item xs={12} sm={6} md={timeRange === 'custom' ? 2 : 3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Error Type</InputLabel>
                  <Select
                    value={errorType}
                    onChange={(e) => setErrorType(e.target.value)}
                    label="Error Type"
                  >
                    <MenuItem value="">All</MenuItem>
                    <MenuItem value="login">Login Errors</MenuItem>
                    <MenuItem value="logout">Logout Errors</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} sm={6} md={timeRange === 'custom' ? 2 : 3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Max Rows</InputLabel>
                  <Select
                    value={rowLimit}
                    onChange={(e) => setRowLimit(e.target.value)}
                    label="Max Rows"
                  >
                    <MenuItem value={100}>100</MenuItem>
                    <MenuItem value={500}>500</MenuItem>
                    <MenuItem value={1000}>1,000</MenuItem>
                    <MenuItem value={2000}>2,000</MenuItem>
                    <MenuItem value={5000}>5,000</MenuItem>
                    <MenuItem value={10000}>10,000</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
            
            {activeTimeRange && (
              <Alert severity="info" sx={{ mt: 2 }}>
                Time Range: {activeTimeRange}
              </Alert>
            )}
          </CardContent>
        </Card>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : connectivityErrors.length === 0 ? (
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="h6" color="textSecondary">
                No connectivity errors found
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
                {errorType ? `No ${errorType} errors found in the selected time range.` : 'No login/logout errors found in the selected time range.'}
              </Typography>
            </CardContent>
          </Card>
        ) : (
          <TableContainer 
            component={Paper}
            sx={{ 
              maxHeight: 'calc(100vh - 400px)',
              overflow: 'auto',
              position: 'relative'
            }}
          >
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: { xs: '0.75rem', sm: '0.875rem' }, position: 'sticky', top: 0, backgroundColor: '#f5f5f5', zIndex: 10 }}>Time (IST)</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: { xs: '0.75rem', sm: '0.875rem' }, position: 'sticky', top: 0, backgroundColor: '#f5f5f5', zIndex: 10 }}>Environment</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: { xs: '0.75rem', sm: '0.875rem' }, position: 'sticky', top: 0, backgroundColor: '#f5f5f5', zIndex: 10 }}>Error Type</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: { xs: '0.75rem', sm: '0.875rem' }, position: 'sticky', top: 0, backgroundColor: '#f5f5f5', zIndex: 10 }}>Status</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: { xs: '0.75rem', sm: '0.875rem' }, position: 'sticky', top: 0, backgroundColor: '#f5f5f5', zIndex: 10 }}>HTTP Code</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: { xs: '0.75rem', sm: '0.875rem' }, position: 'sticky', top: 0, backgroundColor: '#f5f5f5', zIndex: 10 }}>LAMA Code</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: { xs: '0.75rem', sm: '0.875rem' }, position: 'sticky', top: 0, backgroundColor: '#f5f5f5', zIndex: 10 }}>Error Message</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: { xs: '0.75rem', sm: '0.875rem' }, position: 'sticky', top: 0, backgroundColor: '#f5f5f5', zIndex: 10, right: 0 }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {connectivityErrors.map((err) => (
                  <React.Fragment key={err.id}>
                    <TableRow 
                      sx={{ 
                        '&:hover': { backgroundColor: '#fafafa' },
                        '&:last-child td': { borderBottom: expandedRows.has(err.id) ? 'none' : undefined }
                      }}
                    >
                      <TableCell sx={{ fontSize: { xs: '0.75rem', sm: '0.875rem' } }}>
                        {formatDateTime(err.sent_at)}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={err.environment?.toUpperCase() || 'N/A'}
                          size="small"
                          color={err.environment === 'uat' ? 'warning' : 'success'}
                        />
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={err.error_type?.toUpperCase() || 'N/A'}
                          size="small"
                          color={err.error_type === 'login' ? 'error' : 'warning'}
                        />
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={err.status?.toUpperCase() || 'N/A'}
                          size="small"
                          color={getStatusColor(err.status)}
                        />
                      </TableCell>
                      <TableCell sx={{ fontSize: { xs: '0.75rem', sm: '0.875rem' } }}>
                        {err.status_code || '-'}
                      </TableCell>
                      <TableCell sx={{ fontSize: { xs: '0.75rem', sm: '0.875rem' } }}>
                        {err.response_code || '-'}
                      </TableCell>
                      <TableCell 
                        sx={{ 
                          fontSize: { xs: '0.75rem', sm: '0.875rem' },
                          maxWidth: 300,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}
                      >
                        {err.error_message || err.response_desc || '-'}
                      </TableCell>
                      <TableCell 
                        sx={{ 
                          position: 'sticky',
                          right: 0,
                          backgroundColor: 'white',
                          zIndex: 5,
                          minWidth: 60
                        }}
                      >
                        <Tooltip title={expandedRows.has(err.id) ? 'Hide Details' : 'Show Details'}>
                          <IconButton
                            size="small"
                            onClick={(e) => toggleRow(err.id, e)}
                            sx={{ 
                              '&:hover': { backgroundColor: '#f0f0f0' }
                            }}
                          >
                            {expandedRows.has(err.id) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell 
                        colSpan={8} 
                        sx={{ 
                          py: 0, 
                          border: 0,
                          backgroundColor: '#f9f9f9'
                        }}
                      >
                        <Collapse 
                          in={expandedRows.has(err.id)} 
                          timeout="auto" 
                          unmountOnExit
                          sx={{
                            '& .MuiCollapse-wrapper': {
                              transition: 'height 300ms cubic-bezier(0.4, 0, 0.2, 1) 0ms'
                            }
                          }}
                        >
                          <Box sx={{ p: 2, backgroundColor: '#f9f9f9' }}>
                            <Grid container spacing={2}>
                              {/* ENHANCED: Complete Request Details */}
                              <Grid item xs={12}>
                                <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1.5, color: 'primary.main' }}>
                                  📤 Complete Request Details
                                </Typography>
                              </Grid>
                              <Grid item xs={12} md={6}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                  Request URL & Method
                                </Typography>
                                <Box sx={{ mb: 2 }}>
                                  <Typography variant="body2" sx={{ mb: 0.5 }}>
                                    <strong>URL:</strong> {err.request?.url || 'N/A'}
                                  </Typography>
                                  <Typography variant="body2">
                                    <strong>Method:</strong> {err.request?.method || 'POST'}
                                  </Typography>
                                </Box>
                              </Grid>
                              <Grid item xs={12} md={6}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                  Member ID
                                </Typography>
                                <Typography variant="body2">
                                  {err.member_id || 'N/A'}
                                </Typography>
                              </Grid>
                              <Grid item xs={12} md={6}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                  Complete Request Payload
                                </Typography>
                                <Box
                                  component="pre"
                                  sx={{
                                    backgroundColor: 'white',
                                    p: 1.5,
                                    borderRadius: 1,
                                    fontSize: '0.75rem',
                                    overflow: 'auto',
                                    maxHeight: 300,
                                    border: '1px solid #e0e0e0',
                                    fontFamily: 'monospace'
                                  }}
                                >
                                  {err.request?.payload
                                    ? JSON.stringify(err.request.payload, null, 2)
                                    : (err.request_headers ? JSON.stringify({ note: 'Legacy format - payload in headers' }, null, 2) : 'No request payload available')}
                                </Box>
                                {err.request?.payload?.password_encryption_note && (
                                  <Typography variant="caption" sx={{ color: 'text.secondary', mt: 0.5, display: 'block' }}>
                                    ℹ️ {err.request.payload.password_encryption_note}
                                  </Typography>
                                )}
                                {err.request?.payload?.secretKey_note && (
                                  <Typography variant="caption" sx={{ color: 'text.secondary', mt: 0.5, display: 'block' }}>
                                    ℹ️ {err.request.payload.secretKey_note}
                                  </Typography>
                                )}
                              </Grid>
                              <Grid item xs={12} md={6}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                  Complete Request Headers
                                </Typography>
                                <Box
                                  component="pre"
                                  sx={{
                                    backgroundColor: 'white',
                                    p: 1.5,
                                    borderRadius: 1,
                                    fontSize: '0.75rem',
                                    overflow: 'auto',
                                    maxHeight: 300,
                                    border: '1px solid #e0e0e0',
                                    fontFamily: 'monospace'
                                  }}
                                >
                                  {(err.request?.headers && Object.keys(err.request.headers).length > 0)
                                    ? JSON.stringify(err.request.headers, null, 2)
                                    : (err.request_headers && Object.keys(err.request_headers).length > 0
                                      ? JSON.stringify(err.request_headers, null, 2)
                                      : 'No request headers available')}
                                </Box>
                              </Grid>
                              
                              {/* ENHANCED: Complete Response Details */}
                              <Grid item xs={12} sx={{ mt: 1 }}>
                                <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1.5, color: 'success.main' }}>
                                  📥 Complete Response Details
                                </Typography>
                              </Grid>
                              <Grid item xs={12} md={6}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                  Complete Response Body
                                </Typography>
                                <Box
                                  component="pre"
                                  sx={{
                                    backgroundColor: 'white',
                                    p: 1.5,
                                    borderRadius: 1,
                                    fontSize: '0.75rem',
                                    overflow: 'auto',
                                    maxHeight: 400,
                                    border: '1px solid #e0e0e0',
                                    fontFamily: 'monospace'
                                  }}
                                >
                                  {err.response?.body
                                    ? JSON.stringify(err.response.body, null, 2)
                                    : (err.full_response
                                      ? JSON.stringify(err.full_response, null, 2)
                                      : (err.error_message || 'No response body available (timeout/connection error)'))}
                                </Box>
                                {err.response?.responseCode && (
                                  <Typography variant="body2" sx={{ mt: 1 }}>
                                    <strong>LAMA Response Code:</strong> {err.response.responseCode}
                                    {err.response.responseDesc && ` - ${err.response.responseDesc}`}
                                  </Typography>
                                )}
                              </Grid>
                              <Grid item xs={12} md={6}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                  Complete Response Headers
                                </Typography>
                                <Box
                                  component="pre"
                                  sx={{
                                    backgroundColor: 'white',
                                    p: 1.5,
                                    borderRadius: 1,
                                    fontSize: '0.75rem',
                                    overflow: 'auto',
                                    maxHeight: 400,
                                    border: '1px solid #e0e0e0',
                                    fontFamily: 'monospace'
                                  }}
                                >
                                  {(err.response?.headers && Object.keys(err.response.headers).length > 0)
                                    ? JSON.stringify(err.response.headers, null, 2)
                                    : (err.response_headers && Object.keys(err.response_headers).length > 0
                                      ? JSON.stringify(err.response_headers, null, 2)
                                      : 'No response headers available')}
                                </Box>
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  <strong>HTTP Status Code:</strong> {err.response?.status_code || err.status_code || 'N/A'}
                                </Typography>
                              </Grid>
                              
                              {/* Legacy: Full Error Details (for backward compatibility) */}
                              {err.full_response && (!err.response?.body) && (
                                <Grid item xs={12}>
                                  <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                                    Full Error Details (Legacy Format)
                                  </Typography>
                                  <Box
                                    component="pre"
                                    sx={{
                                      backgroundColor: 'white',
                                      p: 1.5,
                                      borderRadius: 1,
                                      fontSize: '0.75rem',
                                      overflow: 'auto',
                                      maxHeight: 300,
                                      border: '1px solid #e0e0e0',
                                      fontFamily: 'monospace'
                                    }}
                                  >
                                    {JSON.stringify(err.full_response, null, 2)}
                                  </Box>
                                </Grid>
                              )}
                            </Grid>
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  </React.Fragment>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Container>
    </LocalizationProvider>
  );
};

export default ExchangeConnectivityErrors;

