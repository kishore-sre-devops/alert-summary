import React, { useEffect, useState, useCallback, useRef } from "react";
import { useLocation, Link } from "react-router-dom";
import {
  Box,
  Paper,
  Button,
  TextField,
  Typography,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Menu,
  MenuItem,
  Alert,
  CircularProgress,
  Chip,
  Select,
  FormControl,
  Container,
  Grid,
  Tooltip,
  TablePagination,
  Card,
  CardHeader,
  CardContent,
  LinearProgress
} from "@mui/material";
import Delete from "@mui/icons-material/Delete";
import DeleteSweep from "@mui/icons-material/DeleteSweep";
import Edit from "@mui/icons-material/Edit";
import AddIcon from "@mui/icons-material/Add";
import SwapHoriz from "@mui/icons-material/SwapHoriz";
import TerminalIcon from "@mui/icons-material/Terminal";
import DesktopWindowsIcon from "@mui/icons-material/DesktopWindows";
import AppleIcon from "@mui/icons-material/Apple";
import StorageIcon from "@mui/icons-material/Storage";
import ComputerIcon from "@mui/icons-material/Computer";
import SearchIcon from "@mui/icons-material/Search";
import CloudIcon from "@mui/icons-material/Cloud";
import PlaceIcon from "@mui/icons-material/Place";
import axios from "../utils/axiosConfig";
import { useEnvironment } from '../hooks/useEnvironment';

export default function Servers() {
  const { environment, withEnvironment } = useEnvironment();
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [moveMenuAnchor, setMoveMenuAnchor] = useState(null);
  const [selectedServerForMove, setSelectedServerForMove] = useState(null);
  const [formData, setFormData] = useState({
    name: "",
    ip: "",
    status: "offline",
    environment: "prod"
  });
  const [hardwareThresholds, setHardwareThresholds] = useState({});
  const hardwareThresholdsRef = useRef({});

  // Sync state to ref for use in WebSocket handler without re-running effect
  useEffect(() => {
    hardwareThresholdsRef.current = hardwareThresholds;
  }, [hardwareThresholds]);
  const [wsConnected, setWsConnected] = useState(false);
  const [locationFilter, setLocationFilter] = useState("");
  
  // Pagination & Search state
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [totalCount, setTotalCount] = useState(0);
  const [systemStats, setSystemStats] = useState({ total: 0, up: 0, down: 0, warn: 0, crit: 0 });
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // LAMA Metrics Summary state
  const [lamaMetricsSummary, setLamaMetricsSummary] = useState({
    hardware: { success: 0, failed: 0, total: 0, last_sent: null },
    network: { success: 0, failed: 0, total: 0, last_sent: null },
    application: { success: 0, failed: 0, total: 0, last_sent: null, enabled: false },
    database: { success: 0, failed: 0, total: 0, last_sent: null, enabled: false },
  });
  const [loadingMetrics, setLoadingMetrics] = useState(false);
  const [timeRange, setTimeRange] = useState('24h');

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(0); // Reset to first page on new search
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Refs for throttling WebSocket updates to prevent re-render storm
  const updateBufferRef = useRef({});
  const lastUpdateRef = useRef(0);
  const ws = useRef(null);

  const getOsIcon = (osType) => {
    const type = (osType || '').toLowerCase();
    
    // Windows - Professional 4-pane logo
    if (type.includes('win')) {
      return (
        <Tooltip title="Windows Server">
          <Box component="svg" viewBox="0 0 24 24" sx={{ width: 18, height: 18, fill: '#0078D7', verticalAlign: 'middle' }}>
            <path d="M0 3.449L9.75 2.1L9.751 11.25H0V3.449zm0 8.551h9.751v9.15L0 19.801V12zm10.55 0h13.45v9.525l-13.45-1.875V12zm0-9.9L24 0v11.25H10.55V2.1z" />
          </Box>
        </Tooltip>
      );
    }
    
    // Linux (Ubuntu/Orange style)
    if (type.includes('linux') || type.includes('ubuntu') || type.includes('centos') || type.includes('redhat') || type.includes('debian')) {
      return (
        <Tooltip title="Linux Server">
          <TerminalIcon fontSize="small" sx={{ color: '#E95420' }} />
        </Tooltip>
      );
    }
    
    // macOS
    if (type.includes('mac') || type.includes('darwin') || type.includes('apple')) {
      return (
        <Tooltip title="macOS">
          <AppleIcon fontSize="small" sx={{ color: '#555555' }} />
        </Tooltip>
      );
    }
    
    // Database
    if (type.includes('db') || type.includes('database') || type.includes('sql') || type.includes('mongo') || type.includes('redis')) {
      return (
        <Tooltip title="Database Server">
          <StorageIcon fontSize="small" sx={{ color: '#4CAF50' }} />
        </Tooltip>
      );
    }

    // Cloud / AWS / ECS
    if (type.includes('aws') || type.includes('cloud') || type.includes('ecs') || type.includes('lambda')) {
      return (
        <Tooltip title="Cloud Resource (AWS)">
          <CloudIcon fontSize="small" sx={{ color: '#FF9900' }} />
        </Tooltip>
      );
    }
    
    // Default / Unknown
    return (
      <Tooltip title="Generic / Unknown OS">
        <ComputerIcon fontSize="small" sx={{ color: '#757575' }} />
      </Tooltip>
    );
  };

  const getLocationChip = (locationId) => {
    switch (locationId) {
      case 1: 
        return <Chip size="small" icon={<PlaceIcon style={{ fontSize: 16, color: '#00695c' }} />} label="DC" sx={{ height: 28, fontSize: '0.9rem', bgcolor: '#e0f2f1', color: '#00695c', border: '1px solid #00695c', fontWeight: 'bold', px: 0.5 }} />;
      case 2: 
        return <Chip size="small" icon={<PlaceIcon style={{ fontSize: 16, color: '#e65100' }} />} label="DR" sx={{ height: 28, fontSize: '0.9rem', bgcolor: '#fff3e0', color: '#e65100', border: '1px solid #e65100', fontWeight: 'bold', px: 0.5 }} />;
      case 3: 
        return <Chip size="small" icon={<CloudIcon style={{ fontSize: 16, color: '#4a148c' }} />} label="Cloud" sx={{ height: 28, fontSize: '0.9rem', bgcolor: '#f3e5f5', color: '#4a148c', border: '1px solid #4a148c', fontWeight: 'bold', px: 0.5 }} />;
      default: 
        return <Chip size="small" label="Unknown" sx={{ height: 28, fontSize: '0.9rem' }} />;
    }
  };

  const calculateEnhancedStatus = useCallback((serverData, thresholds) => {
    let calculatedStatus = serverData.status;
    
    // If server is online but has high resource usage, mark as WARNING or CRITICAL
    if (serverData.status === 'online' && !serverData.is_inactive) {
      const cpu = parseFloat(serverData.cpu) || 0;
      const memory = parseFloat(serverData.memory) || 0;
      const disk = parseFloat(serverData.disk) || 0;

      const getThresholds = (metricKey) => {
        let warning = 101;
        let error = 101;
        if (thresholds && thresholds[metricKey]) {
          warning = thresholds[metricKey].warning;
          error = thresholds[metricKey].error;
        }
        return { warning, error };
      };
      
      const cpuT = getThresholds('cpu');
      const memT = getThresholds('memory');
      const diskT = getThresholds('disk');

      if (cpu >= cpuT.error || memory >= memT.error || disk >= diskT.error) {
        calculatedStatus = 'critical';
      } else if (cpu >= cpuT.warning || memory >= memT.warning || disk >= diskT.warning) {
        calculatedStatus = 'warning';
      }
    }
    return calculatedStatus;
  }, []);

  // Fetch LAMA metrics summary
  const fetchLamaMetricsSummary = useCallback(async () => {
    try {
      setLoadingMetrics(true);
      
      const now = new Date();
      let hours = 24;
      if (timeRange === '30m') hours = 0.5;
      else if (timeRange === '1h') hours = 1;
      else if (timeRange === '3h') hours = 3;
      else if (timeRange === '6h') hours = 6;
      else if (timeRange === '12h') hours = 12;
      else if (timeRange === '24h') hours = 24;
      
      const startDt = new Date(now.getTime() - hours * 60 * 60 * 1000);
      const endDt = now;

      const apiStartDate = startDt.toISOString().split('T')[0];
      const apiStartTime = startDt.toISOString().split('T')[1].split('.')[0];
      const apiEndDate = endDt.toISOString().split('T')[0];
      const apiEndTime = endDt.toISOString().split('T')[1].split('.')[0];

      const summaryResponse = await axios.get('/v1/historical/exchange-transactions-summary', {
        params: {
          ...withEnvironment(),
          start_date: apiStartDate,
          start_time: apiStartTime,
          end_date: apiEndDate,
          end_time: apiEndTime,
        },
      });
      
      const backendSummary = summaryResponse.data || {};
      
      let appEnabled = true;
      let dbEnabled = true;
      try {
        const sourcesResponse = await axios.get('/v1/metric-sources', {
          params: withEnvironment(),
        });
        const appConfigs = sourcesResponse.data || [];
        // Show if configs exist OR if data was sent in recently
        appEnabled = appConfigs.length > 0 || (backendSummary.application?.total || 0) > 0;
        
        const dbConfigResponse = await axios.get('/v1/database-config/', {
          params: withEnvironment(),
        });
        const dbConfigs = Array.isArray(dbConfigResponse.data) ? dbConfigResponse.data : (dbConfigResponse.data?.configs || []);
        // Show if configs exist OR if data was sent in recently
        dbEnabled = dbConfigs.length > 0 || (backendSummary.database?.total || 0) > 0;
      } catch (e) {
        // On error (like 403 or network), default to showing the cards
        appEnabled = true;
        dbEnabled = true;
      }
      
      const summary = {
        hardware: { success: backendSummary.hardware?.success || 0, failed: backendSummary.hardware?.failed || 0, total: backendSummary.hardware?.total || 0, last_sent: null },
        network: { success: backendSummary.network?.success || 0, failed: backendSummary.network?.failed || 0, total: backendSummary.network?.total || 0, last_sent: null },
        application: { success: backendSummary.application?.success || 0, failed: backendSummary.application?.failed || 0, total: backendSummary.application?.total || 0, last_sent: null, enabled: appEnabled },
        database: { success: backendSummary.database?.success || 0, failed: backendSummary.database?.failed || 0, total: backendSummary.database?.total || 0, last_sent: null, enabled: dbEnabled },
      };
      
      setLamaMetricsSummary(summary);
    } catch (error) {
      console.error('Error fetching LAMA metrics summary:', error);
    } finally {
      setLoadingMetrics(false);
    }
  }, [withEnvironment, timeRange]);

  // Fetch LAMA metrics summary on mount and when environment or timeRange changes
  useEffect(() => {
    fetchLamaMetricsSummary();
    const metricsInterval = setInterval(fetchLamaMetricsSummary, 60000); // Refresh every minute
    return () => clearInterval(metricsInterval);
  }, [fetchLamaMetricsSummary]);

  const loadServers = useCallback(async (thresholds = null, silent = false) => {
    try {
      if (!silent) setLoading(true);
      
      
      const currentThresholds = thresholds || hardwareThresholds || {};
      
      const params = {
        ...withEnvironment(),
        location_id: locationFilter || undefined,
        page: page + 1, // API is 1-indexed, MUI is 0-indexed
        size: rowsPerPage,
        search: debouncedSearch
      };

      const res = await axios.get(`/v1/servers/`, {
        params: params,
        headers: {  }
      });
      
      // Handle PaginatedServerResponse structure
      const serversData = res.data?.items || [];
      const total = res.data?.total_count || 0;
      setTotalCount(total);
      
      // Use summary from backend for system stats
      if (res.data?.summary) {
        setSystemStats(res.data.summary);
      }
      
      // Calculate server status with WARNING and CRITICAL detection
      const enhancedServers = serversData.map(server => {
        const calculatedStatus = calculateEnhancedStatus(server, currentThresholds);
        return { ...server, calculatedStatus };
      });
      
      // Sorting is now handled by the backend to ensure consistency across pages
      setServers(enhancedServers);
      setLastRefresh(new Date());
      setError("");
    } catch (e) {
      setError("Failed to load servers");
      console.error(e);
      setServers([]); // Set empty array on error
    } finally {
      if (!silent) setLoading(false);
    }
  }, [withEnvironment, calculateEnhancedStatus, page, rowsPerPage, debouncedSearch, locationFilter]);

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
      return map;
    } catch (error) {
      console.error('Error fetching thresholds:', error);
      return {};
    }
  };

  // Get current user role from localStorage
  const currentUserRole = sessionStorage.getItem('lama_user_role') || 'user';
  const isAdmin = currentUserRole === 'admin';
  
  const location = useLocation(); // Track navigation changes

  // WebSocket for Real-time Updates
  useEffect(() => {
    let reconnectTimer;

    const connectWS = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws/updates`;

      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        console.log('✅ WebSocket Connected (Servers Page)');
        setWsConnected(true);
      };

      ws.current.onmessage = (event) => {
        if (event.data === 'pong') return;

        try {
          const message = JSON.parse(event.data);
          if (message.server_id && message.data) {
            const serverId = message.server_id;
            
            // Buffer the update
            updateBufferRef.current[serverId] = {
              ...updateBufferRef.current[serverId],
              ...message.data,
              type: message.type
            };

            // Process buffer every 2 seconds to handle high-volume updates efficiently
            const now = Date.now();
            if (now - lastUpdateRef.current > 2000) {
              const buffer = { ...updateBufferRef.current };
              updateBufferRef.current = {}; // Clear buffer
              lastUpdateRef.current = now;

              setServers(prevServers => {
                let hasChanges = false;
                const nextServers = prevServers.map(server => {
                  const update = buffer[server.id];
                  if (update) {
                    hasChanges = true;
                    const updatedServer = { ...server, last_seen: new Date().toISOString() };
                    
                    // Update metrics
                    if (update.cpu !== undefined) updatedServer.cpu = parseFloat(update.cpu);
                    if (update.memory !== undefined) updatedServer.memory = parseFloat(update.memory);
                    if (update.memory_used_bytes !== undefined) updatedServer.memory_used_bytes = parseFloat(update.memory_used_bytes);
                    if (update.memory_total_bytes !== undefined) updatedServer.memory_total_bytes = parseFloat(update.memory_total_bytes);
                    if (update.disk !== undefined) updatedServer.disk = parseFloat(update.disk);
                    if (update.disk_used_bytes !== undefined) updatedServer.disk_used_bytes = parseFloat(update.disk_used_bytes);
                    if (update.disk_total_bytes !== undefined) updatedServer.disk_total_bytes = parseFloat(update.disk_total_bytes);
                    if (update.network_bits_per_sec !== undefined) updatedServer.network_bits_per_sec = parseFloat(update.network_bits_per_sec);
                    if (update.uptime !== undefined) updatedServer.uptime = parseFloat(update.uptime);
                    
                    // Update status and re-calculate enhanced status
                    if (update.status !== undefined) updatedServer.status = update.status;
                    
                    // Always re-calculate calculatedStatus using current thresholds
                    updatedServer.calculatedStatus = calculateEnhancedStatus(updatedServer, hardwareThresholdsRef.current);
                    
                    return updatedServer;
                  }
                  return server;
                });
                return hasChanges ? nextServers : prevServers;
              });
            }
          }
        } catch (e) {
          if (event.data !== 'pong') console.warn('WS error:', e);
        }
      };

      ws.current.onclose = () => {
        setWsConnected(false);
        // Only reconnect if not intentionally closed by cleanup
        if (ws.current && !ws.current._intentional_close) {
            reconnectTimer = setTimeout(connectWS, 5000);
        }
      };
    };

    connectWS();

    return () => {
      if (ws.current) {
          ws.current._intentional_close = true;
          ws.current.close();
      }
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
  }, [calculateEnhancedStatus]);

  useEffect(() => {
    const init = async () => {
      const thresholds = await fetchThresholds();
      loadServers(thresholds, false);
    };
    init();
  }, [location.pathname, environment, loadServers, page, rowsPerPage, debouncedSearch, locationFilter]);

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // Auto-refresh every 30 seconds to sync with dashboard behavior
  useEffect(() => {
    const interval = setInterval(() => {
      // Use silent refresh to avoid spinner
      if (hardwareThresholds) {
        loadServers(hardwareThresholds, true);
      }
    }, 10000); 

    return () => {
      clearInterval(interval);
    };
  }, [hardwareThresholds, loadServers]);

  const openCreateDialog = () => {
    setFormData({ name: "", ip: "", status: "offline", environment: environment, os_type: "Linux" });
    setEditingId(null);
    setOpenDialog(true);
  };

  const openEditDialog = (server) => {
    let detectedIps = [];
    if (Array.isArray(server.detected_ips)) {
      detectedIps = server.detected_ips;
    } else if (typeof server.detected_ips === 'string') {
      try {
        detectedIps = JSON.parse(server.detected_ips);
      } catch (e) {
        console.error("Failed to parse detected_ips:", server.detected_ips);
        detectedIps = [];
      }
    }

    setFormData({ 
      name: server.name, 
      ip: server.ip, 
      status: server.status,
      environment: server.environment || 'prod',
      os_type: server.os || 'Linux',
      location_id: server.location_id || 1,
      detected_ips: detectedIps
    });
    setEditingId(server.id);
    setOpenDialog(true);
  };

  const closeDialog = () => {
    setOpenDialog(false);
    setFormData({ name: "", ip: "", status: "offline", environment: environment, os_type: "Linux", location_id: 1 });
  };

  const handleMoveClick = (event, server) => {
    setMoveMenuAnchor(event.currentTarget);
    setSelectedServerForMove(server);
  };

  const handleMoveClose = () => {
    setMoveMenuAnchor(null);
    setSelectedServerForMove(null);
  };

  const moveServer = async (targetEnvironment) => {
    if (!selectedServerForMove) return;
    
    try {
      
      await axios.post(`/v1/servers/${selectedServerForMove.id}/move`, 
        { environment: targetEnvironment },
        { headers: {  } }
      );
      await loadServers(hardwareThresholds);
      handleMoveClose();
      setError("");
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to move server");
      handleMoveClose();
    }
  };

  const saveServer = async () => {
    if (!formData.name || !formData.ip) {
      setError("Name and IP are required.");
      return;
    }

    try {
      
      console.log("Saving server data:", formData);
      
      if (editingId) {
        await axios.put(`/v1/servers/${editingId}`, formData, {
          headers: {  }
        });
        console.log("Server updated successfully");
      } else {
        const serverData = { ...formData, environment: formData.environment || environment };
        await axios.post('/v1/servers/', serverData, {
          headers: {  }
        });
        console.log("Server created successfully");
      }
      
      closeDialog();
      setError("");
      
      console.log("Reloading servers...");
      await loadServers(hardwareThresholds);
      console.log("Servers reloaded");
    } catch (e) {
      console.error("Error saving server:", e);
      setError(e.response?.data?.detail || "Failed to save server");
    }
  };

  const deleteServer = async (id) => {
    if (!window.confirm("Are you sure you want to delete this server?")) return;

    try {
      
      await axios.delete(`/v1/servers/${id}`, {
        headers: {  }
      });
      await loadServers(hardwareThresholds);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to delete server");
    }
  };

  const deleteInactiveServers = async () => {
    const inactiveMinutes = window.prompt("Minutes since last heartbeat to consider inactive (default: 5):", "5");
    if (inactiveMinutes === null) return;
    
    const minutes = parseInt(inactiveMinutes) || 5;
    if (!window.confirm(`Permanently delete all servers inactive for ${minutes}+ mins?`)) return;

    try {
      setLoading(true);
      
      await axios.delete(`/v1/servers/inactive/bulk`, {
        params: withEnvironment({ inactive_minutes: minutes }),
        headers: {  }
      });
      await loadServers(hardwareThresholds);
    } catch (e) {
      setError("Failed: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    return status === "online" ? "success" : status === "warning" ? "warning" : status === "critical" ? "error" : "error";
  };

  const formatMbps = (value) => {
    const bps = parseFloat(value || 0);
    if (Number.isNaN(bps) || bps === 0) return '0 Mbps';
    const mbps = bps / 1000000;
    if (mbps >= 1000) return `${(mbps / 1000).toFixed(2)} Gbps`;
    return `${mbps.toFixed(2)} Mbps`;
  };

  const formatLastSeen = (lastSeenString) => {
    if (!lastSeenString) return 'Never';
    try {
      const lastSeen = new Date(lastSeenString);
      const now = new Date();
      const diffMs = now - lastSeen;
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins} min ago`;
      const diffHours = Math.floor(diffMs / 3600000);
      if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
      return lastSeen.toLocaleDateString() + ' ' + lastSeen.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) { return 'Unknown'; }
  };

  // Helper to clean hostname (remove IP if present in parens)
  const cleanName = (name) => {
    if (!name) return '';
    return name.replace(/\s*\(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\)$/, '');
  };

  const formatUptime = (seconds) => {
    if (!seconds || seconds < 0) return 'N/A';
    const totalSeconds = Math.floor(seconds);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    
    const parts = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    
    return parts.length > 0 ? parts.join(' ') : '< 1m';
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 'bold' }}>🖥️ Servers Management</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
            Last updated: {lastRefresh.toLocaleTimeString('en-IN', { hour12: false })} IST • Auto-refresh: 10s
          </Typography>
        </Box>
        <Chip 
          label={wsConnected ? "REAL-TIME CONNECTED" : "CONNECTING..."} 
          color={wsConnected ? "success" : "warning"} 
          size="small"
          sx={{ fontWeight: 'bold' }}
        />
      </Box>
        
      {/* Status Cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'TOTAL', value: systemStats.total, color: '#2196F3', bg: '#e3f2fd' },
          { label: '🟢 UP', value: systemStats.up, color: '#4CAF50', bg: '#e8f5e9' },
          { label: '🔴 CRIT', value: systemStats.crit, color: '#F44336', bg: '#ffebee' },
          { label: '🟡 WARN', value: systemStats.warn, color: '#FF9800', bg: '#fff3e0' },
          { label: '🔴 DOWN', value: systemStats.down, color: '#9e9e9e', bg: '#f5f5f5' }
        ].map((stat, i) => (
          <Grid item xs={2.4} key={i}>
            <Paper sx={{ p: 2, textAlign: 'center', backgroundColor: stat.bg, borderLeft: `4px solid ${stat.color}` }}>
              <Typography variant="h6" sx={{ color: stat.color, fontWeight: 'bold', fontSize: '0.875rem' }}>{stat.label}</Typography>
              <Typography variant="h4" sx={{ fontWeight: 'bold', fontSize: '2rem' }}>{stat.value}</Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      {/* LAMA Metrics Summary */}
      <Card sx={{ mb: 3, border: '1px solid #e0e0e0' }}>
        <CardHeader
          title={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="h6" sx={{ fontWeight: 'bold', fontSize: '1rem' }}>
                📊 LAMA Exchange Metrics Summary
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 'normal' }}>
                ({timeRange === '30m' ? 'Last 30m' : `Last ${timeRange}`})
              </Typography>
            </Box>
          }
          action={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <Select
                  value={timeRange}
                  onChange={(e) => setTimeRange(e.target.value)}
                  sx={{ fontSize: '0.8125rem', height: 28, bgcolor: 'white' }}
                >
                  <MenuItem value="30m">Last 30m</MenuItem>
                  <MenuItem value="1h">Last 1h</MenuItem>
                  <MenuItem value="3h">Last 3h</MenuItem>
                  <MenuItem value="6h">Last 6h</MenuItem>
                  <MenuItem value="12h">Last 12h</MenuItem>
                  <MenuItem value="24h">Last 24h</MenuItem>
                </Select>
              </FormControl>
              <Button 
                component={Link} 
                to="/exchange-activity" 
                size="small" 
                variant="outlined"
                sx={{ fontSize: '0.75rem', height: 28, fontWeight: 'bold' }}
              >
                View Logs
              </Button>
            </Box>
          }
          sx={{ bgcolor: '#f8f9fa', py: 1, borderBottom: '1px solid #e0e0e0' }}
        />
        <CardContent>
          {loadingMetrics ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={2}>
              {/* Hardware Metrics */}
              <Grid item xs={6} sm={3}>
                <Paper sx={{ p: 2, textAlign: 'center', backgroundColor: '#e8f5e9', border: '1px solid #c8e6c9' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#2e7d32', mb: 1 }}>
                    🖥️ Hardware
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-around' }}>
                    <Box>
                      <Typography variant="h5" sx={{ color: '#4caf50', fontWeight: 'bold' }}>
                        {lamaMetricsSummary.hardware.success}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#666' }}>Success</Typography>
                    </Box>
                    <Box>
                      <Typography variant="h5" sx={{ color: '#f44336', fontWeight: 'bold' }}>
                        {lamaMetricsSummary.hardware.failed}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#666' }}>Failed</Typography>
                    </Box>
                  </Box>
                  {lamaMetricsSummary.hardware.total > 0 && (
                    <Typography variant="caption" sx={{ color: '#666', mt: 1, display: 'block' }}>
                      Out of {lamaMetricsSummary.hardware.total} transactions
                    </Typography>
                  )}
                </Paper>
              </Grid>

              {/* Network Metrics */}
              <Grid item xs={6} sm={3}>
                <Paper sx={{ p: 2, textAlign: 'center', backgroundColor: '#e3f2fd', border: '1px solid #bbdefb' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1565c0', mb: 1 }}>
                    🌐 Network
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-around' }}>
                    <Box>
                      <Typography variant="h5" sx={{ color: '#4caf50', fontWeight: 'bold' }}>
                        {lamaMetricsSummary.network.success}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#666' }}>Success</Typography>
                    </Box>
                    <Box>
                      <Typography variant="h5" sx={{ color: '#f44336', fontWeight: 'bold' }}>
                        {lamaMetricsSummary.network.failed}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#666' }}>Failed</Typography>
                    </Box>
                  </Box>
                  {lamaMetricsSummary.network.total > 0 && (
                    <Typography variant="caption" sx={{ color: '#666', mt: 1, display: 'block' }}>
                      Out of {lamaMetricsSummary.network.total} transactions
                    </Typography>
                  )}
                </Paper>
              </Grid>

              {/* Application Metrics - Only show if enabled */}
              {lamaMetricsSummary.application.enabled !== false && (
                <Grid item xs={6} sm={3}>
                  <Paper sx={{ p: 2, textAlign: 'center', backgroundColor: '#fff3e0', border: '1px solid #ffe0b2' }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#ef6c00', mb: 1 }}>
                      📱 Application
                    </Typography>
                    <Box sx={{ display: 'flex', justifyContent: 'space-around' }}>
                      <Box>
                        <Typography variant="h5" sx={{ color: '#4caf50', fontWeight: 'bold' }}>
                          {lamaMetricsSummary.application.success}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#666' }}>Success</Typography>
                      </Box>
                      <Box>
                        <Typography variant="h5" sx={{ color: '#f44336', fontWeight: 'bold' }}>
                          {lamaMetricsSummary.application.failed}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#666' }}>Failed</Typography>
                      </Box>
                    </Box>
                    {lamaMetricsSummary.application.total > 0 && (
                      <Typography variant="caption" sx={{ color: '#666', mt: 1, display: 'block' }}>
                        Out of {lamaMetricsSummary.application.total} transactions
                      </Typography>
                    )}
                  </Paper>
                </Grid>
              )}

              {/* Database Metrics - Only show if enabled */}
              {lamaMetricsSummary.database.enabled !== false && (
                <Grid item xs={6} sm={3}>
                  <Paper sx={{ p: 2, textAlign: 'center', backgroundColor: '#f3e5f5', border: '1px solid #e1bee7' }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#7b1fa2', mb: 1 }}>
                      🗄️ Database
                    </Typography>
                    <Box sx={{ display: 'flex', justifyContent: 'space-around' }}>
                      <Box>
                        <Typography variant="h5" sx={{ color: '#4caf50', fontWeight: 'bold' }}>
                          {lamaMetricsSummary.database.success}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#666' }}>Success</Typography>
                      </Box>
                      <Box>
                        <Typography variant="h5" sx={{ color: '#f44336', fontWeight: 'bold' }}>
                          {lamaMetricsSummary.database.failed}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#666' }}>Failed</Typography>
                      </Box>
                    </Box>
                    {lamaMetricsSummary.database.total > 0 && (
                      <Typography variant="caption" sx={{ color: '#666', mt: 1, display: 'block' }}>
                        Out of {lamaMetricsSummary.database.total} transactions
                      </Typography>
                    )}
                  </Paper>
                </Grid>
              )}
            </Grid>
          )}
        </CardContent>
      </Card>

      <Paper sx={{ p: 0, boxShadow: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: 'center', p: 2.5, gap: 2, flexWrap: 'wrap' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="h6" sx={{ fontWeight: 'bold' }}>All Servers</Typography>
            <TextField
              size="small"
              placeholder="Search by Name or IP..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              InputProps={{
                startAdornment: <SearchIcon sx={{ color: 'text.secondary', mr: 1 }} fontSize="small" />,
              }}
              sx={{ width: 250 }}
            />
            <FormControl size="small" sx={{ minWidth: 150 }}>
              <Select
                value={locationFilter || ""}
                onChange={(e) => {
                  const val = e.target.value;
                  setLocationFilter(val === "" ? "" : parseInt(val));
                  setPage(0);
                }}
                displayEmpty
              >
                <MenuItem value="">All Locations</MenuItem>
                <MenuItem value={1}>DC (Data Center)</MenuItem>
                <MenuItem value={2}>DR (Disaster Recovery)</MenuItem>
                <MenuItem value={3}>Cloud / AWS</MenuItem>
              </Select>
            </FormControl>
          </Box>
          {isAdmin ? (
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button variant="outlined" color="error" startIcon={<DeleteSweep />} onClick={deleteInactiveServers} disabled={loading}>Remove Inactive</Button>
              <Button variant="contained" startIcon={<AddIcon />} onClick={openCreateDialog}>Add Server</Button>
            </Box>
          ) : (
            <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>Read-only access</Typography>
          )}
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2, mx: 2 }}>{error}</Alert>}

        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead sx={{ bgcolor: '#1a237e', '& th': { color: 'white', fontWeight: 700, py: 1.5 } }}>
              <TableRow>
                <TableCell sx={{ minWidth: '180px' }}>Hostname</TableCell>
                <TableCell sx={{ minWidth: '150px' }}>OS</TableCell>
                <TableCell sx={{ minWidth: '120px' }}>IP Address</TableCell>
                <TableCell>Location</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">CPU</TableCell>
                <TableCell align="right">Memory</TableCell>
                <TableCell align="right">Disk</TableCell>
                <TableCell align="right">Network</TableCell>
                <TableCell>Uptime</TableCell>
                <TableCell>Last Seen</TableCell>
                <TableCell>Env</TableCell>
                {isAdmin && <TableCell align="right">Actions</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {servers.map((server) => (
                <TableRow key={server.id} hover>
                  <TableCell sx={{ fontWeight: '500', wordBreak: 'break-word' }}>
                    <Link 
                      to={`/servers/${server.id}`} 
                      style={{ 
                        textDecoration: 'none', 
                        color: '#1976d2', 
                        fontWeight: 'bold',
                        display: 'block',
                        width: '100%',
                        minHeight: '20px'
                      }}
                    >
                      {cleanName(server.name) || server.ip || `Server-${server.id}`}
                    </Link>
                    {server.resource_id && server.resource_id !== server.ip && (
                      <Typography variant="caption" display="block" sx={{ color: 'text.secondary', fontSize: '0.65rem', mt: 0.2 }}>
                        {server.resource_id}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {getOsIcon(server.os_type)}
                      <Typography variant="body2" sx={{ lineHeight: 1.2 }}>
                        {server.os_name || server.os || 'Linux'}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell sx={{ fontSize: '0.8125rem' }}>{server.ip}</TableCell>
                  <TableCell>
                    {getLocationChip(server.location_id)}
                  </TableCell>
                  <TableCell>
                    <Chip label={server.calculatedStatus?.toUpperCase() || 'OFFLINE'} color={getStatusColor(server.calculatedStatus)} variant="outlined" size="small" sx={{ fontSize: '0.7rem', fontWeight: 'bold' }} />
                  </TableCell>
                  <TableCell align="right">
                    <Box sx={{ bgcolor: server.is_inactive ? '#999' : (server.cpu || 0) > (hardwareThresholds['cpu']?.error || 101) ? '#F44336' : (server.cpu || 0) > (hardwareThresholds['cpu']?.warning || 101) ? '#FF9800' : '#4CAF50', color: 'white', px: 1, py: 0.5, borderRadius: 1, fontSize: '0.75rem', fontWeight: 'bold', minWidth: 45, display: 'inline-block', textAlign: 'center' }}>
                      {(server.is_inactive ? 0 : (server.cpu || 0)).toFixed(1)}%
                    </Box>
                  </TableCell>
                  <TableCell align="right">
                    <Box sx={{ bgcolor: server.is_inactive ? '#999' : (server.memory || 0) > (hardwareThresholds['memory']?.error || 101) ? '#F44336' : (server.memory || 0) > (hardwareThresholds['memory']?.warning || 101) ? '#FF9800' : '#4CAF50', color: 'white', px: 1, py: 0.5, borderRadius: 1, fontSize: '0.75rem', fontWeight: 'bold', minWidth: 45, display: 'inline-block', textAlign: 'center' }}>
                      {server.memory_total_bytes > 0 
                        ? `${(server.memory_used_bytes / (1024**3)).toFixed(1)} / ${(server.memory_total_bytes / (1024**3)).toFixed(1)} GB`
                        : `${(server.is_inactive ? 0 : (server.memory || 0)).toFixed(1)}%`
                      }
                    </Box>
                  </TableCell>
                  <TableCell align="right">
                    <Box sx={{ bgcolor: server.is_inactive ? '#999' : (server.disk || 0) > (hardwareThresholds['disk']?.error || 101) ? '#F44336' : (server.disk || 0) > (hardwareThresholds['disk']?.warning || 101) ? '#FF9800' : '#4CAF50', color: 'white', px: 1, py: 0.5, borderRadius: 1, fontSize: '0.75rem', fontWeight: 'bold', minWidth: 45, display: 'inline-block', textAlign: 'center' }}>
                      {server.disk_total_bytes > 0 
                        ? `${(server.disk_used_bytes / (1024**3)).toFixed(1)} / ${(server.disk_total_bytes / (1024**3)).toFixed(1)} GB`
                        : `${(server.is_inactive ? 0 : (server.disk || 0)).toFixed(1)}%`
                      }
                    </Box>
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 'bold', color: server.is_inactive ? '#999' : '#9C27B0' }}>{formatMbps(server.network_bits_per_sec)}</TableCell>
                  <TableCell sx={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#1565c0' }}>{formatUptime(server.uptime)}</TableCell>
                  <TableCell sx={{ fontSize: '0.75rem' }}>{formatLastSeen(server.last_seen)}</TableCell>
                  <TableCell><Chip label={(server.environment || 'prod').toUpperCase()} size="small" sx={{ bgcolor: (server.environment || 'prod') === 'uat' ? '#FF9800' : '#4CAF50', color: 'white', fontWeight: 'bold', fontSize: '0.65rem' }} /></TableCell>
                  {isAdmin && (
                    <TableCell align="right">
                      <IconButton size="small" onClick={() => openEditDialog(server)} color="primary"><Edit fontSize="small" /></IconButton>
                      <IconButton size="small" onClick={(e) => handleMoveClick(e, server)} color="secondary"><SwapHoriz fontSize="small" /></IconButton>
                      <IconButton size="small" onClick={() => deleteServer(server.id)} color="error"><Delete fontSize="small" /></IconButton>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
        
        <TablePagination
          rowsPerPageOptions={[10, 25, 50, 100]}
          component="div"
          count={totalCount}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={handleChangePage}
          onRowsPerPageChange={handleChangeRowsPerPage}
          sx={{ borderTop: '1px solid #eee' }}
        />

        {servers.length === 0 && !loading && (
          <Box sx={{ textAlign: "center", py: 6, color: "textSecondary" }}>
            <Typography variant="h6" gutterBottom>No servers found for {environment.toUpperCase()}</Typography>
            <Typography variant="body2">
              Add {environment.toUpperCase()} servers to activate monitoring.
            </Typography>
          </Box>
        )}
        {loading && <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>}
      </Paper>

      {/* Move Server Menu & Dialogs */}
      <Menu anchorEl={moveMenuAnchor} open={Boolean(moveMenuAnchor)} onClose={handleMoveClose}>
        <MenuItem onClick={() => moveServer('prod')} disabled={selectedServerForMove?.environment === 'prod'}>Move to PROD</MenuItem>
        <MenuItem onClick={() => moveServer('uat')} disabled={selectedServerForMove?.environment === 'uat'}>Move to UAT</MenuItem>
      </Menu>

      <Dialog open={openDialog} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{editingId ? "Edit Server" : "Add Server"}</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <TextField fullWidth label="Server Name" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} margin="normal" />
          {editingId && formData.detected_ips?.length > 0 ? (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" color="textSecondary">Primary IP Address</Typography>
              <FormControl fullWidth size="small">
                <Select value={formData.ip} onChange={(e) => setFormData({ ...formData, ip: e.target.value })}>
                  {formData.detected_ips.map((ip) => <MenuItem key={ip} value={ip}>{ip}</MenuItem>)}
                  {!formData.detected_ips.includes(formData.ip) && <MenuItem value={formData.ip}>{formData.ip} (Manual)</MenuItem>}
                </Select>
              </FormControl>
            </Box>
          ) : (
            <TextField fullWidth label="IP Address" value={formData.ip} onChange={(e) => setFormData({ ...formData, ip: e.target.value })} margin="normal" />
          )}
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="textSecondary">Environment</Typography>
            <FormControl fullWidth size="small">
              <Select value={formData.environment || 'prod'} onChange={(e) => setFormData({ ...formData, environment: e.target.value })}>
                <MenuItem value="prod">Production (PROD)</MenuItem>
                <MenuItem value="uat">User Acceptance Testing (UAT)</MenuItem>
              </Select>
            </FormControl>
          </Box>
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="textSecondary">OS Type</Typography>
            <FormControl fullWidth size="small">
              <Select value={formData.os_type || 'Linux'} onChange={(e) => setFormData({ ...formData, os_type: e.target.value })}>
                <MenuItem value="Linux">Linux</MenuItem>
                <MenuItem value="Windows">Windows</MenuItem>
              </Select>
            </FormControl>
          </Box>
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="textSecondary">Location (Site)</Typography>
            <FormControl fullWidth size="small">
              <Select value={formData.location_id || 1} onChange={(e) => setFormData({ ...formData, location_id: parseInt(e.target.value) })}>
                <MenuItem value={1}>Data Center (DC)</MenuItem>
                <MenuItem value={2}>Disaster Recovery (DR)</MenuItem>
                <MenuItem value={3}>Cloud / AWS</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </DialogContent>
        <DialogActions><Button onClick={closeDialog}>Cancel</Button><Button onClick={saveServer} variant="contained">Save</Button></DialogActions>
      </Dialog>
    </Container>
  );
}