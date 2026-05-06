import React, { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import {
  Typography,
  TextField,
  Button,
  Paper,
  Grid,
  IconButton,
  Alert,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  InputAdornment,
  FormControlLabel,
  Switch
} from '@mui/material';
import {
  Delete,
  Add,
  Sync,
  Cloud,
  VpnKey,
  Public,
  Storage,
  Dns,
  Search,
  Computer as ComputerIcon
} from '@mui/icons-material';
import Checkbox from '@mui/material/Checkbox';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import axios from 'axios';

const AWSDiscovery = ({ environment }) => {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(null); 
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [useIAM, setUseIAM] = useState(false);
  
  const [formData, setFormData] = useState({
    name: '',
    region: 'ap-south-1',
    access_key: '',
    secret_key: '',
    role_arn: ''
  });

  useEffect(() => {
    loadSources();
  }, [environment]);

  const loadSources = async () => {
    setLoading(true);
    try {
      
      const response = await axios.get(`/v1/metric-sources?environment=${environment}`, {
        headers: {  }
      });
      // Filter for cloudwatch types
      const awsSources = response.data.filter(s => s.type === 'cloudwatch');
      setSources(awsSources);
    } catch (err) {
      console.error('Error loading AWS sources:', err);
      setError('Failed to load AWS sources');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateSource = async () => {
    if (!formData.name) {
      setError('Display Name is required');
      return;
    }

    if (!useIAM && (!formData.access_key || !formData.secret_key)) {
      setError('Access Key and Secret Key are required when not using IAM Role');
      return;
    }

    try {
      
      const payload = {
        name: formData.name,
        type: 'cloudwatch',
        environment: environment,
        config: {
          region: formData.region,
          access_key: useIAM ? '' : formData.access_key,
          secret_key: useIAM ? '' : formData.secret_key,
          use_iam: useIAM,
          role_arn: useIAM ? formData.role_arn : ''
        }
      };

      await axios.post('/v1/metric-sources', payload, {
        headers: {  }
      });

      setMessage('AWS Source added successfully');
      setOpenDialog(false);
      setFormData({ name: '', region: 'ap-south-1', access_key: '', secret_key: '', role_arn: '' });
      setUseIAM(false);
      loadSources();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add AWS source');
    }
  };

  const handleDeleteSource = async (id) => {
    if (!window.confirm('Are you sure you want to delete this AWS source?')) return;

    try {
      
      await axios.delete(`/v1/metric-sources/${id}`, {
        headers: {  }
      });
      loadSources();
    } catch (err) {
      setError('Failed to delete source');
    }
  };

  // Selection Dialog State
  const [selectionDialogOpen, setSelectionDialogOpen] = useState(false);
  const [discoveredResources, setDiscoveredResources] = useState({ ec2: [], rds: [], ecs: [] });
  const [selectedIds, setSelectedIds] = useState({ ec2: [], rds: [], ecs: [] });
  const [metricFlags, setMetricFlags] = useState({ send_application_metrics: true, send_hardware_metrics: true });
  const [activeSourceId, setActiveSourceId] = useState(null);

  const handleScan = async (id) => {
    setSyncing(id);
    setActiveSourceId(id);
    setError(null);
    setMessage(null);
    try {
      
      const response = await axios.get(`/v1/metric-sources/${id}/discover-aws`, {
        headers: {  }
      });
      setDiscoveredResources(response.data);
      // Default select all
      setSelectedIds({
        ec2: response.data.ec2.map(i => i.id),
        rds: response.data.rds.map(i => i.id),
        ecs: response.data.ecs.map(i => i.id)
      });
      setMetricFlags({ send_application_metrics: true, send_hardware_metrics: true });
      setSelectionDialogOpen(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to discover AWS resources');
    } finally {
      setSyncing(null);
    }
  };

  const handleSyncSelected = async () => {
    setLoading(true);
    try {
      
      await axios.post(`/v1/metric-sources/${activeSourceId}/sync-aws`, 
        { 
          selected_ids: selectedIds,
          config_override: {
            send_application_metrics: metricFlags.send_application_metrics,
            send_hardware_metrics: metricFlags.send_hardware_metrics
          }
        },
        { headers: {  } }
      );
      setMessage('Selected AWS resources onboarded successfully');
      setSelectionDialogOpen(false);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to sync resources');
    } finally {
      setLoading(false);
    }
  };

  const toggleSelection = (type, id) => {
    setSelectedIds(prev => {
      const current = prev[type];
      const next = current.includes(id) ? current.filter(i => i !== id) : [...current, id];
      return { ...prev, [type]: next };
    });
  };

  return (
    <Paper sx={{ p: 3, mt: 4, border: '1px solid #e0e0e0' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 1 }}>
            <Cloud color="primary" /> AWS CloudWatch Discovery
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Manage AWS credentials and automatically discover EC2, RDS, ECS, and Lambda resources for monitoring.
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => setOpenDialog(true)}
          sx={{ background: 'linear-gradient(135deg, #FF9900 0%, #E07700 100%)' }}
        >
          Add AWS Source
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}
      {message && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMessage(null)}>{message}</Alert>}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}><CircularProgress /></Box>
      ) : sources.length === 0 ? (
        <Box sx={{ textAlign: 'center', py: 4, bgcolor: '#fcfcfc', borderRadius: 1, border: '1px dashed #ddd' }}>
          <Typography color="textSecondary">No AWS sources configured for {environment.toUpperCase()}</Typography>
        </Box>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Source Name</TableCell>
                <TableCell>Region</TableCell>
                <TableCell>Authentication</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sources.map((src) => (
                <TableRow key={src.id}>
                  <TableCell sx={{ fontWeight: 600 }}>{src.name}</TableCell>
                  <TableCell>
                    <Chip label={src.config.region} size="small" variant="outlined" icon={<Public fontSize="small" />} />
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace' }}>
                    {src.config.access_key ? (
                      `${src.config.access_key.substring(0, 4)}...${src.config.access_key.slice(-4)}`
                    ) : (
                      <Chip label="IAM Role" size="small" color="primary" variant="outlined" icon={<Storage fontSize="small" />} />
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1 }}>
                      <Button
                        size="small"
                        variant="outlined"
                        color="primary"
                        startIcon={syncing === src.id ? <CircularProgress size={16} /> : <Search />}
                        onClick={() => handleScan(src.id)}
                        disabled={syncing !== null}
                      >
                        Scan Resources
                      </Button>
                      <IconButton size="small" color="error" onClick={() => handleDeleteSource(src.id)}>
                        <Delete fontSize="small" />
                      </IconButton>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Resource Selection Dialog */}
      <Dialog open={selectionDialogOpen} onClose={() => setSelectionDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 1 }}>
          <Cloud color="primary" /> Select AWS Resources to Onboard
        </DialogTitle>
        <DialogContent dividers>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {/* EC2 Section */}
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <ComputerIcon fontSize="small" /> EC2 Instances ({discoveredResources.ec2.length})
              </Typography>
              <Paper variant="outlined" sx={{ maxHeight: 200, overflow: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableBody>
                    {discoveredResources.ec2.map(i => (
                      <TableRow key={i.id} hover onClick={() => toggleSelection('ec2', i.id)} sx={{ cursor: 'pointer' }}>
                        <TableCell padding="checkbox">
                          <Checkbox checked={selectedIds.ec2.includes(i.id)} />
                        </TableCell>
                        <TableCell sx={{ fontWeight: 500 }}>{i.name}</TableCell>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{i.id}</TableCell>
                        <TableCell>{i.ip}</TableCell>
                      </TableRow>
                    ))}
                    {discoveredResources.ec2.length === 0 && (
                      <TableRow><TableCell colSpan={4} align="center">No EC2 instances found</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </Paper>
            </Box>

            {/* RDS Section */}
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Storage fontSize="small" /> RDS Databases ({discoveredResources.rds.length})
              </Typography>
              <Paper variant="outlined" sx={{ maxHeight: 200, overflow: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableBody>
                    {discoveredResources.rds.map(i => (
                      <TableRow key={i.id} hover onClick={() => toggleSelection('rds', i.id)} sx={{ cursor: 'pointer' }}>
                        <TableCell padding="checkbox">
                          <Checkbox checked={selectedIds.rds.includes(i.id)} />
                        </TableCell>
                        <TableCell sx={{ fontWeight: 500 }}>{i.id}</TableCell>
                        <TableCell sx={{ fontSize: '0.8rem' }}>{i.engine}</TableCell>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{i.endpoint}</TableCell>
                      </TableRow>
                    ))}
                    {discoveredResources.rds.length === 0 && (
                      <TableRow><TableCell colSpan={4} align="center">No RDS databases found</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </Paper>
            </Box>

            {/* ECS Section */}
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Dns fontSize="small" /> ECS Services ({discoveredResources.ecs.length})
              </Typography>
              <Paper variant="outlined" sx={{ maxHeight: 200, overflow: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableBody>
                    {discoveredResources.ecs.map(i => (
                      <TableRow key={i.id} hover onClick={() => toggleSelection('ecs', i.id)} sx={{ cursor: 'pointer' }}>
                        <TableCell padding="checkbox">
                          <Checkbox checked={selectedIds.ecs.includes(i.id)} />
                        </TableCell>
                        <TableCell sx={{ fontWeight: 500 }}>{i.name}</TableCell>
                        <TableCell sx={{ fontSize: '0.8rem' }}>{i.clusterName}</TableCell>
                      </TableRow>
                    ))}
                    {discoveredResources.ecs.length === 0 && (
                      <TableRow><TableCell colSpan={3} align="center">No ECS services found</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </Paper>
            </Box>
          </Box>
          
          <Box sx={{ mt: 3, p: 2, bgcolor: '#f5f5f5', borderRadius: 1, border: '1px solid #e0e0e0' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>Monitoring Toggles</Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <FormControlLabel
                  control={
                    <Switch 
                      checked={metricFlags.send_application_metrics} 
                      onChange={(e) => setMetricFlags({...metricFlags, send_application_metrics: e.target.checked})} 
                    />
                  }
                  label="Send Application Metrics"
                />
              </Grid>
              <Grid item xs={6}>
                <FormControlLabel
                  control={
                    <Switch 
                      checked={metricFlags.send_hardware_metrics} 
                      onChange={(e) => setMetricFlags({...metricFlags, send_hardware_metrics: e.target.checked})} 
                    />
                  }
                  label="Send Hardware Metrics"
                />
              </Grid>
            </Grid>
            <Typography variant="caption" color="textSecondary">
              Tip: Uncheck 'Application Metrics' if you only want to track CPU/Memory without sending '0' throughput values.
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectionDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleSyncSelected} 
            variant="contained" 
            color="primary"
            disabled={loading || (selectedIds.ec2.length === 0 && selectedIds.rds.length === 0 && selectedIds.ecs.length === 0)}
          >
            {loading ? <CircularProgress size={24} /> : `Onboard ${selectedIds.ec2.length + selectedIds.rds.length + selectedIds.ecs.length} Resources`}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Add Source Dialog */}
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add AWS CloudWatch Source</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              fullWidth
              label="Display Name"
              placeholder="e.g. AWS Production Account"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              size="small"
            />
            <TextField
              fullWidth
              label="AWS Region"
              placeholder="ap-south-1"
              value={formData.region}
              onChange={(e) => setFormData({ ...formData, region: e.target.value })}
              size="small"
            />
            
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <input
                type="checkbox"
                id="useIAM"
                checked={useIAM}
                onChange={(e) => setUseIAM(e.target.checked)}
                style={{ width: 18, height: 18 }}
              />
              <label htmlFor="useIAM" style={{ cursor: 'pointer', fontWeight: 500 }}>
                Use IAM Role (Instance Profile)
              </label>
            </Box>
            
            {useIAM && (
              <TextField
                fullWidth
                label="Role ARN (Optional)"
                placeholder="arn:aws:iam::123456789012:role/CrossAccountRole"
                value={formData.role_arn}
                onChange={(e) => setFormData({ ...formData, role_arn: e.target.value })}
                size="small"
                helperText="Leave empty to use the instance's own role. Enter ARN for cross-account access."
              />
            )}
            
            {!useIAM && (
              <>
                <TextField
                  fullWidth
                  label="AWS Access Key"
                  value={formData.access_key}
                  onChange={(e) => setFormData({ ...formData, access_key: e.target.value })}
                  size="small"
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <VpnKey fontSize="small" />
                      </InputAdornment>
                    ),
                  }}
                />
                <TextField
                  fullWidth
                  label="AWS Secret Key"
                  type={showSecret ? 'text' : 'password'}
                  value={formData.secret_key}
                  onChange={(e) => setFormData({ ...formData, secret_key: e.target.value })}
                  size="small"
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <VpnKey fontSize="small" />
                      </InputAdornment>
                    ),
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton onClick={() => setShowSecret(!showSecret)} size="small">
                          {showSecret ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    )
                  }}
                />
              </>
            )}
            
            <Alert severity="info" icon={<Public />}>
              {useIAM 
                ? "LAMA will use the IAM Role attached to this server. Ensure 'CloudWatchReadOnlyAccess' policy is attached."
                : "LAMA will use these credentials to discover EC2 and RDS instances via AWS SDK (boto3)."
              }
            </Alert>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>Cancel</Button>
          <Button onClick={handleCreateSource} variant="contained" color="primary">Add Source</Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default AWSDiscovery;
