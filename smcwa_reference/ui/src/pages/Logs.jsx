import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Container, Card, CardHeader, CardContent, Table, TableBody, TableCell, TableHead, TableRow, Button, Dialog, DialogTitle, DialogContent, TextField, Box, Grid, Typography, Chip, Select, MenuItem, FormControl, InputLabel } from '@mui/material';
import { Search } from '@mui/icons-material';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';
import StatusBadge from '../components/StatusBadge';

const Logs = () => {
  const { environment, withEnvironment } = useEnvironment();
  const [logs, setLogs] = useState([]);
  const [filteredLogs, setFilteredLogs] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [serviceFilter, setServiceFilter] = useState('');
  const location = useLocation(); // Track navigation changes

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 10000);
    
    return () => {
      clearInterval(interval);
    };
  }, [location.pathname, environment]); // Reload when navigating or environment changes

  useEffect(() => {
    filterLogs();
  }, [logs, searchTerm, statusFilter, serviceFilter]);

  const fetchLogs = async () => {
    try {
      const response = await axios.get('/v1/logs');
      setLogs(response.data || []);
    } catch (error) {
      console.error('Error fetching logs:', error);
      // Mock data for demonstration
      setLogs([
        {
          id: 1,
          timestamp: new Date().toISOString(),
          sequence: 1001,
          exchange: 'NSE',
          status: 'success',
          detail: 'Successfully connected to NSE',
        },
        {
          id: 2,
          timestamp: new Date(Date.now() - 60000).toISOString(),
          sequence: 1000,
          exchange: 'BSE',
          status: 'success',
          detail: 'Successfully connected to BSE',
        },
        {
          id: 3,
          timestamp: new Date(Date.now() - 120000).toISOString(),
          sequence: 999,
          exchange: 'MCX',
          status: 'error',
          detail: 'Connection timeout',
        },
        {
          id: 4,
          timestamp: new Date(Date.now() - 180000).toISOString(),
          sequence: 998,
          exchange: 'NCDEX',
          status: 'warning',
          detail: 'High latency detected',
        },
      ]);
    }
  };

  const filterLogs = () => {
    let filtered = logs;

    if (searchTerm) {
      filtered = filtered.filter(
        (log) =>
          log.detail.toLowerCase().includes(searchTerm.toLowerCase()) ||
          log.exchange.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    if (statusFilter) {
      filtered = filtered.filter((log) => log.status === statusFilter);
    }

    if (serviceFilter) {
      filtered = filtered.filter((log) => log.exchange === serviceFilter);
    }

    setFilteredLogs(filtered.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)));
  };

  const formatTime = (isoString) => {
    if (!isoString) return '';
    
    // Ensure the timestamp is treated as UTC if it doesn't have timezone info
    let dateString = isoString;
    if (typeof dateString === 'string' && !dateString.includes('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
      dateString = dateString + 'Z';
    }
    
    const date = new Date(dateString);
    // Format time in IST (Indian Standard Time - Asia/Kolkata) - HH:MM format (no seconds)
    return date.toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  };

  const formatDate = (isoString) => {
    if (!isoString) return '';
    
    // Ensure the timestamp is treated as UTC if it doesn't have timezone info
    let dateString = isoString;
    if (typeof dateString === 'string' && !dateString.includes('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
      dateString = dateString + 'Z';
    }
    
    const date = new Date(dateString);
    // Format date in IST (Indian Standard Time - Asia/Kolkata)
    return date.toLocaleDateString('en-IN', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    });
  };

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 1.5, sm: 2, md: 2.5 }, px: { xs: 1, sm: 1.5, md: 2 } }}>
      <Typography 
        variant="h4" 
        sx={{ 
          mb: { xs: 2, md: 2.5 },
          fontWeight: 'bold',
          fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.75rem', lg: '2rem' }
        }}
      >
        Activity Logs
      </Typography>

      {/* Filters */}
      <Card sx={{ mb: { xs: 2, md: 2.5 }, boxShadow: 2 }}>
        <CardContent sx={{ p: { xs: 1.5, sm: 2, md: 2.5 } }}>
          <Grid container spacing={{ xs: 1.5, sm: 2, md: 2 }} alignItems="flex-end">
            <Grid item xs={4}>
              <TextField
                fullWidth
                placeholder="Search logs..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                variant="outlined"
                size="small"
                InputProps={{
                  startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />,
                }}
              />
            </Grid>
            <Grid item xs={4}>
              <FormControl fullWidth size="small" sx={{ minWidth: 120 }}>
                <InputLabel id="status-filter-label" sx={{ fontSize: '0.875rem' }}>Status</InputLabel>
                <Select
                  labelId="status-filter-label"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  label="Status"
                  sx={{ fontSize: '0.875rem' }}
                  MenuProps={{
                    PaperProps: {
                      sx: {
                        maxHeight: 200,
                        '& .MuiMenuItem-root': {
                          fontSize: '0.875rem',
                          py: 0.75,
                        }
                      }
                    }
                  }}
                >
                  <MenuItem value="" sx={{ fontSize: '0.875rem' }}>All Status</MenuItem>
                  <MenuItem value="success" sx={{ fontSize: '0.875rem' }}>Success</MenuItem>
                  <MenuItem value="error" sx={{ fontSize: '0.875rem' }}>Error</MenuItem>
                  <MenuItem value="warning" sx={{ fontSize: '0.875rem' }}>Warning</MenuItem>
                  <MenuItem value="pending" sx={{ fontSize: '0.875rem' }}>Pending</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={4}>
              <FormControl fullWidth size="small" sx={{ minWidth: 120 }}>
                <InputLabel id="service-filter-label" sx={{ fontSize: '0.875rem' }}>Service</InputLabel>
                <Select
                  labelId="service-filter-label"
                  value={serviceFilter}
                  onChange={(e) => setServiceFilter(e.target.value)}
                  label="Service"
                  sx={{ fontSize: '0.875rem' }}
                  MenuProps={{
                    PaperProps: {
                      sx: {
                        maxHeight: 200,
                        '& .MuiMenuItem-root': {
                          fontSize: '0.875rem',
                          py: 0.75,
                        }
                      }
                    }
                  }}
                >
                  <MenuItem value="" sx={{ fontSize: '0.875rem' }}>All Services</MenuItem>
                  <MenuItem value="NSE" sx={{ fontSize: '0.875rem' }}>NSE</MenuItem>
                  <MenuItem value="BSE" sx={{ fontSize: '0.875rem' }}>BSE</MenuItem>
                  <MenuItem value="MCX" sx={{ fontSize: '0.875rem' }}>MCX</MenuItem>
                  <MenuItem value="NCDEX" sx={{ fontSize: '0.875rem' }}>NCDEX</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Logs Table */}
      <Card sx={{ boxShadow: 2, ml: 0 }}>
        <CardHeader
          title="All Activities"
          subheader={`Total: ${filteredLogs.length} records`}
          sx={{ 
            pb: 1,
            '& .MuiCardHeader-title': {
              fontSize: '1.25rem'
            }
          }}
        />
        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
          <Box sx={{ overflowX: 'auto', width: '100%' }}>
            <Table 
              sx={{ 
                minWidth: 650,
                '& .MuiTableCell-root': {
                  fontSize: '0.875rem',
                  padding: '16px',
                  whiteSpace: 'nowrap'
                }
              }}
            >
              <TableHead>
                <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                  <TableCell sx={{ fontWeight: 'bold' }}>Date</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Time</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Seq#</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Exchange</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Status</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 200 }}>Detail</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredLogs.length > 0 ? (
                  filteredLogs.map((log) => (
                    <TableRow 
                      key={log.id} 
                      sx={{ 
                        '&:hover': { backgroundColor: '#fafafa', cursor: 'pointer' },
                        transition: 'background-color 0.2s ease'
                      }}
                    >
                      <TableCell>{formatDate(log.timestamp)}</TableCell>
                      <TableCell>{formatTime(log.timestamp)}</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>{log.sequence}</TableCell>
                      <TableCell>
                        <Chip
                          label={log.exchange}
                          size="small"
                          variant="outlined"
                          sx={{ fontSize: '0.75rem' }}
                        />
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={log.status} />
                      </TableCell>
                      <TableCell sx={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {log.detail}
                      </TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} sx={{ textAlign: 'center', py: 3, color: '#999' }}>
                      No logs found
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Box>
        </CardContent>
      </Card>
    </Container>
  );
};

export default Logs;
