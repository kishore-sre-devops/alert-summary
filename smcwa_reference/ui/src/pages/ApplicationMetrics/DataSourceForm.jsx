import React, { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, Button,
  FormControl, InputLabel, Select, MenuItem, FormControlLabel, Switch, Grid,
  Typography, Chip
} from '@mui/material';
import axios from '../../utils/axiosConfig';
import { useEnvironment } from '../../hooks/useEnvironment';

const ECS_TYPES = ['ecs'];
const DB_TYPES = ['mysql', 'postgresql', 'mssql'];
const ALL_TYPES = [
  { value: 'elasticsearch', label: 'Elasticsearch' },
  { value: 'prometheus_app', label: 'Prometheus (LAMA App Exporter)' },
  { value: 'ecs', label: 'AWS ECS / CloudWatch' },
  { value: 'mysql', label: 'MySQL' },
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'mssql', label: 'MSSQL (SQL Server)' },
];

export default function DataSourceForm({ open, onClose, source }) {
  const { environment } = useEnvironment();
  const [formData, setFormData] = useState({
    name: '', type: 'prometheus_app', config: {}, enabled: true
  });
  const [saving, setSaving] = useState(false);
  const isECS = ECS_TYPES.includes(formData.type);
  const isEditing = !!source;

  useEffect(() => {
    if (source) {
      setFormData({
        name: source.name,
        type: source.type,
        config: { ...source.config },
        enabled: source.enabled,
        historical_precalculated: source.historical_precalculated || false
      });
    } else {
      setFormData({
        name: '',
        type: 'prometheus_app',
        config: { host: '', port: 9090, username: '', password: '', database_name: '', instance: 'localhost:8000' },
        enabled: true,
        historical_precalculated: false
      });
    }
  }, [source, open]);

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleConfigChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      config: { ...prev.config, [field]: value }
    }));
  };

  const handleSubmit = async () => {
    setSaving(true);
    try {
      const payload = { ...formData, environment };
      if (source) {
        await axios.put(`/v1/metric-sources/${source.id}`, payload);
      } else {
        await axios.post('/v1/metric-sources', payload);
      }
      onClose(true);
    } catch (error) {
      console.error("Error saving source:", error);
      alert("Failed to save source");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={() => onClose(false)} maxWidth="sm" fullWidth>
      <DialogTitle>{isEditing ? 'Edit Source' : 'Add New Data Source'}</DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Grid container spacing={2} sx={{ mt: 0.5 }}>
          <Grid item xs={12}>
            <TextField
              fullWidth label="Source Name"
              value={formData.name}
              onChange={(e) => handleChange('name', e.target.value)}
              placeholder="e.g. Trading App Logs"
            />
          </Grid>
          <Grid item xs={12}>
            <FormControl fullWidth>
              <InputLabel>Source Type</InputLabel>
              <Select
                value={formData.type}
                label="Source Type"
                onChange={(e) => handleChange('type', e.target.value)}
                disabled={isEditing && isECS}
              >
                {ALL_TYPES.map(t => (
                  <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          {/* ECS-specific fields (read-only display) */}
          {isECS && (
            <>
              <Grid item xs={12}>
                <Box sx={{ bgcolor: '#e3f2fd', p: 2, borderRadius: 1, border: '1px solid #90caf9' }}>
                  <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600, textTransform: 'uppercase', display: 'block', mb: 1 }}>
                    AWS ECS Configuration
                  </Typography>
                  <Grid container spacing={1.5}>
                    <Grid item xs={6}>
                      <TextField fullWidth size="small" label="Cluster" value={formData.config.cluster || ''} InputProps={{ readOnly: true }} />
                    </Grid>
                    <Grid item xs={6}>
                      <TextField fullWidth size="small" label="Service" value={formData.config.service || ''} InputProps={{ readOnly: true }} />
                    </Grid>
                    <Grid item xs={6}>
                      <TextField fullWidth size="small" label="Region" value={formData.config.region || ''} InputProps={{ readOnly: true }} />
                    </Grid>
                    <Grid item xs={6}>
                      <TextField fullWidth size="small" label="IAM Role ARN" value={formData.config.role_arn || ''} InputProps={{ readOnly: true }} />
                    </Grid>
                    {formData.config.albArn && (
                      <Grid item xs={12}>
                        <TextField fullWidth size="small" label="ALB ARN" value={formData.config.albArn} InputProps={{ readOnly: true }} />
                      </Grid>
                    )}
                    {formData.config.nlbArn && (
                      <Grid item xs={12}>
                        <TextField fullWidth size="small" label="NLB ARN" value={formData.config.nlbArn} InputProps={{ readOnly: true }} />
                      </Grid>
                    )}
                    {formData.config.targetGroupArn && (
                      <Grid item xs={12}>
                        <TextField fullWidth size="small" label="Target Group ARN" value={formData.config.targetGroupArn} InputProps={{ readOnly: true }} />
                      </Grid>
                    )}
                  </Grid>
                </Box>
              </Grid>
            </>
          )}

          {/* Non-ECS fields: Host, Port, Credentials */}
          {!isECS && (
            <>
              <Grid item xs={8}>
                <TextField
                  fullWidth label="Host"
                  value={formData.config.host || ''}
                  onChange={(e) => handleConfigChange('host', e.target.value)}
                  placeholder="e.g. 192.168.1.100"
                />
              </Grid>
              <Grid item xs={4}>
                <TextField
                  fullWidth label="Port" type="number"
                  value={formData.config.port || ''}
                  onChange={(e) => handleConfigChange('port', parseInt(e.target.value))}
                />
              </Grid>

              {formData.type === 'prometheus_app' && (
                <Grid item xs={12}>
                  <TextField
                    fullWidth label="Exporter Instance"
                    value={formData.config.instance || ''}
                    onChange={(e) => handleConfigChange('instance', e.target.value)}
                    placeholder="e.g. localhost:8001"
                    helperText="The instance label in Prometheus (host:port of the exporter)"
                  />
                </Grid>
              )}

              {DB_TYPES.includes(formData.type) && (
                <Grid item xs={12}>
                  <TextField
                    fullWidth label="Database Name"
                    value={formData.config.database_name || ''}
                    onChange={(e) => handleConfigChange('database_name', e.target.value)}
                    placeholder="e.g. trading_db"
                  />
                </Grid>
              )}

              <Grid item xs={6}>
                <TextField
                  fullWidth label="Username"
                  value={formData.config.username || ''}
                  onChange={(e) => handleConfigChange('username', e.target.value)}
                />
              </Grid>
              <Grid item xs={6}>
                <TextField
                  fullWidth label="Password" type="password"
                  value={formData.config.password || ''}
                  onChange={(e) => handleConfigChange('password', e.target.value)}
                />
              </Grid>
            </>
          )}

          {/* Metric toggles — shown for all types */}
          <Grid item xs={12}>
            <Box sx={{ display: 'flex', gap: 2, bgcolor: '#f8f9fa', p: 1.5, borderRadius: 1, border: '1px solid #e0e0e0' }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.config.send_application_metrics ?? true}
                    onChange={(e) => handleConfigChange('send_application_metrics', e.target.checked)}
                  />
                }
                label="Send Application Metrics"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.config.send_hardware_metrics ?? true}
                    onChange={(e) => handleConfigChange('send_hardware_metrics', e.target.checked)}
                  />
                }
                label="Send Hardware Metrics"
              />
            </Box>
          </Grid>
          <Grid item xs={12}>
            <FormControlLabel
              control={<Switch checked={formData.enabled} onChange={(e) => handleChange('enabled', e.target.checked)} />}
              label="Source Enabled"
            />
          </Grid>
          <Grid item xs={12}>
            <FormControlLabel
              control={<Switch checked={formData.historical_precalculated} onChange={(e) => handleChange('historical_precalculated', e.target.checked)} color="warning" />}
              label="Historical Metrics Pre-computed in Prometheus (skip 21-day calculation)"
            />
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onClose(false)}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
