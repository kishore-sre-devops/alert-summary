import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Box, Paper, Typography, TextField, Button, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Chip, Grid, FormControl, InputLabel,
  Select, MenuItem, Alert, CircularProgress, Card, CardContent, IconButton,
  Tooltip, Container, Divider, TablePagination, ButtonGroup, Dialog,
  DialogTitle, DialogContent, Tab, Tabs, Fade, List, ListItem, ListItemText, ListItemIcon
} from '@mui/material';
import { DateTimePicker } from '@mui/x-date-pickers/DateTimePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import DownloadIcon from '@mui/icons-material/Download';
import RefreshIcon from '@mui/icons-material/Refresh';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import ErrorIcon from '@mui/icons-material/Error';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import PendingIcon from '@mui/icons-material/Pending';
import FilterAltIcon from '@mui/icons-material/FilterAlt';
import ClearIcon from '@mui/icons-material/Clear';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import HistoryIcon from '@mui/icons-material/History';
import CloseIcon from '@mui/icons-material/Close';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import AccessTimeIcon from '@mui/icons-material/AccessTime';
import AssignmentIndIcon from '@mui/icons-material/AssignmentInd';
import FlagIcon from '@mui/icons-material/Flag';
import CommentIcon from '@mui/icons-material/Comment';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';
import { 
  LineChart, Line, ResponsiveContainer, YAxis, XAxis, CartesianGrid, 
  Tooltip as RechartsTooltip, ReferenceLine, AreaChart, Area
} from 'recharts';

const METRIC_TYPES = [
  { value: '', label: 'All Metric Types' },
  { value: 'hardware', label: 'Hardware' },
  { value: 'network', label: 'Network' },
  { value: 'database', label: 'Database' },
  { value: 'application', label: 'Application' },
];

const SEVERITY_OPTIONS = [
  { value: '', label: 'All Severities' },
  { value: 'warning', label: 'Warning' },
  { value: 'error', label: 'Critical' },
];

const RESOLVED_OPTIONS = [
  { value: '', label: 'All Status' },
  { value: 'true', label: 'Resolved' },
  { value: 'false', label: 'Unresolved' },
];

const styles = {
  pulseRed: {
    '@keyframes pulse-red': {
      '0%': { boxShadow: '0 0 0 0 rgba(211, 47, 47, 0.4)' },
      '70%': { boxShadow: '0 0 0 10px rgba(211, 47, 47, 0)' },
      '100%': { boxShadow: '0 0 0 0 rgba(211, 47, 47, 0)' },
    },
    animation: 'pulse-red 2s infinite',
  },
  pulseOrange: {
    '@keyframes pulse-orange': {
      '0%': { boxShadow: '0 0 0 0 rgba(237, 108, 2, 0.4)' },
      '70%': { boxShadow: '0 0 0 6px rgba(237, 108, 2, 0)' },
      '100%': { boxShadow: '0 0 0 0 rgba(237, 108, 2, 0)' },
    },
    animation: 'pulse-orange 2s infinite',
  },
  tableHeader: {
    bgcolor: '#1a237e',
    '& th': { color: 'white', fontWeight: 700, py: 1.5 }
  }
};

const MiniSparkline = React.memo(({ data, color, onClick }) => (
  <Box 
    onClick={onClick}
    sx={{ width: 100, height: 30, cursor: 'pointer', p: 0.5, borderRadius: '4px', '&:hover': { bgcolor: 'rgba(0,0,0,0.05)' }, transition: 'background 0.2s' }}
  >
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <YAxis hide domain={['auto', 'auto']} />
        <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  </Box>
));

const SummaryCard = ({ title, value, icon, color, active }) => (
  <Card sx={{ height: '100%', boxShadow: active ? 4 : 1, borderTop: `4px solid ${color}`, transition: 'all 0.3s', '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 } }}>
    <CardContent sx={{ py: 2, px: 2.5 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box><Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>{title}</Typography><Typography variant="h4" sx={{ fontWeight: 800, color: color }}>{value}</Typography></Box>
        <Box sx={{ bgcolor: `${color}10`, borderRadius: '12px', p: 1.2, color: color }}>{icon}</Box>
      </Box>
    </CardContent>
  </Card>
);

const formatCommitment = (mins) => {
  if (!mins) return '';
  const m = parseInt(mins);
  if (m === 2880) return '2d';
  if (m === 1440) return '24h';
  if (m === 720) return '12h';
  if (m === 360) return '6h';
  if (m === 180) return '3h';
  if (m === 120) return '2h';
  if (m === 60) return '1h';
  if (m >= 60) return `${Math.floor(m/60)}h ${m%60}m`;
  return `${m}m`;
};

const AlertHistory = () => {
  const { environment, withEnvironment } = useEnvironment();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [alerts, setAlerts] = useState([]);
  const [trends, setTrends] = useState({});
  const [totalCount, setTotalCount] = useState(0);
  const [stats, setStats] = useState({ total: 0, warnings: 0, errors: 0, resolved: 0, unresolved: 0 });
  
  const [startDateTime, setStartDateTime] = useState(null);
  const [endDateTime, setEndDateTime] = useState(null);
  const [metricType, setMetricType] = useState('');
  const [severity, setSeverity] = useState('');
  const [isResolved, setIsResolved] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [filterTrigger, setFilterTrigger] = useState(0);

  const [modalOpen, setModalOpen] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [modalTab, setModalTab] = useState(0);
  const [modalData, setModalData] = useState([]);
  const [modalLoading, setModalLoading] = useState(false);

  // --- CALL FLOW STATE ---
  const [callFlowOpen, setCallFlowOpen] = useState(false);
  const [callFlowData, setCallFlowData] = useState([]);
  const [callFlowLoading, setCallFlowLoading] = useState(false);

  useEffect(() => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    setStartDateTime(yesterday);
    setEndDateTime(today);
    setFilterTrigger(prev => prev + 1);
  }, []);

  const formatDateTimeForAPI = (date) => {
    if (!date) return { date: null, time: null };
    return {
      date: date.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' }),
      time: date.toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false })
    };
  };

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const start = formatDateTimeForAPI(startDateTime);
      const end = formatDateTimeForAPI(endDateTime);
      const params = {
        start_date: start.date, start_time: start.time, end_date: end.date, end_time: end.time,
        metric_type: metricType, severity, is_resolved: isResolved === '' ? null : isResolved === 'true',
        page, page_size: rowsPerPage, ...withEnvironment()
      };
      const response = await axios.get('/v1/alerts/', { params });
      setAlerts(response.data.alerts || []);
      setTotalCount(response.data.count || 0);
      const bs = response.data.stats || {};
      setStats({ total: bs.total || response.data.count || 0, warnings: bs.active_warning || 0, errors: bs.active_critical || 0, resolved: bs.resolved || 0, unresolved: bs.pending || 0 });

      if (response.data.alerts?.length > 0) {
        const trendReqs = response.data.alerts.map(a => ({ alert_id: a.id, server_id: a.server_id, metric_name: a.metric_key, timestamp: a.created_at_raw || a.created_at }));
        const trendRes = await axios.post('/v1/historical/multi-alert-trends', trendReqs);
        setTrends(trendRes.data || {});
      }
    } catch (err) { setError('Sync error.'); } finally { setLoading(false); }
  }, [startDateTime, endDateTime, metricType, severity, isResolved, page, rowsPerPage, withEnvironment]);

  useEffect(() => {
    const timer = setTimeout(fetchAlerts, 100);
    return () => clearTimeout(timer);
  }, [fetchAlerts, filterTrigger, environment]);

  const handleOpenAnalysis = async (alert) => {
    setSelectedAlert(alert);
    setModalOpen(true);
    setModalLoading(true);
    setModalData([]);
    
    // Automatically select the correct tab based on the metric
    const metricStr = (alert.metric_key || '').toLowerCase();
    if (metricStr.includes('cpu')) setModalTab(0);
    else if (metricStr.includes('memory')) setModalTab(1);
    else if (metricStr.includes('bandwidth') || metricStr.includes('network') || metricStr.includes('bits_per_sec')) setModalTab(2);
    else if (metricStr.includes('disk')) setModalTab(3);
    else setModalTab(0);
    
    try {
      const rawTs = alert.created_at_raw || alert.created_at;
      // If it contains a timezone offset (+05:30) or Z, parsing directly works well in modern browsers.
      // If it's UTC missing Z, we add Z.
      const isOffset = rawTs.includes('+') || rawTs.includes('-');
      const alertTsStr = (rawTs.includes('Z') || isOffset) ? rawTs : rawTs + 'Z';
      const alertTs = new Date(alertTsStr);
      const start = new Date(alertTs.getTime() - 60 * 60 * 1000);
      const end = new Date(alertTs.getTime() + 30 * 60 * 1000);
      
      const startFmt = formatDateTimeForAPI(start);
      const endFmt = formatDateTimeForAPI(end);
      
      const res = await axios.get('/v1/historical/bulk-server-metrics', {
        params: {
          server_id: alert.server_id,
          metric_names: ['cpu', 'memory', 'disk', 'network_bits_per_sec', 'network_bandwidth'],
          include_interfaces: true,
          start_date: startFmt.date,
          start_time: startFmt.time,
          end_date: endFmt.date,
          end_time: endFmt.time,
          step: '1m'
        },
        paramsSerializer: p => {
          const sp = new URLSearchParams();
          for (const k in p) {
            if (Array.isArray(p[k])) p[k].forEach(v => sp.append(k, v));
            else sp.append(k, p[k]);
          }
          return sp.toString();
        }
      });
      
      // Extract alert interface (e.g., 'C:' from 'disk.C:')
      let alertInterface = null;
      if (alert.metric_key && alert.metric_key.includes('.')) {
        alertInterface = alert.metric_key.split('.')[1];
      }

      const grouped = (res.data.metrics || []).reduce((acc, m) => {
        const date = new Date(m.timestamp);
        date.setSeconds(0, 0);
        const tsKey = date.toISOString();
        if (!acc[tsKey]) {
          acc[tsKey] = { 
            time: date.toLocaleString('en-IN', { 
              day: '2-digit', 
              month: '2-digit', 
              hour: '2-digit', 
              minute: '2-digit', 
              hour12: false 
            }).replace(',', ''), 
            rawTs: tsKey 
          };
        }
        const val = parseFloat(m.value) || 0;
        
        if (m.metric_name === 'cpu') acc[tsKey].cpu = val;
        if (m.metric_name === 'memory') acc[tsKey].memory = val;
        if (m.metric_name === 'disk') {
          // If no alert interface, or it matches the alert interface, or no metric interface
          if (!alertInterface || m.interface_name === alertInterface || !m.interface_name) {
            acc[tsKey].disk = val;
          }
        }
        if (m.metric_name === 'network_bits_per_sec' || m.metric_name === 'network_bandwidth') {
          if (!alertInterface || m.interface_name === alertInterface || !m.interface_name) {
            // Keep the larger value if both bandwidth and bits_per_sec are returned for some reason
            const existing = acc[tsKey].network_mbps || 0;
            const newVal = (m.metric_name === 'network_bits_per_sec') ? val / 1000000 : val;
            acc[tsKey].network_mbps = Math.max(existing, newVal);
          }
        }
        return acc;
      }, {});
      
      setModalData(Object.values(grouped).sort((a,b) => new Date(a.rawTs) - new Date(b.rawTs)));
    } catch (e) {
      console.error('Diagnostic error:', e);
    } finally {
      setModalLoading(false);
    }
  };

  const getMetricTitle = () => {
    if (modalTab === 0) return 'CPU Utilization (%)';
    if (modalTab === 1) return 'Memory Usage (%)';
    if (modalTab === 2) return 'Network Throughput (Mbps)';
    return 'HDD Usage (%)';
  };

  const getMetricKey = () => {
    if (modalTab === 0) return 'cpu';
    if (modalTab === 1) return 'memory';
    if (modalTab === 2) return 'network_mbps';
    return 'disk';
  };

  const getMetricColor = () => {
    if (modalTab === 0) return '#d32f2f';
    if (modalTab === 1) return '#1976d2';
    if (modalTab === 2) return '#9c27b0';
    return '#ed6c02';
  };

  const getAlertTimeKey = () => {
    if (!selectedAlert) return '';
    const rawTs = selectedAlert.created_at_raw || selectedAlert.created_at;
    const isOffset = rawTs.includes('+') || rawTs.includes('-');
    const date = new Date((rawTs.includes('Z') || isOffset) ? rawTs : rawTs + 'Z');
    date.setSeconds(0, 0);
    return date.toLocaleString('en-IN', { 
      day: '2-digit', 
      month: '2-digit', 
      hour: '2-digit', 
      minute: '2-digit', 
      hour12: false 
    }).replace(',', '');
  };

  const openCallFlow = async (alert) => {
    setSelectedAlert(alert);
    setCallFlowOpen(true);
    setCallFlowLoading(true);
    try {
        const res = await axios.get(`/v1/mobile/alerts/${alert.id}/call-flow`);
        setCallFlowData(res.data || []);
    } catch (e) { console.error(e); } finally { setCallFlowLoading(false); }
  };

  const triageActiveCritical = () => { setSeverity('error'); setIsResolved('false'); setPage(0); setFilterTrigger(p => p + 1); };
  const triageAllPending = () => { setSeverity(''); setIsResolved('false'); setPage(0); setFilterTrigger(p => p + 1); };
  const triageToday = () => { const d = new Date(); d.setHours(0,0,0,0); setStartDateTime(d); setEndDateTime(new Date()); setSeverity(''); setIsResolved(''); setPage(0); setFilterTrigger(p => p + 1); };

  const handleExport = async () => {
    try {
      const start = formatDateTimeForAPI(startDateTime);
      const end = formatDateTimeForAPI(endDateTime);
      const url = `/v1/alerts/export?start_date=${start.date}&start_time=${start.time}&end_date=${end.date}&end_time=${end.time}&metric_type=${metricType}&severity=${severity}&is_resolved=${isResolved === '' ? '' : isResolved === 'true'}&${new URLSearchParams(withEnvironment()).toString()}`;
      window.open(url, '_blank');
    } catch (err) {
      console.error('Export failed', err);
    }
  };

  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Container maxWidth="xl" sx={{ py: 3, ...styles }}>
        <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Box><Typography variant="h4" sx={{ fontWeight: 800, color: 'primary.main' }}>Alert Command Center</Typography><Typography variant="body2" color="text.secondary">Incident Audit Trail • All times IST</Typography></Box>
          <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
            <Button variant="outlined" startIcon={<DownloadIcon />} onClick={handleExport} sx={{ bgcolor: 'white' }}>Export to Excel</Button>
            <ButtonGroup variant="outlined" size="small" sx={{ bgcolor: 'white' }}>
              <Button onClick={triageActiveCritical} startIcon={<NotificationsActiveIcon />} sx={{ color: '#d32f2f', borderColor: '#d32f2f' }}>Active Critical</Button>
              <Button onClick={triageAllPending} startIcon={<PendingIcon />}>Pending</Button>
              <Button onClick={triageToday} startIcon={<HistoryIcon />}>Today</Button>
            </ButtonGroup>
            <IconButton onClick={fetchAlerts} color="primary" sx={{ bgcolor: 'white', boxShadow: 1 }}><RefreshIcon /></IconButton>
          </Box>
        </Box>

        <Grid container spacing={2.5} sx={{ mb: 4 }}>
          <Grid item xs={12} sm={6} md={2.4}><SummaryCard title="Total Found" value={stats.total} color="#1976d2" icon={<FilterAltIcon />} /></Grid>
          <Grid item xs={12} sm={6} md={2.4}><SummaryCard title="Active Pending" value={stats.unresolved} color="#9c27b0" icon={<PendingIcon />} active={stats.unresolved > 0} /></Grid>
          <Grid item xs={12} sm={6} md={2.4}><SummaryCard title="Active Critical" value={stats.errors} color="#d32f2f" icon={<ErrorIcon />} active={stats.errors > 0} /></Grid>
          <Grid item xs={12} sm={6} md={2.4}><SummaryCard title="Active Warning" value={stats.warnings} color="#ed6c02" icon={<WarningAmberIcon />} /></Grid>
          <Grid item xs={12} sm={6} md={2.4}><SummaryCard title="Resolved" value={stats.resolved} color="#2e7d32" icon={<CheckCircleIcon />} /></Grid>
        </Grid>

        <Paper elevation={0} sx={{ p: 2.5, mb: 3, borderRadius: '12px', border: '1px solid #e0e0e0', bgcolor: '#fcfcfc' }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={4} sx={{ display: 'flex', gap: 1 }}><DateTimePicker label="From" value={startDateTime} onChange={setStartDateTime} slotProps={{ textField: { size: 'small', fullWidth: true } }} format="dd/MM/yy HH:mm" /><DateTimePicker label="To" value={endDateTime} onChange={setEndDateTime} slotProps={{ textField: { size: 'small', fullWidth: true } }} format="dd/MM/yy HH:mm" /></Grid>
            <Grid item xs={6} md={2}><FormControl fullWidth size="small"><InputLabel>Metric</InputLabel><Select value={metricType} onChange={e => setMetricType(e.target.value)} label="Metric">{METRIC_TYPES.map(t => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}</Select></FormControl></Grid>
            <Grid item xs={6} md={2}><FormControl fullWidth size="small"><InputLabel>Severity</InputLabel><Select value={severity} onChange={e => setSeverity(e.target.value)} label="Severity">{SEVERITY_OPTIONS.map(o => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}</Select></FormControl></Grid>
            <Grid item xs={6} md={2}><FormControl fullWidth size="small"><InputLabel>Status</InputLabel><Select value={isResolved} onChange={e => setIsResolved(e.target.value)} label="Status">{RESOLVED_OPTIONS.map(o => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}</Select></FormControl></Grid>
            <Grid item xs={6} md={2}><Button variant="contained" fullWidth onClick={() => setFilterTrigger(p => p + 1)} sx={{ height: 40, fontWeight: 700 }}>Apply</Button></Grid>
          </Grid>
        </Paper>

        <Paper elevation={0} sx={{ borderRadius: '12px', border: '1px solid #e0e0e0', overflow: 'hidden' }}>
          <TableContainer sx={{ maxHeight: '60vh' }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Timestamp</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>System / IP</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Domain</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }} align="center">Severity</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }} align="center">Trend</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700, minWidth: 250 }}>Message</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }} align="center">Status</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Resolved At</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Ack By / ERT</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }}>Justification</TableCell>
                  <TableCell sx={{ bgcolor: '#1a237e', color: 'white', fontWeight: 700 }} align="center">Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading ? <TableRow><TableCell colSpan={11} align="center" sx={{ py: 5 }}><CircularProgress /></TableCell></TableRow> : alerts.map((alert) => {
                  const isActive = !alert.is_resolved; const isCrit = alert.severity === 'error';
                  return (
                    <TableRow key={alert.id} hover sx={{ bgcolor: isActive ? (isCrit ? 'rgba(211, 47, 47, 0.03)' : 'rgba(237, 108, 2, 0.02)') : 'inherit' }}>
                      <TableCell sx={{ fontWeight: isActive ? 700 : 400 }}>{alert.created_at}</TableCell>
                      <TableCell><Typography variant="body2" sx={{ fontWeight: 700 }}>{alert.server_name}</Typography><Typography variant="caption" color="text.secondary">{alert.server_ip}</Typography></TableCell>
                      <TableCell><Chip label={alert.metric_type} size="small" variant="outlined" sx={{ fontWeight: 700, fontSize: '10px' }} /><Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>{alert.metric_key}</Typography></TableCell>
                      <TableCell align="center"><Box sx={{ display: 'inline-flex', p: 0.5, borderRadius: '50%', ...(isActive ? (isCrit ? styles.pulseRed : styles.pulseOrange) : {}) }}><Chip label={isCrit ? 'CRITICAL' : 'WARNING'} size="small" color={isCrit ? 'error' : 'warning'} sx={{ fontWeight: 800, fontSize: '10px' }} /></Box></TableCell>
                      <TableCell align="center"><MiniSparkline data={trends[String(alert.id)] || []} color={isCrit ? '#d32f2f' : '#ed6c02'} onClick={() => handleOpenAnalysis(alert)} /></TableCell>
                      <TableCell><Typography variant="body2" sx={{ lineHeight: 1.2 }}>{alert.message}</Typography></TableCell>
                      <TableCell align="center"><Chip label={alert.is_resolved ? 'RESOLVED' : 'ACTIVE'} variant={alert.is_resolved ? 'outlined' : 'filled'} color={alert.is_resolved ? 'success' : 'default'} size="small" icon={alert.is_resolved ? <CheckCircleIcon /> : <NotificationsActiveIcon />} sx={{ fontWeight: 700 }} /></TableCell>
                      <TableCell sx={{ fontSize: '0.8rem' }}>{alert.resolved_at || 'Ongoing'}</TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{alert.acknowledged_by_name || '-'}</Typography>
                        {alert.ert_at && (
                          <Chip 
                            label={`ERT: ${alert.ert_at}`} 
                            size="small" 
                            color="primary" 
                            variant="outlined" 
                            sx={{ mt: 0.5, fontSize: '0.7rem' }} 
                          />
                        )}
                      </TableCell>
                      <TableCell>
                        {alert.ert_justification ? (
                          <Tooltip title={alert.ert_justification}>
                            <Typography variant="caption" sx={{ fontStyle: 'italic', color: 'text.secondary' }}>
                              {alert.ert_justification.length > 20 ? alert.ert_justification.substring(0, 20) + '...' : alert.ert_justification}
                            </Typography>
                          </Tooltip>
                        ) : '-'}
                      </TableCell>
                      <TableCell align="center"><Tooltip title="View Call Flow"><IconButton size="small" color="primary" onClick={() => openCallFlow(alert)}><HistoryIcon /></IconButton></Tooltip></TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination component="div" count={totalCount} page={page} onPageChange={(e, p) => setPage(p)} rowsPerPage={rowsPerPage} onRowsPerPageChange={e => { setRowsPerPage(parseInt(e.target.value, 10)); setPage(0); }} rowsPerPageOptions={[25, 50, 100]} />
        </Paper>

        <Dialog open={modalOpen} onClose={() => setModalOpen(false)} maxWidth="md" fullWidth TransitionComponent={Fade}>
          <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: '#f8f9fa' }}>
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 800 }}>Root Cause Analysis</Typography>
              <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                {selectedAlert?.server_name} ({selectedAlert?.server_ip}) • Breach: {
                  selectedAlert?.metric_key.includes('.') 
                    ? `${selectedAlert.metric_key.split('.')[0].toUpperCase()} [${selectedAlert.metric_key.split('.')[0] === 'disk' ? 'Partition' : 'Interface'}: ${selectedAlert.metric_key.split('.')[1]}]`
                    : selectedAlert?.metric_key?.toUpperCase()
                }
              </Typography>
            </Box>
            <IconButton onClick={() => setModalOpen(false)}><CloseIcon /></IconButton>
          </DialogTitle>
          <DialogContent sx={{ mt: 2 }}>
            <Tabs value={modalTab} onChange={(e,v) => setModalTab(v)} sx={{ mb: 3 }} variant="fullWidth">
              <Tab label="CPU" /><Tab label="Memory" /><Tab label="Network" /><Tab label="Disk" />
            </Tabs>
            {modalLoading ? (
              <Box sx={{ height: 350, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2 }}><CircularProgress /><Typography variant="body2" color="text.secondary">Fetching historical telemetry from ClickHouse...</Typography></Box>
            ) : modalData.length === 0 ? (
              <Box sx={{ height: 350, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', bgcolor: '#fafafa', borderRadius: '8px' }}><HistoryIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} /><Typography variant="h6" color="text.disabled">No telemetry available</Typography></Box>
            ) : (
              <Box sx={{ height: 350, mt: 2 }}>
                <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 700, color: getMetricColor(), display: 'flex', alignItems: 'center', gap: 1 }}><ShowChartIcon fontSize="small" /> {getMetricTitle()}</Typography>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={modalData}>
                    <defs><linearGradient id="colorMetric" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={getMetricColor()} stopOpacity={0.3}/><stop offset="95%" stopColor={getMetricColor()} stopOpacity={0}/></linearGradient></defs>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eee" />
                    <XAxis dataKey="time" minTickGap={30} fontSize={11} tick={{ fill: '#666' }} />
                    <YAxis fontSize={11} tick={{ fill: '#666' }} />
                    <RechartsTooltip formatter={(value) => [Number(value).toFixed(2), getMetricKey()]} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }} />
                    <ReferenceLine x={getAlertTimeKey()} stroke="#000" strokeWidth={2} label={{ position: 'top', value: 'ALERT', fill: '#000', fontSize: 10, fontWeight: 900 }} strokeDasharray="3 3" />
                    <Area type="monotone" dataKey={getMetricKey()} stroke={getMetricColor()} fillOpacity={1} fill="url(#colorMetric)" strokeWidth={3} isAnimationActive={true} />
                  </AreaChart>
                </ResponsiveContainer>
              </Box>
            )}
            <Box sx={{ mt: 3, p: 2, bgcolor: '#e3f2fd', borderRadius: '8px', border: '1px solid #bbdefb' }}>
              <Typography variant="body2" sx={{ fontWeight: 700, color: '#1565c0', display: 'flex', alignItems: 'center', gap: 1 }}><NotificationsActiveIcon sx={{ fontSize: 16 }} /> Operational Guidance:</Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>Review the {getMetricKey().toUpperCase()} trajectory leading up to the black dashed line.</Typography>
            </Box>
          </DialogContent>
        </Dialog>

        {/* CALL FLOW MODAL */}
        <Dialog open={callFlowOpen} onClose={() => setCallFlowOpen(false)} maxWidth="sm" fullWidth>
          <DialogTitle sx={{ bgcolor: '#f8f9fa', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Box><Typography variant="h6" fontWeight="bold">Incident Call Flow</Typography><Typography variant="caption" color="text.secondary">Lifecycle of Alert #{selectedAlert?.id}</Typography></Box>
            <IconButton onClick={() => setCallFlowOpen(false)}><CloseIcon /></IconButton>
          </DialogTitle>
          <DialogContent sx={{ p: 0 }}>
            {callFlowLoading ? <Box sx={{ p: 5, textAlign: 'center' }}><CircularProgress /></Box> : (
              <List sx={{ p: 2 }}>
                {callFlowData.length === 0 ? <Box sx={{ p: 3, textAlign: 'center' }}><Typography color="text.secondary">No flow data recorded for this incident.</Typography></Box> : callFlowData.map((step, idx) => (
                  <ListItem key={step.id} sx={{ mb: 2, alignItems: 'flex-start', borderLeft: '2px solid #1a237e', ml: 1, pl: 3 }}>
                    <ListItemIcon sx={{ minWidth: 40, mt: 0.5 }}>
                        {step.action === 'Triggered' && <NotificationsActiveIcon color="error" />}
                        {step.action === 'Acknowledge' && <AssignmentIndIcon color="primary" />}
                        {step.action === 'ERT Expired' && <AccessTimeIcon color="warning" />}
                        {step.action === 'Resolved' && <CheckCircleIcon color="success" />}
                    </ListItemIcon>
                    <ListItemText 
                        primary={<Box sx={{ display: 'flex', justifyContent: 'space-between' }}><Typography fontWeight="bold" variant="body1">{step.action}</Typography><Typography variant="caption" color="text.secondary">{step.timestamp}</Typography></Box>}
                        secondary={
                            <Box sx={{ mt: 0.5 }}>
                                <Typography variant="body2" color="text.primary">By: <strong>{step.user}</strong></Typography>
                                {step.details?.ert_minutes && <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}><AccessTimeIcon sx={{ fontSize: 14 }} /> Commitment: {formatCommitment(step.details.ert_minutes)}</Typography>}
                                {step.details?.justification && <Typography variant="body2" sx={{ bgcolor: '#fff9c4', p: 1, borderRadius: 1, mt: 1, fontStyle: 'italic' }}><CommentIcon sx={{ fontSize: 14, mr: 0.5 }} /> "{step.details.justification}"</Typography>}
                                {step.details?.failed_step !== undefined && <Typography variant="body2" color="error">Escalation Level {step.details.failed_step + 1} failed to resolve.</Typography>}
                            </Box>
                        }
                    />
                  </ListItem>
                ))}
              </List>
            )}
          </DialogContent>
        </Dialog>
      </Container>
    </LocalizationProvider>
  );
};

export default AlertHistory;
