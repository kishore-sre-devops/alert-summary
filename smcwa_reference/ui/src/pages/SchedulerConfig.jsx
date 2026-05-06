import React, { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import Chip from '@mui/material/Chip';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import Save from '@mui/icons-material/Save';
import axios from '../utils/axiosConfig';

export default function SchedulerConfig() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [edits, setEdits] = useState({});

  useEffect(() => { loadJobs(); }, []);

  const loadJobs = async () => {
    try {
      const res = await axios.get('/v1/scheduler-config/');
      setJobs(res.data);
      setEdits({});
    } catch (e) {
      setMessage('Failed to load scheduler config');
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (jobId) => {
    try {
      await axios.put(`/v1/scheduler-config/${jobId}/toggle`);
      loadJobs();
    } catch (e) {
      setMessage('Failed to toggle scheduler');
    }
  };

  const handleEdit = (jobId, field, value) => {
    setEdits(prev => ({ ...prev, [jobId]: { ...prev[jobId], [field]: value } }));
  };

  const handleSave = async (jobId) => {
    const changes = edits[jobId];
    if (!changes) return;
    try {
      const payload = {};
      if (changes.cron_expression !== undefined) payload.cron_expression = changes.cron_expression;
      if (changes.interval_minutes !== undefined) payload.interval_minutes = parseInt(changes.interval_minutes);
      await axios.put(`/v1/scheduler-config/${jobId}`, payload);
      setMessage(`Updated ${jobId} — restart scheduler container to apply`);
      loadJobs();
    } catch (e) {
      setMessage('Failed to save');
    }
  };

  const getDisplayTiming = (job) => {
    if (job.cron_expression) return `cron: ${job.cron_expression}`;
    if (job.interval_minutes) return `every ${job.interval_minutes}m`;
    return '-';
  };

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 2 }}>Scheduler Configuration</Typography>
      <Alert severity="info" sx={{ mb: 2 }}>
        Changes to timing require a scheduler container restart to take effect. Enable/disable takes effect on next restart.
      </Alert>
      {message && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMessage('')}>{message}</Alert>}

      <Paper sx={{ overflow: 'hidden' }}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ bgcolor: '#f5f5f5' }}>
              <TableCell>Job</TableCell>
              <TableCell>Description</TableCell>
              <TableCell>Timing</TableCell>
              <TableCell align="center">Enabled</TableCell>
              <TableCell align="center">Edit Timing</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={5} align="center"><CircularProgress size={24} /></TableCell></TableRow>
            ) : jobs.map((job) => (
              <TableRow key={job.job_id}>
                <TableCell>
                  <Typography variant="body2" fontWeight={600}>{job.name}</Typography>
                  <Typography variant="caption" color="textSecondary">{job.job_id}</Typography>
                </TableCell>
                <TableCell><Typography variant="body2">{job.description || '-'}</Typography></TableCell>
                <TableCell>
                  <Chip label={getDisplayTiming(job)} size="small" variant="outlined" />
                </TableCell>
                <TableCell align="center">
                  <Switch checked={job.enabled} onChange={() => handleToggle(job.job_id)} color="success" />
                </TableCell>
                <TableCell align="center">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'center' }}>
                    {job.cron_expression !== null ? (
                      <TextField
                        size="small" placeholder="0 7 * * *"
                        value={edits[job.job_id]?.cron_expression ?? job.cron_expression}
                        onChange={(e) => handleEdit(job.job_id, 'cron_expression', e.target.value)}
                        sx={{ width: 140 }}
                      />
                    ) : (
                      <TextField
                        size="small" type="number" placeholder="mins"
                        value={edits[job.job_id]?.interval_minutes ?? job.interval_minutes}
                        onChange={(e) => handleEdit(job.job_id, 'interval_minutes', e.target.value)}
                        sx={{ width: 80 }}
                      />
                    )}
                    {edits[job.job_id] && (
                      <Tooltip title="Save">
                        <IconButton size="small" color="primary" onClick={() => handleSave(job.job_id)}>
                          <Save fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </Box>
  );
}
