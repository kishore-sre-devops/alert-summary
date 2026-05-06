import React from 'react';
import { Card, CardHeader, CardContent, Table, TableBody, TableCell, TableHead, TableRow, Chip, Typography, Box } from '@mui/material';

const ServiceCard = ({ service = {}, servers = [] }) => {
  const { name = 'Service', status = 'offline', totalServers = 0, activeServers = 0, failedServers = 0 } = service;

  const getStatusColor = (status) => {
    if (status === 'online') return '#4CAF50';
    if (status === 'partial') return '#FF9800';
    return '#F44336';
  };

  const getStatusLabel = (status) => {
    if (status === 'online') return 'Online';
    if (status === 'partial') return 'Partial';
    return 'Offline';
  };

  return (
    <Card sx={{ mb: 2, boxShadow: 2 }}>
      <CardHeader
        title={name}
        action={
          <Chip
            label={getStatusLabel(status)}
            sx={{
              backgroundColor: getStatusColor(status),
              color: 'white',
              fontWeight: 'bold',
            }}
          />
        }
        sx={{ backgroundColor: '#f9f9f9' }}
      />
      <CardContent>
        <Box sx={{ mb: 2, display: 'flex', gap: 3 }}>
          <Box>
            <Typography variant="caption" sx={{ color: '#666' }}>Total Servers</Typography>
            <Typography variant="h6" sx={{ fontWeight: 'bold' }}>{totalServers}</Typography>
          </Box>
          <Box>
            <Typography variant="caption" sx={{ color: '#4CAF50' }}>Active</Typography>
            <Typography variant="h6" sx={{ fontWeight: 'bold', color: '#4CAF50' }}>{activeServers}</Typography>
          </Box>
          <Box>
            <Typography variant="caption" sx={{ color: '#F44336' }}>Failed</Typography>
            <Typography variant="h6" sx={{ fontWeight: 'bold', color: '#F44336' }}>{failedServers}</Typography>
          </Box>
        </Box>

        <Table size="small">
          <TableHead>
            <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
              <TableCell sx={{ fontWeight: 'bold' }}>Server Name</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>IP Address</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>Status</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>CPU</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>Memory</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {servers.length > 0 ? (
              servers.map((server, idx) => (
                <TableRow key={idx} sx={{ '&:hover': { backgroundColor: '#fafafa' } }}>
                  <TableCell>{server.name}</TableCell>
                  <TableCell>{server.ip}</TableCell>
                  <TableCell>
                    <Chip
                      label={server.status === 'online' ? 'Online' : 'Offline'}
                      size="small"
                      sx={{
                        backgroundColor: server.status === 'online' ? '#c8e6c9' : '#ffcccc',
                        color: server.status === 'online' ? '#2e7d32' : '#c62828',
                      }}
                    />
                  </TableCell>
                  <TableCell>{server.cpu}%</TableCell>
                  <TableCell>{server.memory}%</TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={5} sx={{ textAlign: 'center', color: '#999', py: 3 }}>
                  No servers available
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

export default ServiceCard;
