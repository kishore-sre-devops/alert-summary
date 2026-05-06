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
  TextField,
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
import { format } from 'date-fns';

const SchedulerLogs = () => {
  const { environment, withEnvironment } = useEnvironment();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [logs, setLogs] = useState([]);
  
  // Filters
  const [timeRange, setTimeRange] = useState('15'); // Last 15 minutes
  const [schedulerFilter, setSchedulerFilter] = useState('');
  const [exchangeFilter, setExchangeFilter] = useState('');
  const [logTypeFilter, setLogTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [startDateTime, setStartDateTime] = useState(null);
  const [endDateTime, setEndDateTime] = useState(null);
  const [activeTimeRange, setActiveTimeRange] = useState('');
  const [rowLimit, setRowLimit] = useState(1000);
  
  // Expandable rows
  const [expandedRows, setExpandedRows] = useState(new Set());
  
  const intervalRef = useRef('15');
  const fetchRef = useRef(null);
  
  // CRITICAL FIX: Ensure schedulerFilter is never set to old "App-Scheduler" value
  // If somehow it gets set (e.g., from browser cache), reset it to "Application-Scheduler"
  useEffect(() => {
    if (schedulerFilter === 'App-Scheduler') {
      console.warn('⚠️ Detected old App-Scheduler value in schedulerFilter, resetting to Application-Scheduler');
      setSchedulerFilter('Application-Scheduler');
    }
  }, [schedulerFilter]);
  
  useEffect(() => {
    intervalRef.current = timeRange;
  }, [timeRange]);
  
  const fetchLogs = useCallback(async (silent = false) => {
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
      
      const currentInterval = intervalRef.current || timeRange || '15';
      if (currentInterval && currentInterval !== 'custom') {
        const now = new Date();
        const intervalMinutes = parseInt(currentInterval, 10) || 15;
        const minutesAgo = new Date(now.getTime() - intervalMinutes * 60 * 1000);
        const startUTC = convertToUTC(minutesAgo);
        const endUTC = convertToUTC(now);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
        setActiveTimeRange(`Last ${intervalMinutes} minutes`);
      } else if (currentInterval === 'custom' && startDateTime && endDateTime) {
        const startUTC = convertToUTC(startDateTime);
        const endUTC = convertToUTC(endDateTime);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
        setActiveTimeRange(`${startUTC.date} ${startUTC.time} to ${endUTC.date} ${endUTC.time} UTC`);
      } else {
        // Default: Last 15 minutes
        const now = new Date();
        const minutesAgo = new Date(now.getTime() - 15 * 60 * 1000);
        const startUTC = convertToUTC(minutesAgo);
        const endUTC = convertToUTC(now);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
        setActiveTimeRange('Last 15 minutes');
      }
      
      params = { ...params, ...withEnvironment() };
      if (schedulerFilter) {
        // CRITICAL FIX: Never send old "App-Scheduler" value - always use "Application-Scheduler"
        if (schedulerFilter === 'App-Scheduler') {
          console.warn('⚠️ Preventing old App-Scheduler value from being sent to API');
          params.scheduler_name = 'Application-Scheduler';
        } else {
          params.scheduler_name = schedulerFilter;
        }
      }
      if (exchangeFilter) params.exchange_id = exchangeFilter;
      if (logTypeFilter) params.log_type = logTypeFilter;
      if (statusFilter) params.status = statusFilter;
      params.limit = rowLimit;
      
      const response = await axios.get('/v1/scheduler-logs', { params });
      const logsData = response.data.logs || [];
      setLogs(logsData);
      if (!silent) {
        setSuccess(`Loaded ${logsData.length} scheduler log${logsData.length !== 1 ? 's' : ''}`);
      }
    } catch (error) {
      console.error('Error fetching scheduler logs:', error);
      setError('Failed to load scheduler logs: ' + (error.response?.data?.detail || error.message));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [environment, timeRange, schedulerFilter, exchangeFilter, logTypeFilter, statusFilter, startDateTime, endDateTime, rowLimit, withEnvironment]);
  
  // Store fetch function in ref for auto-refresh
  useEffect(() => {
    fetchRef.current = fetchLogs;
  }, [fetchLogs]);
  
  // Initial data load
  useEffect(() => {
    const timer = setTimeout(() => {
      if (timeRange !== 'custom' || (startDateTime && endDateTime)) {
        fetchLogs();
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [fetchLogs, timeRange, startDateTime, endDateTime, rowLimit]);
  
  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (fetchRef.current) {
        fetchRef.current(true); // silent refresh
      }
    }, 30000); // 30 seconds
    
    return () => clearInterval(interval);
  }, []);
  
  const toggleRow = (logId) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(logId)) {
      newExpanded.delete(logId);
    } else {
      newExpanded.add(logId);
    }
    setExpandedRows(newExpanded);
  };
  
  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case 'success': return 'success';
      case 'failed': return 'error';
      case 'error': return 'error';
      case 'warning': return 'warning';
      case 'info': return 'info';
      default: return 'default';
    }
  };
  
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    try {
      // Ensure the timestamp is treated as UTC if it doesn't have timezone info
      let dateString = timestamp;
      if (!dateString.includes('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
        // If no timezone info, assume it's UTC and add 'Z'
        dateString = dateString.endsWith('Z') ? dateString : dateString + 'Z';
      }
      const date = new Date(dateString);
      // Format in IST (Indian Standard Time - Asia/Kolkata) - DD-MM-YYYY HH:MM:SS format
      return date.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
      });
    } catch {
      return timestamp;
    }
  };
  
  const getLogTypeColor = (logType) => {
    switch (logType?.toLowerCase()) {
      case 'token': return 'primary';
      case 'sequence_id': return 'secondary';
      case 'scheduler': return 'info';
      case 'retry': return 'warning';
      case 'error': return 'error';
      case 'success': return 'success';
      default: return 'default';
    }
  };
  
  // Truncate message and show if it's expandable
  const truncateMessage = (message, maxLength = 60) => {
    if (!message) return 'N/A';
    if (message.length <= maxLength) return message;
    return message.substring(0, maxLength) + '...';
  };
  
  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" component="h1" gutterBottom>
            Scheduler Logs
          </Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Tooltip title="Refresh">
              <IconButton onClick={() => fetchLogs()} color="primary" disabled={loading}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
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
        
        {/* Filters */}
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Time Range</InputLabel>
                  <Select
                    value={timeRange}
                    label="Time Range"
                    onChange={(e) => setTimeRange(e.target.value)}
                  >
                    <MenuItem value="15">Last 15 mins</MenuItem>
                    <MenuItem value="60">Last 1 hour</MenuItem>
                    <MenuItem value="120">Last 2 hours</MenuItem>
                    <MenuItem value="1440">Last 24 hours</MenuItem>
                    <MenuItem value="custom">Custom</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              {timeRange === 'custom' && (
                <>
                  <Grid item xs={12} sm={6} md={3}>
                    <LocalizationProvider dateAdapter={AdapterDateFns}>
                      <DateTimePicker
                        label="Start Date/Time"
                        value={startDateTime}
                        onChange={setStartDateTime}
                        renderInput={(params) => <TextField {...params} size="small" fullWidth />}
                      />
                    </LocalizationProvider>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <LocalizationProvider dateAdapter={AdapterDateFns}>
                      <DateTimePicker
                        label="End Date/Time"
                        value={endDateTime}
                        onChange={setEndDateTime}
                        renderInput={(params) => <TextField {...params} size="small" fullWidth />}
                      />
                    </LocalizationProvider>
                  </Grid>
                </>
              )}
              
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Scheduler</InputLabel>
                  <Select
                    value={schedulerFilter}
                    label="Scheduler"
                    onChange={(e) => setSchedulerFilter(e.target.value)}
                  >
                    <MenuItem value="">All</MenuItem>
                    <MenuItem value="Hardware-Scheduler">Hardware</MenuItem>
                    <MenuItem value="Network-Scheduler">Network</MenuItem>
                    <MenuItem value="Application-Scheduler">Application</MenuItem>
                    {/* REMOVED: Old App-Scheduler option - scheduler is disabled and deprecated */}
                    <MenuItem value="DB-Scheduler">Database</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Exchange</InputLabel>
                  <Select
                    value={exchangeFilter}
                    label="Exchange"
                    onChange={(e) => setExchangeFilter(e.target.value)}
                  >
                    <MenuItem value="">All</MenuItem>
                    <MenuItem value="1">NSE</MenuItem>
                    <MenuItem value="2">BSE</MenuItem>
                    <MenuItem value="4">MCX</MenuItem>
                    <MenuItem value="5">NCDEX</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Log Type</InputLabel>
                  <Select
                    value={logTypeFilter}
                    label="Log Type"
                    onChange={(e) => setLogTypeFilter(e.target.value)}
                  >
                    <MenuItem value="">All</MenuItem>
                    <MenuItem value="token">Token</MenuItem>
                    <MenuItem value="sequence_id">Sequence ID</MenuItem>
                    <MenuItem value="scheduler">Scheduler</MenuItem>
                    <MenuItem value="retry">Retry (704)</MenuItem>
                    <MenuItem value="error">Error</MenuItem>
                    <MenuItem value="success">Success</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Status</InputLabel>
                  <Select
                    value={statusFilter}
                    label="Status"
                    onChange={(e) => setStatusFilter(e.target.value)}
                  >
                    <MenuItem value="">All</MenuItem>
                    <MenuItem value="success">Success</MenuItem>
                    <MenuItem value="failed">Failed</MenuItem>
                    <MenuItem value="warning">Warning</MenuItem>
                    <MenuItem value="info">Info</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} sm={6} md={2}>
                <TextField
                  fullWidth
                  size="small"
                  label="Row Limit"
                  type="number"
                  value={rowLimit}
                  onChange={(e) => setRowLimit(parseInt(e.target.value) || 1000)}
                />
              </Grid>
            </Grid>
            
            {activeTimeRange && (
              <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'text.secondary' }}>
                Showing logs for: {activeTimeRange}
              </Typography>
            )}
          </CardContent>
        </Card>
        
        {/* Logs Table */}
        <Card>
          <CardContent>
            {loading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                <CircularProgress />
              </Box>
            ) : logs.length === 0 ? (
              <Alert severity="info">No scheduler logs found for the selected filters.</Alert>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Time (IST)</TableCell>
                      <TableCell>Scheduler</TableCell>
                      <TableCell>Environment</TableCell>
                      <TableCell>Exchange</TableCell>
                      <TableCell>Metric Type</TableCell>
                      <TableCell>Log Type</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell>Message</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Duration</TableCell>
                      <TableCell></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {logs.map((log) => (
                      <React.Fragment key={log.id}>
                        <TableRow hover>
                          <TableCell>{formatTimestamp(log.timestamp || log.created_at)}</TableCell>
                          <TableCell>
                            <Chip label={log.scheduler_name || 'N/A'} size="small" />
                          </TableCell>
                          <TableCell>
                            <Chip 
                              label={log.environment?.toUpperCase() || 'N/A'} 
                              size="small"
                              color={log.environment === 'uat' ? 'warning' : 'success'}
                            />
                          </TableCell>
                          <TableCell>{log.exchange_name || 'N/A'}</TableCell>
                          <TableCell>{log.metric_type || 'N/A'}</TableCell>
                          <TableCell>
                            <Chip 
                              label={log.log_type || 'N/A'} 
                              size="small"
                              color={getLogTypeColor(log.log_type)}
                            />
                          </TableCell>
                          <TableCell>{log.action || 'N/A'}</TableCell>
                          <TableCell sx={{ maxWidth: 400, cursor: 'pointer' }} onClick={() => toggleRow(log.id)}>
                            <Tooltip title={log.message || 'N/A'} arrow placement="top">
                              <Typography 
                                variant="body2" 
                                sx={{ 
                                  display: 'flex', 
                                  alignItems: 'center',
                                  '&:hover': { color: 'primary.main' }
                                }}
                              >
                                {truncateMessage(log.message)}
                                {log.message && log.message.length > 60 && (
                                  <ExpandMoreIcon sx={{ fontSize: 16, ml: 0.5, color: 'text.secondary' }} />
                                )}
                              </Typography>
                            </Tooltip>
                          </TableCell>
                          <TableCell>
                            {log.status && (
                              <Chip 
                                label={log.status} 
                                size="small"
                                color={getStatusColor(log.status)}
                              />
                            )}
                          </TableCell>
                          <TableCell>
                            {log.duration_ms ? `${log.duration_ms}ms` : 'N/A'}
                          </TableCell>
                          <TableCell>
                            <IconButton
                              size="small"
                              onClick={() => toggleRow(log.id)}
                              color={expandedRows.has(log.id) ? 'primary' : 'default'}
                            >
                              {expandedRows.has(log.id) ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                            </IconButton>
                          </TableCell>
                        </TableRow>
                        {expandedRows.has(log.id) && (
                          <TableRow>
                            <TableCell colSpan={11} sx={{ py: 2, bgcolor: 'action.hover' }}>
                              {/* Full Message */}
                              <Typography variant="subtitle2" gutterBottom sx={{ color: 'primary.main' }}>
                                📝 Full Message:
                              </Typography>
                              <Box
                                sx={{
                                  bgcolor: 'background.paper',
                                  p: 2,
                                  borderRadius: 1,
                                  mb: 2,
                                  border: '1px solid',
                                  borderColor: 'divider',
                                  wordBreak: 'break-word'
                                }}
                              >
                                <Typography variant="body2">
                                  {log.message || 'N/A'}
                                </Typography>
                              </Box>
                              
                              {/* Full Response (from details.full_response) */}
                              {log.details?.full_response && (
                                <>
                                  <Typography variant="subtitle2" gutterBottom sx={{ color: 'warning.main' }}>
                                    📦 Exchange Response:
                                  </Typography>
                                  <Box
                                    component="pre"
                                    sx={{
                                      bgcolor: '#1e1e1e',
                                      color: '#d4d4d4',
                                      p: 2,
                                      borderRadius: 1,
                                      overflow: 'auto',
                                      maxHeight: 300,
                                      fontSize: '0.75rem',
                                      fontFamily: 'monospace',
                                      mb: 2,
                                    }}
                                  >
                                    {typeof log.details.full_response === 'string' 
                                      ? log.details.full_response 
                                      : JSON.stringify(log.details.full_response, null, 2)}
                                  </Box>
                                </>
                              )}
                              
                              {/* Details */}
                              {log.details && Object.keys(log.details).length > 0 && (
                                <>
                                  <Typography variant="subtitle2" gutterBottom sx={{ color: 'info.main' }}>
                                    📋 Details:
                                  </Typography>
                                  <Box
                                    component="pre"
                                    sx={{
                                      bgcolor: 'background.paper',
                                      p: 2,
                                      borderRadius: 1,
                                      overflow: 'auto',
                                      maxHeight: 400,
                                      fontSize: '0.875rem',
                                      border: '1px solid',
                                      borderColor: 'divider',
                                    }}
                                  >
                                    {JSON.stringify(log.details, null, 2)}
                                  </Box>
                                </>
                              )}
                            </TableCell>
                          </TableRow>
                        )}
                      </React.Fragment>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        </Card>
      </Box>
    </Container>
  );
};

export default SchedulerLogs;

