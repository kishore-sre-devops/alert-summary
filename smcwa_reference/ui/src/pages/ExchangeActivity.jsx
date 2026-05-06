import React, { useState, useEffect, useRef } from 'react';
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
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Menu,
  Container,
  TablePagination,
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
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  // Date and time range (combined)
  const [startDateTime, setStartDateTime] = useState(null);
  const [endDateTime, setEndDateTime] = useState(null);
  
  // Filters
  const [metricType, setMetricType] = useState('all'); // 'all' = show all metric types
  const [status, setStatus] = useState('all'); // 'all' = show all statuses
  const [locationFilter, setLocationFilter] = useState(''); // '' = all locations
  const [exchangeFilter, setExchangeFilter] = useState('ALL');
  const [sequenceIdSearch, setSequenceIdSearch] = useState('');
  const [timeRange, setTimeRange] = useState('15'); // Default: Last 15 minutes (matching vendor dashboard)
  const [viewType, setViewType] = useState('activity'); // 'activity' or 'transactions'
  const [rowLimit, setRowLimit] = useState(20); // Number of rows per page
  const [page, setPage] = useState(0); // Material UI TablePagination uses 0-indexed page
  const [totalCount, setTotalCount] = useState(0);
  const intervalRef = useRef('15'); // Store interval in ref to prevent loss
  
  // Ensure timeRange always has a valid value (prevent empty/null)
  const safeTimeRange = timeRange || '15';
  
  // Helper function to get display text for interval
  const getIntervalDisplayText = (intervalValue) => {
    const intervalMap = {
      '5': 'Last 5 minutes',
      '15': 'Last 15 minutes',
      '30': 'Last 30 minutes',
      '60': 'Last 1 hour',
      '120': 'Last 2 hours',
      '180': 'Last 3 hours',
      '2880': 'Last 2 days',
      '4320': 'Last 3 days',
      '10080': 'Last 7 days',
      '1440': 'Last 24 hours',
      'custom': 'Custom Date & Time'
    };
    return intervalMap[intervalValue] || 'Last 15 minutes';
  };
  
  // Data
  const [exchangeTransactions, setExchangeTransactions] = useState([]);
  // Fixed: enforce single-tab view; always treat as Exchange Activity
  const tabValue = 0;
  
  // Details modal state
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);
  const [selectedTransaction, setSelectedTransaction] = useState(null);
  const [serverDetails, setServerDetails] = useState([]);
  const [aggregatedMetrics, setAggregatedMetrics] = useState([]);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState(null);
  const [selectedRowId, setSelectedRowId] = useState(null);
  const [jsonModalOpen, setJsonModalOpen] = useState(false);
  const [selectedJsonData, setSelectedJsonData] = useState(null);
  const [expandedDetails, setExpandedDetails] = useState({}); // Track expanded detail rows
  const [activeTimeRange, setActiveTimeRange] = useState(''); // Store the active time range display text
  const [detailsMetricTypeFilter, setDetailsMetricTypeFilter] = useState('All'); // Metric type filter for Details modal (Hardware/Network/Application/Database/All)

  // Track if this is the first render to skip initial mount
  const isFirstRender = React.useRef(true);
  
  // Store latest fetch function in ref to avoid stale closures in setInterval
  const fetchRef = useRef(null);

  const fetchExchangeTransactions = async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }
    setError('');
    try {
      let params = {};
      
      // Unified date/time selection: Use timeRange OR custom date/time
      // CRITICAL: Convert to UTC for backend consistency (database stores UTC)
      const convertToUTC = (date) => {
        if (!date) return null;
        // Get UTC date/time components for API calls
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

      // Format date/time in IST for display (user-friendly)
      const formatDateTimeIST = (date) => {
        if (!date) return '';
        const d = new Date(date);
        const istDate = d.toLocaleString('en-IN', {
          timeZone: 'Asia/Kolkata',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false
        });
        return istDate.replace(/(\d+)\/(\d+)\/(\d+),/, '$3-$2-$1'); // Convert DD/MM/YYYY to YYYY-MM-DD
      };
      
      // Use interval from ref to ensure we have the latest value
      const currentInterval = intervalRef.current || timeRange || '15';
      if (currentInterval && currentInterval !== 'custom') {
        // Use predefined interval (5 mins, 15 mins, etc.)
        const now = new Date();
        const intervalMinutes = parseInt(currentInterval, 10);
        if (isNaN(intervalMinutes)) {
          console.error('[FETCH] Invalid interval:', currentInterval);
          // Default to 15 minutes if invalid
          const minutesAgo = new Date(now.getTime() - (15 + 1) * 60 * 1000); // 1-minute buffer
          const startUTC = convertToUTC(minutesAgo);
          const endUTC = convertToUTC(now);
          params.start_date = startUTC.date;
          params.start_time = startUTC.time;
          params.end_date = endUTC.date;
          params.end_time = endUTC.time;
          // Update active time range display (show IST for user)
          setActiveTimeRange(`${formatDateTimeIST(minutesAgo)} to ${formatDateTimeIST(now)} IST`);
        } else {
          // ADD 5 MINUTE BUFFER to catch cycles on the boundary
          // Schedulers push every 5 minutes, so a 1-min buffer is too small
          const minutesAgo = new Date(now.getTime() - (intervalMinutes + 5) * 60 * 1000);
          const startUTC = convertToUTC(minutesAgo);
          const endUTC = convertToUTC(now);
          params.start_date = startUTC.date;
          params.start_time = startUTC.time;
          params.end_date = endUTC.date;
          params.end_time = endUTC.time;
          // Update active time range display (show IST for user)
          setActiveTimeRange(`${formatDateTimeIST(minutesAgo)} to ${formatDateTimeIST(now)} IST`);
      
        }
      } else if (currentInterval === 'custom' && startDateTime && endDateTime) {
        // Use custom DateTimePicker values - convert to UTC
        const startUTC = convertToUTC(startDateTime);
        const endUTC = convertToUTC(endDateTime);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
        // Update active time range display
        setActiveTimeRange(`${formatDateTimeIST(startDateTime)} to ${formatDateTimeIST(endDateTime)} IST`);
    
      } else {
        // Default: Last 15 minutes if nothing is selected
        const now = new Date();
        const minutesAgo = new Date(now.getTime() - 15 * 60 * 1000);
        const startUTC = convertToUTC(minutesAgo);
        const endUTC = convertToUTC(now);
        params.start_date = startUTC.date;
        params.start_time = startUTC.time;
        params.end_date = endUTC.date;
        params.end_time = endUTC.time;
        // Update active time range display (show IST for user)
        setActiveTimeRange(`${formatDateTimeIST(minutesAgo)} to ${formatDateTimeIST(now)} IST`);
    
      }
      
  
      
      // Use withEnvironment to always include environment from sidebar selector
      params = { ...params, ...withEnvironment() };
      
      // GLOBAL SEARCH: Add manual Sequence ID search parameter
      if (sequenceIdSearch && sequenceIdSearch.trim()) {
        params.sequence_id_search = sequenceIdSearch.trim();
      }

      // CRITICAL: Only send filters if they have non-empty values ('all' = show all)
      if (metricType && metricType.trim() && metricType !== 'all') params.metric_type = metricType;
      if (status && status.trim() && status !== 'all') params.status = status;
      if (exchangeFilter && exchangeFilter !== 'ALL') {
        // Convert exchange name to ID (1=NSE, 2=BSE, 3=MSE, 4=MCX, 5=NCDEX)
        const exchangeMap = { 'NSE': '1', 'BSE': '2', 'MSE': '3', 'MCX': '4', 'NCDEX': '5' };
        params.exchange_id = parseInt(exchangeMap[exchangeFilter] || exchangeFilter);
      }

      if (locationFilter !== '') {
        params.location_id = locationFilter;
      }
      
      // Pagination parameters
      params.page = page + 1; // Backend uses 1-indexed page
      params.size = rowLimit;
      
      // Enable grouping by exchange to show one entry per exchange per push time
      params.group_by_exchange = true;
      
  
      const response = await axios.get('/v1/historical/exchange-transactions', { params });
  


      const transactions = response.data?.items || response.data?.transactions || [];
      const total = response.data?.total_count || 0;
  
      setExchangeTransactions(transactions);
      setTotalCount(total);
      
      if (!silent) {
        setSuccess(`Loaded ${transactions.length} exchange transactions (Total: ${total})`);
      }
    } catch (error) {
      console.error('Error fetching exchange transactions:', error);
      if (!silent) {
        // Show more detailed error message
        let errorMessage = 'Failed to load exchange transactions';
        if (error.response) {
          // Server responded with error status
          const status = error.response.status;
          const detail = error.response.data?.detail || error.response.data?.message || '';
          if (status === 401) {
            errorMessage = 'Authentication failed. Please log in again.';
          } else if (status === 403) {
            errorMessage = 'Access denied. You do not have permission.';
          } else if (status === 500) {
            errorMessage = 'Server error. Please check backend logs.';
          } else if (detail) {
            errorMessage = `Failed to load: ${detail}`;
          } else {
            errorMessage = `Failed to load exchange transactions (HTTP ${status})`;
          }
        } else if (error.request) {
          // Request made but no response
          errorMessage = 'Network error. Please check your connection.';
        } else {
          // Error in request setup
          errorMessage = `Error: ${error.message || 'Unknown error'}`;
        }
        setError(errorMessage);
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };
  
  // Update ref after function is defined (for auto-refresh timer)
  useEffect(() => {
    fetchRef.current = fetchExchangeTransactions;
  });
  
  // Sync ref when timeRange changes
  useEffect(() => {
    intervalRef.current = timeRange;
  }, [timeRange]);
  
  // Initialize and load data on mount (moved after function definition)
  useEffect(() => {
    intervalRef.current = timeRange; // Initialize ref
    // Initial data load on mount
    fetchExchangeTransactions();
  }, []); // Only run on mount
  
  // Auto-refresh every 30 seconds for real-time updates
  useEffect(() => {
    // Only auto-refresh if we're on Exchange Activity tab (tabValue === 0)
    // and not using custom date/time (which should be manual refresh only)
    const currentInterval = intervalRef.current || timeRange;
    if (tabValue === 0 && currentInterval !== 'custom') {
      const refreshTimer = setInterval(() => {
        // Use ref to always call latest version with current filter values
        if (fetchRef.current) {
          fetchRef.current(true); // Pass silent=true to avoid loading spinner
        }
      }, 30000); // Refresh every 30 seconds
      
      return () => {
        clearInterval(refreshTimer);
      };
    }
  }, [tabValue, timeRange]); // Re-run when tab or timeRange changes
  
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
  
  // Unified auto-refresh: Watch all filter changes and auto-fetch data
  useEffect(() => {
    // Skip initial mount - let the initial useEffect handle first load
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    
    // This effect handles subsequent filter changes
    let isMounted = true;
    let timer;
    
    // Debounce the API call to avoid too many requests
    // Don't clear data immediately - let users see existing data while new data loads
    timer = setTimeout(() => {
      if (isMounted) {
        fetchExchangeTransactions(false); // Show loading state for manual filter changes
      }
    }, 300); // 300ms debounce for smooth UX
    
    return () => {
      isMounted = false;
      if (timer) clearTimeout(timer);
    };
    // CRITICAL: Include timeRange in dependencies so time range changes trigger fetch
    // Note: fetchExchangeTransactions is not in deps to avoid infinite loops
    // It uses the current state values via closure
  }, [environment, metricType, status, startDateTime, endDateTime, timeRange, rowLimit, exchangeFilter, page, locationFilter]);

  const handleExport = async () => {
    setExporting(true);
    setError('');
    try {
      let params = {
        data_type: 'exchange'
      };
      
      // Unified date/time selection: Use timeRange OR custom date/time
      // CRITICAL: Use UTC dates/times for API calls since database stores UTC
      if (timeRange && timeRange !== 'custom') {
        const now = new Date();
        const minutesAgo = new Date(now.getTime() - parseInt(timeRange) * 60 * 1000);
        params.start_date = formatDateUTC(minutesAgo);
        params.end_date = formatDateUTC(now);
        params.start_time = formatTimeFromDateUTC(minutesAgo);
        params.end_time = formatTimeFromDateUTC(now);
      } else if (timeRange === 'custom' && startDateTime && endDateTime) {
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

      if (exchangeFilter && exchangeFilter !== 'ALL') {
        const exchangeMap = { 'NSE': '1', 'BSE': '2', 'MSE': '3', 'MCX': '4', 'NCDEX': '5' };
        params.exchange_id = parseInt(exchangeMap[exchangeFilter] || exchangeFilter);
      }
      
      if (locationFilter !== '') {
        params.location_id = locationFilter;
      }
      
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
    // Parse as-is (no Z suffix) so JS treats it as local time, then format for display.
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

  // Removed handleTabChange: single-tab view only

  const getStatusColor = (tx) => {
    const displayStatus = getDisplayStatus(tx);
    switch (displayStatus) {
      case 'SUCCESS': return 'success';
      case 'FAILED': return 'error';
      case 'NOT FOUND': return 'warning';
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
    if (responseDesc) {
      return responseDesc;
    }
    
    // Fallback to error_message
    return errorMsg || 'Unknown error';
  };

  const getMetricTypeStyle = (type) => {
    switch (type) {
      case 'hardware': 
        return { 
          backgroundColor: '#e3f2fd', 
          color: '#1565c0', 
          fontWeight: 'bold',
          border: '1px solid #bbdefb'
        };
      case 'network': 
        return { 
          backgroundColor: '#f3e5f5', 
          color: '#7b1fa2', 
          fontWeight: 'bold',
          border: '1px solid #e1bee7'
        };
      case 'database': 
        return { 
          backgroundColor: '#fff3e0', 
          color: '#ef6c00', 
          fontWeight: 'bold',
          border: '1px solid #ffe0b2'
        };
      case 'application': 
        return { 
          backgroundColor: '#e8f5e9', 
          color: '#2e7d32', 
          fontWeight: 'bold',
          border: '1px solid #c8e6c9'
        };
      case 'login': 
        return { 
          backgroundColor: '#ffebee', 
          color: '#c62828', 
          fontWeight: 'bold'
        };
      case 'logout': 
        return { 
          backgroundColor: '#fff3e0', 
          color: '#ef6c00', 
          fontWeight: 'bold'
        };
      default: 
        return { fontWeight: 'bold' };
    }
  };



  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Container maxWidth="xl" sx={{ py: { xs: 1.5, sm: 2, md: 2.5 }, px: { xs: 1, sm: 1.5, md: 2 } }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: { xs: 2, md: 2.5 } }}>
        <Box>
          <Typography variant="h4" sx={{ 
            fontWeight: 'bold', 
            fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.75rem', lg: '2rem' }
          }}>
            Exchange Activity
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
            Auto-refresh: 30s
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title="Refresh">
            <IconButton onClick={() => fetchExchangeTransactions(false)}>
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
                <InputLabel id="time-range-label">Time Range</InputLabel>
                <Select
                  labelId="time-range-label"
                  value={safeTimeRange}
                  onChange={(e) => {
                    const value = e.target.value;
                
                    // Update both state and ref immediately - ensure value is never empty
                    const newValue = value || '1440';
                    intervalRef.current = newValue;
                    setTimeRange(newValue);
                    if (newValue === 'custom') {
                      // Don't clear date/time when switching to custom
                    } else {
                      setStartDateTime(null);
                      setEndDateTime(null);
                    }
                    // Note: Auto-refresh will be handled by useEffect watching timeRange
                  }}
                  label="Time Range"
                  displayEmpty={false}
                  renderValue={(selected) => {
                    // Material-UI Select passes the value directly to renderValue
                    // Always use the safeTimeRange to ensure consistent display
                    const valueToDisplay = safeTimeRange || selected || '1440';
                    const displayText = getIntervalDisplayText(valueToDisplay);
                
                    return displayText;
                  }}
                >
                  <MenuItem value="5">Last 5 minutes</MenuItem>
                  <MenuItem value="15">Last 15 minutes</MenuItem>
                  <MenuItem value="30">Last 30 minutes</MenuItem>
                  <MenuItem value="60">Last 1 hour</MenuItem>
                  <MenuItem value="120">Last 2 hours</MenuItem>
                  <MenuItem value="180">Last 3 hours</MenuItem>
                  <MenuItem value="2880">Last 2 days</MenuItem>
                  <MenuItem value="4320">Last 3 days</MenuItem>
                  <MenuItem value="10080">Last 7 days</MenuItem>
                  <MenuItem value="1440">Last 24 hours</MenuItem>
                  <MenuItem value="custom">Custom Date & Time</MenuItem>
                </Select>
              </FormControl>
              {safeTimeRange && (
                <Box sx={{ mt: 0.5 }}>
                  <Typography variant="caption" color="primary" sx={{ display: 'block', fontWeight: 'medium' }}>
                    ✓ {getIntervalDisplayText(safeTimeRange)}
                  </Typography>
                  {activeTimeRange && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontSize: '0.7rem', mt: 0.25 }}>
                      {activeTimeRange}
                    </Typography>
                  )}
                </Box>
              )}
            </Grid>
            {timeRange === 'custom' && (
              <>
                <Grid item xs={12} sm={6} md={3}>
                  <DateTimePicker
                    label="Start Date & Time"
                    value={startDateTime}
                    onChange={(newValue) => {
                      setStartDateTime(newValue);
                      // Auto-refresh handled by unified useEffect
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
                      // Auto-refresh handled by unified useEffect
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
            <Grid item xs={12} sm={6} md={timeRange === 'custom' ? 2 : 2}>
              <TextField
                fullWidth
                size="small"
                label="Sequence ID"
                placeholder="Global Search ID..."
                value={sequenceIdSearch}
                onChange={(e) => {
                  setSequenceIdSearch(e.target.value);
                  setPage(0);
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={timeRange === 'custom' ? 2 : 2}>
              <FormControl fullWidth size="small">
                <InputLabel>Metric Type</InputLabel>
                <Select
                  value={metricType || 'all'}
                  onChange={(e) => {
                
                    setMetricType(e.target.value || 'all');
                    // Auto-refresh will be handled by useEffect watching metricType
                  }}
                  label="Metric Type"
                >
                  <MenuItem value="all">All</MenuItem>
                  <MenuItem value="hardware">Hardware</MenuItem>
                  <MenuItem value="network">Network</MenuItem>
                  <MenuItem value="database">Database</MenuItem>
                  <MenuItem value="application">Application</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={timeRange === 'custom' ? 2 : 2}>
              <FormControl fullWidth size="small">
                <InputLabel>Status</InputLabel>
                <Select
                  value={status || 'all'}
                  onChange={(e) => {
                
                    setStatus(e.target.value || 'all');
                    // Auto-refresh will be handled by useEffect watching status
                  }}
                  label="Status"
                >
                  <MenuItem value="all">All</MenuItem>
                  <MenuItem value="success">Success</MenuItem>
                  <MenuItem value="failed">Failed</MenuItem>
                  <MenuItem value="error">Error</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={timeRange === 'custom' ? 2 : 2}>
              <FormControl fullWidth size="small">
                <InputLabel>Rows per page</InputLabel>
                <Select
                  value={rowLimit}
                  onChange={(e) => {
                    setRowLimit(e.target.value);
                    setPage(0);
                  }}
                  label="Rows per page"
                >
                  <MenuItem value={10}>10</MenuItem>
                  <MenuItem value={20}>20</MenuItem>
                  <MenuItem value={50}>50</MenuItem>
                  <MenuItem value={100}>100</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={timeRange === 'custom' ? 2 : 2}>
              <FormControl fullWidth size="small">
                <InputLabel>Exchange</InputLabel>
                <Select
                  value={exchangeFilter}
                  onChange={(e) => {
                    setExchangeFilter(e.target.value);
                    setPage(0);
                    // Changing exchange triggers refetch via effect dependency
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
            <Grid item xs={12} sm={6} md={timeRange === 'custom' ? 2 : 2}>
              <FormControl fullWidth size="small">
                <InputLabel>Location</InputLabel>
                <Select
                  value={locationFilter}
                  onChange={(e) => {
                    setLocationFilter(e.target.value);
                    setPage(0);
                  }}
                  label="Location"
                >
                  <MenuItem value="">All Locations</MenuItem>
                  <MenuItem value={1}>DC (Data Center)</MenuItem>
                  <MenuItem value={2}>DR (Disaster Recovery)</MenuItem>
                  <MenuItem value={3}>Cloud / AWS</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={timeRange === 'custom' ? 2 : 2}>
              <FormControl fullWidth size="small">
                <InputLabel>View Type</InputLabel>
                <Select
                  value={viewType}
                  onChange={(e) => {
                    setViewType(e.target.value);
                    setPage(0);
                    // Data is already loaded, just change view
                  }}
                  label="View Type"
                >
                  <MenuItem value="activity">Activity View</MenuItem>
                  <MenuItem value="transactions">Transactions View</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Paper>

        {viewType === 'activity' && (
              <Box sx={{ p: 2 }}>
                {/* Exchange Activity Filters - Only unique filters for this tab */}
                {/* Note: Sequence ID search moved to column header dropdown */}
                
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
                <TableContainer sx={{ 
                  maxHeight: { xs: 400, sm: 500, md: 600 },
                  overflowX: 'auto',
                  '& .MuiTableCell-root': {
                    padding: { xs: '8px 12px', sm: '12px 16px' },
                    fontSize: { xs: '0.75rem', sm: '0.875rem' }
                  }
                }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Time (IST - When Sent)</TableCell>
                        <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Seq No</TableCell>
                        <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Exchange</TableCell>
                        <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Location</TableCell>
                        <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Metric Type</TableCell>
                        <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Status</TableCell>
                        <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700, minWidth: 500 }}>Detail</TableCell>
                        <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Action</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                    {exchangeTransactions.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} align="center">
                          <Box sx={{ py: 3 }}>
                            <Typography variant="body1" color="text.secondary" gutterBottom>
                              No transactions found for the selected time range.
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              Try selecting a larger time range (e.g., Last 24 hours or Last 7 days) to view historical data.
                            </Typography>
                          </Box>
                        </TableCell>
                      </TableRow>
                    ) : (
                      exchangeTransactions
                        .map((tx) => {
                          // CRITICAL: Get exchange_id from backend response (preferred) or fallback to JSON
                          // Backend now extracts exchange_id from stored JSON and includes it in response
                          const metricsSent = tx.metrics_sent || {};
                          const lamaPayload = metricsSent.lama_v1_2_payload || {};
                          let exchangeId = tx.exchange_id;  // Use backend-extracted value first
                          
                          // Fallback: try to get from JSON if backend didn't extract it
                          if (exchangeId === undefined || exchangeId === null) {
                            exchangeId = lamaPayload.exchangeId || metricsSent.exchangeId || tx.exchange_response?.exchangeId;
                          }
                          
                          // Extract payload array from V1.2 structure
                          const payload = lamaPayload.payload || [];
                          
                          // Fallback: if no payload, try to get from original_metrics
                          const originalMetrics = metricsSent.original_metrics || [];
                          
                          const exchangeResponse = tx.exchange_response || {};
                          
                          // Get Exchange name
                          const getExchangeName = (id) => {
                            // For login/logout errors, show special label
                            if (tx.metric_type === 'login') {
                              return 'LOGIN ERROR';
                            }
                            if (tx.metric_type === 'logout') {
                              return 'LOGOUT ERROR';
                            }
                            
                            if (id === undefined || id === null || id === '') {
                              return 'N/A';
                            }
                            const map = { '1': 'NSE', '2': 'BSE', '3': 'MSE', '4': 'MCX', '5': 'NCDEX' };
                            return map[String(id)] || `ID: ${id}`;
                          };
                          
                          // Format Detail string to match exact LAMA Exchange format
                          // Format: SUCCESS | response Code : 601 | Lama : V1 | response Desc : success ,cpu : min: 0.3 ,max: 0.3 ,avg: 0.3 ,med: 0.3 ...
                          // Special handling for login/logout errors
                          const formatDetail = () => {
                            // For login/logout errors, show detailed format with headers and response
                            if (tx.metric_type === 'login' || tx.metric_type === 'logout') {
                              const displayStatus = getDisplayStatus(tx);
                              const errorMsg = getErrorMessage(tx);
                              const statusCode = tx.status_code || exchangeResponse.responseCode || exchangeResponse.response_code || '';
                              const responseDesc = exchangeResponse.responseDesc || exchangeResponse.response_desc || exchangeResponse.message || '';
                              const responseCode = exchangeResponse.responseCode || exchangeResponse.response_code || '';
                              
                              // Build detailed parts array
                              const parts = [displayStatus];
                              
                              // Add HTTP status code
                              if (statusCode) {
                                parts.push(`HTTP ${statusCode}`);
                              }
                              
                              // Add LAMA response code if available
                              if (responseCode && String(responseCode) !== String(statusCode)) {
                                parts.push(`response Code : ${responseCode}`);
                              }
                              
                              // Add LAMA response description
                              if (responseDesc) {
                                parts.push(`response Desc : ${responseDesc.toLowerCase()}`);
                              } else if (errorMsg) {
                                parts.push(`response Desc : ${errorMsg.toLowerCase()}`);
                              }
                              
                              // Add error message if different from response desc
                              if (errorMsg && errorMsg !== responseDesc) {
                                parts.push(`Error: ${errorMsg}`);
                              }
                              
                              // Add request headers info (from metrics_sent if available)
                              const requestHeaders = metricsSent.headers || metricsSent.requestHeaders || {};
                              if (Object.keys(requestHeaders).length > 0) {
                                const headerParts = [];
                                if (requestHeaders['Content-Type']) headerParts.push(`Content-Type: ${requestHeaders['Content-Type']}`);
                                if (requestHeaders['User-Agent']) headerParts.push(`User-Agent: ${requestHeaders['User-Agent'].substring(0, 30)}...`);
                                if (requestHeaders['Accept']) headerParts.push(`Accept: ${requestHeaders['Accept']}`);
                                if (headerParts.length > 0) {
                                  parts.push(`Headers: ${headerParts.join(', ')}`);
                                }
                              }
                              
                              // Add full response data if available
                              if (Object.keys(exchangeResponse).length > 0) {
                                const responseKeys = Object.keys(exchangeResponse).filter(k => 
                                  !['responseCode', 'response_code', 'responseDesc', 'response_desc', 'message'].includes(k)
                                );
                                if (responseKeys.length > 0) {
                                  const responseInfo = responseKeys.slice(0, 3).map(k => {
                                    const val = exchangeResponse[k];
                                    if (typeof val === 'object') {
                                      return `${k}: ${JSON.stringify(val).substring(0, 50)}...`;
                                    }
                                    return `${k}: ${String(val).substring(0, 50)}`;
                                  }).join(', ');
                                  parts.push(`Response: ${responseInfo}`);
                                }
                              }
                              
                              return parts.join(' | ');
                            }
                            
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
                            
                            // Format metrics to match vendor dashboard EXACTLY
                            // Vendor format: "cpu: min: 0.2 ,max: 0.2,avg: 0.2,med: 0.2 disk: min: 7 ,max: 14, avg: 10.5,med: 10.5 ... applicationId - 1, cpu: min: 0,max: 51.82,avg: 5.14,med: 3.64 ... applicationId - 4,"
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
                                const metricKey = metric.key || metric.name || '';
                                
                                // Handle both object format {min, max, avg, med} and simple numeric values
                                if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                                  const { min, max, avg, med } = value;
                                  // Format values - match vendor format (integers as-is, decimals with 2 places)
                                  const formatValue = (val) => {
                                    if (val === null || val === undefined) return 0;
                                    const num = typeof val === 'number' ? val : parseFloat(val);
                                    if (isNaN(num)) return 0;
                                    // Return as-is for integers, otherwise keep decimals
                                    return num;
                                  };
                                  
                                  const minVal = formatValue(min);
                                  const maxVal = formatValue(max);
                                  const avgVal = formatValue(avg);
                                  const medVal = formatValue(med);
                                  
                                  if (appIndex === 0) {
                                    // First applicationId group: "metricName: min: X ,max: Y,avg: Z,med: W" (space before first comma only)
                                    metricStrings.push(`${metricKey}: min: ${minVal} ,max: ${maxVal},avg: ${avgVal},med: ${medVal}`);
                                  } else {
                                    // Subsequent groups: "metricName: min: X,max: Y,avg: Z,med: W" (no spaces around commas)
                                    metricStrings.push(`${metricKey}: min: ${minVal},max: ${maxVal},avg: ${avgVal},med: ${medVal}`);
                                  }
                                } else {
                                  // Simple numeric value (for packetCount, lookupCount)
                                  const numValue = typeof value === 'number' ? value : (parseFloat(value) || 0);
                                  metricStrings.push(`${metricKey}: ${numValue}`);
                                }
                              });
                              
                              // Add applicationId marker - vendor format: " applicationId - X," (space before, comma at end)
                              appIdGroups.push(metricStrings.join(' ') + ` applicationId - ${appId},`);
                            });
                            
                            // Combine: main parts with | separator (with spaces), then metrics with comma prefix
                            let result = mainParts.join(' | ');
                            if (appIdGroups.length > 0) {
                              result += ' ,' + appIdGroups.join(' ');
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
                                  // CRITICAL: Get sequence ID from backend response (preferred) or fallback to JSON
                                  // Backend now extracts sequence_id from stored column or JSON, so use tx.sequence_id first
                                  const seqId = tx.sequence_id || 
                                               tx.metrics_sent?.lama_v1_2_payload?.sequenceId ||
                                               tx.metrics_sent?.sequenceId;
                                  // Only show "-" if sequence_id is truly empty/null/undefined
                                  return (seqId !== null && seqId !== undefined && seqId !== '') ? String(seqId) : '-';
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
                                  label={tx.location_name || 'DC'} 
                                  size="small" 
                                  variant="outlined"
                                  sx={{ 
                                    fontWeight: 600,
                                    borderColor: tx.location_id === 3 ? '#ed6c02' : (tx.location_id === 2 ? '#9c27b0' : '#1a237e'),
                                    color: tx.location_id === 3 ? '#ed6c02' : (tx.location_id === 2 ? '#9c27b0' : '#1a237e')
                                  }}
                                />
                              </TableCell>
                              <TableCell>
                                {tx.metric_type === 'all' && tx.metric_types ? (
                                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                                    {tx.metric_types.map((type) => (
                                      <Chip 
                                        key={type}
                                        label={type.charAt(0).toUpperCase() + type.slice(1)} 
                                        size="small" 
                                        sx={{ 
                                          ...getMetricTypeStyle(type),
                                          height: 22, 
                                          fontSize: '0.7rem' 
                                        }}
                                      />
                                    ))}
                                  </Box>
                                ) : (
                                  <Chip 
                                    label={tx.metric_type.charAt(0).toUpperCase() + tx.metric_type.slice(1)} 
                                    size="small" 
                                    sx={getMetricTypeStyle(tx.metric_type)}
                                  />
                                )}
                              </TableCell>
                              <TableCell>
                                <Chip 
                                  label={getDisplayStatus(tx)} 
                                  size="small" 
                                  color={getStatusColor(tx)}
                                  sx={{ 
                                    color: getDisplayStatus(tx) === 'SUCCESS' ? 'white' : 'inherit',
                                    fontWeight: 'bold'
                                  }}
                                />
                              </TableCell>
                              <TableCell>
                                {(() => {
                                  const detailText = formatDetail();
                                  const isExpanded = expandedDetails[tx.id];
                                  const maxLength = 150; // Truncate after 150 characters
                                  const shouldTruncate = detailText.length > maxLength;
                                  const displayText = shouldTruncate && !isExpanded 
                                    ? detailText.substring(0, maxLength) + '...'
                                    : detailText;
                                  
                                  return (
                                    <Box>
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
                                        {displayText}
                                      </Typography>
                                      {shouldTruncate && (
                                        <Button
                                          size="small"
                                          onClick={() => {
                                            setExpandedDetails(prev => ({
                                              ...prev,
                                              [tx.id]: !prev[tx.id]
                                            }));
                                          }}
                                          sx={{ 
                                            mt: 0.5, 
                                            minWidth: 'auto',
                                            fontSize: '0.7rem',
                                            textTransform: 'none'
                                          }}
                                        >
                                          {isExpanded ? 'Show Less' : '... Show More'}
                                        </Button>
                                      )}
                                    </Box>
                                  );
                                })()}
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
              <TablePagination
                rowsPerPageOptions={[10, 20, 50, 100]}
                component="div"
                count={totalCount}
                rowsPerPage={rowLimit}
                page={page}
                onPageChange={(e, newPage) => setPage(newPage)}
                onRowsPerPageChange={(e) => {
                  setRowLimit(parseInt(e.target.value, 10));
                  setPage(0);
                }}
              />
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
              <Box>
              <TableContainer sx={{ 
                maxHeight: { xs: 400, sm: 500, md: 600 },
                overflowX: 'auto',
                '& .MuiTableCell-root': {
                  padding: { xs: '8px 12px', sm: '12px 16px' },
                  fontSize: { xs: '0.75rem', sm: '0.875rem' }
                }
              }}>
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
                              <Chip label={tx.metric_type} size="small" sx={getMetricTypeStyle(tx.metric_type)} />
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
              <TablePagination
                rowsPerPageOptions={[10, 20, 50, 100]}
                component="div"
                count={totalCount}
                rowsPerPage={rowLimit}
                page={page}
                onPageChange={(e, newPage) => setPage(newPage)}
                onRowsPerPageChange={(e) => {
                  setRowLimit(parseInt(e.target.value, 10));
                  setPage(0);
                }}
              />
              </Box>
            )}
          </Box>
        )}
      </Paper>

      
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
              setDetailsMetricTypeFilter('All'); // Reset filter when opening modal
              setLoadingDetails(true);
              setDetailsModalOpen(true);
              try {
                const response = await axios.get(`/v1/historical/exchange-transactions/${selectedTransaction.id}/servers`);
                setServerDetails(response.data.servers || []);
                setAggregatedMetrics(response.data.aggregated_metrics || []);
              } catch (error) {
                console.error('Error fetching server details:', error);
                setError('Failed to load server details');
                setServerDetails([]);
                setAggregatedMetrics([]);
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
          onClick={async () => {
            if (selectedTransaction) {
              setLoadingDetails(true);
              setJsonModalOpen(true);
              try {
                // CRITICAL FIX: Display the COMPLETE V1.3 JSON payload as stored in the database
                // This ensures root-level locationId, timestamp, memberId, and sequenceId are visible
                const metricsSent = selectedTransaction.metrics_sent || {};
                const lamaPayload = metricsSent.lama_v1_2_payload;
                
                if (lamaPayload) {
                  // If we have the specific V1.2/V1.3 payload object, show it directly
                  setSelectedJsonData(lamaPayload);
                } else {
                  // Fallback: If structure is different, show metrics_sent as is
                  setSelectedJsonData(metricsSent);
                }
              } catch (error) {
                console.error('Error preparing JSON data:', error);
                setSelectedJsonData(selectedTransaction.metrics_sent || { error: 'No payload available' });
              } finally {
                setLoadingDetails(false);
                setMenuAnchor(null);
              }
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
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">
              {selectedTransaction && (() => {
                // Use backend-extracted exchange_id first, fallback to JSON
                const exchangeId = selectedTransaction.exchange_id || selectedTransaction.metrics_sent?.lama_v1_2_payload?.exchangeId;
                const exchangeName = {1: "NSE", 2: "BSE", 3: "MSE", 4: "MCX", 5: "NCDEX"}[exchangeId] || `Exchange ${exchangeId}`;
                const metricType = selectedTransaction.metric_type || 'system';
                // Format timestamp to match vendor: "30-11-2025 13:52"
                const timestamp = formatDateTime(selectedTransaction.sent_at);
                // Vendor format: "BSE - System - 30-11-2025 13:52"
                return `${exchangeName} - ${metricType.charAt(0).toUpperCase() + metricType.slice(1)} - ${timestamp.replace(', ', ' ')}`;
              })()}
            </Typography>
            {/* Metric Type Filter */}
            <FormControl size="small" sx={{ minWidth: 150 }}>
              <Select
                value={detailsMetricTypeFilter}
                onChange={(e) => setDetailsMetricTypeFilter(e.target.value)}
              >
                <MenuItem value="All">All</MenuItem>
                <MenuItem value="Hardware">Hardware</MenuItem>
                <MenuItem value="Network">Network</MenuItem>
                <MenuItem value="Application">Application</MenuItem>
                <MenuItem value="Database">Database</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </DialogTitle>
        <DialogContent>
          {loadingDetails ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              {/* Aggregated Metrics Section */}
              {aggregatedMetrics && aggregatedMetrics.length > 0 && (
                <Paper variant="outlined" sx={{ p: 2, mb: 3, bgcolor: '#f8f9fa' }}>
                  <Typography variant="subtitle1" fontWeight="bold" gutterBottom color="primary">
                    Aggregated Metrics Sent (Global Values)
                  </Typography>
                  <Grid container spacing={2}>
                    {aggregatedMetrics.map((metric, idx) => (
                      <Grid item xs={12} sm={6} md={4} key={idx}>
                        <Box>
                          <Typography variant="body2" fontWeight="bold">
                            {metric.name}
                          </Typography>
                          <Typography variant="body2" fontFamily="monospace">
                            {metric.type === 'statistical' 
                              ? `min: ${metric.min}, max: ${metric.max}, avg: ${metric.avg}, med: ${metric.med}`
                              : `Value: ${metric.value}`
                            }
                          </Typography>
                        </Box>
                      </Grid>
                    ))}
                  </Grid>
                </Paper>
              )}

              {/* Resource Breakdown Table */}
              <Typography variant="subtitle1" fontWeight="bold" gutterBottom sx={{ mt: 2 }}>
                Resource Breakdown (Individual Server Details)
              </Typography>
              
              {serverDetails.length === 0 ? (
                <Typography>No server details found</Typography>
              ) : (
                <TableContainer>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 'bold' }}>Time</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>Server / Source</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>Details</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>Badge</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {serverDetails.map((server, serverIdx) => {
                    // Format details to match vendor format EXACTLY
                    // Vendor format: "ApplicationId: 4 - cpu - min: 0,max: 0,avg: 0,med: 0, memory - min: 6.05,max: 6.06,avg: 6.06,med: 6.06, ..."
                    let detailsText = '';
                    
                    if (server.metrics && server.metrics.length > 0) {
                      // Get applicationId from server metrics or transaction
                      const appId = selectedTransaction?.metrics_sent?.lama_v1_2_payload?.payload?.[0]?.applicationId || 
                                   server.metrics[0]?.applicationId || '1';
                      
                      // Filter metrics by metric type if filter is set
                      let filteredMetrics = server.metrics;
                      if (detailsMetricTypeFilter !== 'All') {
                        // Map metric type filter to metric names
                        const metricTypeMap = {
                          'Hardware': ['cpu', 'memory', 'disk', 'uptime'],
                          'Network': ['bandwidth', 'packetCount'],
                          'Application': ['throughput', 'latency', 'log'],
                          'Database': ['status', 'qsize']
                        };
                        const allowedNames = metricTypeMap[detailsMetricTypeFilter] || [];
                        filteredMetrics = server.metrics.filter(m => {
                          const metricName = (m.name || m.key || '').toLowerCase();
                          return allowedNames.some(name => metricName.includes(name));
                        });
                      }
                      
                      // Format: ApplicationId: X - metricName - min: X,max: Y,avg: Z,med: W, ...
                      const metricStrings = [];
                      filteredMetrics.forEach((metric) => {
                        const metricName = metric.name || metric.key || '';
                        if (metric.type === 'statistical' || (metric.min !== undefined || metric.max !== undefined)) {
                          // Format with min, max, avg, med
                          const minVal = metric.min !== undefined ? (typeof metric.min === 'number' ? metric.min : parseFloat(metric.min) || 0) : 0;
                          const maxVal = metric.max !== undefined ? (typeof metric.max === 'number' ? metric.max : parseFloat(metric.max) || 0) : 0;
                          const avgVal = metric.avg !== undefined ? (typeof metric.avg === 'number' ? metric.avg : parseFloat(metric.avg) || 0) : 0;
                          const medVal = metric.med !== undefined ? (typeof metric.med === 'number' ? metric.med : parseFloat(metric.med) || 0) : 0;
                          // Vendor format: "metricName - min: X,max: Y,avg: Z,med: W,"
                          metricStrings.push(`${metricName} - min: ${minVal},max: ${maxVal},avg: ${avgVal},med: ${medVal},`);
                        } else if (metric.value !== undefined) {
                          // Simple numeric value
                          metricStrings.push(`${metricName} - ${metric.value},`);
                        }
                      });
                      
                      // Vendor format: "ApplicationId: 4 - metric1 - min: 0,max: 0,avg: 0,med: 0, metric2 - min: 6.05,max: 6.06,avg: 6.06,med: 6.06, ..."
                      if (metricStrings.length > 0) {
                        detailsText = `ApplicationId: ${appId} - ${metricStrings.join(' ')}`;
                        // Remove trailing comma from last metric
                        detailsText = detailsText.replace(/,\s*$/, '');
                      } else {
                        detailsText = 'Data Not Found';
                      }
                    } else {
                      detailsText = server.details || 'Data Not Found';
                    }
                    
                    const isMax = (server.metrics || []).some(m => {
                      const globalAgg = aggregatedMetrics.find(am => am.name === m.name);
                      if (!globalAgg) return false;
                      if (m.name === 'uptime') return m.min === globalAgg.min;
                      return m.type === 'statistical' && m.max === globalAgg.max && globalAgg.max > 0;
                    });

                    const isWarn = (server.metrics || []).some(m => {
                      const val = m.type === 'statistical' ? m.max : m.value;
                      if (val === undefined || val === null) return false;
                      
                      const n = m.name.toLowerCase();
                      if (n.includes('cpu')) return val > 80;
                      if (n.includes('memory')) return val > 85;
                      if (n.includes('disk')) return val > 90;
                      if (n.includes('qsize')) return val > 30; // DB replication lag
                      if (n.includes('status')) return val === 0; // DB down
                      if (n.includes('bandwidth')) return val > 90;
                      if (n.includes('errorrate')) return val > 5;
                      if (n.includes('latency')) {
                        // Application latency > 500ms, Network > 100ms
                        const limit = (selectedTransaction?.metric_type === 'application') ? 500 : 100;
                        return val > limit;
                      }
                      return false;
                    });

                    return (
                      <TableRow 
                        key={serverIdx} 
                        hover
                        sx={{
                          backgroundColor: isMax ? 'rgba(211, 47, 47, 0.04)' : (isWarn ? 'rgba(255, 152, 0, 0.04)' : 'inherit')
                        }}
                      >
                        <TableCell>
                          {/* Format time to match vendor: "30-11-2025 13:50" */}
                          {formatDateTime(server.time || selectedTransaction?.sent_at).replace(', ', ' ')}
                        </TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                            <Typography variant="body2" fontWeight="bold">
                                {server.server_name || server.name || 'Unknown Source'}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                                {server.ip || 'N/A'}
                            </Typography>
                          </Box>
                        </TableCell>
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
                            {/* Format details to match vendor format EXACTLY with Highlighting */}
                            {(() => {
                              const appId = selectedTransaction?.metrics_sent?.lama_v1_2_payload?.payload?.[0]?.applicationId || 
                                           server.metrics?.[0]?.applicationId || '1';
                              
                              let filteredMetrics = server.metrics || [];
                              if (detailsMetricTypeFilter !== 'All') {
                                const metricTypeMap = {
                                  'Hardware': ['cpu', 'memory', 'disk', 'uptime'],
                                  'Network': ['bandwidth', 'packetCount'],
                                  'Application': ['throughput', 'latency'],
                                  'Database': ['status', 'qsize']
                                };
                                const allowedNames = metricTypeMap[detailsMetricTypeFilter] || [];
                                filteredMetrics = filteredMetrics.filter(m => {
                                  const metricName = (m.name || m.key || '').toLowerCase();
                                  return allowedNames.some(name => metricName.includes(name));
                                });
                              }

                              return (
                                <Box>
                                  <span style={{ fontWeight: 'bold' }}>ApplicationId: {appId} - </span>
                                  {filteredMetrics.map((m, midx) => {
                                    const globalAgg = aggregatedMetrics.find(am => am.name === m.name);
                                    let isThisMetricMax = false;
                                    
                                    if (globalAgg) {
                                        if (m.name === 'uptime') {
                                            isThisMetricMax = m.min === globalAgg.min;
                                        } else {
                                            isThisMetricMax = m.type === 'statistical' && m.max === globalAgg.max && globalAgg.max > 0;
                                        }
                                    }

                                    const compSuffix = m.component_name ? ` (${m.component_name})` : '';
                                    
                                    return (
                                      <span key={midx} style={{ color: isThisMetricMax ? '#d32f2f' : '#333', fontWeight: isThisMetricMax ? 'bold' : 'normal' }}>
                                        {m.name}{compSuffix} - {m.type === 'statistical' 
                                          ? `min: ${m.min},max: ${m.max},avg: ${m.avg},med: ${m.med}` 
                                          : m.value
                                        }{midx < filteredMetrics.length - 1 ? ', ' : ''}
                                        {isThisMetricMax && ' ⚠️'}
                                      </span>
                                    );
                                  })}
                                </Box>
                              );
                            })()}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', gap: 0.5 }}>
                            {isMax && (
                              <Tooltip title="Contributing to Global Maximum (Worst Case Source)">
                                <Chip label="MAX" size="small" color="error" sx={{ height: 20, fontSize: '0.65rem', fontWeight: 'bold' }} />
                              </Tooltip>
                            )}
                            {isWarn && (
                              <Tooltip title="Metric exceeding threshold">
                                <Chip label="WARN" size="small" color="warning" sx={{ height: 20, fontSize: '0.65rem', fontWeight: 'bold' }} />
                              </Tooltip>
                            )}
                          </Box>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
                                </Table>
                              </TableContainer>
                            )}
                          </>
                        )}
                      </DialogContent>        <DialogActions>
          <Button onClick={() => setDetailsModalOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
      
      {/* JSON Modal */}
      <Dialog
        open={jsonModalOpen}
        onClose={() => setJsonModalOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          {selectedTransaction && (() => {
            const exchangeId = selectedTransaction.exchange_id || selectedTransaction.metrics_sent?.lama_v1_2_payload?.exchangeId;
            const exchangeName = {1: "NSE", 2: "BSE", 3: "MSE", 4: "MCX", 5: "NCDEX"}[exchangeId] || `Exchange ${exchangeId}`;
            const metricType = selectedTransaction.metric_type || 'system';
            // Format timestamp to match vendor: "30-11-2025 13:52"
            const timestamp = formatDateTime(selectedTransaction.sent_at);
            // Vendor format: "JSON - BSE - System"
            return `JSON - ${exchangeName} - ${metricType.charAt(0).toUpperCase() + metricType.slice(1)}`;
          })()}
        </DialogTitle>
        <DialogContent>
          {loadingDetails ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <Box
              sx={{
                fontFamily: 'monospace',
                fontSize: '0.75rem',
                backgroundColor: '#1e1e1e',
                color: '#d4d4d4',
                p: 2,
                borderRadius: 1,
                maxHeight: 600,
                overflow: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word'
              }}
            >
              {selectedJsonData ? JSON.stringify(selectedJsonData, null, 2) : 'No data available'}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setJsonModalOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
      </Container>
    </LocalizationProvider>
  );
};

export default HistoricalData;

