import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Alert,
  CircularProgress,
  Card,
  CardContent,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Container,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { IconButton, Tooltip } from '@mui/material';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';

const ActivityLog = () => {
  const { environment, withEnvironment } = useEnvironment();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [activityLogs, setActivityLogs] = useState([]);
  
  // Filters
  const [actionFilter, setActionFilter] = useState('');

  useEffect(() => {
    // Initial data load
    fetchActivityLogs();
  }, [environment]); // Reload when environment changes

  const fetchActivityLogs = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await axios.get('/v1/logs');
      const logs = response.data.logs || response.data || [];
      // Sort by timestamp descending (most recent first)
      const sortedLogs = logs.sort((a, b) => {
        const timeA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
        const timeB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
        return timeB - timeA;
      });
      setActivityLogs(sortedLogs);
      setSuccess(`Loaded ${sortedLogs.length} activity logs`);
    } catch (error) {
      console.error('Error fetching activity logs:', error);
      setError('Failed to load activity logs');
    } finally {
      setLoading(false);
    }
  };

  const formatDateTime = (isoString) => {
    if (!isoString) return '';
    // Ensure the timestamp is treated as UTC if it doesn't have timezone info
    let dateString = isoString;
    if (!dateString.includes('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
      // If no timezone info, assume it's UTC and add 'Z'
      dateString = dateString.endsWith('Z') ? dateString : dateString + 'Z';
    }
    const date = new Date(dateString);
    // Format in IST (Indian Standard Time - Asia/Kolkata) - DD-MM-YYYY, HH:MM format
    return date.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  };

  // Get unique actions for filter
  const uniqueActions = Array.from(new Set(activityLogs.map(log => log.action))).sort();

  // Filter logs
  const filteredLogs = activityLogs.filter(log => {
    if (actionFilter && log.action !== actionFilter) return false;
    return true;
  });

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 1.5, sm: 2, md: 2.5 }, px: { xs: 1, sm: 1.5, md: 2 } }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: { xs: 2, md: 2.5 } }}>
        <Typography variant="h4" sx={{ 
          fontWeight: 'bold', 
          fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.75rem', lg: '2rem' }
        }}>
          Activity Log
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title="Refresh">
            <IconButton onClick={fetchActivityLogs}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess('')}>
          {success}
        </Alert>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={6} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Action</InputLabel>
                <Select
                  value={actionFilter || ''}
                  onChange={(e) => setActionFilter(e.target.value)}
                  label="Action"
                >
                  <MenuItem value="">All</MenuItem>
                  {uniqueActions.map(action => (
                    <MenuItem key={action} value={action}>{action}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Paper>
        <TableContainer sx={{ maxHeight: 600 }}>
          <Table stickyHeader size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 'bold' }}>Time</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>User</TableCell>
                <TableCell sx={{ fontWeight: 'bold' }}>Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={3} align="center">
                    <CircularProgress />
                  </TableCell>
                </TableRow>
              ) : filteredLogs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} align="center">No activity logs found</TableCell>
                </TableRow>
              ) : (
                filteredLogs.map((log) => (
                  <TableRow 
                    key={log.id}
                    sx={{
                      '&:nth-of-type(odd)': {
                        backgroundColor: '#f5f5f5',
                      },
                      '&:hover': {
                        backgroundColor: '#e3f2fd',
                      }
                    }}
                  >
                    <TableCell>{formatDateTime(log.timestamp)}</TableCell>
                    <TableCell>{log.user_email || 'System'}</TableCell>
                    <TableCell>{log.action || 'Unknown'}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Container>
  );
};

export default ActivityLog;
