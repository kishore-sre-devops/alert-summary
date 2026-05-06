// ui/src/pages/LamaMonitor.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Container,
  Box,
  Grid,
  Card,
  CardHeader,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Chip,
  Paper,
  LinearProgress,
  Button,
  Alert,
  AlertTitle,
  IconButton,
  Tooltip,
  CircularProgress,
} from '@mui/material';
import {
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Schedule as ScheduleIcon,
  Security as SecurityIcon,
  VerifiedUser as VerifiedUserIcon,
  AccessTime as AccessTimeIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
} from '@mui/icons-material';
import axios from '../utils/axiosConfig';
import { useEnvironment } from '../hooks/useEnvironment';

// Auto-refresh interval in seconds
const AUTO_REFRESH_INTERVAL = 30;

const LamaMonitor = () => {
  const { environment, withEnvironment } = useEnvironment();
  // Login Status state
  const [failedAttemptsStatus, setFailedAttemptsStatus] = useState(null);
  const [loadingLoginStatus, setLoadingLoginStatus] = useState(true);
  
  // Scheduler Status state
  const [schedulerStatus, setSchedulerStatus] = useState({
    scheduler_running: false,
    jobs: [],
    loading: true,
  });
  
  // Certificate Status state
  const [certificateStatus, setCertificateStatus] = useState({
    loading: true,
    found: false,
    data: null,
  });
  
  // Auto-refresh state
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [nextRefreshIn, setNextRefreshIn] = useState(AUTO_REFRESH_INTERVAL);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const countdownRef = useRef(null);

  // Fetch login status
  const fetchLoginStatus = useCallback(async () => {
    try {
      setLoadingLoginStatus(true);
      
      const response = await axios.get('/v1/exchange/login-status', {
        params: withEnvironment(),
        
      });
      setFailedAttemptsStatus(response.data);
    } catch (error) {
      console.error('Error fetching login status:', error);
    } finally {
      setLoadingLoginStatus(false);
    }
  }, [withEnvironment]);

  // Fetch scheduler status
  const fetchSchedulerStatus = useCallback(async () => {
    try {
      
      const response = await axios.get('/v1/schedulers/status', {
        params: withEnvironment(),
        
      });
      setSchedulerStatus({
        scheduler_running: response.data.scheduler_running,
        jobs: response.data.jobs || [],
        loading: false,
      });
    } catch (error) {
      console.error('Error fetching scheduler status:', error);
      setSchedulerStatus(prev => ({ ...prev, loading: false }));
    }
  }, [withEnvironment]);

  // Fetch certificate status
  const fetchCertificateStatus = useCallback(async () => {
    try {
      
      const response = await axios.get('/v1/certificate/status', {
        params: withEnvironment(),
        
      });
      setCertificateStatus({
        loading: false,
        found: response.data.found,
        data: response.data,
      });
    } catch (error) {
      console.error('Error fetching certificate status:', error);
      setCertificateStatus({
        loading: false,
        found: false,
        data: { error: error.message },
      });
    }
  }, [withEnvironment]);

  // Refresh all data
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await Promise.all([
      fetchLoginStatus(),
      fetchSchedulerStatus(),
      fetchCertificateStatus(),
    ]);
    setLastRefresh(new Date());
    setNextRefreshIn(AUTO_REFRESH_INTERVAL);
    setIsRefreshing(false);
  }, [fetchLoginStatus, fetchSchedulerStatus, fetchCertificateStatus]);

  // Initial load
  useEffect(() => {
    handleRefresh();
  }, [handleRefresh]);

  // Auto-refresh countdown
  useEffect(() => {
    countdownRef.current = setInterval(() => {
      setNextRefreshIn(prev => {
        if (prev <= 1) {
          handleRefresh();
          return AUTO_REFRESH_INTERVAL;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (countdownRef.current) {
        clearInterval(countdownRef.current);
      }
    };
  }, [handleRefresh]);

  // Handle lock permanently action
  const handleLockPermanently = async (env, exchangeId) => {
    if (!window.confirm(`Are you sure you want to permanently lock login for ${env.toUpperCase()} Exchange ID ${exchangeId}?`)) {
      return;
    }
    try {
      
      await axios.post('/v1/exchange/login-lock', {
        environment: env,
        exchange_id: exchangeId,
        action: 'lock_permanently',
        reason: 'Manually locked from LAMA Monitor'
      }, {
        
      });
      fetchLoginStatus();
      alert('Exchange locked successfully');
    } catch (error) {
      console.error('Error locking exchange:', error);
      alert('Failed to lock exchange: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Handle unlock manual lock action
  const handleUnlockManual = async (env, exchangeId) => {
    try {
      
      await axios.post('/v1/exchange/login-lock', {
        environment: env,
        exchange_id: exchangeId,
        action: 'unlock_manual'
      }, {
        
      });
      fetchLoginStatus();
      alert('Exchange unlocked successfully');
    } catch (error) {
      console.error('Error unlocking exchange:', error);
      alert('Failed to unlock exchange: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Handle unlock soft block action
  const handleUnlockSoftBlock = async (env, exchangeId) => {
    if (!window.confirm('Warning: Unlocking allows login attempts 4-5, which may trigger Error 907 (LAMA lockout). Continue?')) {
      return;
    }
    try {
      
      await axios.post('/v1/exchange/login-lock', {
        environment: env,
        exchange_id: exchangeId,
        action: 'unlock_soft_block'
      }, {
        
      });
      fetchLoginStatus();
      alert('Soft block cleared - login attempts allowed');
    } catch (error) {
      console.error('Error clearing soft block:', error);
      alert('Failed to clear soft block: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Handle clear Error 907 action
  const handleClearError907 = async (env, exchangeId) => {
    if (!window.confirm('Clear Error 907 cooldown?\n\nIMPORTANT: Only do this if LAMA has unlocked the account.\nIf LAMA is still locked, you will get Error 907 again.')) {
      return;
    }
    try {
      
      await axios.post('/v1/exchange/login-lock', {
        environment: env,
        exchange_id: exchangeId,
        action: 'clear_error_907'
      }, {
        
      });
      fetchLoginStatus();
      alert('Error 907 cooldown cleared - you can now retry login.');
    } catch (error) {
      console.error('Error clearing Error 907:', error);
      alert('Failed to clear Error 907: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Get status counts for summary
  const getStatusSummary = () => {
    if (!failedAttemptsStatus?.environments) return { ok: 0, warning: 0, error: 0 };
    
    let ok = 0, warning = 0, error = 0;
    Object.values(failedAttemptsStatus.environments).forEach(exchanges => {
      Object.values(exchanges).forEach(status => {
        if (status.is_error_907_locked || status.is_manually_locked) {
          error++;
        } else if (status.is_soft_blocked || status.failed_attempts > 0) {
          warning++;
        } else {
          ok++;
        }
      });
    });
    return { ok, warning, error };
  };

  const statusSummary = getStatusSummary();

  // Get certificate status color
  const getCertStatusColor = () => {
    if (!certificateStatus.found) return '#9e9e9e';
    const status = certificateStatus.data?.status;
    if (status === 'ok') return '#4caf50';
    if (status === 'notice') return '#2196f3';
    if (status === 'warning') return '#ff9800';
    return '#f44336';
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      {/* Header with Auto-refresh Indicator */}
      <Paper 
        elevation={0} 
        sx={{ 
          p: 2, 
          mb: 3, 
          background: 'linear-gradient(135deg, #1a237e 0%, #283593 100%)',
          borderRadius: 2,
          color: 'white'
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 1 }}>
              📊 LAMA Monitor
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.8, mt: 0.5 }}>
              Real-time login status, scheduler monitoring & certificate health
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {/* Auto-refresh countdown */}
            <Box sx={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 1, 
              bgcolor: 'rgba(255,255,255,0.1)', 
              px: 2, 
              py: 1, 
              borderRadius: 2 
            }}>
              <AccessTimeIcon sx={{ fontSize: 18 }} />
              <Typography variant="body2">
                Auto-refresh in <strong>{nextRefreshIn}s</strong>
              </Typography>
            </Box>
            {/* Last updated */}
            <Typography variant="body2" sx={{ opacity: 0.7 }}>
              Updated: {lastRefresh.toLocaleTimeString()}
            </Typography>
            {/* Refresh button */}
            <Tooltip title="Refresh Now">
              <IconButton 
                onClick={handleRefresh} 
                disabled={isRefreshing}
                sx={{ 
                  bgcolor: 'rgba(255,255,255,0.15)', 
                  color: 'white',
                  '&:hover': { bgcolor: 'rgba(255,255,255,0.25)' }
                }}
              >
                {isRefreshing ? (
                  <CircularProgress size={24} color="inherit" />
                ) : (
                  <RefreshIcon />
                )}
              </IconButton>
            </Tooltip>
          </Box>
        </Box>
      </Paper>

      {/* Status Summary Cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={4}>
          <Paper 
            elevation={0}
            sx={{ 
              p: 2.5, 
              borderRadius: 2,
              border: '1px solid #e0e0e0',
              borderLeft: '4px solid #4caf50',
              display: 'flex',
              alignItems: 'center',
              gap: 2
            }}
          >
            <Box sx={{ 
              width: 56, 
              height: 56, 
              borderRadius: '50%', 
              bgcolor: '#e8f5e9', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center' 
            }}>
              <CheckCircleIcon sx={{ color: '#4caf50', fontSize: 32 }} />
            </Box>
            <Box>
              <Typography variant="h3" sx={{ fontWeight: 700, color: '#2e7d32', lineHeight: 1 }}>
                {statusSummary.ok}
              </Typography>
              <Typography variant="body2" color="text.secondary">Healthy</Typography>
            </Box>
          </Paper>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Paper 
            elevation={0}
            sx={{ 
              p: 2.5, 
              borderRadius: 2,
              border: '1px solid #e0e0e0',
              borderLeft: '4px solid #ff9800',
              display: 'flex',
              alignItems: 'center',
              gap: 2
            }}
          >
            <Box sx={{ 
              width: 56, 
              height: 56, 
              borderRadius: '50%', 
              bgcolor: '#fff3e0', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center' 
            }}>
              <WarningIcon sx={{ color: '#ff9800', fontSize: 32 }} />
            </Box>
            <Box>
              <Typography variant="h3" sx={{ fontWeight: 700, color: '#e65100', lineHeight: 1 }}>
                {statusSummary.warning}
              </Typography>
              <Typography variant="body2" color="text.secondary">Warnings</Typography>
            </Box>
          </Paper>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Paper 
            elevation={0}
            sx={{ 
              p: 2.5, 
              borderRadius: 2,
              border: '1px solid #e0e0e0',
              borderLeft: '4px solid #f44336',
              display: 'flex',
              alignItems: 'center',
              gap: 2
            }}
          >
            <Box sx={{ 
              width: 56, 
              height: 56, 
              borderRadius: '50%', 
              bgcolor: '#ffebee', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center' 
            }}>
              <ErrorIcon sx={{ color: '#f44336', fontSize: 32 }} />
            </Box>
            <Box>
              <Typography variant="h3" sx={{ fontWeight: 700, color: '#c62828', lineHeight: 1 }}>
                {statusSummary.error}
              </Typography>
              <Typography variant="body2" color="text.secondary">Blocked/Locked</Typography>
            </Box>
          </Paper>
        </Grid>
      </Grid>

      {/* Alert Banners for Critical Issues */}
      {failedAttemptsStatus?.environments && 
        Object.entries(failedAttemptsStatus.environments).map(([env, exchanges]) => 
          Object.entries(exchanges).map(([exchangeId, status]) => {
            if (status.is_error_907_locked) {
              return (
                <Alert severity="error" sx={{ mb: 2, borderRadius: 2 }} key={`${env}-${exchangeId}-907`}>
                  <AlertTitle>⛔ Error 907 - LAMA Account Locked</AlertTitle>
                  <strong>{status.exchange_name}</strong> ({env.toUpperCase()}) - Contact LAMA support to unlock.
                </Alert>
              );
            }
            if (status.is_soft_blocked) {
              return (
                <Alert severity="warning" sx={{ mb: 2, borderRadius: 2 }} key={`${env}-${exchangeId}-soft`}>
                  <AlertTitle>⚠️ Soft Block - Admin Action Required</AlertTitle>
                  <strong>{status.exchange_name}</strong> ({env.toUpperCase()}) - {status.failed_attempts} failed attempts.
                </Alert>
              );
            }
            return null;
          })
        )
      }

      <Grid container spacing={3}>
        {/* Login Status Section */}
        <Grid item xs={12} lg={8}>
          <Paper elevation={0} sx={{ borderRadius: 2, border: '1px solid #e0e0e0', overflow: 'hidden' }}>
            <Box sx={{ 
              p: 2, 
              bgcolor: '#fafafa', 
              borderBottom: '1px solid #e0e0e0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <SecurityIcon sx={{ color: '#1976d2' }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  Login Status
                </Typography>
              </Box>
              {loadingLoginStatus && <CircularProgress size={20} />}
            </Box>
            <Box sx={{ p: 2 }}>
              {failedAttemptsStatus?.environments ? (
                <Grid container spacing={2}>
                  {Object.entries(failedAttemptsStatus.environments).map(([env, exchanges]) => (
                    <Grid item xs={12} md={6} key={env}>
                      <Paper 
                        elevation={0} 
                        sx={{ 
                          p: 2, 
                          bgcolor: env === 'prod' ? '#fff8e1' : '#e3f2fd',
                          borderRadius: 2,
                          border: `1px solid ${env === 'prod' ? '#ffe082' : '#90caf9'}`
                        }}
                      >
                        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
                          {env === 'prod' ? '🔴' : '🟡'} {env.toUpperCase()} Environment
                        </Typography>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell sx={{ fontWeight: 600, py: 1 }}>Exchange</TableCell>
                              <TableCell sx={{ fontWeight: 600, py: 1 }}>Status</TableCell>
                              <TableCell sx={{ fontWeight: 600, py: 1 }}>Action</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {Object.entries(exchanges).map(([exchangeId, status]) => (
                              <TableRow key={exchangeId}>
                                <TableCell sx={{ py: 1 }}>
                                  <Typography variant="body2" sx={{ fontWeight: 500 }}>
                                    {status.exchange_name}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary">
                                    {status.failed_attempts}/3 attempts
                                  </Typography>
                                </TableCell>
                                <TableCell sx={{ py: 1 }}>
                                  {status.is_error_907_locked ? (
                                    <Chip label="Error 907" size="small" color="error" />
                                  ) : status.is_manually_locked ? (
                                    <Chip label="Locked" size="small" color="error" />
                                  ) : status.is_soft_blocked ? (
                                    <Chip label="Soft Block" size="small" color="warning" />
                                  ) : status.failed_attempts > 0 ? (
                                    <Chip label={`${status.failed_attempts} Failed`} size="small" color="info" />
                                  ) : (
                                    <Chip label="OK" size="small" color="success" />
                                  )}
                                </TableCell>
                                <TableCell sx={{ py: 1 }}>
                                  {status.is_error_907_locked ? (
                                    <Button size="small" variant="outlined" color="warning" onClick={() => handleClearError907(env, parseInt(exchangeId))}>
                                      Clear
                                    </Button>
                                  ) : status.is_manually_locked ? (
                                    <Button size="small" variant="outlined" color="success" onClick={() => handleUnlockManual(env, parseInt(exchangeId))}>
                                      Unlock
                                    </Button>
                                  ) : status.is_soft_blocked ? (
                                    <Box sx={{ display: 'flex', gap: 0.5 }}>
                                      <Button size="small" variant="outlined" color="error" onClick={() => handleLockPermanently(env, parseInt(exchangeId))}>
                                        Lock
                                      </Button>
                                      <Button size="small" variant="contained" color="success" onClick={() => handleUnlockSoftBlock(env, parseInt(exchangeId))}>
                                        Unlock
                                      </Button>
                                    </Box>
                                  ) : (
                                    <Button size="small" variant="text" color="inherit" disabled>
                                      —
                                    </Button>
                                  )}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </Paper>
                    </Grid>
                  ))}
                </Grid>
              ) : (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                  <CircularProgress />
                </Box>
              )}
            </Box>
          </Paper>
        </Grid>

        {/* Right Column - Quick Reference */}
        <Grid item xs={12} lg={4}>
          {/* Quick Reference */}
          <Paper elevation={0} sx={{ borderRadius: 2, border: '1px solid #e0e0e0', overflow: 'hidden' }}>
            <Box sx={{ p: 2, bgcolor: '#fafafa', borderBottom: '1px solid #e0e0e0' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                ℹ️ Login Status Guide
              </Typography>
            </Box>
            <Box sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip label="OK" size="small" color="success" sx={{ width: 80 }} />
                  <Typography variant="caption">Login working</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip label="Failed" size="small" color="info" sx={{ width: 80 }} />
                  <Typography variant="caption">1-2 attempts, will retry</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip label="Soft Block" size="small" color="warning" sx={{ width: 80 }} />
                  <Typography variant="caption">3 attempts, needs action</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip label="Locked" size="small" color="error" sx={{ width: 80 }} />
                  <Typography variant="caption">Admin locked</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip label="Error 907" size="small" color="error" sx={{ width: 80 }} />
                  <Typography variant="caption">LAMA locked</Typography>
                </Box>
              </Box>
            </Box>
          </Paper>
        </Grid>

        {/* Scheduler Status - Full Width */}
        <Grid item xs={12}>
          <Paper elevation={0} sx={{ borderRadius: 2, border: '1px solid #e0e0e0', overflow: 'hidden' }}>
            <Box sx={{ 
              p: 2, 
              bgcolor: '#fafafa', 
              borderBottom: '1px solid #e0e0e0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <ScheduleIcon sx={{ color: '#7c4dff' }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  🗓️ Scheduler Status
                </Typography>
              </Box>
              <Chip 
                icon={schedulerStatus.scheduler_running ? <PlayArrowIcon /> : <StopIcon />}
                label={schedulerStatus.scheduler_running ? "Running" : "Stopped"}
                color={schedulerStatus.scheduler_running ? "success" : "error"}
                size="small"
              />
            </Box>
            <Box sx={{ p: 2 }}>
              {schedulerStatus.loading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                  <CircularProgress />
                </Box>
              ) : schedulerStatus.jobs?.length > 0 ? (
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#f5f5f5' }}>
                      <TableCell sx={{ fontWeight: 600 }}>Job Name</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>Schedule</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>Next Run</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>Status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {schedulerStatus.jobs.map((job, index) => (
                      <TableRow key={index} hover>
                        <TableCell>
                          <Typography variant="body2" sx={{ fontWeight: 500 }}>
                            {job.name || job.id || `Job ${index + 1}`}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" color="text.secondary">
                            {job.trigger || 'N/A'}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">
                            {job.next_run_time 
                              ? new Date(job.next_run_time).toLocaleString('en-IN', {
                                  day: 'numeric',
                                  month: 'short',
                                  year: 'numeric',
                                  hour: '2-digit',
                                  minute: '2-digit',
                                  hour12: true
                                })
                              : 'N/A'}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label="Scheduled" 
                            size="small" 
                            color="success"
                            sx={{ fontSize: '0.7rem' }}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    No scheduled jobs found
                  </Typography>
                </Box>
              )}
            </Box>
          </Paper>
        </Grid>

        {/* SSL Certificate Status - Full Width */}
        <Grid item xs={12}>
          <Paper elevation={0} sx={{ borderRadius: 2, border: '1px solid #e0e0e0', overflow: 'hidden' }}>
            <Box sx={{ 
              p: 2, 
              bgcolor: '#fafafa', 
              borderBottom: '1px solid #e0e0e0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <VerifiedUserIcon sx={{ color: getCertStatusColor() }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  SSL Certificate
                </Typography>
              </Box>
              {certificateStatus.found && (
                <Chip 
                  icon={<CheckCircleIcon />}
                  label={`${certificateStatus.data?.days_remaining} days`}
                  color={certificateStatus.data?.status_color || "default"}
                  size="small"
                />
              )}
            </Box>
            <Box sx={{ p: 2 }}>
              {certificateStatus.loading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
                  <CircularProgress />
                </Box>
              ) : !certificateStatus.found ? (
                <Alert severity="warning">No SSL certificate found</Alert>
              ) : (
                <Grid container spacing={3} alignItems="center">
                  {/* Days Remaining - Visual */}
                  <Grid item xs={12} sm={4} md={3}>
                    <Box sx={{ 
                      textAlign: 'center', 
                      p: 3, 
                      bgcolor: certificateStatus.data.status === 'ok' ? '#e8f5e9' : 
                               certificateStatus.data.status === 'warning' ? '#fff3e0' : '#ffebee',
                      borderRadius: 2
                    }}>
                      <Typography variant="h2" sx={{ fontWeight: 700, color: getCertStatusColor(), lineHeight: 1 }}>
                        {certificateStatus.data.days_remaining}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                        Days Remaining
                      </Typography>
                      <Chip 
                        label={certificateStatus.data.status === 'ok' ? 'Valid' : 
                               certificateStatus.data.status === 'warning' ? 'Expiring Soon' : 'Critical'}
                        color={certificateStatus.data.status_color}
                        size="small"
                        sx={{ mt: 1 }}
                      />
                    </Box>
                  </Grid>

                  {/* Certificate Details */}
                  <Grid item xs={12} sm={8} md={5}>
                    <Table size="small">
                      <TableBody>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 600, border: 0, py: 0.75 }}>Domain</TableCell>
                          <TableCell sx={{ border: 0, py: 0.75 }}>{certificateStatus.data.common_name}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 600, border: 0, py: 0.75 }}>Issuer</TableCell>
                          <TableCell sx={{ border: 0, py: 0.75 }}>{certificateStatus.data.issuer}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 600, border: 0, py: 0.75 }}>Valid From</TableCell>
                          <TableCell sx={{ border: 0, py: 0.75 }}>
                            {certificateStatus.data.not_before ? new Date(certificateStatus.data.not_before).toLocaleDateString() : 'N/A'}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 600, border: 0, py: 0.75 }}>Expires</TableCell>
                          <TableCell sx={{ border: 0, py: 0.75, fontWeight: 600, color: getCertStatusColor() }}>
                            {certificateStatus.data.not_after ? new Date(certificateStatus.data.not_after).toLocaleDateString() : 'N/A'}
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </Grid>

                  {/* Alert Thresholds */}
                  <Grid item xs={12} md={4}>
                    <Paper elevation={0} sx={{ p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                        Alert Thresholds
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                        <Chip label="30d Notice" size="small" variant="outlined" color="info" />
                        <Chip label="15d Warning" size="small" variant="outlined" color="warning" />
                        <Chip label="7d Critical" size="small" variant="outlined" color="error" />
                      </Box>
                    </Paper>
                  </Grid>
                </Grid>
              )}
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Container>
  );
};

export default LamaMonitor;
