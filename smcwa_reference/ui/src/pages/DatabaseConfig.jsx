import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import IconButton from '@mui/material/IconButton';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Autocomplete from '@mui/material/Autocomplete';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Tooltip from '@mui/material/Tooltip';
import Container from '@mui/material/Container';
import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import FormLabel from '@mui/material/FormLabel';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import StorageIcon from '@mui/icons-material/Storage';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';

export default function DatabaseConfig() {
  const { environment, withEnvironment } = useEnvironment();
  const [configs, setConfigs] = useState([]);
  const [discoveredConfigs, setDiscoveredConfigs] = useState([]);
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [discoveredLoading, setDiscoveredLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingConfig, setEditingConfig] = useState(null);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('');
  const [testing, setTesting] = useState({});
  const location = useLocation();

  // Prometheus DB Exporter sources (from metric_sources table)
  const [promDbSources, setPromDbSources] = useState([]);
  const [promDbDialog, setPromDbDialog] = useState(false);
  const [promDbForm, setPromDbForm] = useState({ name: '', host: '', port: 9090, instance: '', is_replication: false, master_host: '' });
  const [editingPromDb, setEditingPromDb] = useState(null);

  const [formData, setFormData] = useState({
    server_id: '',
    db_type: 'postgresql',
    host: '',
    port: 5432,
    database: '',
    username: '',
    password: '',
    is_replication: false,
    master_host: '',
    master_port: 5432,
    enabled: true,
  });

  const [masterDatabases, setMasterDatabases] = useState([]);

  useEffect(() => {
    loadConfigs();
    loadDiscoveredConfigs();
    loadServers();
    loadPromDbSources();
  }, [location.pathname, environment]);

  useEffect(() => {
    const masters = configs.filter(c => !c.is_replication && c.enabled);
    setMasterDatabases(masters);
  }, [configs]);

  const loadServers = async () => {
    try {
      const response = await axios.get('/v1/servers/', {
        params: { ...withEnvironment(), include_databases: true, size: 200 },
      });
      const serversData = response.data.items || (Array.isArray(response.data) ? response.data : []);
      setServers(serversData);
    } catch (error) {
      console.error('Error loading servers:', error);
      setServers([]);
    }
  };

  const loadConfigs = async () => {
    try {
      setLoading(true);
      setMessage('');
      const response = await axios.get('/v1/database-config/', {
        params: withEnvironment(),
      });
      const configsData = Array.isArray(response.data) ? response.data : (response.data?.configs || []);
      
      const masters = configsData.filter(c => !c.is_replication);
      const slaves = configsData.filter(c => c.is_replication);
      const sortedConfigs = [];
      
      masters.forEach(master => {
        sortedConfigs.push(master);
        const mySlaves = slaves.filter(s => s.master_host === master.host);
        sortedConfigs.push(...mySlaves);
      });
      
      const processedIds = new Set(sortedConfigs.map(c => c.id));
      const remainingSlaves = slaves.filter(s => !processedIds.has(s.id));
      sortedConfigs.push(...remainingSlaves);
      
      setConfigs(sortedConfigs);
    } catch (error) {
      console.error('Error loading database configs:', error);
      setMessage('Error loading database configurations: ' + (error.response?.data?.detail || error.message));
      setMessageType('error');
      setConfigs([]);
    } finally {
      setLoading(false);
    }
  };

  const loadDiscoveredConfigs = async () => {
    try {
      setDiscoveredLoading(true);
      const response = await axios.get('/v1/database-config/discovered', {
        params: withEnvironment(),
      });
      setDiscoveredConfigs(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error('Error loading discovered configs:', error);
      setDiscoveredConfigs([]);
    } finally {
      setDiscoveredLoading(false);
    }
  };

  const handleOpenDialog = (config = null) => {
    if (config) {
      setEditingConfig(config);
      setFormData({
        server_id: config.server_id,
        db_type: config.db_type,
        host: config.host,
        port: config.port,
        database: config.database,
        username: config.username,
        password: '',
        is_replication: config.is_replication,
        master_host: config.master_host || '',
        master_port: config.master_port || 5432,
        enabled: config.enabled,
      });
    } else {
      setEditingConfig(null);
      setFormData({
        server_id: '',
        db_type: 'postgresql',
        host: '',
        port: 5432,
        database: '',
        username: '',
        password: '',
        is_replication: false,
        master_host: '',
        master_port: 5432,
        enabled: true,
      });
    }
    setDialogOpen(true);
    setMessage('');
  };

  const handleCloseDialog = () => {
    setDialogOpen(false);
  };

  const [dialogTesting, setDialogTesting] = useState(false);

  const handleTestConnection = async () => {
    try {
      setDialogTesting(true);
      setMessage('');
      
      const payload = {
        host: formData.host,
        port: formData.port,
        database: formData.database,
        username: formData.username,
        password: formData.password,
        db_type: formData.db_type
      };

      if (!payload.host || !payload.database || !payload.username || (!editingConfig && !payload.password)) {
        setMessage('Please fill in Host, Database, Username and Password to test');
        setMessageType('error');
        setDialogTesting(false);
        return;
      }

      const response = await axios.post('/v1/database-config/test-connection', payload);
      
      if (response.data.success) {
        setMessage(response.data.message);
        setMessageType('success');
        // AUTO-ROLE DETECTION: Update the switch based on probe result
        setFormData({ ...formData, is_replication: response.data.is_replication });
      } else {
        setMessage(`Connection failed: ${response.data.message}`);
        setMessageType('error');
      }
    } catch (error) {
      setMessage('Error testing connection: ' + (error.response?.data?.detail || error.message));
      setMessageType('error');
    } finally {
      setDialogTesting(false);
    }
  };

  const handleSave = async () => {
    try {
      if (!formData.server_id || !formData.host || !formData.database || !formData.username) {
        setMessage('Please fill in all required fields');
        setMessageType('error');
        return;
      }
      if (!editingConfig && !formData.password) {
        setMessage('Password is required for new configurations');
        setMessageType('error');
        return;
      }

      if (editingConfig) {
        const updateData = { ...formData };
        if (!updateData.password) delete updateData.password;
        await axios.put(`/v1/database-config/${editingConfig.id}`, updateData);
        setMessage('Database configuration updated successfully');
      } else {
        await axios.post('/v1/database-config/', formData);
        setMessage('Database configuration created successfully');
      }
      
      setMessageType('success');
      handleCloseDialog();
      loadConfigs();
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error saving configuration');
      setMessageType('error');
    }
  };

  const handleDelete = async (configId) => {
    if (!window.confirm('Are you sure you want to delete this configuration?')) return;
    try {
      await axios.delete(`/v1/database-config/${configId}`);
      setMessage('Configuration deleted successfully');
      setMessageType('success');
      loadConfigs();
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error deleting configuration');
      setMessageType('error');
    }
  };

  const handleDeleteDiscovered = async (dbId) => {
    if (!window.confirm('Are you sure you want to remove this managed RDS instance?')) return;
    try {
      await axios.delete(`/v1/database-config/discovered/${dbId}`);
      setMessage('Managed RDS instance removed successfully');
      setMessageType('success');
      loadDiscoveredConfigs();
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Error removing RDS instance');
      setMessageType('error');
    }
  };

  const handleTest = async (configId) => {
    try {
      setTesting({ ...testing, [configId]: true });
      const response = await axios.post(`/v1/database-config/${configId}/test`, {});
      if (response.data.success) {
        setMessage('Connection successful!');
        setMessageType('success');
      } else {
        setMessage(`Connection failed: ${response.data.message}`);
        setMessageType('error');
      }
    } catch (error) {
      setMessage('Error testing connection');
      setMessageType('error');
    } finally {
      setTesting({ ...testing, [configId]: false });
    }
  };

  const getServerName = (config) => {
    const server = servers.find(s => s.id === config.server_id);
    return server ? server.name : `Server ${config.server_id}`;
  };

  // --- Prometheus DB Exporter CRUD ---
  const loadPromDbSources = async () => {
    try {
      const res = await axios.get('/v1/metric-sources', { params: { environment } });
      setPromDbSources((res.data || []).filter(s => s.type === 'prometheus_db'));
    } catch (e) { console.error('Error loading prometheus DB sources:', e); }
  };

  const handlePromDbSave = async () => {
    try {
      const payload = {
        name: promDbForm.name,
        type: 'prometheus_db',
        config: { host: promDbForm.host, port: promDbForm.port, url: `http://${promDbForm.host}:${promDbForm.port}`, instance: promDbForm.instance, is_replication: promDbForm.is_replication, master_host: promDbForm.master_host },
        environment,
        enabled: true,
      };
      let sourceId = editingPromDb?.id;
      if (editingPromDb) {
        await axios.put(`/v1/metric-sources/${editingPromDb.id}`, payload);
      } else {
        const res = await axios.post('/v1/metric-sources', payload);
        sourceId = res.data?.id;
      }
      // Update database_status replication info
      if (sourceId) {
        try {
          await axios.put(`/v1/database-config/prometheus-db/${sourceId}/replication`, {
            is_replication: promDbForm.is_replication,
            master_host: promDbForm.master_host,
          });
        } catch (e) { console.warn('Replication update skipped:', e); }
      }
      setPromDbDialog(false);
      setEditingPromDb(null);
      setPromDbForm({ name: '', host: '', port: 9090, instance: '', is_replication: false, master_host: '' });
      loadPromDbSources();
      setMessage('Prometheus DB source saved'); setMessageType('success');
    } catch (e) { setMessage('Error saving source'); setMessageType('error'); }
  };

  const handlePromDbDelete = async (id) => {
    if (!window.confirm('Delete this Prometheus DB source?')) return;
    try {
      await axios.delete(`/v1/metric-sources/${id}`);
      loadPromDbSources();
    } catch (e) { setMessage('Error deleting source'); setMessageType('error'); }
  };

  const handlePromDbEdit = (src) => {
    setEditingPromDb(src);
    setPromDbForm({ name: src.name, host: src.config?.host || '', port: src.config?.port || 9090, instance: src.config?.instance || '', is_replication: src.config?.is_replication || false, master_host: src.config?.master_host || '' });
    setPromDbDialog(true);
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Paper sx={{ p: 3, mb: 3, boxShadow: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 600 }}>Database Configuration</Typography>
            <Typography variant="body2" color="textSecondary">Manage database credentials and RDS monitoring</Typography>
          </Box>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => handleOpenDialog()}>Add Config</Button>
        </Box>
      </Paper>

      {message && <Alert severity={messageType} sx={{ mb: 2 }} onClose={() => setMessage('')}>{message}</Alert>}

      <Box sx={{ mb: 4 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1, color: '#1976d2', display: 'flex', alignItems: 'center', gap: 1 }}>
          <StorageIcon fontSize="small" /> Manual Database Configurations
        </Typography>
        <Paper sx={{ boxShadow: 2 }}>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                <TableCell>Server</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Host:Port</TableCell>
                <TableCell>Database</TableCell>
                <TableCell>Role</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? <TableRow><TableCell colSpan={7} align="center">Loading...</TableCell></TableRow> :
               configs.length === 0 ? <TableRow><TableCell colSpan={7} align="center">No configurations found</TableCell></TableRow> :
               configs.map((config) => (
                <TableRow key={config.id}>
                  <TableCell>{config.is_replication ? `↳ ${getServerName(config)}` : getServerName(config)}</TableCell>
                  <TableCell><Chip label={config.db_type.toUpperCase()} size="small" color="primary" /></TableCell>
                  <TableCell>{config.host}:{config.port}</TableCell>
                  <TableCell>{config.database}</TableCell>
                  <TableCell><Chip label={config.is_replication ? "Slave" : "Master"} size="small" color={config.is_replication ? "info" : "success"} /></TableCell>
                  <TableCell><Chip label={config.enabled ? 'Enabled' : 'Disabled'} size="small" /></TableCell>
                  <TableCell>
                    <IconButton size="small" onClick={() => handleTest(config.id)} disabled={testing[config.id]}><CheckCircleIcon /></IconButton>
                    <IconButton size="small" onClick={() => handleOpenDialog(config)}><EditIcon /></IconButton>
                    <IconButton size="small" onClick={() => handleDelete(config.id)} color="error"><DeleteIcon /></IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      </Box>

      <Box sx={{ mb: 4 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1, color: '#2e7d32', display: 'flex', alignItems: 'center', gap: 1 }}>
          <StorageIcon fontSize="small" /> AWS Managed Databases (RDS)
        </Typography>
        <Paper sx={{ boxShadow: 2 }}>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                <TableCell>Instance Name</TableCell>
                <TableCell>Engine</TableCell>
                <TableCell>Environment</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {discoveredLoading ? <TableRow><TableCell colSpan={5} align="center">Loading...</TableCell></TableRow> :
               discoveredConfigs.length === 0 ? <TableRow><TableCell colSpan={5} align="center">No RDS instances found</TableCell></TableRow> :
               discoveredConfigs.map((db) => (
                <TableRow key={db.id}>
                  <TableCell sx={{ fontWeight: 500 }}>{db.name}</TableCell>
                  <TableCell><Chip label={db.engine.toUpperCase()} size="small" variant="outlined" /></TableCell>
                  <TableCell><Chip label={db.environment.toUpperCase()} size="small" variant="outlined" /></TableCell>
                  <TableCell><Chip label={db.status} size="small" color={db.status === 'online' ? 'success' : 'default'} /></TableCell>
                  <TableCell>
                    <IconButton size="small" onClick={() => handleDeleteDiscovered(db.id)} color="error"><DeleteIcon /></IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      </Box>

      {/* Prometheus DB Exporters Section */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, color: '#e65100', display: 'flex', alignItems: 'center', gap: 1 }}>
            <StorageIcon fontSize="small" /> Prometheus DB Exporters
          </Typography>
          <Button size="small" variant="outlined" startIcon={<AddIcon />} onClick={() => { setEditingPromDb(null); setPromDbForm({ name: '', host: '', port: 9090, instance: '', is_replication: false, master_host: '' }); setPromDbDialog(true); }}>
            Add Exporter
          </Button>
        </Box>
        <Paper sx={{ boxShadow: 2 }}>
          <Table>
            <TableHead>
              <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                <TableCell>Name</TableCell>
                <TableCell>Prometheus URL</TableCell>
                <TableCell>Exporter Instance</TableCell>
                <TableCell>Role</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {promDbSources.length === 0 ? (
                <TableRow><TableCell colSpan={5} align="center">No Prometheus DB exporters configured</TableCell></TableRow>
              ) : promDbSources.map((src) => (
                <TableRow key={src.id}>
                  <TableCell sx={{ fontWeight: 500 }}>{src.name}</TableCell>
                  <TableCell>{src.config?.host}:{src.config?.port}</TableCell>
                  <TableCell><Chip label={src.config?.instance || '-'} size="small" variant="outlined" /></TableCell>
                  <TableCell><Chip label={src.config?.is_replication ? 'Replica' : 'Master'} size="small" color={src.config?.is_replication ? 'info' : 'success'} /></TableCell>
                  <TableCell>
                    <IconButton size="small" onClick={() => handlePromDbEdit(src)}><EditIcon /></IconButton>
                    <IconButton size="small" color="error" onClick={() => handlePromDbDelete(src.id)}><DeleteIcon /></IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      </Box>

      {/* Prometheus DB Exporter Dialog */}
      <Dialog open={promDbDialog} onClose={() => setPromDbDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editingPromDb ? 'Edit' : 'Add'} Prometheus DB Exporter</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField label="Name" value={promDbForm.name} onChange={(e) => setPromDbForm({ ...promDbForm, name: e.target.value })} fullWidth placeholder="e.g. MySQL DC Master (192.168.1.21)" />
            <TextField label="Prometheus Host" value={promDbForm.host} onChange={(e) => setPromDbForm({ ...promDbForm, host: e.target.value })} fullWidth placeholder="e.g. 10.215.33.196" />
            <TextField label="Prometheus Port" type="number" value={promDbForm.port} onChange={(e) => setPromDbForm({ ...promDbForm, port: parseInt(e.target.value) })} fullWidth />
            <TextField label="Exporter Instance" value={promDbForm.instance} onChange={(e) => setPromDbForm({ ...promDbForm, instance: e.target.value })} fullWidth placeholder="e.g. localhost:8001" helperText="The instance label in Prometheus that exposes db_status, db_qsize, db_bandwidth, db_latency" />
            <FormControlLabel control={<Switch checked={promDbForm.is_replication} onChange={(e) => setPromDbForm({ ...promDbForm, is_replication: e.target.checked })} />} label="Is Replica?" />
            {promDbForm.is_replication && (
              <Autocomplete
                options={promDbSources.filter(s => s.id !== editingPromDb?.id && !s.config?.is_replication)}
                getOptionLabel={(opt) => `${opt.name} (${opt.config?.host || opt.config?.instance || ''})`}
                value={promDbSources.find(s => (s.config?.host || s.config?.instance || '') === promDbForm.master_host || s.name === promDbForm.master_host) || null}
                onChange={(e, v) => setPromDbForm({ ...promDbForm, master_host: v?.config?.host || v?.config?.instance || '' })}
                renderInput={(params) => <TextField {...params} label="Master Host" placeholder="Select the master database" helperText="Select the master this replica replicates from" />}
                freeSolo
                onInputChange={(e, val, reason) => { if (reason === 'input') setPromDbForm({ ...promDbForm, master_host: val }); }}
              />
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPromDbDialog(false)}>Cancel</Button>
          <Button variant="contained" onClick={handlePromDbSave}>{editingPromDb ? 'Update' : 'Create'}</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>{editingConfig ? 'Edit Configuration' : 'Add Configuration'}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <Autocomplete
              options={servers}
              getOptionLabel={(option) => `${option.name} (${option.ip})`}
              value={servers.find(s => s.id === formData.server_id) || null}
              onChange={(e, v) => setFormData({ ...formData, server_id: v ? v.id : '' })}
              renderInput={(params) => <TextField {...params} label="Select Server" required />}
              disabled={!!editingConfig}
            />
            <FormControl fullWidth>
              <InputLabel>Database Type</InputLabel>
              <Select value={formData.db_type} label="Database Type" onChange={(e) => setFormData({ ...formData, db_type: e.target.value })}>
                <MenuItem value="postgresql">PostgreSQL</MenuItem>
                <MenuItem value="mysql">MySQL</MenuItem>
                <MenuItem value="mssql">MSSQL</MenuItem>
              </Select>
            </FormControl>
            <TextField label="Host" value={formData.host} onChange={(e) => setFormData({ ...formData, host: e.target.value })} fullWidth required />
            <TextField label="Port" type="number" value={formData.port} onChange={(e) => setFormData({ ...formData, port: parseInt(e.target.value) })} fullWidth required />
            <TextField label="Database" value={formData.database} onChange={(e) => setFormData({ ...formData, database: e.target.value })} fullWidth required />
            <TextField label="Username" value={formData.username} onChange={(e) => setFormData({ ...formData, username: e.target.value })} fullWidth required />
            <TextField label="Password" type="password" value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} fullWidth required={!editingConfig} />
            <FormControlLabel control={<Switch checked={formData.is_replication} onChange={(e) => setFormData({ ...formData, is_replication: e.target.checked })} />} label="Is Replica?" />
            {formData.is_replication && (
              <TextField label="Master Host" value={formData.master_host} onChange={(e) => setFormData({ ...formData, master_host: e.target.value })} fullWidth required />
            )}
            <FormControlLabel control={<Switch checked={formData.enabled} onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })} />} label="Enabled" />
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 3, justifyContent: 'space-between' }}>
          <Button 
            variant="outlined" 
            color="info" 
            onClick={handleTestConnection} 
            disabled={dialogTesting}
            startIcon={dialogTesting ? <CircularProgress size={20} /> : <CheckCircleIcon />}
          >
            Test Connection & Probe Role
          </Button>
          <Box>
            <Button onClick={handleCloseDialog} sx={{ mr: 1 }}>Cancel</Button>
            <Button onClick={handleSave} variant="contained" color="primary">
              {editingConfig ? 'Update' : 'Create'}
            </Button>
          </Box>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
