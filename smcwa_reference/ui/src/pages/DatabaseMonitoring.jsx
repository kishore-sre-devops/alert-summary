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
  Tooltip,
  IconButton,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  Schedule as ScheduleIcon,
  CheckCircle as CheckCircleIcon,
  Storage as StorageIcon,
  Delete as DeleteIcon,
  SwapHoriz as SwapHorizIcon,
} from '@mui/icons-material';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';

export default function DatabaseMonitoring() {
  const { environment, withEnvironment } = useEnvironment();
  const [loading, setLoading] = useState(true);
  const [liveServers, setLiveServers] = useState([]);
  const [error, setError] = useState('');
  const [lastRefresh, setLastRefresh] = useState(new Date());
  
  // Pagination state for Live Servers
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(20);
  const [totalCount, setTotalCount] = useState(0);

  // Fetch Live Real-time Metrics
  const fetchLiveMetrics = useCallback(async () => {
    try {
      const params = { 
        ...withEnvironment(),
        page: page + 1,
        size: rowsPerPage
      };
      
      const response = await axios.get('/v1/dashboard/database-monitoring', {
        params
      });

      if (response.data && response.data.items) {
        setLiveServers(response.data.items);
        setTotalCount(response.data.total_count || 0);
      }
      setLastRefresh(new Date());
      setError('');
    } catch (err) {
      console.error('Error fetching live database metrics:', err);
      // Only set error if it's NOT a 401 (401 is handled by axios interceptor redirect)
      if (err.response?.status !== 401) {
        setError(err.response?.data?.detail || 'Failed to fetch live database metrics');
      }
    }
  }, [environment, withEnvironment, page, rowsPerPage]);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    await fetchLiveMetrics();
    setLoading(false);
  }, [fetchLiveMetrics]);

  useEffect(() => {
    refreshAll();
    // Auto-refresh live data every 30 seconds (Real-time)
    const liveInterval = setInterval(fetchLiveMetrics, 30000);
    return () => clearInterval(liveInterval);
  }, [refreshAll, fetchLiveMetrics]);

  useEffect(() => {
    setPage(0);
  }, [environment]);

  const formatValue = (value) => {
    if (value === null || value === undefined) return '-';
    const num = parseFloat(value);
    if (isNaN(num)) return '-';
    return num.toFixed(2);
  };

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to permanently delete this database source? It will be removed from all monitoring and the LAMA Exchange.")) return;

    try {
      setLoading(true);
      await axios.delete(`/v1/dashboard/database-monitoring/${id}`);
      await fetchLiveMetrics();
    } catch (err) {
      console.error('Error deleting database:', err);
      setError(err.response?.data?.detail || 'Failed to delete database source');
    } finally {
      setLoading(false);
    }
  };

  const handleMoveEnv = async (id, name) => {
    const target = environment === 'uat' ? 'prod' : 'uat';
    if (!window.confirm(`Move "${name}" to ${target.toUpperCase()}?`)) return;
    try {
      await axios.put(`/v1/dashboard/database-monitoring/${id}/move`, { environment: target });
      await fetchLiveMetrics();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to move database');
    }
  };

  // Topology View Component
  const renderTopologyView = () => {
    if (liveServers.length === 0) {
      return (
        <Paper sx={{ p: 4, mb: 3, textAlign: 'center', bgcolor: '#f8f9fa' }}>
          <Typography color="textSecondary">No database servers found or configuration not enabled.</Typography>
        </Paper>
      );
    }

    // Group servers by Cluster (Master + Slaves)
    const clusters = {};
    const orphans = [];
    const serverMap = {};
    
    liveServers.forEach(s => {
      serverMap[s.ip] = s;
      if (s.db_host) serverMap[s.db_host] = s;
      if (s.name) serverMap[s.name] = s;
    });

    liveServers.forEach(server => {
      if (server.db_role === 'master' || !server.master_host) {
        const clusterKey = server.db_host || server.ip;
        if (!clusters[clusterKey]) {
          clusters[clusterKey] = { master: server, slaves: [] };
        } else {
          clusters[clusterKey].master = server;
        }
      } else if (server.db_role === 'slave' && server.master_host) {
        const masterServer = serverMap[server.master_host];
        const masterKey = masterServer ? (masterServer.db_host || masterServer.ip) : server.master_host;
        
        if (!clusters[masterKey]) {
          clusters[masterKey] = { master: null, slaves: [] };
        }
        if (masterServer && !clusters[masterKey].master) {
          clusters[masterKey].master = masterServer;
        }
        clusters[masterKey].slaves.push(server);
      } else {
        orphans.push(server);
      }
    });

    // Handle "Ghost" masters
    Object.keys(clusters).forEach(masterIp => {
      if (!clusters[masterIp].master && clusters[masterIp].slaves.length > 0) {
        clusters[masterIp].master = {
          name: `External Master (${masterIp})`,
          ip: masterIp,
          is_ghost: true,
          replication_status: 'Unknown'
        };
      }
    });

    if (Object.keys(clusters).length === 0 && orphans.length === 0) return null;

    return (
      <Box sx={{ mb: 4 }}>
        <style>
          {`
            @keyframes flow {
              0% { background-position: 0% 50%; }
              100% { background-position: 100% 50%; }
            }
          `}
        </style>
        <Box sx={{ 
          p: 2, 
          bgcolor: '#e3f2fd', 
          borderBottom: '1px solid #90caf9', 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          mb: 2,
          borderRadius: 1
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <StorageIcon color="primary" />
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 600, color: '#0d47a1', lineHeight: 1.2 }}>
                Database Cluster Topology
              </Typography>
              <Typography variant="caption" color="textSecondary">
                Real-time Replication Flow & Status
              </Typography>
            </Box>
          </Box>
          <Chip 
            label="LIVE TOPOLOGY" 
            color="success" 
            size="small" 
            icon={<CheckCircleIcon />} 
            sx={{ fontWeight: 'bold' }}
          />
        </Box>

        {Object.values(clusters).map((cluster, idx) => cluster.master && (
          <Paper key={idx} sx={{ p: 3, mb: 3, bgcolor: '#fbfbfb', border: '1px solid #e0e0e0', position: 'relative' }}>
            <Grid container spacing={4} alignItems="center">
              <Grid item xs={12} md={4}>
                <Card elevation={3} sx={{ borderLeft: `5px solid ${cluster.master.is_inactive ? '#9e9e9e' : '#2196F3'}`, position: 'relative', overflow: 'visible' }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1, alignItems: 'center' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: cluster.master.is_inactive ? '#f44336' : '#4caf50' }} />
                        <Typography variant="subtitle2" color="primary" fontWeight="bold">MASTER</Typography>
                      </Box>
                      <Chip 
                        label={cluster.master.replication_status === 'Online' ? 'PRIMARY' : cluster.master.replication_status} 
                        color={cluster.master.replication_status === 'Online' ? 'primary' : 'error'} 
                        size="small" 
                        sx={{ fontWeight: 'bold', fontSize: '0.65rem' }}
                      />
                    </Box>
                    <Typography variant="h6" fontWeight="bold">{cluster.master.name}</Typography>
                    <Typography variant="body2" color="textSecondary">{cluster.master.ip}</Typography>
                  </CardContent>
                  {cluster.slaves.length > 0 && (
                    <Box sx={{ position: 'absolute', right: -6, top: '50%', width: 12, height: 12, bgcolor: cluster.master.is_inactive ? '#9e9e9e' : '#2196F3', borderRadius: '50%', transform: 'translateY(-50%)', zIndex: 2 }} />
                  )}
                </Card>
              </Grid>

              <Grid item xs={12} md={8}>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {cluster.slaves.map((slave, sIdx) => (
                    <Box key={sIdx} sx={{ display: 'flex', alignItems: 'center' }}>
                      <Box sx={{ 
                        width: '80px', 
                        height: '4px', 
                        bgcolor: slave.replication_status === 'Online' ? '#e8f5e9' : '#ffebee',
                        backgroundImage: slave.replication_status === 'Online' ? `linear-gradient(90deg, #c8e6c9 25%, #4caf50 50%, #c8e6c9 75%)` : 'none',
                        backgroundSize: '200% 100%',
                        animation: slave.replication_status === 'Online' ? `flow 3s linear infinite` : 'none',
                        mx: 2, display: { xs: 'none', md: 'block' }, position: 'relative'
                      }}>
                        <Box sx={{ position: 'absolute', top: -25, left: '50%', transform: 'translateX(-50%)', width: 'max-content' }}>
                          <Typography variant="caption" sx={{ fontWeight: 'bold', color: '#2e7d32' }}>{formatValue(slave.replication_latency)} μs</Typography>
                        </Box>
                      </Box>

                      <Card elevation={2} sx={{ flexGrow: 1, borderLeft: `5px solid ${slave.is_inactive ? '#9e9e9e' : '#9C27B0'}` }}>
                        <CardContent sx={{ py: 1.5 }}>
                          <Grid container alignItems="center">
                            <Grid item xs={12} sm={4}>
                              <Typography variant="subtitle2" color="secondary" fontWeight="bold">SLAVE</Typography>
                              <Typography variant="subtitle1" fontWeight="bold">{slave.name}</Typography>
                            </Grid>
                            <Grid item xs={6} sm={4} sx={{ textAlign: 'center' }}>
                              <Typography variant="caption" color="textSecondary" display="block">Queue Size</Typography>
                              <Typography variant="h6" color="primary">{formatValue(slave.replication_queue_size)}</Typography>
                            </Grid>
                            <Grid item xs={6} sm={4} sx={{ textAlign: 'right' }}>
                              <Chip label={slave.replication_status} color={slave.replication_status === 'Online' ? 'success' : 'error'} size="small" />
                            </Grid>
                          </Grid>
                        </CardContent>
                      </Card>
                    </Box>
                  ))}
                </Box>
              </Grid>
            </Grid>
          </Paper>
        ))}
      </Box>
    );
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold' }}>Database Monitoring</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Tooltip title="Refresh now">
            <IconButton onClick={refreshAll} color="primary"><RefreshIcon /></IconButton>
          </Tooltip>
          <Chip icon={<ScheduleIcon />} label="REAL-TIME" color="success" sx={{ fontWeight: 'bold' }} />
        </Box>
      </Box>

      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
        Last refreshed: {lastRefresh.toLocaleTimeString('en-IN', { hour12: false })} IST
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 10 }}><CircularProgress /></Box>
      ) : (
        <>
          {renderTopologyView()}
          
          <Paper sx={{ mb: 4, boxShadow: 2 }}>
            <Box sx={{ p: 2, bgcolor: '#f5f5f5', borderBottom: '1px solid #e0e0e0' }}>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>Database Servers Status</Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead sx={{ bgcolor: '#1a237e', '& th': { color: 'white', fontWeight: 700, py: 1.5 } }}>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 'bold' }}>Server Name</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>IP Address</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>Role</TableCell>
                    <TableCell sx={{ fontWeight: 'bold' }}>Status</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'center' }}>Queue Size</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'center' }}>Bandwidth (Mbps)</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'center' }}>Latency (ms)</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', textAlign: 'center' }}>Actions</TableCell>
                    </TableRow>
                    </TableHead>
                    <TableBody>
                      {liveServers.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={8} align="center" sx={{ py: 3 }}>
                            No database servers found or configuration not enabled.
                          </TableCell>
                        </TableRow>
                      ) : (
                        liveServers.map((server) => (

                      <TableRow key={server.id} hover>
                        <TableCell sx={{ fontWeight: 500, paddingLeft: server.db_role === 'slave' ? 4 : 2 }}>
                          {server.db_role === 'slave' && <Typography component="span" variant="body2" color="textSecondary" sx={{ mr: 1 }}>↳</Typography>}
                          {server.name}
                        </TableCell>
                        <TableCell>{server.ip}</TableCell>
                        <TableCell>
                          <Chip label={server.db_role?.toUpperCase() || 'N/A'} size="small" variant="outlined" color={server.db_role === 'master' ? 'primary' : 'secondary'} />
                        </TableCell>
                        <TableCell>
                          <Chip label={server.replication_status} color={server.replication_status === 'Online' ? 'success' : 'error'} size="small" />
                        </TableCell>
                        <TableCell sx={{ textAlign: 'center' }}>{formatValue(server.replication_queue_size)}</TableCell>
                        <TableCell sx={{ textAlign: 'center' }}>{formatValue(server.replication_bandwidth)}</TableCell>
                        <TableCell sx={{ textAlign: 'center' }}>{formatValue(server.replication_latency)}</TableCell>
                        <TableCell sx={{ textAlign: 'center' }}>
                          {sessionStorage.getItem('lama_user_role') === 'admin' && (
                            <>
                              <Tooltip title={`Move to ${environment === 'uat' ? 'PROD' : 'UAT'}`}>
                                <IconButton size="small" onClick={() => handleMoveEnv(server.id, server.name)} color="secondary">
                                  <SwapHorizIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                              <IconButton size="small" onClick={() => handleDelete(server.id)} color="error">
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
              rowsPerPageOptions={[10, 20, 50, 100]}
              component="div"
              count={totalCount}
              rowsPerPage={rowsPerPage}
              page={page}
              onPageChange={handleChangePage}
              onRowsPerPageChange={handleChangeRowsPerPage}
            />
          </Paper>
        </>
      )}
    </Container>
  );
}
