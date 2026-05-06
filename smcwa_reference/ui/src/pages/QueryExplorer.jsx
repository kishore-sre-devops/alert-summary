import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Grid, TextField, Autocomplete, 
  Button, CircularProgress, Alert, Card, CardContent,
  Table, TableBody, TableCell, TableHead, TableRow, TableContainer,
  Divider, IconButton, Tooltip, Chip, FormControl, InputLabel, Select, MenuItem, Stack
} from '@mui/material';
import {
  Search as SearchIcon,
  PlayArrow as PlayIcon,
  History as HistoryIcon,
  Code as CodeIcon,
  Storage as StorageIcon,
  Cloud as CloudIcon,
  Dns as DnsIcon,
  ContentCopy as CopyIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, 
  CartesianGrid, Tooltip as RechartsTooltip, Legend
} from 'recharts';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';

const RESOURCE_TYPES = {
  rds: { label: 'RDS Database', icon: <StorageIcon fontSize="small" color="warning" />, labelKey: 'dimension_DBInstanceIdentifier' },
  ecs: { label: 'ECS Service', icon: <CloudIcon fontSize="small" color="success" />, labelKey: 'ecs_service_name' },
  server: { label: 'Linux Server', icon: <DnsIcon fontSize="small" color="primary" />, labelKey: 'instance' },
  ec2: { label: 'EC2 Instance', icon: <DnsIcon fontSize="small" color="info" />, labelKey: 'instance' }
};

export default function QueryExplorer() {
  const { environment } = useEnvironment();
  const [sources, setSources] = useState([]);
  const [selectedSource, setSelectedSource] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [targets, setTargets] = useState([]);
  const [selectedTarget, setSelectedTarget] = useState(null);
  const [metrics, setMetrics] = useState([]);
  const [selectedMetric, setSelectedMetric] = useState('');
  const [rawQuery, setRawQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [queryLoading, setQueryLoading] = useState(false);
  const [error, setError] = useState('');
  const [chartData, setChartData] = useState([]);
  const [tableData, setTableData] = useState([]);
  const [rangeMinutes, setRangeMinutes] = useState(60);
  const [isCustomRange, setIsCustomRange] = useState(false);
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');

  // Load available sources
  useEffect(() => {
    const fetchSources = async () => {
      try {
        setLoading(true);
        const resp = await axios.get(`/v1/metric-sources?environment=${environment}`);
        // Filter for Prometheus/Mimir sources
        const promSources = resp.data.filter(s => s.type === 'prometheus' || s.type === 'mimir');
        setSources(promSources);
        if (promSources.length > 0) {
          setSelectedSource(promSources[0].id);
        }
      } catch (err) {
        setError('Failed to load metric sources');
      } finally {
        setLoading(false);
      }
    };
    fetchSources();
  }, [environment]);

  // Load targets for selected source
  useEffect(() => {
    if (!selectedSource) return;
    const fetchTargets = async () => {
      try {
        setLoading(true);
        const resp = await axios.post('/v1/query-explorer/targets', { source_id: selectedSource });
        setTargets(resp.data.targets || []);
      } catch (err) {
        setError('Failed to load targets for this source');
      } finally {
        setLoading(false);
      }
    };
    fetchTargets();
  }, [selectedSource]);

  // Load metrics for selected target
  useEffect(() => {
    if (!selectedTarget || !selectedSource) return;
    const fetchMetrics = async () => {
      try {
        setLoading(true);
        const resp = await axios.post('/v1/query-explorer/metrics', {
          source_id: selectedSource,
          target_id: selectedTarget.id,
          resource_type: selectedTarget.type
        });
        setMetrics(resp.data.metrics || []);
      } catch (err) {
        setError('Failed to load available metrics');
      } finally {
        setLoading(false);
      }
    };
    fetchMetrics();
  }, [selectedTarget, selectedSource]);

  // Generate PromQL automatically
  useEffect(() => {
    if (selectedTarget && selectedMetric) {
      const labelKey = RESOURCE_TYPES[selectedTarget.type]?.labelKey || 'instance';
      const query = `${selectedMetric}{${labelKey}=~".*${selectedTarget.id}.*"}`;
      setRawQuery(query);
    }
  }, [selectedTarget, selectedMetric]);

  const handleRunQuery = async () => {
    if (!rawQuery) return;
    if (isCustomRange && (!customStart || !customEnd)) {
      setError('Please select both start and end times for the custom range.');
      return;
    }
    setQueryLoading(true);
    setError('');
    try {
      const payload = {
        source_id: selectedSource,
        query: rawQuery,
        range_minutes: rangeMinutes
      };

      if (isCustomRange) {
        payload.start_time = new Date(customStart).toISOString();
        payload.end_time = new Date(customEnd).toISOString();
      }

      const resp = await axios.post('/v1/query-explorer/run', payload);

      if (resp.data.status === 'success') {
        const results = resp.data.data.result || [];
        if (results.length === 0) {
          setError('No data points found for this query window.');
          setChartData([]);
          setTableData([]);
          return;
        }

        // Process for Recharts
        const formattedData = [];
        const seriesMap = {};
        
        results.forEach((series, idx) => {
          const seriesName = series.metric.dimension_DBInstanceIdentifier || 
                             series.metric.ecs_service_name || 
                             series.metric.instance || 
                             `Series ${idx + 1}`;
          seriesMap[idx] = seriesName;
          
          series.values.forEach(([ts, val]) => {
            const time = new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const point = formattedData.find(p => p.time === time) || { time, timestamp: ts };
            point[seriesName] = parseFloat(parseFloat(val).toFixed(3));
            if (!formattedData.find(p => p.time === time)) formattedData.push(point);
          });
        });

        setChartData(formattedData.sort((a, b) => a.timestamp - b.timestamp));
        
        // Process for Table (Latest points)
        const latestPoints = [];
        results.forEach((series, idx) => {
          const seriesName = seriesMap[idx];
          if (series.values.length > 0) {
            const last = series.values[series.values.length - 1];
            latestPoints.push({
              name: seriesName,
              timestamp: new Date(last[0] * 1000).toLocaleString(),
              value: last[1],
              labels: series.metric
            });
          }
        });
        setTableData(latestPoints);
      } else {
        setError(resp.data.error || 'Query failed');
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Execution error');
    } finally {
      setQueryLoading(false);
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(rawQuery);
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ fontWeight: 'bold', mb: 3, display: 'flex', alignItems: 'center', gap: 1 }}>
        <SearchIcon color="primary" /> Smart Query Explorer
      </Typography>

      <Grid container spacing={3}>
        {/* Left Panel: Controls */}
        <Grid item xs={12} md={4}>
          <Card sx={{ border: '1px solid #e0e0e0', boxShadow: 'none' }}>
            <CardContent>
              <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <CodeIcon fontSize="small" color="action" /> QUERY BUILDER
              </Typography>

              <Stack spacing={2.5}>
                <FormControl fullWidth size="small">
                  <InputLabel>Data Source (Mimir/Prometheus)</InputLabel>
                  <Select
                    value={selectedSource}
                    label="Data Source (Mimir/Prometheus)"
                    onChange={(e) => setSelectedSource(e.target.value)}
                  >
                    {sources.map(s => (
                      <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <FormControl fullWidth size="small">
                  <InputLabel>Resource Type Filter</InputLabel>
                  <Select
                    value={filterType}
                    label="Resource Type Filter"
                    onChange={(e) => {
                      setFilterType(e.target.value);
                      setSelectedTarget(null);
                      setMetrics([]);
                      setSelectedMetric('');
                    }}
                  >
                    <MenuItem value="all">All Resources</MenuItem>
                    <MenuItem value="rds">RDS Databases</MenuItem>
                    <MenuItem value="ecs">ECS Services</MenuItem>
                    <MenuItem value="server">Linux Servers</MenuItem>
                    <MenuItem value="ec2">EC2 Instances</MenuItem>
                  </Select>
                </FormControl>

                <Autocomplete
                  size="small"
                  options={targets.filter(t => filterType === 'all' || t.type === filterType)}
                  getOptionLabel={(option) => `${option.name} (${option.type.toUpperCase()})`}
                  value={selectedTarget}
                  onChange={(e, val) => setSelectedTarget(val)}
                  renderInput={(params) => <TextField {...params} label="Target Resource" placeholder="Search resources..." />}
                  renderOption={(props, option) => (
                    <Box component="li" {...props} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {RESOURCE_TYPES[option.type]?.icon}
                      <Box>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{option.name}</Typography>
                        <Typography variant="caption" color="textSecondary">{option.account || 'Local'}</Typography>
                      </Box>
                    </Box>
                  )}
                />

                <Autocomplete
                  size="small"
                  options={metrics}
                  value={selectedMetric}
                  onChange={(e, val) => setSelectedMetric(val)}
                  disabled={!selectedTarget}
                  renderInput={(params) => <TextField {...params} label="Available Metrics" placeholder="Select metric..." />}
                />

                <Divider sx={{ my: 1 }}> OR </Divider>

                <TextField
                  fullWidth
                  multiline
                  rows={4}
                  label="Custom PromQL Query"
                  placeholder="Enter raw PromQL here..."
                  value={rawQuery}
                  onChange={(e) => setRawQuery(e.target.value)}
                  sx={{ fontFamily: 'monospace', '& .MuiInputBase-input': { fontSize: '0.85rem' } }}
                />

                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <FormControl size="small" sx={{ width: 140 }}>
                      <InputLabel>Time Range</InputLabel>
                      <Select
                        value={isCustomRange ? 'custom' : rangeMinutes}
                        label="Time Range"
                        onChange={(e) => {
                          if (e.target.value === 'custom') {
                            setIsCustomRange(true);
                          } else {
                            setIsCustomRange(false);
                            setRangeMinutes(e.target.value);
                          }
                        }}
                      >
                        <MenuItem value={15}>Last 15m</MenuItem>
                        <MenuItem value={30}>Last 30m</MenuItem>
                        <MenuItem value={60}>Last 1h</MenuItem>
                        <MenuItem value={180}>Last 3h</MenuItem>
                        <MenuItem value={360}>Last 6h</MenuItem>
                        <MenuItem value={1440}>Last 24h</MenuItem>
                        <MenuItem value="custom">Custom Range</MenuItem>
                      </Select>
                    </FormControl>

                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Tooltip title="Copy Query">
                        <IconButton size="small" onClick={copyToClipboard} disabled={!rawQuery}>
                          <CopyIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Button
                        variant="contained"
                        startIcon={queryLoading ? <CircularProgress size={18} color="inherit" /> : <PlayIcon />}
                        onClick={handleRunQuery}
                        disabled={!rawQuery || queryLoading}
                      >
                        Run
                      </Button>
                    </Box>
                  </Box>

                  {isCustomRange && (
                    <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                      <TextField
                        size="small"
                        type="datetime-local"
                        label="From"
                        value={customStart}
                        onChange={(e) => setCustomStart(e.target.value)}
                        InputLabelProps={{ shrink: true }}
                        fullWidth
                      />
                      <TextField
                        size="small"
                        type="datetime-local"
                        label="To"
                        value={customEnd}
                        onChange={(e) => setCustomEnd(e.target.value)}
                        InputLabelProps={{ shrink: true }}
                        fullWidth
                      />
                    </Box>
                  )}
                </Box>
              </Stack>
            </CardContent>
          </Card>

          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
          <Alert severity="info" sx={{ mt: 2, fontSize: '0.8rem' }} icon={<HistoryIcon fontSize="small" />}>
            Generated queries automatically include the 60-minute dynamic window to compensate for cloud ingestion delays.
          </Alert>
        </Grid>

        {/* Right Panel: Visualization */}
        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 2, mb: 3, border: '1px solid #e0e0e0', boxShadow: 'none', height: 400 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TrendingUpIcon fontSize="small" color="primary" /> TIME SERIES GRAPH
              </Box>
              {chartData.length > 0 && <Chip label={`${chartData.length} points`} size="small" variant="outlined" />}
            </Typography>
            
            {queryLoading ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '80%' }}>
                <CircularProgress size={40} />
                <Typography variant="body2" sx={{ mt: 2 }} color="textSecondary">Executing PromQL...</Typography>
              </Box>
            ) : chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="90%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="time" style={{ fontSize: '0.7rem' }} />
                  <YAxis style={{ fontSize: '0.7rem' }} />
                  <RechartsTooltip />
                  <Legend wrapperStyle={{ fontSize: '0.8rem' }} />
                  {Object.keys(chartData[0]).filter(k => k !== 'time' && k !== 'timestamp').map((key, idx) => (
                    <Line 
                      key={key} 
                      type="monotone" 
                      dataKey={key} 
                      stroke={['#1976d2', '#2e7d32', '#ed6c02', '#9c27b0', '#d32f2f'][idx % 5]} 
                      dot={false}
                      strokeWidth={2}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '80%', bgcolor: '#fbfbfb', borderRadius: 1, border: '1px dashed #ddd' }}>
                <Typography color="textSecondary">Execute a query to see the visualization</Typography>
              </Box>
            )}
          </Paper>

          <TableContainer component={Paper} sx={{ border: '1px solid #e0e0e0', boxShadow: 'none' }}>
            <Table size="small">
              <TableHead sx={{ bgcolor: '#f5f5f5' }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold' }}>Series</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Last Value</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Timestamp</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tableData.map((row, idx) => (
                  <TableRow key={idx}>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{row.name}</Typography>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'text.secondary' }}>
                        {Object.entries(row.labels).filter(([k]) => k !== '__name__').map(([k, v]) => `${k}="${v}"`).join(', ')}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip label={parseFloat(row.value).toFixed(3)} size="small" color="primary" variant="outlined" sx={{ fontWeight: 700 }} />
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.8rem' }}>{row.timestamp}</TableCell>
                  </TableRow>
                ))}
                {tableData.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={3} align="center" sx={{ py: 3, color: 'text.secondary' }}>No data points to display</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Grid>
      </Grid>
    </Box>
  );
}

// Sub-component for icons
function TrendingUpIcon(props) {
  return (
    <svg width={20} height={20} fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" {...props}>
      <path d="M23 6l-9.5 9.5-5-5L1 18" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M17 6h6v6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
