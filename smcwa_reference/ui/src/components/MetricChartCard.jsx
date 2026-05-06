import React, { useState, useMemo } from 'react';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Box from '@mui/material/Box';
import Grid from '@mui/material/Grid';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Chip from '@mui/material/Chip';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import {
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

// Professional Color Palette for multiple lines
const LINE_COLORS = [
  '#1976d2', '#d32f2f', '#2e7d32', '#ed6c02', '#9c27b0', 
  '#00BCD4', '#E91E63', '#795548', '#607D8B', '#3F51B5'
];

const formatXAxis = (tickItem, index, range, isLongRange) => {
  if (!tickItem) return '';
  const date = new Date(tickItem);
  if (isNaN(date.getTime())) return '';

  const options = {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  };

  if (range >= 24 * 60 * 60 * 1000 - 1000 || isLongRange) {
    options.day = '2-digit';
    options.month = 'short';
  }
  
  if (range <= 6 * 60 * 60 * 1000 + 1000) {
    options.second = '2-digit';
  }

  return date.toLocaleTimeString('en-IN', options);
};

const MetricChartCard = ({
  title,
  data,
  dataKey, // Single line key
  multiLineConfig, // Optional: array of { key, name, color } for multiple lines
  pctKey, 
  color,
  unit = '%',
  loading,
  error,
  leftDomain,
  rightDomain,
  ticks = [],
  onMouseDown,
  onMouseMove,
  onMouseUp,
  refAreaLeft,
  refAreaRight,
  onFullView, 
  hideMenu = false,
  isLongRange = false,
  height = 500
}) => {
  const range = rightDomain - leftDomain;
  const [anchorEl, setAnchorEl] = useState(null);
  const [hiddenSeries, setHiddenSeries] = useState(new Set());
  const open = Boolean(anchorEl);

  const handleMenuOpen = (event) => setAnchorEl(event.currentTarget);
  const handleMenuClose = () => setAnchorEl(null);

  const handleFullViewClick = () => {
    handleMenuClose();
    if (onFullView) onFullView();
  };

  const toggleSeries = (key) => {
    const newHidden = new Set(hiddenSeries);
    if (newHidden.has(key)) {
      newHidden.delete(key);
    } else {
      newHidden.add(key);
    }
    setHiddenSeries(newHidden);
  };

  const showOnly = (key) => {
    if (!multiLineConfig) return;
    const newHidden = new Set();
    multiLineConfig.forEach(cfg => {
      if (cfg.key !== key) newHidden.add(cfg.key);
    });
    setHiddenSeries(newHidden);
  };

  const showAll = () => setHiddenSeries(new Set());

  const stats = useMemo(() => {
    if (!data || data.length === 0) return { min: 0, max: 0, avg: 0 };
    const visibleData = data.filter(d => d.timestamp >= leftDomain && d.timestamp <= rightDomain);
    if (visibleData.length === 0) return { min: 0, max: 0, avg: 0 };

    let activeKey = dataKey;
    if (multiLineConfig) {
      const firstVisible = multiLineConfig.find(c => !hiddenSeries.has(c.key));
      if (firstVisible) activeKey = firstVisible.key;
    }
    
    const values = visibleData.map(d => d[activeKey]).filter(v => v != null && !isNaN(v));
    const pctValues = pctKey ? visibleData.map(d => d[pctKey]).filter(v => v != null && !isNaN(v)) : [];
    
    if (values.length === 0) return { min: 0, max: 0, avg: 0 };

    return {
      min: Math.min(...values).toFixed(2),
      max: Math.max(...values).toFixed(2),
      avg: (values.reduce((a, b) => a + b, 0) / values.length).toFixed(2),
      minPct: pctValues.length > 0 ? Math.min(...pctValues).toFixed(1) : null,
      maxPct: pctValues.length > 0 ? Math.max(...pctValues).toFixed(1) : null,
      avgPct: pctValues.length > 0 ? (pctValues.reduce((a, b) => a + b, 0) / pctValues.length).toFixed(1) : null,
    };
  }, [data, leftDomain, rightDomain, dataKey, multiLineConfig, hiddenSeries, pctKey]);

  return (
      <Paper sx={{ p: 2, height: height, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRadius: '12px', border: '1px solid #e0e0e0' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 800, color: '#444' }}>{title}</Typography>
          {!hideMenu && (
            <Box>
              <IconButton size="small" onClick={handleMenuOpen}>
                <MoreVertIcon fontSize="small" />
              </IconButton>
              <Menu anchorEl={anchorEl} open={open} onClose={handleMenuClose}>
                <MenuItem onClick={handleFullViewClick}>
                  <FullscreenIcon fontSize="small" sx={{ mr: 1 }} /> Full View
                </MenuItem>
              </Menu>
            </Box>
          )}
        </Box>

        {/* STATS ROW */}
        <Box sx={{ display: 'flex', justifyContent: 'space-around', alignItems: 'center', mb: 1, flexWrap: 'wrap', height: '24px' }}>
          {data && data.length > 0 && (
            <>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>Min: <strong style={{ color: '#333' }}>{stats.min}{unit}{stats.minPct && ` (${stats.minPct}${unit === '%' ? ' GB' : '%'})`}</strong></Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>Max: <strong style={{ color: '#333' }}>{stats.max}{unit}{stats.maxPct && ` (${stats.maxPct}${unit === '%' ? ' GB' : '%'})`}</strong></Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>Avg: <strong style={{ color: '#333' }}>{stats.avg}{unit}{stats.avgPct && ` (${stats.avgPct}${unit === '%' ? ' GB' : '%'})`}</strong></Typography>
            </>
          )}
        </Box>

        {/* CHART AREA */}
        <Box sx={{ flexGrow: 1, width: '100%', height: multiLineConfig ? 'calc(100% - 130px)' : 'calc(100% - 80px)', position: 'relative' }}>
          {loading && (!data || data.length === 0) && (
            <Box sx={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', justifyContent: 'center', alignItems: 'center', backgroundColor: 'rgba(255, 255, 255, 0.5)', zIndex: 2 }}>
              <CircularProgress size={40} />
            </Box>
          )}
          {!error && (!data || data.length === 0) && !loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', color: 'text.secondary', fontStyle: 'italic' }}>
              No data available
            </Box>
          )}
          {!error && data && data.length > 0 && (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart 
                data={data} 
                margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
                onMouseDown={onMouseDown}
                onMouseMove={onMouseMove}
                onMouseUp={onMouseUp}
              >
                <defs>
                  <linearGradient id={`colorGrad_${dataKey || 'multi'}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={color || LINE_COLORS[0]} stopOpacity={0.3}/>
                    <stop offset="95%" stopColor={color || LINE_COLORS[0]} stopOpacity={0}/>
                  </linearGradient>
                  {multiLineConfig && multiLineConfig.map((cfg, idx) => (
                    <linearGradient key={`grad_${cfg.key}`} id={`colorGrad_${cfg.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={cfg.color || LINE_COLORS[idx % LINE_COLORS.length]} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={cfg.color || LINE_COLORS[idx % LINE_COLORS.length]} stopOpacity={0}/>
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eee" />
                <XAxis
                  allowDataOverflow
                  dataKey="timestamp"
                  domain={[leftDomain, rightDomain]}
                  ticks={ticks.length > 0 ? ticks : undefined}
                  type="number"
                  scale="time"
                  tickFormatter={(val, idx) => formatXAxis(val, idx, range, isLongRange)}
                  tick={{ fontSize: 10, fill: '#666' }}
                  axisLine={{ stroke: '#ddd' }}
                />
                <YAxis
                  allowDataOverflow
                  domain={unit === '%' ? [0, 100] : [0, 'auto']}
                  tickFormatter={(val) => `${val.toFixed(0)}${unit}`}
                  tick={{ fontSize: 10, fill: '#666' }}
                  width={60}
                  axisLine={{ stroke: '#ddd' }}
                />
                <Tooltip
                  labelFormatter={(val) => formatXAxis(val, 0, range, isLongRange)}
                  formatter={(value, name, props) => {
                    const val = parseFloat(value).toFixed(2);
                    const pctVal = props.payload[pctKey];
                    const displayValue = (pctVal !== undefined && pctVal !== null && pctKey !== dataKey) 
                      ? `${val}${unit} (${parseFloat(pctVal).toFixed(1)}${unit === '%' ? ' GB' : '%'})` 
                      : `${val}${unit}`;
                    return [displayValue, name];
                  }}
                  contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.95)', borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.15)', fontSize: '12px' }}
                />
                
                {multiLineConfig ? (
                  multiLineConfig.map((cfg, idx) => (
                    <Area
                      key={cfg.key}
                      type="monotone"
                      dataKey={cfg.key}
                      name={cfg.name}
                      stroke={cfg.color || LINE_COLORS[idx % LINE_COLORS.length]}
                      fill={`url(#colorGrad_${cfg.key})`}
                      strokeWidth={3}
                      dot={false}
                      activeDot={{ r: 4 }}
                      isAnimationActive={false}
                      connectNulls={true}
                      hide={hiddenSeries.has(cfg.key)}
                    />
                  ))
                ) : (
                  <Area
                    type="monotone"
                    dataKey={dataKey}
                    name={title.split(' (')[0]}
                    stroke={color}
                    fill={`url(#colorGrad_${dataKey})`}
                    strokeWidth={3}
                    dot={false}
                    activeDot={{ r: 4 }}
                    isAnimationActive={false} 
                    connectNulls={true}
                  />
                )}

                {refAreaLeft && refAreaRight && (
                  <ReferenceArea x1={refAreaLeft} x2={refAreaRight} strokeOpacity={0.3} fill="#1976d2" fillOpacity={0.2} />
                )}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Box>

        {/* INTERACTIVE MULTI-LINE LEGEND */}
        {multiLineConfig && multiLineConfig.length > 0 && (
          <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap', justifyContent: 'center', overflowY: 'auto', maxHeight: '80px', p: 1, borderTop: '1px solid #eee' }}>
            <Chip 
              label="ALL" 
              size="small" 
              variant={hiddenSeries.size === 0 ? "filled" : "outlined"}
              onClick={showAll}
              sx={{ fontWeight: 'bold', cursor: 'pointer' }}
            />
            {multiLineConfig.map((cfg, idx) => {
              const isHidden = hiddenSeries.has(cfg.key);
              const itemColor = cfg.color || LINE_COLORS[idx % LINE_COLORS.length];
              return (
                <Chip
                  key={cfg.key}
                  label={cfg.name}
                  size="small"
                  onClick={() => showOnly(cfg.key)}
                  onDelete={() => toggleSeries(cfg.key)}
                  deleteIcon={isHidden ? <Box sx={{ width: 16, height: 16 }} /> : undefined}
                  sx={{ 
                    cursor: 'pointer',
                    fontWeight: 'bold',
                    backgroundColor: isHidden ? 'transparent' : itemColor,
                    color: isHidden ? itemColor : '#fff',
                    borderColor: itemColor,
                    '&:hover': { backgroundColor: isHidden ? 'rgba(0,0,0,0.05)' : itemColor }
                  }}
                />
              );
            })}
          </Box>
        )}
      </Paper>
  );
};

export default MetricChartCard;