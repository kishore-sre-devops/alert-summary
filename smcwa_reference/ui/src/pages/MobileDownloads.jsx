import React from 'react';
import { Box, Typography, Button, Card, CardContent, Grid } from '@mui/material';
import { Android, Apple } from '@mui/icons-material';

const MobileDownloads = () => {
  return (
    <Box sx={{ p: { xs: 2, sm: 3, md: 4 } }}>
      <Typography variant="h4" sx={{ mb: 1, fontWeight: 'bold', color: '#1a237e' }}>
        Mobile App Downloads
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
        Download the SMC LAMA Mobile App for Android and iOS.
      </Typography>

      <Grid container spacing={4}>
        {/* Android Section */}
        <Grid item xs={12} md={6}>
          <Card elevation={3} sx={{ height: '100%', borderRadius: 3 }}>
            <CardContent sx={{ textAlign: 'center', py: 5 }}>
              <Android sx={{ fontSize: 60, color: '#3DDC84', mb: 2 }} />
              <Typography variant="h5" gutterBottom>
                Android
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, textAlign: 'left' }}>
                Download the latest stable APK with professional voice alerts and system enhancements:
              </Typography>
              <Box sx={{ textAlign: 'left', mb: 3, pl: 2 }}>
                <Typography variant="body2" color="text.secondary">• <b>Professional Voice Alerts:</b> Standardized voice templates for all metrics (CPU, Disk, Network, DB).</Typography>
                <Typography variant="body2" color="text.secondary">• <b>Better Identification:</b> Voice alerts now clearly identify the specific Drive Partition or Network Interface.</Typography>
                <Typography variant="body2" color="text.secondary">• <b>Fixed Critical Crash:</b> Resolves issues on Android 14+ when receiving red alerts.</Typography>
                <Typography variant="body2" color="text.secondary">• <b>Immediate Escalation:</b> Notifications trigger instantly when severity upgrades.</Typography>
                <Typography variant="body2" color="text.secondary">• <b>Scenario 1 (Fixed):</b> Fast-path acknowledgement directly from notification alarms.</Typography>
                <Typography variant="body2" color="text.secondary">• <b>Scenario 2 (Fixed):</b> Manual acknowledgement with correct resolution time selection.</Typography>
              </Box>
              
              <Button
                variant="contained"
                color="primary"
                size="large"
                href="/download/smclama-v1.0.53-fixed.apk"
                download
                startIcon={<Android />}
                sx={{ borderRadius: 2, px: 4, py: 1.5, fontWeight: 'bold', boxShadow: '0 4px 12px rgba(26, 35, 126, 0.3)' }}
              >
                Download APK v1.0.53
              </Button>

              <Typography variant="caption" display="block" sx={{ mt: 3, fontWeight: 'medium', color: '#666' }}>
                Latest Release: Mar 04, 2026 (Recommended for all users)
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* iOS Section */}
        <Grid item xs={12} md={6}>
          <Card elevation={3} sx={{ height: '100%', borderRadius: 3 }}>
            <CardContent sx={{ textAlign: 'center', py: 5 }}>
              <Apple sx={{ fontSize: 60, color: '#000', mb: 2 }} />
              <Typography variant="h5" gutterBottom>
                iOS
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                iOS builds require TestFlight or Enterprise distribution. 
                Please contact your administrator for the installation link.
              </Typography>
              
              <Button
                variant="outlined"
                color="inherit"
                size="large"
                disabled
                startIcon={<Apple />}
              >
                Download IPA (Unavailable)
              </Button>
              
              <Typography variant="caption" display="block" sx={{ mt: 2 }}>
                Contact Admin
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default MobileDownloads;
