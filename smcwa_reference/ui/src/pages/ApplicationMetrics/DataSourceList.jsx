import React, { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import IconButton from '@mui/material/IconButton';
import Chip from '@mui/material/Chip';
import Tooltip from '@mui/material/Tooltip';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Alert from '@mui/material/Alert';
import Add from '@mui/icons-material/Add';
import Edit from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import CheckCircle from '@mui/icons-material/CheckCircle';
import Cancel from '@mui/icons-material/Cancel';
import Settings from '@mui/icons-material/Settings';
import SwapHoriz from '@mui/icons-material/SwapHoriz';
import ContentCopy from '@mui/icons-material/ContentCopy';
import axios from '../../utils/axiosConfig';
import { useEnvironment } from '../../hooks/useEnvironment';
import DataSourceForm from './DataSourceForm';
import MetricQueryManager from './MetricQueryManager';

export default function DataSourceList() {
  const { environment, withEnvironment } = useEnvironment();
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [openForm, setOpenForm] = useState(false);
  const [editingSource, setEditingUser] = useState(null);
  const [openQueryManager, setOpenQueryManager] = useState(false);
  const [selectedSource, setSelectedSource] = useState(null);
  const [message, setMessage] = useState('');
  const [promoting, setPromoting] = useState(false);

  useEffect(() => {
    loadSources();
  }, [environment]);

  const loadSources = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/v1/metric-sources', { params: withEnvironment() });
      const appTypes = ['ecs', 'elasticsearch', 'prometheus_app', 'mysql', 'postgresql', 'mssql'];
      setSources((response.data || []).filter(s => {
        if (!appTypes.includes(s.type)) return false;
        // Only show ECS services that have application metrics
        if (s.type === 'ecs' && s.config?.send_application_metrics === false) return false;
        return true;
      }));
    } catch (error) {
      console.error("Error loading sources:", error);
      setMessage("Failed to load sources");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to delete this source?")) return;
    try {
      await axios.delete(`/v1/metric-sources/${id}`);
      loadSources();
    } catch (error) {
      console.error("Error deleting source:", error);
      setMessage("Failed to delete source");
    }
  };

  const handlePromote = async () => {
    const target = environment === 'uat' ? 'prod' : 'uat';
    if (!window.confirm(`Clone all sources from ${environment.toUpperCase()} → ${target.toUpperCase()}?\n\nExisting sources in ${target.toUpperCase()} will NOT be affected. Duplicates (by name) are skipped.`)) return;
    setPromoting(true);
    try {
      const res = await axios.post('/v1/metric-sources/promote', { target_environment: target });
      const { cloned, skipped } = res.data;
      setMessage(`Promoted ${cloned.length} source(s) to ${target.toUpperCase()}. ${skipped.length ? `Skipped (already exist): ${skipped.join(', ')}` : ''}`);
    } catch (error) {
      setMessage("Failed to promote sources");
    } finally {
      setPromoting(false);
    }
  };

  const handleSwitchEnv = async (sourceId) => {
    const target = environment === 'uat' ? 'prod' : 'uat';
    if (!window.confirm(`Move this source to ${target.toUpperCase()}?`)) return;
    try {
      await axios.put(`/v1/metric-sources/${sourceId}/environment`, { target_environment: target });
      loadSources();
    } catch (error) {
      setMessage("Failed to switch environment");
    }
  };

  const handleToggleHistorical = async (sourceId) => {
    try {
      await axios.put(`/v1/metric-sources/${sourceId}/historical-precalculated`);
      loadSources();
    } catch (error) {
      setMessage("Failed to toggle historical flag");
    }
  };

  const handleEdit = (source) => {
    setEditingUser(source);
    setOpenForm(true);
  };

  const handleManageQueries = (source) => {
    setSelectedSource(source);
    setOpenQueryManager(true);
  };

  const handleFormClose = (refresh = false) => {
    setOpenForm(false);
    setEditingUser(null);
    if (refresh) loadSources();
  };

  const handleToggleFlag = async (sourceId, flag, currentConfig) => {
    try {
      const currentVal = currentConfig?.[flag] !== false; // default true
      await axios.put(`/v1/metric-sources/${sourceId}/metric-flags`, { [flag]: !currentVal });
      loadSources();
    } catch (error) {
      setMessage("Failed to update metric flag");
    }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6">Application Data Sources</Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button variant="outlined" startIcon={<ContentCopy />} onClick={handlePromote} disabled={promoting}>
            {promoting ? 'Promoting...' : `Clone All → ${environment === 'uat' ? 'PROD' : 'UAT'}`}
          </Button>
          <Button variant="contained" startIcon={<Add />} onClick={() => setOpenForm(true)}>
            Add Source
          </Button>
        </Box>
      </Box>

      {message && <Alert severity={message.startsWith('Failed') ? 'error' : 'success'} sx={{ mb: 2 }} onClose={() => setMessage('')}>{message}</Alert>}

      <Paper sx={{ overflow: 'hidden' }}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ bgcolor: '#f5f5f5' }}>
              <TableCell>Name</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Host / Cluster</TableCell>
              <TableCell align="center">Scheduler Flags</TableCell>
              <TableCell align="center">Historical</TableCell>
              <TableCell align="center">Status</TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} align="center"><CircularProgress size={24} /></TableCell>
              </TableRow>
            ) : sources.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center">No data sources configured.</TableCell>
              </TableRow>
            ) : (
              sources.map((source) => (
                <TableRow key={source.id}>
                  <TableCell>{source.name}</TableCell>
                  <TableCell>
                    <Chip label={source.type} size="small" color="primary" variant="outlined" />
                  </TableCell>
                  <TableCell>
                    {source.type === 'ecs' 
                      ? `${source.config?.cluster || '-'} / ${source.config?.service || '-'}`
                      : source.config?.host || '-'}
                  </TableCell>
                  <TableCell align="center">
                    {source.type === 'ecs' ? (
                      <Box sx={{ display: 'flex', gap: 0.3, justifyContent: 'center', flexWrap: 'wrap' }}>
                        {[
                          { key: 'send_hardware_metrics', label: 'HW' },
                          { key: 'send_network_metrics', label: 'NET' },
                          { key: 'send_application_metrics', label: 'APP' },
                        ].map(f => {
                          const on = source.config?.[f.key] !== false;
                          return (
                            <Tooltip key={f.key} title={`${on ? 'Disable' : 'Enable'} ${f.label} scheduler`}>
                              <Chip
                                label={f.label}
                                size="small"
                                color={on ? 'success' : 'default'}
                                variant={on ? 'filled' : 'outlined'}
                                onClick={() => handleToggleFlag(source.id, f.key, source.config)}
                                sx={{ fontSize: '0.6rem', height: 20, cursor: 'pointer', opacity: on ? 1 : 0.4 }}
                              />
                            </Tooltip>
                          );
                        })}
                      </Box>
                    ) : (
                      <Typography variant="caption" color="textSecondary">—</Typography>
                    )}
                  </TableCell>
                  <TableCell align="center">
                    <Tooltip title="Toggle: Historical metrics pre-computed in Prometheus">
                      <Chip
                        label={source.historical_precalculated ? 'Prometheus' : 'App-Calc'}
                        size="small"
                        color={source.historical_precalculated ? 'warning' : 'default'}
                        variant={source.historical_precalculated ? 'filled' : 'outlined'}
                        onClick={() => handleToggleHistorical(source.id)}
                        sx={{ cursor: 'pointer' }}
                      />
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center">
                    {source.enabled ? <CheckCircle color="success" fontSize="small" /> : <Cancel color="disabled" fontSize="small" />}
                  </TableCell>
                  <TableCell align="center">
                    <Tooltip title="Manage Queries">
                      <IconButton size="small" color="info" onClick={() => handleManageQueries(source)}>
                        <Settings fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Edit Source">
                      <IconButton size="small" onClick={() => handleEdit(source)}>
                        <Edit fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={`Move to ${environment === 'uat' ? 'PROD' : 'UAT'}`}>
                      <IconButton size="small" color="secondary" onClick={() => handleSwitchEnv(source.id)}>
                        <SwapHoriz fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete Source">
                      <IconButton size="small" color="error" onClick={() => handleDelete(source.id)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Paper>

      {/* Forms */}
      <DataSourceForm open={openForm} onClose={handleFormClose} source={editingSource} />
      
      {selectedSource && (
        <Dialog open={openQueryManager} onClose={() => setOpenQueryManager(false)} maxWidth="lg" fullWidth>
          <DialogTitle>
            Manage Metrics: {selectedSource.name}
          </DialogTitle>
          <DialogContent>
            <MetricQueryManager source={selectedSource} />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpenQueryManager(false)}>Close</Button>
          </DialogActions>
        </Dialog>
      )}
    </Box>
  );
}
