import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableContainer,
  TablePagination,
  CircularProgress,
  Container,
  Chip,
  Alert,
  Grid,
  Card,
  CardContent,
  TextField,
  Tooltip,
  IconButton,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
  Stack,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  Schedule as ScheduleIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Close as CloseIcon,
  TrendingUp as TrendingUpIcon,
  Delete as DeleteIcon,
  SwapHoriz as SwapHorizIcon,
} from '@mui/icons-material';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  AreaChart,
  Area,
} from 'recharts';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';

export default function ApplicationMonitoring() {
  const { environment, withEnvironment } = useEnvironment();
  const [loading, setLoading] = useState(true);
  const [liveServers, setLiveServers] = useState([]);
  const [error, setError] = useState('');
  const [lastRefresh, setLastRefresh] = useState(new Date());

  // Pagination state for Live Status
  const [livePage, setLivePage] = useState(0);
  const [liveRowsPerPage, setLiveRowsPerPage] = useState(100);
  const [liveTotalCount, setLiveTotalCount] = useState(0);

  // Detail Modal State
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [selectedServer, setSelectedServer] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [latencyData, setLatencyData] = useState([]);
  const [throughputData, setThroughputData] = useState([]);

  const handleOpenDetail = async (server) => {
    setSelectedServer(server);
    setDetailModalOpen(true);
    setDetailLoading(true);
    try {
      
      const params = {
        server_id: server.id,
        limit: 100,
        // Fetch last 1 hour of history
        start_date: new Date(Date.now() - 3600000).toISOString().split('T')[0]
      };
      
      const [latencyRes, throughputRes] = await Promise.all([
        axios.get('/v1/historical/server-metrics', {
          params: { ...params, metric_name: 'app_latency' },
          
        }),
        axios.get('/v1/historical/server-metrics', {
          params: { ...params, metric_name: 'app_throughput' },
          
        })
      ]);

      const processData = (res) => {
        const data = Array.isArray(res.data) ? res.data : (res.data?.metrics || []);
        return data.map(m => {
          const ts = m.ts || m.timestamp;
          const date = ts ? new Date(ts) : null;
          return {
            time: date && !isNaN(date) ? date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '-',
            value: parseFloat(m.value) || 0
          };
        }).filter(m => m.time !== '-').reverse();
      };

      setLatencyData(processData(latencyRes));
      setThroughputData(processData(throughputRes));
    } catch (err) {
      console.error('Error fetching detail metrics:', err);
    } finally {
      setDetailLoading(false);
    }
  };

  const fetchLiveMetrics = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const params = { 
        ...withEnvironment(),
        page: livePage + 1,
        size: liveRowsPerPage
      };
      
      const response = await axios.get('/v1/dashboard/application-monitoring', {
        params,
      });

      if (response.data && response.data.items) {
        setLiveServers(response.data.items);
        setLiveTotalCount(response.data.total_count || 0);
      }
      setLastRefresh(new Date());
    } catch (err) {
      console.error('Error fetching live application metrics:', err);
      setError('Failed to fetch live application metrics');
    } finally {
      setLoading(false);
    }
  }, [environment, withEnvironment, livePage, liveRowsPerPage]);

  const handleDelete = async (e, id) => {
    e.stopPropagation(); // Prevent opening the detail modal
    if (!window.confirm("Are you sure you want to permanently delete this application source? It will be removed from all monitoring and the LAMA Exchange.")) return;

    try {
      setLoading(true);
      await axios.delete(`/v1/dashboard/application-monitoring/${id}`);
      await fetchLiveMetrics();
    } catch (err) {
      console.error('Error deleting application:', err);
      setError(err.response?.data?.detail || 'Failed to delete application source');
    } finally {
      setLoading(false);
    }
  };

  const handleMoveEnv = async (e, id, name) => {
    e.stopPropagation();
    const target = environment === 'uat' ? 'prod' : 'uat';
    if (!window.confirm(`Move "${name}" to ${target.toUpperCase()}?`)) return;
    try {
      await axios.put(`/v1/dashboard/application-monitoring/${id}/move`, { environment: target });
      await fetchLiveMetrics();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to move application');
    }
  };

  useEffect(() => {
    fetchLiveMetrics();
    
    // Auto-refresh live data every 30 seconds
    const liveInterval = setInterval(fetchLiveMetrics, 30000);

    return () => {
      clearInterval(liveInterval);
    };
  }, [fetchLiveMetrics]);

  const handleChangeLivePage = (event, newPage) => {
    setLivePage(newPage);
  };

  const handleChangeLiveRowsPerPage = (event) => {
    setLiveRowsPerPage(parseInt(event.target.value, 10));
    setLivePage(0);
  };

  useEffect(() => {
    setLivePage(0);
  }, [environment]);

  const formatValue = (value, metricKey) => {
    if (value === null || value === undefined) return '-';
    const num = parseFloat(value);
    if (isNaN(num)) return '-';
    if (metricKey && (metricKey.toLowerCase().includes('failure') || metricKey === 'log')) {
      return num.toFixed(0);
    }
    return num.toFixed(2);
  };

  const formatDateTime = (dateStr) => {
    if (!dateStr) return '-';
    // Ensure the timestamp is treated as UTC if it doesn't have timezone info
    let normalizedDateStr = dateStr;
    if (!normalizedDateStr.includes('Z') && !normalizedDateStr.includes('+') && !normalizedDateStr.includes('-', 10)) {
      normalizedDateStr += 'Z';
    }
    const date = new Date(normalizedDateStr);
    return date.toLocaleString('en-IN', { 
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      {/* Header */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
          Application Monitoring
        </Typography>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          {/* Refresh Button */}
          <Tooltip title="Refresh now">
            <IconButton onClick={fetchLiveMetrics} color="primary">
              <RefreshIcon />
            </IconButton>
          </Tooltip>
          
          {/* Auto-sync indicator */}
          <Chip
            icon={<ScheduleIcon />}
            label="Auto-refresh every 30s"
            color="success"
            variant="outlined"
            size="small"
          />
        </Box>
      </Box>

      {/* Last refresh time */}
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
        Last refreshed: {lastRefresh.toLocaleTimeString('en-IN', { 
          timeZone: 'Asia/Kolkata',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: true
        })} IST
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '400px' }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          <Paper sx={{ mb: 4, boxShadow: 2 }}>
            <Box sx={{ p: 2, bgcolor: '#e3f2fd', borderBottom: '1px solid #90caf9', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="h6" sx={{ fontWeight: 600, color: '#0d47a1' }}>
                Live Application Health
              </Typography>
              <Chip 
                label="REAL-TIME" 
                color="success" 
                size="small" 
                icon={<CheckCircleIcon />} 
                sx={{ fontWeight: 'bold' }}
              />
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead sx={{ bgcolor: '#fafafa' }}>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 'bold' }}>Server Name</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>IP Address</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'center' }}>Status</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'right' }}>Latency (μs)</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'right' }}>Throughput (req/s)</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'right' }}>Auth Failures</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'right' }}>API Failures</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'center' }}>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {liveServers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} align="center" sx={{ py: 3 }}>
                        No application metrics configured for {environment.toUpperCase()}. 
                        Add {environment.toUpperCase()} exchange config to activate.
                      </TableCell>
                    </TableRow>
                  ) : (
                    liveServers.map((server) => (
                      <TableRow 
                        key={server.id} 
                        hover 
                        sx={{ cursor: 'pointer' }}
                        onClick={() => handleOpenDetail(server)}
                      >
                        <TableCell sx={{ fontWeight: 500, color: '#1976d2' }}>{server.name}</TableCell>
                        <TableCell>{server.ip}</TableCell>
                        <TableCell sx={{ textAlign: 'center' }}>
                          <Chip 
                            label={server.is_inactive ? "Offline" : "Online"} 
                            color={server.is_inactive ? "error" : "success"} 
                            size="small" 
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell sx={{ textAlign: 'right' }}>{formatValue(server.latency)}</TableCell>
                        <TableCell sx={{ textAlign: 'right' }}>{formatValue(server.throughput)}</TableCell>
                        <TableCell sx={{ textAlign: 'right', color: server.failure_auth > 0 ? 'error.main' : 'inherit' }}>
                          {formatValue(server.failure_auth)}
                        </TableCell>
                        <TableCell sx={{ textAlign: 'right', color: server.failure_trade > 0 ? 'error.main' : 'inherit' }}>
                          {formatValue(server.failure_trade)}
                        </TableCell>
                        <TableCell sx={{ textAlign: 'center' }}>
                          {sessionStorage.getItem('lama_user_role') === 'admin' && (
                            <>
                              <Tooltip title={`Move to ${environment === 'uat' ? 'PROD' : 'UAT'}`}>
                                <IconButton size="small" onClick={(e) => handleMoveEnv(e, server.id, server.name)} color="secondary">
                                  <SwapHorizIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                              <IconButton size="small" onClick={(e) => handleDelete(e, server.id)} color="error">
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              rowsPerPageOptions={[10, 25, 50, 100, 200]}
              component="div"
              count={liveTotalCount}
              rowsPerPage={liveRowsPerPage}
              page={livePage}
              onPageChange={handleChangeLivePage}
              onRowsPerPageChange={handleChangeLiveRowsPerPage}
            />
          </Paper>
        </>
      )}

      {/* Metric Detail Dialog */}
      <Dialog 
        open={detailModalOpen} 
        onClose={() => setDetailModalOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: '#f5f5f5' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TrendingUpIcon color="primary" />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Performance Metrics: {selectedServer?.name}
            </Typography>
          </Box>
          <IconButton onClick={() => setDetailModalOpen(false)} size="small">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent sx={{ mt: 2 }}>
          {detailLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
              <CircularProgress />
            </Box>
          ) : (
            <Stack spacing={4}>
              {/* Stats Row */}
              <Grid container spacing={2}>
                <Grid item xs={12} sm={3}>
                  <Paper variant="outlined" sx={{ p: 2, textAlign: 'center' }}>
                    <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>Current Latency</Typography>
                    <Typography variant="h5" color="primary">{formatValue(selectedServer?.latency)} <small style={{ fontSize: '0.8rem' }}>μs</small></Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Paper variant="outlined" sx={{ p: 2, textAlign: 'center' }}>
                    <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>Current Throughput</Typography>
                    <Typography variant="h5" color="secondary">{formatValue(selectedServer?.throughput)} <small style={{ fontSize: '0.8rem' }}>req/s</small></Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Paper variant="outlined" sx={{ p: 2, textAlign: 'center' }}>
                    <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>Auth Failures</Typography>
                    <Typography variant="h5" sx={{ color: (selectedServer?.failure_auth > 0 ? '#f44336' : '#4caf50') }}>{formatValue(selectedServer?.failure_auth)}</Typography>
                  </Paper>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Paper variant="outlined" sx={{ p: 2, textAlign: 'center' }}>
                    <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>API Failures</Typography>
                    <Typography variant="h5" sx={{ color: (selectedServer?.failure_trade > 0 ? '#f44336' : '#4caf50') }}>{formatValue(selectedServer?.failure_trade)}</Typography>
                  </Paper>
                </Grid>
              </Grid>

              <Divider />

              {/* Latency Chart */}
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  Latency (μs) Over Last Hour
                </Typography>
                <Box sx={{ height: 300, width: '100%' }}>
                  {latencyData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={latencyData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="time" />
                        <YAxis />
                        <RechartsTooltip />
                        <Area type="monotone" dataKey="value" stroke="#FF9800" fill="#FFF3E0" />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'text.secondary' }}>
                      No latency data available for this service
                    </Box>
                  )}
                </Box>
              </Box>

              <Divider />

              {/* Throughput Chart */}
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                  Throughput (req/s) Over Last Hour
                </Typography>
                <Box sx={{ height: 300, width: '100%' }}>
                  {throughputData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={throughputData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="time" />
                        <YAxis />
                        <RechartsTooltip />
                        <Line type="monotone" dataKey="value" stroke="#2196F3" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'text.secondary' }}>
                      No throughput data available for this service
                    </Box>
                  )}
                </Box>
              </Box>
            </Stack>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2, bgcolor: '#f5f5f5' }}>
          <Button onClick={() => setDetailModalOpen(false)} variant="contained" color="primary">
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
