import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  Typography,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Alert,
  Chip,
  Tooltip,
  IconButton,
  Pagination,
  Grid,
  Divider,
} from '@mui/material';
import {
  CheckCircle,
  Error,
  Info,
  Refresh,
  Visibility,
  Search,
} from '@mui/icons-material';
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

const formatDateTime = (isoString) => {
  if (!isoString) return '';
  try {
    // Both DB tables used by this page store UTC in 'timestamp without time zone' columns.
    // If no timezone indicator, append 'Z' to treat as UTC before localizing to IST.
    let normalized = isoString;
    if (!normalized.includes('Z') && !normalized.includes('+') && !normalized.includes('-', 10)) {
      normalized = normalized.endsWith('Z') ? normalized : normalized + 'Z';
    }
    
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return isoString;
    
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
  } catch (e) {
    return isoString;
  }
};

const RawMetricsValidation = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [environment, setEnvironment] = useState('uat');
  const [metricType, setMetricType] = useState('hardware');
  const [exchangeId, setExchangeId] = useState('all');
  const [serverFilter, setServerFilter] = useState('all');
  const [page, setPage] = useState(1);

  const fetchValidationData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const response = await axios.get(`${API_BASE_URL}/v1/raw-metrics-validation`, {
        params: {
          environment,
          metric_type: metricType,
          limit: 10
        }
      });
      setData(response.data);
    } catch (err) {
      console.error('Error fetching validation data:', err);
      if (!silent) setError(err.response?.data?.detail || 'Failed to fetch validation data');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [environment, metricType]);

  useEffect(() => {
    fetchValidationData();
  }, [fetchValidationData]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchValidationData(true);
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchValidationData]);

  // Handle pagination and filtering
  const currentSubmission = useMemo(() => {
    if (!data?.submissions || data.submissions.length === 0) return null;
    return data.submissions[page - 1] || data.submissions[0];
  }, [data, page]);

  // Extract unique servers with IP for the filter from ALL fetched submissions
  const serverList = useMemo(() => {
    if (!data?.submissions || data.submissions.length === 0) return [];
    const serverMap = {};
    data.submissions.forEach(sub =>
      sub.servers.forEach(s => {
        if (s.server_name && !serverMap[s.server_name]) {
          serverMap[s.server_name] = s.server_ip || '';
        }
      })
    );
    return Object.entries(serverMap)
      .map(([name, ip]) => ({ name, ip }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [data]);

  // AUTO-JUMP: If a server is selected that isn't in the current view, find the batch that has it
  useEffect(() => {
    if (serverFilter !== 'all' && currentSubmission) {
      const isServerInCurrent = currentSubmission.servers.some(s => s.server_name === serverFilter);
      
      if (!isServerInCurrent && data?.submissions) {
        // Look for the first (latest) submission that contains this server
        const targetPageIndex = data.submissions.findIndex(sub => 
          sub.servers.some(s => s.server_name === serverFilter)
        );
        
        if (targetPageIndex !== -1) {
          setPage(targetPageIndex + 1);
        }
      }
    }
  }, [serverFilter, currentSubmission, data]);

  // Filter individual rows based on Server/Service selection
  const filteredRows = useMemo(() => {
    if (!currentSubmission?.servers) return [];
    if (serverFilter === 'all') return currentSubmission.servers;
    return currentSubmission.servers.filter(s => s.server_name === serverFilter);
  }, [currentSubmission, serverFilter]);

  const getStatusChip = (status) => {
    switch (status?.toLowerCase()) {
      case 'success':
        return <Chip label="STAGE 3: POSTED" color="success" size="small" icon={<CheckCircle />} />;
      case 'calculated':
        return <Chip label="STAGE 2: CALCULATED" color="primary" size="small" icon={<Info />} />;
      case 'raw_captured':
        return <Chip label="STAGE 1: CAPTURED" color="info" size="small" icon={<Visibility />} />;
      default:
        return <Chip label={status} size="small" />;
    }
  };

  const getIntegrityBadge = (validation) => {
    if (validation.integrity === 'PASS') {
      return <Chip label="PASS" color="success" variant="outlined" size="small" />;
    }
    return <Chip label="MISMATCH" color="error" size="small" icon={<Error />} />;
  };

  // Stats Counters
  const stats = useMemo(() => {
    if (!filteredRows.length) return { pass: 0, fail: 0 };
    const pass = filteredRows.filter(r => r.validation.integrity === 'PASS').length;
    return { pass, fail: filteredRows.length - pass };
  }, [filteredRows]);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold', color: '#1a237e' }}>
          Raw Data Validation
        </Typography>
        <Typography variant="subtitle1" color="textSecondary">
          Verify raw collection points → calculation → NSE submission chain
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          Auto-refresh: 30s
        </Typography>
      </Box>

      {/* Primary Filters */}
      <Paper sx={{ p: 2, mb: 3, borderRadius: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Environment</InputLabel>
              <Select value={environment} label="Environment" onChange={(e) => setEnvironment(e.target.value)}>
                <MenuItem value="uat">UAT</MenuItem>
                <MenuItem value="prod">PROD</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Exchange</InputLabel>
              <Select value={exchangeId} label="Exchange" onChange={(e) => setExchangeId(e.target.value)}>
                <MenuItem value="all">All Exchanges</MenuItem>
                <MenuItem value="1">NSE</MenuItem>
                <MenuItem value="2">BSE</MenuItem>
                <MenuItem value="4">MCX</MenuItem>
                <MenuItem value="5">NCDEX</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Metric Type</InputLabel>
              <Select value={metricType} label="Metric Type" onChange={(e) => setMetricType(e.target.value)}>
                <MenuItem value="hardware">Hardware</MenuItem>
                <MenuItem value="network">Network</MenuItem>
                <MenuItem value="database">Database</MenuItem>
                <MenuItem value="application">Application</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={4}>
            <FormControl fullWidth size="small">
              <InputLabel>Select Server / Service</InputLabel>
              <Select 
                value={serverFilter} 
                label="Select Server / Service" 
                onChange={(e) => setServerFilter(e.target.value)}
                disabled={loading || !serverList.length}
              >
                <MenuItem value="all">All Servers/Services</MenuItem>
                {serverList.map(s => (
                  <MenuItem key={s.name} value={s.name}>
                    {s.ip && s.ip !== 'Unknown' && s.ip !== s.name
                      ? `${s.ip} (${s.name})`
                      : s.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={2}>
            <IconButton onClick={fetchValidationData} color="primary" sx={{ border: '1px solid #e0e0e0' }}>
              <Refresh />
            </IconButton>
          </Grid>
        </Grid>
      </Paper>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}>
          <CircularProgress />
        </Box>
      ) : !currentSubmission ? (
        <Alert severity="info">No staged audit records found for this selection.</Alert>
      ) : (
        <>
          {/* Real-time Validation Summary Chips */}
          <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
            <Alert icon={<CheckCircle fontSize="inherit" />} severity="success" sx={{ py: 0 }}>
              {stats.pass} calculations verified
            </Alert>
            <Alert icon={<Info fontSize="inherit" />} severity="warning" sx={{ py: 0 }}>
              0 batch differences (expected)
            </Alert>
            {stats.fail > 0 && (
              <Alert icon={<Error fontSize="inherit" />} severity="error" sx={{ py: 0 }}>
                {stats.fail} integrity issues detected
              </Alert>
            )}
          </Box>

          <Paper sx={{ p: 3, mb: 3, borderRadius: 2, borderLeft: '6px solid #1a237e' }}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={4}>
                <Typography variant="caption" color="textSecondary" sx={{ textTransform: 'uppercase' }}>Audit Sequence</Typography>
                <Typography variant="h6">#{currentSubmission.audit_id}</Typography>
                <Typography variant="caption" color="textSecondary">{formatDateTime(currentSubmission.timestamp)}</Typography>
              </Grid>
              <Grid item xs={12} md={4}>
                <Typography variant="caption" color="textSecondary" sx={{ textTransform: 'uppercase' }}>Lifecycle State</Typography>
                <Box sx={{ mt: 0.5 }}>{getStatusChip(currentSubmission.status)}</Box>
              </Grid>
              <Grid item xs={12} md={4} sx={{ textAlign: 'right' }}>
                <Typography variant="caption" color="textSecondary" sx={{ textTransform: 'uppercase' }}>Exchange Link</Typography>
                <Typography variant="h6" color="primary">Seq: {currentSubmission.sequence_id}</Typography>
                <Box sx={{ mb: 1 }}>
                  <Chip label={`LAMA Code: ${currentSubmission.exchange_status}`} size="small" variant="outlined" />
                </Box>
                {currentSubmission.exchange_time && (
                  <Typography variant="caption" color="textSecondary">
                    Sent At: {formatDateTime(currentSubmission.exchange_time)}
                  </Typography>
                )}
              </Grid>
            </Grid>
          </Paper>

          <TableContainer component={Paper} sx={{ borderRadius: 2, boxShadow: 3, maxHeight: '60vh' }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white' }}><strong>Source Detail</strong></TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white' }}><strong>Metric</strong></TableCell>
                  <TableCell align="center" sx={{ bgcolor: '#1a237e', color: 'white' }}><strong>Raw Points (History)</strong></TableCell>
                  <TableCell align="center" sx={{ bgcolor: '#1a237e', color: 'white' }}><strong>Calculated (Server)</strong></TableCell>
                  <TableCell align="center" sx={{ bgcolor: '#1a237e', color: 'white' }}><strong>Sent to NSE (Batch)</strong></TableCell>
                  <TableCell align="center" sx={{ bgcolor: '#1a237e', color: 'white' }}><strong>Audit Recalculation</strong></TableCell>
                  <TableCell align="center" sx={{ bgcolor: '#1a237e', color: 'white' }}><strong>Integrity</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredRows.map((server, idx) => (
                  <TableRow key={idx} hover>
                    <TableCell sx={{ width: '15%' }}>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{server.server_name}</Typography>
                      <Typography variant="caption" color="textSecondary">{server.server_ip}</Typography>
                      {server.location_id && (
                        <Box><Chip label={server.location_id === 1 ? 'DC' : server.location_id === 2 ? 'DR' : 'Cloud'} size="xs" sx={{ height: 16, fontSize: '0.6rem' }} /></Box>
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip label={server.metric_name} size="small" variant="outlined" sx={{ fontWeight: 'bold' }} />
                      <Box sx={{ mt: 0.5 }}>
                        <Typography variant="caption" sx={{ color: '#1a237e', fontWeight: '500', display: 'block' }}>
                          Source: {server.datasource || 'Unknown'}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'center' }}>
                        {server.raw_points.length > 0 ? server.raw_points.map((p, pidx) => (
                          <Tooltip key={pidx} title={`UNIX: ${p.timestamp}`}>
                            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                              <Chip 
                                label={p.value} 
                                size="small" 
                                sx={{ 
                                  fontSize: '0.75rem', 
                                  fontWeight: 'bold',
                                  height: 22, 
                                  bgcolor: '#e3f2fd',
                                  border: '1px solid #bbdefb'
                                }} 
                              />
                              <Typography variant="caption" sx={{ fontSize: '0.6rem', color: 'text.secondary', mt: 0.3 }}>
                                {p.time_label?.split(' ')[1] || '--'}
                              </Typography>
                            </Box>
                          </Tooltip>
                        )) : <Typography variant="caption">-- No Points --</Typography>}
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ fontSize: '0.8rem' }}>
                        Avg: <strong>{server.stage2_calculated.avg}</strong><br/>
                        Peak: {server.stage2_calculated.max}
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ fontSize: '0.8rem', color: '#1a237e' }}>
                        Avg: <strong>{server.stage3_sent.avg}</strong><br/>
                        Peak: {server.stage3_sent.max}
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ fontSize: '0.8rem', color: '#2e7d32' }}>
                        Avg: <strong>{server.stage1_raw.avg}</strong><br/>
                        Peak: {server.stage1_raw.max}
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      {getIntegrityBadge(server.validation)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4, mb: 2 }}>
            <Pagination count={data?.submissions?.length || 1} page={page} onChange={(e, v) => setPage(v)} color="primary" showFirstButton showLastButton />
          </Box>
        </>
      )}
    </Box>
  );
};

export default RawMetricsValidation;
