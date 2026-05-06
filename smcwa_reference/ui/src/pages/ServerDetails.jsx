import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Skeleton from '@mui/material/Skeleton';
import Alert from '@mui/material/Alert';
import Paper from '@mui/material/Paper';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import LinearProgress from '@mui/material/LinearProgress';
import CircularProgress from '@mui/material/CircularProgress';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Divider from '@mui/material/Divider';
import PdfIcon from '@mui/icons-material/PictureAsPdf';
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Chip from '@mui/material/Chip';
import PlaceIcon from "@mui/icons-material/Place";
import CloudIcon from "@mui/icons-material/Cloud";
import axios from '../utils/axiosConfig';
import { exportToPDF } from '../utils/pdfExporter';
import MetricChartCard from '../components/MetricChartCard';

const ServerDetails = () => {
  const { serverId } = useParams();
  
  // -- STATE --
  const [server, setServer] = useState(null);
  const [loadingServer, setLoadingServer] = useState(true); // Separate loading for metadata
  const [error, setError] = useState(null);
  const contentRef = useRef(null);
  
  const [timeRange, setTimeRange] = useState('15m');
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');

  // Data State: Use Map for O(1) updates and preventing duplicates
  const [metricsMap, setMetricsMap] = useState(new Map());
  const [interfaceMetricsMap, setInterfaceMetricsMap] = useState(new Map());
  const [loadingMetrics, setLoadingMetrics] = useState(true); // Separate loading for charts
  const [loadingInterfaces, setLoadingInterfaces] = useState(false);
  const [diskPartitions, setDiskPartitions] = useState([]);
  const [detectedPartitions, setDetectedPartitions] = useState(new Set());

  // Full View State
  const [fullViewMetric, setFullViewMetric] = useState(null); // 'cpu', 'memory', 'disk', 'network'

  // Fixed Domain State: Ensures chart grid is stable immediately
  const [domain, setDomain] = useState({ min: Date.now() - 24 * 60 * 60 * 1000, max: Date.now() });

  // -- ZOOM STATE --
  const [refAreaLeft, setRefAreaLeft] = useState(null);
  const [refAreaRight, setRefAreaRight] = useState(null);
  const [isZoomed, setIsZoomed] = useState(false);

  const isMounted = useRef(true);
  const ws = useRef(null);
  // FIX: Use a queue for metrics to prevent data loss if multiple updates arrive within the throttle window
  const wsBuffer = useRef({ server: null, metricsQueue: [] });

  // Helper to sanitize partition names for Recharts keys (replace : with _)
  const sanitizeKey = (name) => `disk_partition_${name.replace(/[^a-zA-Z0-9]/g, '_')}`;

  // UI THROTTLE: Synchronized with 10-second system heartbeat
  useEffect(() => {
    const flushBuffer = () => {
        const { server: bufferedServer, metricsQueue } = wsBuffer.current;
        
        if (bufferedServer) {
            setServer(prev => ({ ...prev, ...bufferedServer }));
            wsBuffer.current.server = null;
        }

        setMetricsMap(prevMap => {
            const newMap = new Map(prevMap);
            let lastValues = {};
            if (newMap.size > 0) {
                const lastKey = Array.from(newMap.keys()).pop();
                lastValues = newMap.get(lastKey) || {};
            }

            const queueToProcess = [...metricsQueue];
            // 10s STANDARD: Only update on real data, no synthetic crawling
            if (queueToProcess.length > 0) {
                queueToProcess.forEach(bufferedMetrics => {
                    let timestamp = bufferedMetrics._arrival_ts || Date.now();
                    
                    const newPoint = {
                        timestamp: timestamp,
                        cpu: bufferedMetrics.cpu !== undefined ? parseFloat(bufferedMetrics.cpu) : lastValues.cpu,
                        memory_pct: bufferedMetrics.memory !== undefined ? parseFloat(bufferedMetrics.memory) : lastValues.memory_pct,
                        memory_used_gb: bufferedMetrics.memory_used_bytes !== undefined ? parseFloat(bufferedMetrics.memory_used_bytes) / (1024**3) : lastValues.memory_used_gb,
                        disk_used_gb: bufferedMetrics.disk_used_bytes !== undefined ? parseFloat(bufferedMetrics.disk_used_bytes) / (1024**3) : lastValues.disk_used_gb,
                        disk_pct: bufferedMetrics.disk_pct !== undefined ? parseFloat(bufferedMetrics.disk_pct) : lastValues.disk_pct,
                        // SYNC FIX: Backend now sends 'network_bits_per_sec' (bps)
                        network_mbps: bufferedMetrics.network_bits_per_sec !== undefined ? parseFloat(bufferedMetrics.network_bits_per_sec) / 1000000 : lastValues.network_mbps,
                        network_pct: bufferedMetrics.network_bandwidth !== undefined ? parseFloat(bufferedMetrics.network_bandwidth) : lastValues.network_pct,
                    };

                    // SYNC FIX: Also update the 'server' state for the Current Throughput card
                    if (bufferedMetrics.network_bits_per_sec !== undefined) {
                        setServer(prev => prev ? { ...prev, network_bits_per_sec: parseFloat(bufferedMetrics.network_bits_per_sec) } : prev);
                    }
                    if (bufferedMetrics.packet_count !== undefined) {
                        setServer(prev => prev ? { ...prev, packet_count: parseFloat(bufferedMetrics.packet_count) } : prev);
                    }

                    // SYNC DISK PARTITIONS (Both Graph and Cards)
                    const updatedPartitions = [];
                    Object.keys(bufferedMetrics).forEach(key => {
                        if (key.startsWith('disk_partition_')) {
                            const pName = key.replace('disk_partition_', '');
                            const safeKey = sanitizeKey(pName);
                            const util = parseFloat(bufferedMetrics[key]);
                            
                            // 1. Percentage for Tooltip/Sync
                            newPoint[safeKey + '_pct'] = util;
                            
                            // 2. Used GB for the Graph Line
                            const usedBytes = bufferedMetrics[`disk_part_used_bytes_${pName}`];
                            const totalBytes = bufferedMetrics[`disk_part_total_bytes_${pName}`];
                            
                            if (usedBytes !== undefined) {
                                const usedGb = parseFloat(usedBytes) / (1024**3);
                                const totalGb = parseFloat(totalBytes) / (1024**3);
                                newPoint[safeKey] = usedGb; // THIS IS WHAT THE GRAPH PLOTS
                                
                                // Update Cards State in Real-Time
                                updatedPartitions.push({
                                    name: pName,
                                    utilization: util,
                                    used_gb: usedGb,
                                    total_gb: totalGb
                                });
                            }

                            setDetectedPartitions(prev => {
                                if (prev.has(pName)) return prev;
                                const next = new Set(prev);
                                next.add(pName);
                                return next;
                            });
                        }
                    });

                    if (updatedPartitions.length > 0) {
                        setDiskPartitions(updatedPartitions);
                    }

                    // Carry over previous partition values to prevent gaps
                    Object.keys(lastValues).forEach(k => {
                        if (k.startsWith('disk_partition_') && newPoint[k] === undefined) {
                            newPoint[k] = lastValues[k];
                        }
                    });
                    
                    if (newPoint.cpu !== undefined || newPoint.memory_used_gb !== undefined || 
                        newPoint.disk_used_gb !== undefined || newPoint.network_mbps !== undefined) {
                        newMap.set(timestamp, newPoint);
                    }
                });
                
                if (newMap.size > 3600) {
                    const sortedKeys = Array.from(newMap.keys()).sort((a,b) => a - b);
                    const itemsToRemove = newMap.size - 3600;
                    for (let i = 0; i < itemsToRemove; i++) {
                        newMap.delete(sortedKeys[i]);
                    }
                }
            }
            return newMap;
        });
        
        wsBuffer.current.metricsQueue = [];
    };

    const intervalId = setInterval(flushBuffer, 10000);
    return () => clearInterval(intervalId);
  }, [serverId]);

  const diskLineConfig = useMemo(() => {
    if (detectedPartitions.size === 0) return null;
    return Array.from(detectedPartitions).sort().map(p => ({
      key: sanitizeKey(p), // SANITIZE: Match the data key format
      name: p
    }));
  }, [detectedPartitions]);

  // -- LOGIC --
  
  // Memoized sorted array for Recharts (only recalculates when map updates)
  const metricsHistory = useMemo(() => {
    return Array.from(metricsMap.values()).sort((a, b) => a.timestamp - b.timestamp);
  }, [metricsMap]);

  // -- LOGIC --

  // 1. Domain Calculation (Auto-Sliding) - Synchronized with 10s Backend
  const updateDomain = () => {
      if (isZoomed && timeRange !== 'custom') return; 

      const nowUtc = Date.now(); 
      let minTime;
      let maxTime = nowUtc;
      
      if (timeRange === 'custom' && customStartDate && customEndDate) {
        minTime = new Date(customStartDate + 'T00:00:00Z').getTime();
        maxTime = new Date(customEndDate + 'T23:59:59Z').getTime();
      } else {
        switch (timeRange) {
          case '15m': minTime = nowUtc - 15 * 60 * 1000; break;
          case '30m': minTime = nowUtc - 30 * 60 * 1000; break;
          case '1h': minTime = nowUtc - 1 * 60 * 60 * 1000; break;
          case '6h': minTime = nowUtc - 6 * 60 * 60 * 1000; break;
          case '24h': minTime = nowUtc - 24 * 60 * 60 * 1000; break;
          case '7d': minTime = nowUtc - 7 * 24 * 60 * 60 * 1000; break;
          case '30d': minTime = nowUtc - 30 * 24 * 60 * 60 * 1000; break;
          default: minTime = nowUtc - 24 * 60 * 60 * 1000;
        }
      }
      setDomain({ min: minTime, max: maxTime });
  };

  useEffect(() => {
    updateDomain(); 

    let intervalId = null;
    if (timeRange !== 'custom' && !isZoomed) {
        // PROFESSIONAL SYNC: Run domain update every 1 second for true real-time per-second visibility
        intervalId = setInterval(updateDomain, 1000); 
    }

    return () => {
        if (intervalId) clearInterval(intervalId);
    };
  }, [timeRange, customStartDate, customEndDate, isZoomed]);

  // -- ZOOM HANDLERS --
  const handleZoom = () => {
    if (refAreaLeft === refAreaRight || refAreaRight === null) {
      setRefAreaLeft(null);
      setRefAreaRight(null);
      return;
    }

    let newLeft = refAreaLeft;
    let newRight = refAreaRight;
    if (refAreaLeft > refAreaRight) {
      newLeft = refAreaRight;
      newRight = refAreaLeft;
    }

    setDomain({ min: newLeft, max: newRight });
    setIsZoomed(true);
    setRefAreaLeft(null);
    setRefAreaRight(null);
  };

  const resetZoom = () => {
    setIsZoomed(false);
  };

  const getLocationChip = (locationId) => {
    switch (locationId) {
      case 1: 
        return <Chip size="small" icon={<PlaceIcon style={{ fontSize: 14 }} />} label="DC" sx={{ height: 24, fontSize: '0.75rem', bgcolor: '#e3f2fd', color: '#1976d2', fontWeight: 'bold' }} />;
      case 2: 
        return <Chip size="small" icon={<PlaceIcon style={{ fontSize: 14 }} />} label="DR" sx={{ height: 24, fontSize: '0.75rem', bgcolor: '#fff3e0', color: '#e65100', fontWeight: 'bold' }} />;
      case 3: 
        return <Chip size="small" icon={<CloudIcon style={{ fontSize: 14 }} />} label="Cloud" sx={{ height: 24, fontSize: '0.75rem', bgcolor: '#f3e5f5', color: '#7b1fa2', fontWeight: 'bold' }} />;
      default: 
        return <Chip size="small" label="Unknown" sx={{ height: 24, fontSize: '0.75rem' }} />;
    }
  };

  const onMouseDown = (e) => {
    if (e && e.activeLabel) {
      setRefAreaLeft(e.activeLabel);
    }
  };

  const onMouseMove = (e) => {
    if (refAreaLeft !== null && e && e.activeLabel) {
      setRefAreaRight(e.activeLabel);
    }
  };

  // Generates granular, 'pretty' ticks for the X-axis
  const generateTicks = (min, max) => {
    if (isNaN(min) || isNaN(max) || min >= max) return [];
    
    const range = max - min;
    const ticks = [];
    
    // Choose interval based on range
    let interval;
    if (range <= 1.5 * 60 * 1000) { // 1.5 min or less
      interval = 5 * 1000; // 5 seconds
    } else if (range <= 5.1 * 60 * 1000) { // 5 min
      interval = 15 * 1000; // 15 seconds
    } else if (range <= 16 * 60 * 1000) { // 15m or less
      interval = 1 * 60 * 1000; // 1 minute markers
    } else if (range <= 31 * 60 * 1000) { // 30m
      interval = 2 * 60 * 1000; // 2 min
    } else if (range <= 1.1 * 60 * 60 * 1000) { // 1h
      interval = 5 * 60 * 1000; // 5 min
    } else if (range <= 6.1 * 60 * 60 * 1000) { // 6h
      interval = 1 * 60 * 60 * 1000; // 1 hour
    } else if (range <= 24.1 * 60 * 60 * 1000) { // 24h
      interval = 4 * 60 * 60 * 1000; // 4 hours
    } else if (range <= 7.1 * 24 * 60 * 60 * 1000) { // 7d
      interval = 24 * 60 * 60 * 1000; // 1 day
    } else { // 30d+
      interval = 5 * 24 * 60 * 60 * 1000; // 5 days
    }

    // Start from the first 'clean' interval point after min
    let current = Math.ceil(min / interval) * interval;
    while (current < max) {
      ticks.push(current);
      current += interval;
    }

    // Always ensure the LAST timestamp (NOW) is visible on the axis
    if (max - ticks[ticks.length-1] > (interval / 2)) {
        ticks.push(max);
    }
    
    return ticks;
  };

  const chartTicks = useMemo(() => generateTicks(domain.min, domain.max), [domain]);

  // Calculate aggregation step - High Density Standard
  const getStepForRange = (r, start, end) => {
      let durationHours;
      if (start && end) {
          durationHours = (end.getTime() - start.getTime()) / (1000 * 60 * 60);
      } else {
          switch (r) {
              case '15m': durationHours = 0.25; break;
              case '30m': durationHours = 0.5; break;
              case '1h': durationHours = 1; break;
              case '6h': durationHours = 6; break;
              case '24h': durationHours = 24; break;
              case '7d': durationHours = 24 * 7; break;
              case '30d': durationHours = 24 * 30; break;
              default: durationHours = 24;
          }
      }
      
      // 10s STANDARD: Target 10s resolution for all real-time views (up to 1.1 hours)
      if (durationHours <= 1.1) return '10s'; 
      if (durationHours <= 6.1) return '1m';  
      if (durationHours <= 24.1) return '5m';
      if (durationHours <= 24 * 3.1) return '15m'; 
      return '1h'; 
  };

  // Fetch Metrics History
  const fetchMetricsForRange = async (range, customStart, customEnd) => {
    if (!isMounted.current) return;
    setLoadingMetrics(true);
    setError(null);
    
    try {
      
      const now = new Date();
      let startDt, endDt;

      if (range === 'custom' && customStart && customEnd) {
        startDt = new Date(customStart);
        endDt = new Date(customEnd);
      } else {
        switch (range) {
          case '15m': startDt = new Date(now.getTime() - 15 * 60 * 1000); break;
          case '30m': startDt = new Date(now.getTime() - 30 * 60 * 1000); break;
          case '1h': startDt = new Date(now.getTime() - 1 * 60 * 60 * 1000); break;
          case '6h': startDt = new Date(now.getTime() - 6 * 60 * 60 * 1000); break;
          case '7d': startDt = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000); break;
          case '30d': startDt = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000); break;
          default: startDt = new Date(now.getTime() - 24 * 60 * 60 * 1000); 
        }
        endDt = now;
      }
      
      const step = getStepForRange(range, startDt, endDt);

      // CRITICAL FIX: Use local IST strings instead of toISOString() which forces UTC
      const toLocalISO = (date) => {
        const pad = (num) => String(num).padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
      };

      const startLocal = toLocalISO(startDt);
      const endLocal = toLocalISO(endDt);

      let url = `/v1/historical/bulk-server-metrics?server_id=${serverId}&step=${step}&include_interfaces=true`;
      url += `&start_date=${startLocal.split('T')[0]}`;
      url += `&end_date=${endLocal.split('T')[0]}`;
      url += `&start_time=${startLocal.split('T')[1]}`;
      url += `&end_time=${endLocal.split('T')[1]}`;
      
      const metricNames = ['cpu', 'memory', 'memory_used_bytes', 'disk', 'disk_used_bytes', 'network_bandwidth', 'network_bits_per_sec', 'packet_count'];
      metricNames.forEach(name => {
        url += `&metric_names=${encodeURIComponent(name)}`;
      });

      // DYNAMIC FIX: Also request specific partition metrics if we know them
      if (diskPartitions && diskPartitions.length > 0) {
          diskPartitions.forEach(p => {
              if (p.name) {
                  url += `&metric_names=${encodeURIComponent('disk_partition_' + p.name)}`;
                  url += `&metric_names=${encodeURIComponent('disk_part_used_bytes_' + p.name)}`;
              }
          });
      }

      const response = await axios.get(url, {
        
        timeout: 30000,
        paramsSerializer: p => {
          const sp = new URLSearchParams();
          for (const k in p) {
            if (Array.isArray(p[k])) p[k].forEach(v => sp.append(k, v));
            else sp.append(k, p[k]);
          }
          return sp.toString();
        }
      });
      
      if (isMounted.current) {
        if (!response.data || !Array.isArray(response.data.metrics)) {
            console.warn('Invalid metrics response format:', response.data);
            setMetricsMap(new Map());
            return;
        }

        const newMap = new Map();
        const metrics = response.data.metrics;
        const partitionsFound = new Set();
        
        for (let i = 0; i < metrics.length; i++) {
            const m = metrics[i];
            if (!m || !m.timestamp) continue;

            const ts = new Date(m.timestamp).getTime();
            if (isNaN(ts)) continue;

            let entry = newMap.get(ts);
            if (!entry) {
                entry = { timestamp: ts };
                newMap.set(ts, entry);
            }

            const val = parseFloat(m.value) || 0;

            if (m.metric_name === 'cpu') {
                entry['cpu'] = val;
            } else if (m.metric_name === 'memory') {
                entry['memory_pct'] = val;
            } else if (m.metric_name === 'memory_used_bytes') {
                entry['memory_used_gb'] = val / (1024 * 1024 * 1024);
            } else if (m.metric_name === 'disk') {
                if (m.interface_name) {
                    const pName = m.interface_name;
                    partitionsFound.add(pName);
                    const safeKey = sanitizeKey(pName);
                    entry[safeKey + '_pct'] = val;
                } else {
                    entry['disk_pct'] = val;
                }
            } else if (m.metric_name === 'disk_used_bytes') {
                entry['disk_used_gb'] = val / (1024 * 1024 * 1024);
            } else if (m.metric_name.startsWith('disk_partition_')) {
                // Format: disk_partition_C:
                const pName = m.metric_name.replace('disk_partition_', '');
                partitionsFound.add(pName);
                const safeKey = sanitizeKey(pName);
                entry[safeKey + '_pct'] = val;
            } else if (m.metric_name.startsWith('disk_part_used_bytes_')) {
                // Format: disk_part_used_bytes_C:
                const pName = m.metric_name.replace('disk_part_used_bytes_', '');
                const safeKey = sanitizeKey(pName);
                entry[safeKey] = val / (1024 * 1024 * 1024);
            } else if (m.metric_name === 'network_bandwidth') {
                entry['network_pct'] = val;
            } else if (m.metric_name === 'network_bits_per_sec') {
                entry['network_mbps'] = val / 1000000;
            } else if (m.metric_name === 'packet_count') {
                entry['packet_count'] = val;
            }
        }
        
        if (partitionsFound.size > 0) {
            setDetectedPartitions(prev => {
                const combined = new Set(prev);
                partitionsFound.forEach(p => {
                    if (p && p.trim()) combined.add(p);
                });
                return combined;
            });
        }
        setMetricsMap(newMap);
        fetchInterfaceMetrics(startDt, endDt, step);
      }
    } catch (err) {
      if (isMounted.current) {
        const errorMsg = err.response?.data?.detail || err.message;
        setError(`Failed to fetch metrics history: ${errorMsg}`);
      }
    } finally {
      if (isMounted.current) {
        setLoadingMetrics(false);
      }
    }
  };

  const fetchInterfaceMetrics = async (startDt, endDt, step) => {
    if (!isMounted.current) return;
    setLoadingInterfaces(true);
    try {
        
        
        // CRITICAL FIX: Use local IST strings instead of toISOString() which forces UTC
        const toLocalISO = (date) => {
          const pad = (num) => String(num).padStart(2, '0');
          return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
        };

        const startLocal = toLocalISO(startDt);
        const endLocal = toLocalISO(endDt);

        let url = `/v1/historical/bulk-server-metrics?server_id=${serverId}&step=${step}&include_interfaces=true`;
        url += `&start_date=${startLocal.split('T')[0]}`;
        url += `&end_date=${endLocal.split('T')[0]}`;
        url += `&start_time=${startLocal.split('T')[1]}`;
        url += `&end_time=${endLocal.split('T')[1]}`;
        url += `&metric_names=network_bits_per_sec`;

        const response = await axios.get(url, {  });
        
        if (isMounted.current && response.data?.metrics) {
            const ifaceMap = new Map();
            
            response.data.metrics.forEach(m => {
                const name = m.interface_name;
                if (!name) return;

                if (!ifaceMap.has(name)) ifaceMap.set(name, new Map());
                
                const ts = new Date(m.timestamp).getTime();
                
                ifaceMap.get(name).set(ts, {
                    timestamp: ts,
                    value: (parseFloat(m.value) || 0) / 1000000 // Mbps
                });
            });

            const finalMap = new Map();
            ifaceMap.forEach((dataMap, name) => {
                finalMap.set(name, Array.from(dataMap.values()).sort((a,b) => a.timestamp - b.timestamp));
            });
            
            if (finalMap.size > 0) {
                setInterfaceMetricsMap(finalMap);
            }
        }
    } catch (e) {
        console.error("Failed to fetch interface metrics", e);
    } finally {
        if (isMounted.current) setLoadingInterfaces(false);
    }
  };

  // Initial Load & WebSocket Setup
  useEffect(() => {
    isMounted.current = true;
    
    const fetchServerData = async () => {
      setLoadingServer(true);
      try {
        
        const serverResponse = await axios.get(`/v1/servers/${serverId}`, {  });
        if (isMounted.current) {
          setServer(serverResponse.data);
        }
      } catch (err) {
        if(isMounted.current) setError(`Failed to load server details: ${err.message}`);
      } finally {
        if(isMounted.current) setLoadingServer(false);
      }
    };
    
    const fetchDiskPartitionsData = async () => {
      try {
        
        const response = await axios.get(`/v1/servers/${serverId}/disk-partitions`, {  });
        if (isMounted.current) {
          const parts = response.data.partitions || [];
          setDiskPartitions(parts);
          
          // PROACTIVE FIX: Pre-populate chart lines from metadata immediately
          // This makes the legend/lines appear instantly, without waiting for the first metric packet
          if (parts.length > 0) {
              setDetectedPartitions(prev => {
                  const next = new Set(prev);
                  parts.forEach(p => {
                      if (p.name) next.add(p.name);
                  });
                  return next;
              });
          }
        }
      } catch (err) {
        console.error('Failed to fetch disk partitions', err);
      }
    };

    const connectWS = () => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const wsUrl = `${protocol}//${host}/ws/updates`;
        ws.current = new WebSocket(wsUrl);
        
        ws.current.onmessage = (event) => {
            if (event.data === 'pong') return;

            try {
                const message = JSON.parse(event.data);
                if (message.server_id === parseInt(serverId)) {
                    if (message.type === 'metrics' || message.type === 'status') {
                        // Buffer for throttled UI update
                        if (message.type === 'status') {
                             wsBuffer.current.server = { ...wsBuffer.current.server, ...message.data, last_seen: new Date().toISOString() };
                        }
                        if (message.type === 'metrics') {
                            // Sync with Client Time to prevent chart gaps
                            message.data._arrival_ts = Date.now();
                            wsBuffer.current.metricsQueue.push(message.data);
                        }
                    }
                }
            } catch (e) {
                if (event.data !== 'pong') console.warn('Error parsing WebSocket message:', e);
            }
        };
    };
    
    fetchServerData();
    fetchDiskPartitionsData();
    connectWS();

    return () => {
      isMounted.current = false;
      if (ws.current) ws.current.close();
    };
  }, [serverId]);

  useEffect(() => {
    if (isZoomed) {
        const startIso = new Date(domain.min).toISOString();
        const endIso = new Date(domain.max).toISOString();
        fetchMetricsForRange('custom', startIso, endIso);
    } else {
        fetchMetricsForRange(timeRange, customStartDate, customEndDate);
    }
  }, [serverId, timeRange, customStartDate, customEndDate, isZoomed, diskPartitions]);

  const handleTimeRangeChange = (event) => {
    const newRange = event.target.value;
    setIsZoomed(false);
    setRefAreaLeft(null);
    setRefAreaRight(null);
    setMetricsMap(new Map());
    setTimeRange(newRange);
  };

  const handleCustomDateRange = () => {
    if (customStartDate && customEndDate) {
        setIsZoomed(false); 
        fetchMetricsForRange('custom', customStartDate, customEndDate);
    }
  };

  const formatMbps = (value, speed) => {
    const bps = parseFloat(value || 0);
    const speedBps = parseFloat(speed || 0);
    
    if (isNaN(bps) || bps === 0) return speedBps > 0 ? `0 Mbps / ${formatSpeed(speedBps)}` : '0 Mbps';
    
    const mbps = bps / 1000000;
    const usageStr = mbps >= 1000 ? `${(mbps / 1000).toFixed(2)} Gbps` : `${mbps.toFixed(2)} Mbps`;
    
    if (speedBps > 0) {
        return `${usageStr} / ${formatSpeed(speedBps)}`;
    }
    return usageStr;
  };

  const formatSpeed = (bps) => {
    if (!bps || bps <= 0) return 'N/A';
    const mbps = bps / 1000000;
    if (mbps >= 1000) return `${(mbps / 1000).toFixed(0)} Gbps`;
    return `${mbps.toFixed(0)} Mbps`;
  };

  const formatUptime = (seconds) => {
    if (!seconds || seconds < 0) return 'N/A';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const parts = [];
    if (d > 0) parts.push(`${d}d`);
    if (h > 0) parts.push(`${h}h`);
    if (m > 0) parts.push(`${m}m`);
    return parts.length > 0 ? parts.join(' ') : '< 1m';
  };

  const formatLastSeen = (lastSeenString) => {
    try {
      if (!lastSeenString) return 'Never';
      const diffMins = Math.floor((new Date() - new Date(lastSeenString)) / 60000);
      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins} mins ago`;
      const diffHours = Math.floor(diffMins / 60);
      if (diffHours < 24) return `${diffHours} hours ago`;
      return `${Math.floor(diffHours / 24)} days ago`;
    } catch (e) { return 'Unknown'; }
  };

  const getProgressColor = (value) => {
    if (value >= 90) return "error";
    if (value >= 70) return "warning";
    return "success";
  };

  return (
    <Box sx={{ p: 3 }} ref={contentRef}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        {loadingServer ? (
            <Skeleton variant="text" width={400} height={80} animation="wave" />
        ) : (
            <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 0.5 }}>
                    <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
                        {server?.name || 'Unknown'}
                    </Typography>
                    {server && getLocationChip(server.location_id)}
                </Box>
                <Typography variant="subtitle1" color="textSecondary">
                    IP Address: {server?.ip || 'N/A'} | Environment: {server?.environment?.toUpperCase() || 'N/A'}
                    {server?.resource_id && server.resource_id !== server.ip && ` | Resource ID: ${server.resource_id}`}
                </Typography>
            </Box>
        )}
        <Button variant="contained" color="primary" startIcon={<PdfIcon />} onClick={() => exportToPDF(contentRef, server?.name)} disabled={loadingServer}>Export PDF</Button>
      </Box>
      
      <Paper sx={{ p: 2, mb: 3, backgroundColor: '#f8f9fa' }}>
         <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <Typography variant="h6" sx={{ fontWeight: 'bold', minWidth: 'fit-content' }}>Time Range</Typography>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Range</InputLabel>
            <Select value={timeRange} label="Range" onChange={handleTimeRangeChange}>
              <MenuItem value="15m">Last 15 Minutes</MenuItem>
              <MenuItem value="30m">Last 30 Minutes</MenuItem>
              <MenuItem value="1h">Last 1 Hour</MenuItem>
              <MenuItem value="6h">Last 6 Hours</MenuItem>
              <MenuItem value="24h">Last 24 Hours</MenuItem>
              <MenuItem value="7d">Last 7 Days</MenuItem>
              <MenuItem value="30d">Last 30 Days</MenuItem>
              <MenuItem value="custom">Custom</MenuItem>
            </Select>
          </FormControl>
          {timeRange === 'custom' && (
            <>
              <TextField label="Start Date" type="date" size="small" value={customStartDate} onChange={(e) => setCustomStartDate(e.target.value)} InputLabelProps={{ shrink: true }} />
              <TextField label="End Date" type="date" size="small" value={customEndDate} onChange={(e) => setCustomEndDate(e.target.value)} InputLabelProps={{ shrink: true }} />
              <Button variant="contained" onClick={handleCustomDateRange} disabled={!customStartDate || !customEndDate} size="small">Apply</Button>
            </>
          )}
          {isZoomed && (
            <Button variant="outlined" color="secondary" onClick={resetZoom} size="small">Reset Zoom</Button>
          )}
        </Box>
      </Paper>
      
      <Grid container spacing={2} sx={{ mb: 4 }}>
         <Grid item xs={12} sm={6} md={3}>
             {loadingServer ? (
                 <Skeleton variant="rectangular" height={110} sx={{ borderRadius: 2 }} animation="wave" />
             ) : (
                 <Card sx={{ bgcolor: '#e3f2fd', borderLeft: '4px solid #2196F3', height: '100%' }}>
                     <CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}>
                         <Typography variant="overline" color="textSecondary" sx={{ fontWeight: 'bold' }}>Last Seen</Typography>
                         <Typography variant="h6">{server ? formatLastSeen(server.last_seen) : 'N/A'}</Typography>
                     </CardContent>
                 </Card>
             )}
         </Grid>
          <Grid item xs={12} sm={6} md={3}>
              {loadingServer ? (
                 <Skeleton variant="rectangular" height={110} sx={{ borderRadius: 2 }} animation="wave" />
             ) : (
                <Card sx={{ bgcolor: '#e8f5e9', borderLeft: '4px solid #4CAF50', height: '100%' }}><CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}><Typography variant="overline" color="textSecondary" sx={{ fontWeight: 'bold' }}>System Uptime</Typography><Typography variant="h6">{server?.uptime ? formatUptime(server.uptime) : 'N/A'}</Typography></CardContent></Card>
             )}
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
              {loadingServer ? (
                 <Skeleton variant="rectangular" height={110} sx={{ borderRadius: 2 }} animation="wave" />
             ) : (
                <Card sx={{ bgcolor: '#fff3e0', borderLeft: '4px solid #FF9800', height: '100%' }}><CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}><Typography variant="overline" color="textSecondary" sx={{ fontWeight: 'bold' }}>Packet Error Count</Typography><Typography variant="h6">{server?.packet_count?.toLocaleString() || '0'}</Typography></CardContent></Card>
             )}
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
              {loadingServer ? (
                 <Skeleton variant="rectangular" height={110} sx={{ borderRadius: 2 }} animation="wave" />
             ) : (
                <Card sx={{ bgcolor: '#f3e5f5', borderLeft: '4px solid #9c27b0', height: '100%' }}><CardContent sx={{ py: 2, '&:last-child': { pb: 2 } }}><Typography variant="overline" color="textSecondary" sx={{ fontWeight: 'bold' }}>Current Throughput</Typography><Typography variant="h6">{server ? formatMbps(server.network_bits_per_sec, server.network_speed) : '0 Mbps'}</Typography></CardContent></Card>
             )}
          </Grid>
      </Grid>
      
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
            <MetricChartCard 
                title="CPU Usage" data={metricsHistory} dataKey="cpu" color="#d32f2f" unit="%" 
                loading={loadingMetrics} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                refAreaLeft={refAreaLeft} refAreaRight={refAreaRight} onFullView={() => setFullViewMetric('cpu')}
                isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
            />
        </Grid>
        <Grid item xs={12} md={6}>
            <MetricChartCard 
                title="Memory Usage" data={metricsHistory} 
                dataKey="memory_pct" 
                pctKey="memory_used_gb" color="#1976d2" unit="%" 
                loading={loadingMetrics} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                refAreaLeft={refAreaLeft} refAreaRight={refAreaRight} onFullView={() => setFullViewMetric('memory')}
                isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
            />
            {server?.memory_total_bytes > 0 && (
                <Box sx={{ mt: 1, textAlign: 'center' }}>
                    <Typography variant="h6" sx={{ fontWeight: 'bold', color: '#666' }}>
                        Total Memory: {(server.memory_total_bytes / (1024**3)).toFixed(1)} GB
                    </Typography>
                </Box>
            )}
        </Grid>
        <Grid item xs={12} md={6}>
            <MetricChartCard 
                title="Total Disk Usage (Aggregate)" data={metricsHistory} 
                dataKey="disk_pct" pctKey="disk_used_gb" 
                color="#ed6c02" unit="%" 
                loading={loadingMetrics} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                refAreaLeft={refAreaLeft} refAreaRight={refAreaRight} onFullView={() => setFullViewMetric('disk')}
                isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
            />
            {server?.disk_total_bytes > 0 && (
                <Box sx={{ mt: 1, textAlign: 'center' }}>
                    <Typography variant="h6" sx={{ fontWeight: 'bold', color: '#666' }}>
                        Total Capacity: {(server.disk_total_bytes / (1024**3)).toFixed(1)} GB
                    </Typography>
                </Box>
            )}
        </Grid>
        <Grid item xs={12} md={6}>
            <MetricChartCard 
                title="Network Throughput" data={metricsHistory} dataKey="network_mbps" pctKey="network_pct" color="#9c27b0" unit="Mbps" 
                loading={loadingMetrics} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                refAreaLeft={refAreaLeft} refAreaRight={refAreaRight} onFullView={() => setFullViewMetric('network')}
                isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
            />
        </Grid>
      </Grid>

      <Dialog fullScreen open={Boolean(fullViewMetric)} onClose={() => setFullViewMetric(null)}>
        <DialogTitle sx={{ m: 0, p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: '#f5f5f5' }}>
          <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
            {fullViewMetric === 'cpu' && 'CPU Usage - Full View'}
            {fullViewMetric === 'memory' && 'Memory Usage - Full View'}
            {fullViewMetric === 'disk' && 'Total Disk Usage (Aggregate) - Full View'}
            {fullViewMetric === 'network' && 'Network Throughput - Full View'}
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
             <FormControl size="small" sx={{ minWidth: 150 }}>
                <InputLabel>Range</InputLabel>
                <Select value={timeRange} label="Range" onChange={handleTimeRangeChange}>
                    <MenuItem value="15m">Last 15 Minutes</MenuItem>
                    <MenuItem value="30m">Last 30 Minutes</MenuItem>
                    <MenuItem value="1h">Last 1 Hour</MenuItem>
                    <MenuItem value="6h">Last 6 Hours</MenuItem>
                    <MenuItem value="24h">Last 24 Hours</MenuItem>
                    <MenuItem value="7d">Last 7 Days</MenuItem>
                    <MenuItem value="30d">Last 30 Days</MenuItem>
                </Select>
            </FormControl>
            {isZoomed && <Button variant="outlined" color="secondary" onClick={resetZoom} size="small">Reset Zoom</Button>}
            <IconButton onClick={() => setFullViewMetric(null)}><CloseIcon /></IconButton>
          </Box>
        </DialogTitle>
        <DialogContent sx={{ p: 3, display: 'flex', flexDirection: 'column' }}>
            <Box sx={{ flexGrow: 1, minHeight: 500 }}>
                {fullViewMetric === 'cpu' && (
                    <MetricChartCard 
                        title="CPU Usage" data={metricsHistory} dataKey="cpu" color="#d32f2f" unit="%" 
                        loading={loadingMetrics} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                        ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                        refAreaLeft={refAreaLeft} refAreaRight={refAreaRight} hideMenu={true}
                        isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
                    />
                )}
                {fullViewMetric === 'memory' && (
                    <>
                        <MetricChartCard 
                            title="Memory Usage" data={metricsHistory} 
                            dataKey="memory_pct" 
                            pctKey="memory_used_gb" color="#1976d2" unit="%" 
                            loading={loadingMetrics} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                            ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                            refAreaLeft={refAreaLeft} refAreaRight={refAreaRight} hideMenu={true}
                            isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
                        />
                        {server?.memory_total_bytes > 0 && (
                            <Box sx={{ mt: 2, textAlign: 'center' }}>
                                <Typography variant="h5" sx={{ fontWeight: 'bold', color: '#666' }}>
                                    Total Memory: {(server.memory_total_bytes / (1024**3)).toFixed(1)} GB
                                </Typography>
                            </Box>
                        )}
                    </>
                )}
                {fullViewMetric === 'disk' && (
                    <>
                        <MetricChartCard 
                            title="Total Disk Usage (Aggregate)" data={metricsHistory} 
                            dataKey="disk_pct" 
                            pctKey="disk_used_gb" color="#ed6c02" unit="%" 
                            loading={loadingMetrics} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                            ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                            refAreaLeft={refAreaLeft} refAreaRight={refAreaRight} hideMenu={true}
                            isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
                        />
                        {server?.disk_total_bytes > 0 && (
                            <Box sx={{ mt: 2, textAlign: 'center' }}>
                                <Typography variant="h5" sx={{ fontWeight: 'bold', color: '#666' }}>
                                    Total Capacity: {(server.disk_total_bytes / (1024**3)).toFixed(1)} GB
                                </Typography>
                            </Box>
                        )}
                    </>
                )}
                {fullViewMetric === 'network' && (
                    <MetricChartCard 
                        title="Network Throughput" data={metricsHistory} dataKey="network_mbps" pctKey="network_pct" color="#9c27b0" unit="Mbps" 
                        loading={loadingMetrics} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                        ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                        refAreaLeft={refAreaLeft} refAreaRight={refAreaRight} hideMenu={true}
                        isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
                    />
                )}
            </Box>
        </DialogContent>
      </Dialog>

      {interfaceMetricsMap.size > 0 && (
        <>
          <Divider sx={{ my: 4 }} />
          <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="h5" sx={{ fontWeight: 'bold' }}>Network Interface Details</Typography>
            {loadingInterfaces && <CircularProgress size={20} />}
          </Box>
          <Grid container spacing={3}>
            {Array.from(interfaceMetricsMap.entries()).map(([ifaceName, history]) => {
              const latestPoint = history[history.length - 1];
              // Note: We need to find the speed for this specific interface from our latest data source
              // For now, let's show the Mbps unit in the title
              return (
                <Grid item xs={12} md={6} lg={4} key={ifaceName}>
                  <MetricChartCard 
                    title={`NIC: ${ifaceName}`} data={history} dataKey="value" color="#9c27b0" unit="Mbps" 
                    loading={false} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                    ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                    refAreaLeft={refAreaLeft} refAreaRight={refAreaRight}
                    isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
                    height={350}
                  />
                </Grid>
              );
            })}
          </Grid>
        </>
      )}
      
      {diskPartitions.length > 0 && (
        <>
          <Divider sx={{ my: 4 }} />
          <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="h5" sx={{ fontWeight: 'bold' }}>Disk Partition Details</Typography>
          </Box>
          <Grid container spacing={3}>
            {diskPartitions.map((partition, index) => {
              const safeKey = sanitizeKey(partition.name);
              return (
                <Grid item xs={12} md={6} lg={4} key={index}>
                    <MetricChartCard 
                        title={`Disk: ${partition.name}`} 
                        data={metricsHistory} 
                        dataKey={safeKey + '_pct'} 
                        pctKey={safeKey}
                        color="#ed6c02" unit="%" 
                        loading={loadingMetrics} error={null} leftDomain={domain.min} rightDomain={domain.max} 
                        ticks={chartTicks} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={handleZoom}
                        refAreaLeft={refAreaLeft} refAreaRight={refAreaRight}
                        isLongRange={['24h', '7d', '30d', 'custom'].includes(timeRange)}
                        height={350}
                    />
                    <Card sx={{ mt: 1 }}>
                        <CardContent sx={{ p: '12px !important' }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>{partition.name}</Typography>
                                <Typography variant="subtitle2" color={getProgressColor(partition.utilization)} sx={{ fontWeight: 'bold' }}>{(partition.utilization || 0).toFixed(1)}%</Typography>
                            </Box>
                            <LinearProgress variant="determinate" value={partition.utilization || 0} color={getProgressColor(partition.utilization || 0)} sx={{ height: 8, borderRadius: 4, mb: 1 }} />
                            <Typography variant="caption" color="textSecondary">Used: {(partition.used_gb || 0).toFixed(1)} GB / Total: {(partition.total_gb || 0).toFixed(1)} GB</Typography>
                        </CardContent>
                    </Card>
                </Grid>
              );
            })}
          </Grid>
        </>
      )}
    </Box>
  );
};

export default ServerDetails;
