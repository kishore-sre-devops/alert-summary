import React from 'react';
import Box from '@mui/material/Box';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';
import Chip from '@mui/material/Chip';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TableContainer from '@mui/material/TableContainer';
import Button from '@mui/material/Button';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceArea,
} from 'recharts';

/**
 * Unified Single-Panel Dashboard Component
 * All metrics in one scrollable view - no tabs
 */
const GrafanaDashboard = ({
  instance,
  getTimeRangeDisplay,
  getMetricStats,
  formatBytes,
  formatMbps,
}) => {
  const serverId = instance.id;
  
  // Zoom state
  const [left, setLeft] = React.useState('dataMin');
  const [right, setRight] = React.useState('dataMax');
  const [refAreaLeft, setRefAreaLeft] = React.useState('');
  const [refAreaRight, setRefAreaRight] = React.useState('');

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

  const getColorForValue = (value, threshold1 = 60, threshold2 = 80) => {
    const numValue = parseFloat(value);
    if (numValue > threshold2) return '#F44336'; // Red
    if (numValue > threshold1) return '#FF9800'; // Orange
    return '#4CAF50'; // Green
  };

  // Detect OS type for customization
  const detectOS = () => {
    const os = (instance.os || '').toLowerCase();
    if (os.includes('windows')) return 'windows';
    if (os.includes('linux')) return 'linux';
    if (os.includes('aws') || os.includes('ecs') || os.includes('fargate')) return 'aws';
    if (os.includes('mac') || os.includes('darwin')) return 'macos';
    return 'linux'; // default
  };

  const osType = detectOS();

  // Helper: Format uptime
  const formatUptime = (seconds) => {
    if (!seconds) return 'N/A';
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    return `${days}d ${hours}h`;
  };

  return (
    <Box sx={{ width: '100%', mt: 2, backgroundColor: '#f5f5f5', p: 2, borderRadius: 2 }}>
      {(left !== 'dataMin' || right !== 'dataMax') && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
           <Button variant="outlined" size="small" onClick={zoomOut}>Reset Zoom</Button>
        </Box>
      )}
      {/* Quick Stats Bar */}
      <Paper sx={{ p: 2, mb: 3, backgroundColor: 'white' }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={2.4}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">CPU</Typography>
              <Typography variant="h6" sx={{ fontWeight: 'bold', color: getColorForValue(instance.cpu) }}>
                {(parseFloat(instance.cpu) || 0).toFixed(1)}%
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={2.4}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">Memory</Typography>
              <Typography variant="h6" sx={{ fontWeight: 'bold', color: getColorForValue(instance.memory) }}>
                {(parseFloat(instance.memory) || 0).toFixed(1)}%
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={2.4}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">Disk</Typography>
              <Typography variant="h6" sx={{ fontWeight: 'bold', color: getColorForValue(instance.disk || instance.hdd) }}>
                {(parseFloat(instance.disk || instance.hdd) || 0).toFixed(1)}%
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={2.4}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">Network</Typography>
              <Typography variant="h6" sx={{ fontWeight: 'bold', color: '#9C27B0' }}>
                {(parseFloat(instance.network) || 0).toFixed(1)}%
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={2.4}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="caption" color="text.secondary">Uptime</Typography>
              <Typography variant="h6" sx={{ fontWeight: 'bold', color: '#607D8B' }}>
                {formatUptime(instance.uptime)}
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </Paper>

      {/* Performance Charts - Grid */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <MetricCard
            title="📈 CPU Utilization"
            timeRange={getTimeRangeDisplay()}
            data={instance.metricsHistory}
            dataKey="cpu"
            value={instance.cpu ?? 0}
            unit="%"
            color="#2196F3"
            axisLabel="%"
            domain={[0, 100]}
            instanceId={serverId}
            getMetricStats={getMetricStats}
            zoomState={{ left, right, refAreaLeft, refAreaRight }}
            zoomHandlers={{ setRefAreaLeft, setRefAreaRight, zoom }}
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <MetricCard
            title="💾 Memory Utilization"
            timeRange={getTimeRangeDisplay()}
            data={instance.metricsHistory}
            dataKey="memory"
            value={instance.memory ?? 0}
            unit="%"
            color="#4CAF50"
            axisLabel="%"
            domain={[0, 100]}
            instanceId={serverId}
            getMetricStats={getMetricStats}
            zoomState={{ left, right, refAreaLeft, refAreaRight }}
            zoomHandlers={{ setRefAreaLeft, setRefAreaRight, zoom }}
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <MetricCard
            title="🌐 Network Utilization"
            timeRange={getTimeRangeDisplay()}
            data={instance.metricsHistory}
            dataKey="network_bandwidth"
            value={instance.network ?? 0}
            unit="%"
            color="#9C27B0"
            axisLabel="%"
            domain={[0, 100]}
            instanceId={serverId}
            getMetricStats={getMetricStats}
            zoomState={{ left, right, refAreaLeft, refAreaRight }}
            zoomHandlers={{ setRefAreaLeft, setRefAreaRight, zoom }}
          />
        </Grid>
        <Grid item xs={12} md={6}>
          <MetricCard
            title="💿 Disk Utilization"
            timeRange={getTimeRangeDisplay()}
            data={instance.metricsHistory}
            dataKey="disk"
            value={instance.disk ?? instance.hdd ?? 0}
            unit="%"
            color="#FF9800"
            axisLabel="%"
            domain={[0, 100]}
            instanceId={serverId}
            getMetricStats={getMetricStats}
            zoomState={{ left, right, refAreaLeft, refAreaRight }}
            zoomHandlers={{ setRefAreaLeft, setRefAreaRight, zoom }}
          />
        </Grid>
        <Grid item xs={12} md={12}>
          <MetricCard
            title="⚠️ Network Packet Errors"
            timeRange={getTimeRangeDisplay()}
            data={instance.metricsHistory}
            dataKey="packet_count"
            value={instance.packet_count ?? 0}
            unit=""
            color="#f44336"
            axisLabel="Errors"
            domain={[0, 'dataMax + 10']}
            instanceId={serverId}
            getMetricStats={getMetricStats}
            zoomState={{ left, right, refAreaLeft, refAreaRight }}
            zoomHandlers={{ setRefAreaLeft, setRefAreaRight, zoom }}
          />
        </Grid>
      </Grid>

      {/* Disk Partitions Section */}
      <Paper sx={{ p: 2, mb: 3, backgroundColor: 'white' }}>
        <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold', color: '#666' }}>
          {osType === 'windows' ? '💾 Drive Letters' : osType === 'aws' ? '💾 Storage Volumes' : '💾 Disk Partitions'}
        </Typography>
        {(!instance.diskPartitions || instance.diskPartitions.length === 0) ? (
          <Box sx={{ p: 2, textAlign: 'center', backgroundColor: '#f5f5f5', borderRadius: 1 }}>
            <Typography variant="body2" color="text.secondary">
              No disk partition data available
            </Typography>
          </Box>
        ) : (
          <Grid container spacing={2}>
            {instance.diskPartitions.map((partition, index) => {
              const usage = parseFloat(partition.usage_percent || partition.utilization || 0);
              // Backend returns "name" field with proper drive letters/mount points (C:, D:, /, /home)
              // Fallback to mount_point or device for backward compatibility
              const partitionName = partition.name 
                                    || (partition.mount_point && partition.mount_point.trim()) 
                                    || (partition.device && partition.device.trim()) 
                                    || `Partition ${index + 1}`;
              
              return (
                <Grid item xs={12} sm={6} md={4} key={index}>
                  <Paper sx={{ p: 2, border: '1px solid #e0e0e0', backgroundColor: '#fafafa' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 'bold', fontSize: '14px' }}>
                        {partitionName}
                      </Typography>
                      <Chip 
                        label={`${usage.toFixed(1)}%`}
                        size="small"
                        sx={{
                          backgroundColor: getColorForValue(usage),
                          color: 'white',
                          fontWeight: 'bold',
                          fontSize: '11px'
                        }}
                      />
                    </Box>
                    {partition.device && partition.device.trim() && partition.device !== partitionName && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                        Device: {partition.device}
                      </Typography>
                    )}
                    {partition.mount_point && partition.mount_point.trim() && partition.mount_point !== partitionName && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                        Mount: {partition.mount_point}
                      </Typography>
                    )}
                    <LinearProgress 
                      variant="determinate" 
                      value={Math.min(usage, 100)} 
                      sx={{ 
                        height: 6, 
                        borderRadius: 3,
                        mb: 1,
                        backgroundColor: '#e0e0e0',
                        '& .MuiLinearProgress-bar': {
                          backgroundColor: getColorForValue(usage)
                        }
                      }} 
                    />
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '11px' }}>
                        {partition.used_gb ? `${parseFloat(partition.used_gb).toFixed(1)} GB` : 'N/A'} used
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '11px' }}>
                        {partition.total_gb ? `${parseFloat(partition.total_gb).toFixed(1)} GB` : 'N/A'} total
                      </Typography>
                    </Box>
                  </Paper>
                </Grid>
              );
            })}
          </Grid>
        )}
      </Paper>

      {/* Network Interfaces Compact Table */}
      {instance.networkInterfaces && instance.networkInterfaces.length > 0 && (
        <Paper sx={{ p: 2, mb: 3, backgroundColor: 'white' }}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold', color: '#666' }}>
            🌐 Network Interfaces ({instance.networkInterfaces.length} adapters)
          </Typography>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: '12px' }}>Interface</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: '12px' }}>Speed</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: '12px' }}>Throughput</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: '12px' }}>Sent</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: '12px' }}>Received</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', fontSize: '12px' }}>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {instance.networkInterfaces.map((iface, index) => {
                  const utilization = parseFloat(iface.utilization || 0);
                  const speedGbps = (parseFloat(iface.speed_bps || 0) / 1_000_000_000).toFixed(1);
                  const throughputMbps = (parseFloat(iface.bits_per_sec || 0) / 1_000_000).toFixed(1);
                  
                  return (
                    <TableRow key={index} sx={{ '&:hover': { backgroundColor: '#f9f9f9' } }}>
                      <TableCell sx={{ fontSize: '12px', fontWeight: 600 }}>{iface.name}</TableCell>
                      <TableCell sx={{ fontSize: '12px' }}>
                        <Chip label={`${speedGbps} Gbps`} size="small" sx={{ fontSize: '10px', height: '20px' }} />
                      </TableCell>
                      <TableCell sx={{ fontSize: '12px' }}>{formatMbps ? formatMbps(throughputMbps) : `${throughputMbps} Mbps`}</TableCell>
                      <TableCell sx={{ fontSize: '12px' }}>{formatBytes ? formatBytes(parseFloat(iface.bytes_sent || 0)) : 'N/A'}</TableCell>
                      <TableCell sx={{ fontSize: '12px' }}>{formatBytes ? formatBytes(parseFloat(iface.bytes_recv || 0)) : 'N/A'}</TableCell>
                      <TableCell sx={{ fontSize: '12px' }}>
                        <Chip
                          label={utilization > 0 ? 'Active' : 'Idle'}
                          size="small"
                          color={utilization > 0 ? 'success' : 'default'}
                          sx={{ fontSize: '10px', height: '20px' }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      {/* System Information Footer */}
      <Paper sx={{ p: 2, backgroundColor: 'white' }}>
        <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold', color: '#666' }}>
          ℹ️ System Information
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={3}>
            <Box>
              <Typography variant="caption" color="text.secondary">Operating System</Typography>
              <Typography variant="body2" sx={{ fontWeight: '500' }}>{instance.os || 'Unknown'}</Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Box>
              <Typography variant="caption" color="text.secondary">Location / Site</Typography>
              <Box sx={{ mt: 0.5 }}>
                {instance.location_id === 1 ? (
                  <Chip label="DC (Data Center)" size="small" color="primary" sx={{ height: 22, fontSize: '0.7rem', fontWeight: 'bold' }} />
                ) : instance.location_id === 2 ? (
                  <Chip label="DR (Disaster Recovery)" size="small" color="warning" sx={{ height: 22, fontSize: '0.7rem', fontWeight: 'bold' }} />
                ) : instance.location_id === 3 ? (
                  <Chip label="Cloud / AWS" size="small" color="secondary" sx={{ height: 22, fontSize: '0.7rem', fontWeight: 'bold' }} />
                ) : (
                  <Chip label="Unknown" size="small" sx={{ height: 22, fontSize: '0.7rem' }} />
                )}
              </Box>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Box>
              <Typography variant="caption" color="text.secondary">IP Addresses</Typography>
              <Typography variant="body2" sx={{ fontWeight: '500', fontSize: '12px' }}>
                Primary: {instance.privateIp || 'N/A'}
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: '500', fontSize: '12px' }}>
                Source: {instance.publicIp || 'N/A'}
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Box>
              <Typography variant="caption" color="text.secondary">Last Heartbeat</Typography>
              <Typography variant="body2" sx={{ fontWeight: '500', fontSize: '12px' }}>
                {instance.last_seen 
                  ? new Date(instance.last_seen).toLocaleString('en-IN', { 
                      timeZone: 'Asia/Kolkata',
                      month: 'short',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit'
                    })
                  : 'N/A'}
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </Paper>
    </Box>
  );
};

// Helper Component: Metric Card with Chart
const MetricCard = ({
  title,
  value,
  unit,
  timeRange,
  data,
  dataKey,
  color,
  axisLabel,
  domain,
  instanceId,
  getMetricStats,
  zoomState,
  zoomHandlers,
}) => {
  const stats = getMetricStats(data, dataKey);
  const formattedValue = Number.parseFloat(value) || 0;
  const maxStat = Number.parseFloat(stats.max) || 0;
  const progressValue = maxStat > 0 ? Math.min((formattedValue / maxStat) * 100, 100) : 0;
  const progress = ['cpu', 'memory', 'disk'].includes(dataKey)
    ? Math.min(formattedValue, 100)
    : progressValue;
  const yDomain = domain || [0, 100];
  const yLabel = axisLabel || unit || '';

  const { left, right, refAreaLeft, refAreaRight } = zoomState || {};
  const { setRefAreaLeft, setRefAreaRight, zoom } = zoomHandlers || {};

  const formatXAxis = (unixTime) => {
    const date = new Date(unixTime);
    // Always show Date + Time
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <Paper sx={{ p: 2, backgroundColor: 'white', minHeight: 320 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
        {title} - {timeRange}
      </Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
        <Box sx={{ flex: 1 }}>
          <LinearProgress
            variant="determinate"
            value={progress}
            sx={{
              height: 8,
              borderRadius: 4,
              backgroundColor: '#e0e0e0',
              '& .MuiLinearProgress-bar': {
                backgroundColor: color
              }
            }}
          />
        </Box>
        <Typography variant="h6" sx={{ fontWeight: 'bold', minWidth: '80px', textAlign: 'right' }}>
          {formattedValue.toFixed(1)}{unit}
        </Typography>
      </Box>
      <Box sx={{ width: '100%', height: 180, mt: 1 }}>
        {(!data || data.length === 0) ? (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#999' }}>
            <Typography variant="caption">No historical data available</Typography>
          </Box>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart 
              data={data}
              onMouseDown={(e) => setRefAreaLeft && e && setRefAreaLeft(e.activeLabel)}
              onMouseMove={(e) => refAreaLeft && setRefAreaRight && e && e.activeLabel && setRefAreaRight(e.activeLabel)}
              onMouseUp={zoom}
            >
              <defs>
                <linearGradient id={`color${dataKey}${instanceId}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.8}/>
                  <stop offset="95%" stopColor={color} stopOpacity={0.1}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
              <XAxis 
                dataKey="timestamp" 
                scale="time"
                type="number"
                domain={[left, right]}
                allowDataOverflow
                tickFormatter={formatXAxis}
                height={80}
                angle={-45}
                textAnchor="end"
                minTickGap={10}
                tickCount={20}
                interval="preserveStartEnd"
              />
              <YAxis 
                tick={{ fontSize: 10 }}
                domain={yDomain}
                tickCount={10}
              />
              <RechartsTooltip 
                contentStyle={{ 
                  backgroundColor: 'rgba(255, 255, 255, 0.95)', 
                  border: '1px solid #ccc',
                  borderRadius: '4px',
                  fontSize: '12px'
                }}
                formatter={(val, name) => {
                  // Ensure val is a number and not a timestamp passed by mistake
                  if (typeof val === 'number' && val > 1000000000000) { // Heuristic: if value is a large number, it might be a timestamp
                    return [`${new Date(val).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit' })}`, 'Time'];
                  }
                  return [`${Number(val).toFixed(1)}${unit}`, title];
                }}
                labelFormatter={(unixTime) => new Date(unixTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' })}
              />
              <Area 
                type="monotone" 
                dataKey={dataKey} 
                stroke={color} 
                strokeWidth={2}
                fillOpacity={1} 
                fill={`url(#color${dataKey}${instanceId})`} 
                connectNulls={true}
                isAnimationActive={false}
              />
              {refAreaLeft && refAreaRight ? (
                <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} />
              ) : null}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Box>
    </Paper>
  );
};

export default GrafanaDashboard;
