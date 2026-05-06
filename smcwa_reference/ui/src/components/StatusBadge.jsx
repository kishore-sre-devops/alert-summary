import React from 'react';
import { Chip } from '@mui/material';

const StatusBadge = ({ status = 'unknown', variant = 'filled' }) => {
  const statusConfig = {
    online: { color: 'success', label: 'Online', backgroundColor: '#4CAF50', textColor: '#fff' },
    offline: { color: 'error', label: 'Offline', backgroundColor: '#F44336', textColor: '#fff' },
    partial: { color: 'warning', label: 'Partial', backgroundColor: '#FF9800', textColor: '#fff' },
    pending: { color: 'info', label: 'Pending', backgroundColor: '#2196F3', textColor: '#fff' },
    success: { color: 'success', label: 'Success', backgroundColor: '#4CAF50', textColor: '#fff' },
    error: { color: 'error', label: 'Error', backgroundColor: '#F44336', textColor: '#fff' },
    warning: { color: 'warning', label: 'Warning', backgroundColor: '#FF9800', textColor: '#fff' },
    unknown: { color: 'default', label: 'Unknown', backgroundColor: '#999', textColor: '#fff' },
  };

  const config = statusConfig[status] || statusConfig.unknown;

  return (
    <Chip
      label={config.label}
      variant={variant}
      sx={{
        backgroundColor: config.backgroundColor,
        color: config.textColor,
        fontWeight: 'bold',
      }}
    />
  );
};

export default StatusBadge;
