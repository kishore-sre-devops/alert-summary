import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  FormControl,
  Select,
  MenuItem,
  TextField,
  InputLabel,
  CircularProgress,
  Alert,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
} from '@mui/material';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceArea,
} from 'recharts';
import { Cloud as CloudIcon } from '@mui/icons-material';
import { useEnvironment } from '../hooks/useEnvironment';
import axios from '../utils/axiosConfig';

const AWSServerMonitoring = () => {
  const { environment, withEnvironment } = useEnvironment();
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState('24h');
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');
  const [metricsData, setMetricsData] = useState({});
  const [hardwareThresholds, setHardwareThresholds] = useState({});

  const fetchThresholds = async () => {
    try {
      
      const response = await axios.get('/v1/thresholds/hardware', {
        
      });
      const map = {};
      if (response.data && Array.isArray(response.data)) {
        response.data.forEach(t => {
          if (t.enabled) {
            map[t.metric_key] = {
              warning: t.warning_threshold,
              error: t.error_threshold
            };
          }
        });
      }
      setHardwareThresholds(map);
    } catch (err) {
      console.error('Error fetching thresholds:', err);
    }
  };

  useEffect(() => {
    fetchThresholds();
  }, []);

  // Zoom state
  const [left, setLeft] = useState('dataMin');
  const [right, setRight] = useState('dataMax');
  const [refAreaLeft, setRefAreaLeft] = useState('');
  const [refAreaRight, setRefAreaRight] = useState('');

  const zoom = () => {
    if (refAreaLeft === refAreaRight || refAreaRight === '') {
      setRefAreaLeft('');
      setRefAreaRight('');
      return;
    }

    // Ensure left is smaller than right for the domain
    let newLeft = refAreaLeft;
    let newRight = refAreaRight;
    if (refAreaLeft > refAreaRight) {
        newLeft = refAreaRight;
        newRight = refAreaLeft;
    }

    setLeft(newLeft);
    setRight(newRight);
    setRefAreaLeft('');
    setRefAreaRight('');
  };

  const zoomOut = () => {
    setLeft('dataMin');
    setRight('dataMax');
    setRefAreaLeft('');
    setRefAreaRight('');
  };

  // Load AWS/ECS/Fargate servers
  const loadServers = async () => {
    setLoading(true);
    setError(null);
    try {
      axios.defaults.baseURL = '/api';
      
      const res = await axios.get(`/v1/servers/`, {
        params: withEnvironment(),
        headers: {  }
      });
      const data = Array.isArray(res.data) ? res.data : (res.data?.servers || []);
      
      // Filter AWS, ECS, Fargate servers
      const awsServers = data.filter(server => 
        server.os && (
          server.os.toLowerCase().includes('aws') ||
          server.os.toLowerCase().includes('ecs') ||
          server.os.toLowerCase().includes('fargate') ||
          server.os.toLowerCase().includes('amazon')
        )
      );

      // Add calculated status
      const enhancedServers = awsServers.map(server => {
        let calculatedStatus = server.status;
        if (server.status === 'online' && !server.is_inactive) {
          const cpu = parseFloat(server.cpu) || 0;
          const memory = parseFloat(server.memory) || 0;
          const disk = parseFloat(server.disk) || 0;
          
          const cpuT = hardwareThresholds['cpu'] || { warning: 101, error: 101 };
          const memT = hardwareThresholds['memory'] || { warning: 101, error: 101 };
          const diskT = hardwareThresholds['disk'] || { warning: 101, error: 101 };

          if (cpu >= cpuT.error || memory >= memT.error || disk >= diskT.error) {
            calculatedStatus = 'warning';
          } else if (cpu >= cpuT.warning || memory >= memT.warning || disk >= diskT.warning) {
            calculatedStatus = 'warning';
          }
        }
        return { ...server, calculatedStatus };
      });

      setServers(enhancedServers);
      
      // Load metrics for each server
      enhancedServers.forEach(server => {
        loadServerMetrics(server.id);
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Load metrics for a specific server
  const loadServerMetrics = async (serverId) => {
    try {
      
      
      let apiStartDate, apiEndDate;
      const now = new Date();
      
      if (timeRange === 'custom' && customStartDate && customEndDate) {
        apiStartDate = new Date(customStartDate).toISOString().split('T')[0];
        apiEndDate = new Date(customEndDate).toISOString().split('T')[0];
      } else {
        let startDate = new Date();
        switch (timeRange) {
          case '1h':
            startDate.setHours(now.getHours() - 1);
            break;
          case '6h':
            startDate.setHours(now.getHours() - 6);
            break;
          case '24h':
            startDate.setHours(now.getHours() - 24);
            break;
          case '7d':
            startDate.setDate(now.getDate() - 7);
            break;
          case '30d':
            startDate.setDate(now.getDate() - 30);
            break;
          default:
            startDate.setHours(now.getHours() - 24);
        }
        apiStartDate = startDate.toISOString().split('T')[0];
        apiEndDate = now.toISOString().split('T')[0];
      }
      
      // Calculate duration to set limit
      const startDt = new Date(apiStartDate);
      const endDt = new Date(apiEndDate);
      const durationMs = endDt - startDt;
      const durationDays = durationMs / (1000 * 60 * 60 * 24);
      const dataLimit = durationDays > 7 ? 2000 : 1000;

      const metricNames = [
        'cpu', 'memory', 'disk', 'network_bandwidth', 'packet_count', 'uptime',
        'memory_total_bytes', 'memory_used_bytes', 'disk_total_bytes', 'disk_used_bytes'
      ];
      const allMetrics = [];

      for (const metricName of metricNames) {
        try {
          const response = await axios.get('/v1/historical/server-metrics', {
            params: {
              server_id: serverId,
              start_date: apiStartDate,
              end_date: apiEndDate,
              metric_name: metricName,
              limit: dataLimit
            },
            headers: {  }
          });
          
          if (response.data && response.data.metrics) {
            allMetrics.push(...response.data.metrics);
          }
        } catch (e) {
          console.warn(`Could not fetch ${metricName} for server ${serverId}:`, e);
        }
      }
      
      // Consolidate metrics by timestamp
      const historyData = allMetrics.reduce((acc, metric) => {
        const metricDate = new Date(metric.timestamp);
        const timestamp = metricDate.getTime();
        
        if (!acc[timestamp]) {
          acc[timestamp] = {
            timestamp: timestamp,
            time: metricDate.toLocaleTimeString('en-IN', {
              timeZone: 'Asia/Kolkata',
              hour: '2-digit',
              minute: '2-digit'
            }),
          };
        }
        // Ensure numeric value and use metric_name as key
        const value = parseFloat(metric.value);
        if (!isNaN(value)) {
          acc[timestamp][metric.metric_name] = value;
          
          // On-the-fly GB conversion
          if (metric.metric_name === 'memory_used_bytes') {
              acc[timestamp]['memory_used_gb'] = value / (1024**3);
          }
          if (metric.metric_name === 'disk_used_bytes') {
              acc[timestamp]['disk_used_gb'] = value / (1024**3);
          }
        }
        return acc;
      }, {});
      
      const sortedHistory = Object.values(historyData)
        .sort((a, b) => a.timestamp - b.timestamp);
      
      setMetricsData(prev => ({
        ...prev,
        [serverId]: sortedHistory,
      }));
    } catch (err) {
      console.error(`Failed to load metrics for server ${serverId}:`, err);
    }
  };

  useEffect(() => {
    loadServers();
  }, [environment]);

  useEffect(() => {
    if (timeRange !== 'custom' || (customStartDate && customEndDate)) {
      servers.forEach(server => {
        loadServerMetrics(server.id);
      });
    }
  }, [timeRange, customStartDate, customEndDate]);

  const systemStats = {
    total: servers.length,
    online: servers.filter(s => s.calculatedStatus === 'online').length,
    warning: servers.filter(s => s.calculatedStatus === 'warning').length,
    offline: servers.filter(s => s.calculatedStatus === 'offline').length,
  };

  const StatusBadge = ({ status }) => {
    const statusConfig = {
      online: { color: '#4CAF50', label: 'Online' },
      warning: { color: '#FF9800', label: 'Warning' },
      offline: { color: '#F44336', label: 'Offline' },
    };
    const config = statusConfig[status] || statusConfig.offline;
    return (
      <Chip
        label={config.label}
        size="small"
        sx={{ backgroundColor: config.color, color: 'white', fontWeight: 'bold' }}
      />
    );
  };

  const MetricBadge = ({ value, isInactive, metricKey }) => {
    if (isInactive) {
      return (
        <Box sx={{ backgroundColor: '#9E9E9E', color: 'white', padding: '2px 8px', borderRadius: '4px', display: 'inline-block', fontSize: '0.875rem' }}>
          N/A
        </Box>
      );
    }
    const numValue = parseFloat(value) || 0;
    const t = hardwareThresholds[metricKey] || { warning: 101, error: 101 };
    const backgroundColor = numValue >= t.error ? '#F44336' : numValue >= t.warning ? '#FF9800' : '#4CAF50';
    return (
      <Box sx={{ backgroundColor, color: 'white', padding: '2px 8px', borderRadius: '4px', display: 'inline-block', fontSize: '0.875rem', fontWeight: 'bold' }}>
        {numValue.toFixed(1)}%
      </Box>
    );
  };

  // Format X-axis ticks based on time range
  const formatXAxis = (timestamp) => {
    const date = new Date(timestamp);
    // Always show Date + Time
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <Paper sx={{ p: 1.5, backgroundColor: 'rgba(255,255,255,0.95)' }}>
          <Typography variant="body2" sx={{ fontWeight: 'bold', mb: 0.5 }}>
            {new Date(label).toLocaleString()}
          </Typography>
          {payload.map((entry, index) => (
            <Typography key={index} variant="body2" sx={{ color: entry.color }}>
              {entry.name}: {entry.value.toFixed(2)}{entry.name === 'Packet Errors' ? '' : '%'}
            </Typography>
          ))}
        </Paper>
      );
    }
    return null;
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <CloudIcon sx={{ fontSize: 40, color: '#FF9900' }} />
          <Typography variant="h4" fontWeight="bold">
            AWS / ECS / Fargate Monitoring
          </Typography>
        </Box>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Time Range</InputLabel>
            <Select
              value={timeRange}
              label="Time Range"
              onChange={(e) => setTimeRange(e.target.value)}
            >
              <MenuItem value="1h">Last 1 Hour</MenuItem>
              <MenuItem value="6h">Last 6 Hours</MenuItem>
              <MenuItem value="24h">Last 24 Hours</MenuItem>
              <MenuItem value="7d">Last 7 Days</MenuItem>
              <MenuItem value="30d">Last 30 Days</MenuItem>
              <MenuItem value="custom">Custom Range</MenuItem>
            </Select>
          </FormControl>
          
          {timeRange === 'custom' && (
            <>
              <TextField
                type="date"
                size="small"
                label="Start Date"
                value={customStartDate}
                onChange={(e) => setCustomStartDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                type="date"
                size="small"
                label="End Date"
                value={customEndDate}
                onChange={(e) => setCustomEndDate(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </>
          )}
          {(left !== 'dataMin' || right !== 'dataMax') && (
            <Button variant="outlined" size="small" onClick={zoomOut}>
              Reset Zoom
            </Button>
          )}
        </Box>
      </Box>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ borderLeft: '4px solid #FF9900' }}>
            <CardContent>
              <Typography variant="h6" color="text.secondary">Total Servers</Typography>
              <Typography variant="h3" fontWeight="bold">{systemStats.total}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ borderLeft: '4px solid #4CAF50' }}>
            <CardContent>
              <Typography variant="h6" color="text.secondary">Online</Typography>
              <Typography variant="h3" fontWeight="bold" color="success.main">{systemStats.online}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ borderLeft: '4px solid #FF9800' }}>
            <CardContent>
              <Typography variant="h6" color="text.secondary">Warning</Typography>
              <Typography variant="h3" fontWeight="bold" color="warning.main">{systemStats.warning}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ borderLeft: '4px solid #F44336' }}>
            <CardContent>
              <Typography variant="h6" color="text.secondary">Offline</Typography>
              <Typography variant="h3" fontWeight="bold" color="error.main">{systemStats.offline}</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : servers.length === 0 ? (
        <Alert severity="info">
          No AWS/ECS/Fargate servers found in <strong>{environment.toUpperCase()}</strong> environment.
          {environment === 'uat' && (
            <Box sx={{ mt: 1 }}>
              💡 Tip: Servers are added to PROD environment by default. Switch to PROD to see them, or move servers to UAT environment from the Servers page.
            </Box>
          )}
        </Alert>
      ) : (
        <>
          <Paper sx={{ mb: 3 }}>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                    <TableCell><strong>Server Name</strong></TableCell>
                    <TableCell><strong>IP Address</strong></TableCell>
                    <TableCell><strong>OS/Platform</strong></TableCell>
                    <TableCell><strong>Status</strong></TableCell>
                    <TableCell align="center"><strong>CPU</strong></TableCell>
                    <TableCell align="center"><strong>Memory</strong></TableCell>
                    <TableCell align="center"><strong>Disk</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {servers.map((server) => (
                    <TableRow key={server.id} hover>
                      <TableCell>{server.name}</TableCell>
                      <TableCell>{server.ip_address}</TableCell>
                      <TableCell>{server.os}</TableCell>
                      <TableCell><StatusBadge status={server.calculatedStatus} /></TableCell>
                                            <TableCell align="center">
                                              <MetricBadge value={server.cpu} isInactive={server.is_inactive} metricKey="cpu" />
                                            </TableCell>
                                            <TableCell align="center">
                                              <MetricBadge value={server.memory} isInactive={server.is_inactive} metricKey="memory" />
                                            </TableCell>
                                            <TableCell align="center">
                                              <MetricBadge value={server.disk} isInactive={server.is_inactive} metricKey="disk" />
                                            </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          {servers.map((server) => (
            <Paper key={server.id} sx={{ p: 3, mb: 3 }}>
              <Typography variant="h6" fontWeight="bold" sx={{ mb: 2 }}>
                {server.name} - Performance Metrics
              </Typography>
              {metricsData[server.id] && metricsData[server.id].length > 0 ? (
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>CPU Usage (%)</Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <AreaChart
                        data={metricsData[server.id]}
                        onMouseDown={(e) => e && setRefAreaLeft(e.activeLabel)}
                        onMouseMove={(e) => refAreaLeft && e && setRefAreaRight(e.activeLabel)}
                        onMouseUp={zoom}
                      >
                        <defs>
                          <linearGradient id={`cpuGradient-${server.id}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#2196F3" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="#2196F3" stopOpacity={0.1}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                        <XAxis 
                          dataKey="timestamp" 
                          tickFormatter={formatXAxis} 
                          stroke="#666" 
                          height={80}
                          angle={-45}
                          textAnchor="end"
                          minTickGap={20}
                          type="number"
                          domain={[left, right]}
                          scale="time"
                          tickCount={15}
                        />
                        <YAxis domain={[0, 100]} stroke="#666" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="cpu" stroke="#2196F3" fill={`url(#cpuGradient-${server.id})`} name="CPU" isAnimationActive={false} />
                        {refAreaLeft && refAreaRight ? (
                          <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} />
                        ) : null}
                      </AreaChart>
                    </ResponsiveContainer>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>Memory Usage (GB)</Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <AreaChart
                        data={metricsData[server.id]}
                        onMouseDown={(e) => e && setRefAreaLeft(e.activeLabel)}
                        onMouseMove={(e) => refAreaLeft && e && setRefAreaRight(e.activeLabel)}
                        onMouseUp={zoom}
                      >
                        <defs>
                          <linearGradient id={`memoryGradient-${server.id}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#4CAF50" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="#4CAF50" stopOpacity={0.1}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                        <XAxis 
                          dataKey="timestamp" 
                          tickFormatter={formatXAxis} 
                          stroke="#666" 
                          height={80}
                          angle={-45}
                          textAnchor="end"
                          minTickGap={20}
                          type="number"
                          domain={[left, right]}
                          scale="time"
                          tickCount={15}
                        />
                        <YAxis domain={['auto', 'auto']} tickFormatter={(val) => `${val.toFixed(1)} GB`} stroke="#666" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="memory_used_gb" stroke="#4CAF50" fill={`url(#memoryGradient-${server.id})`} name="Memory" isAnimationActive={false} />
                        {refAreaLeft && refAreaRight ? (
                          <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} />
                        ) : null}
                      </AreaChart>
                    </ResponsiveContainer>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>Disk Usage (GB)</Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <AreaChart
                        data={metricsData[server.id]}
                        onMouseDown={(e) => e && setRefAreaLeft(e.activeLabel)}
                        onMouseMove={(e) => refAreaLeft && e && setRefAreaRight(e.activeLabel)}
                        onMouseUp={zoom}
                      >
                        <defs>
                          <linearGradient id={`diskGradient-${server.id}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#FF9800" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="#FF9800" stopOpacity={0.1}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                        <XAxis 
                          dataKey="timestamp" 
                          tickFormatter={formatXAxis} 
                          stroke="#666" 
                          height={80}
                          angle={-45}
                          textAnchor="end"
                          minTickGap={20}
                          type="number"
                          domain={[left, right]}
                          scale="time"
                          tickCount={15}
                        />
                        <YAxis domain={['auto', 'auto']} tickFormatter={(val) => `${val.toFixed(1)} GB`} stroke="#666" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="disk_used_gb" stroke="#FF9800" fill={`url(#diskGradient-${server.id})`} name="Disk" isAnimationActive={false} />
                        {refAreaLeft && refAreaRight ? (
                          <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} />
                        ) : null}
                      </AreaChart>
                    </ResponsiveContainer>
                  </Grid>
                  {/* Network Chart */}
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>
                      Network Bandwidth (Mbps)
                    </Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <AreaChart
                        data={metricsData[server.id]}
                        onMouseDown={(e) => e && setRefAreaLeft(e.activeLabel)}
                        onMouseMove={(e) => refAreaLeft && e && setRefAreaRight(e.activeLabel)}
                        onMouseUp={zoom}
                      >
                        <defs>
                          <linearGradient id={`networkGradient-${server.id}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#9C27B0" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="#9C27B0" stopOpacity={0.1}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                        <XAxis 
                          dataKey="timestamp" 
                          tickFormatter={formatXAxis}
                          stroke="#666"
                          height={80}
                          angle={-45}
                          textAnchor="end"
                          minTickGap={20}
                          type="number"
                          domain={[left, right]}
                          scale="time"
                          tickCount={15}
                        />
                        <YAxis domain={['auto', 'auto']} tickFormatter={(val) => `${val.toFixed(2)} Mbps`} stroke="#666" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="network_bandwidth" stroke="#9C27B0" fill={`url(#networkGradient-${server.id})`} name="Network" isAnimationActive={false} />
                        {refAreaLeft && refAreaRight ? (
                          <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} />
                        ) : null}
                      </AreaChart>
                    </ResponsiveContainer>
                  </Grid>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                        <XAxis 
                          dataKey="timestamp" 
                          tickFormatter={formatXAxis}
                          stroke="#666"
                          height={80}
                          angle={-45}
                          textAnchor="end"
                          minTickGap={20}
                          type="number"
                          domain={[left, right]}
                          scale="time"
                          tickCount={15}
                        />
                        <YAxis domain={[0, 100]} stroke="#666" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area 
                          type="monotone" 
                          dataKey="network_bandwidth" 
                          stroke="#9C27B0" 
                          fill={`url(#networkGradient-${server.id})`}
                          name="Network"
                          isAnimationActive={false}
                        />
                        {refAreaLeft && refAreaRight ? (
                          <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} />
                        ) : null}
                      </AreaChart>
                    </ResponsiveContainer>
                  </Grid>

                  {/* Packet Errors Chart */}
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>
                      Network Packet Errors
                    </Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <AreaChart
                        data={metricsData[server.id]}
                        onMouseDown={(e) => e && setRefAreaLeft(e.activeLabel)}
                        onMouseMove={(e) => refAreaLeft && e && setRefAreaRight(e.activeLabel)}
                        onMouseUp={zoom}
                      >
                        <defs>
                          <linearGradient id={`packetGradient-${server.id}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#f44336" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="#f44336" stopOpacity={0.1}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                        <XAxis 
                          dataKey="timestamp" 
                          tickFormatter={formatXAxis}
                          stroke="#666"
                          height={80}
                          angle={-45}
                          textAnchor="end"
                          minTickGap={20}
                          type="number"
                          domain={[left, right]}
                          scale="time"
                          tickCount={15}
                        />
                        <YAxis stroke="#666" />
                        <Tooltip content={<CustomTooltip />} />
                        <Area 
                          type="monotone" 
                          dataKey="packet_count" 
                          stroke="#f44336" 
                          fill={`url(#packetGradient-${server.id})`}
                          name="Packet Errors"
                          isAnimationActive={false}
                        />
                        {refAreaLeft && refAreaRight ? (
                          <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} />
                        ) : null}
                      </AreaChart>
                    </ResponsiveContainer>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>Combined Metrics</Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart
                        data={metricsData[server.id]}
                        onMouseDown={(e) => e && setRefAreaLeft(e.activeLabel)}
                        onMouseMove={(e) => refAreaLeft && e && setRefAreaRight(e.activeLabel)}
                        onMouseUp={zoom}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                        <XAxis 
                          dataKey="timestamp" 
                          tickFormatter={formatXAxis} 
                          stroke="#666" 
                          height={80}
                          angle={-45}
                          textAnchor="end"
                          minTickGap={20}
                          type="number"
                          domain={[left, right]}
                          scale="time"
                          tickCount={15}
                        />
                        <YAxis domain={[0, 100]} stroke="#666" />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend />
                        <Line type="monotone" dataKey="cpu" stroke="#2196F3" name="CPU" strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line type="monotone" dataKey="memory" stroke="#4CAF50" name="Memory" strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line type="monotone" dataKey="disk" stroke="#FF9800" name="Disk" strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line type="monotone" dataKey="network_bandwidth" stroke="#9C27B0" name="Network" strokeWidth={2} dot={false} isAnimationActive={false} />
                        {refAreaLeft && refAreaRight ? (
                          <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} />
                        ) : null}
                      </LineChart>
                    </ResponsiveContainer>
                  </Grid>
                </Grid>
              ) : (
                <Alert severity="info">No metrics data available for this server.</Alert>
              )}
            </Paper>
          ))}
        </>
      )}
    </Box>
  );
};

export default AWSServerMonitoring;
