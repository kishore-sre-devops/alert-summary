import React from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Chip from '@mui/material/Chip';
import Container from '@mui/material/Container';
import ScheduleIcon from '@mui/icons-material/Schedule';
import DataSourceList from './ApplicationMetrics/DataSourceList';

export default function ApplicationMetrics() {
  return (
    <Container maxWidth="xl" sx={{ py: { xs: 1.5, sm: 2, md: 2.5 }, px: { xs: 1, sm: 1.5, md: 2 } }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: { xs: 2, md: 3 } }}>
        <Box>
          <Typography variant="h4" sx={{ 
            fontWeight: 'bold', 
            fontSize: { xs: '1.25rem', sm: '1.5rem', md: '1.75rem', lg: '2rem' }
          }}>
            Application Data Sources
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage multiple application servers and configure their metric collection queries.
          </Typography>
        </Box>
        <Chip
          icon={<ScheduleIcon />}
          label="Auto-sync every 5 min"
          color="success"
          variant="outlined"
          sx={{ fontWeight: 600 }}
        />
      </Box>

      <DataSourceList />
    </Container>
  );
}
