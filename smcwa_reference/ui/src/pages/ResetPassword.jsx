import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  CircularProgress,
  InputAdornment,
  IconButton
} from '@mui/material';
import { Visibility, VisibilityOff, LockReset } from '@mui/icons-material';
import axios from '../utils/axiosConfig';
import smcLogo from "../assets/logo-smc.png";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [tokenValid, setTokenValid] = useState(false);
  const [userEmail, setUserEmail] = useState('');

  useEffect(() => {
    axios.defaults.baseURL = '/api';
    
    if (!token) {
      setError('Invalid password reset link');
      setLoading(false);
      return;
    }

    // Verify token
    verifyToken();
  }, [token]);

  const verifyToken = async () => {
    try {
      const res = await axios.get(`/auth/verify-reset-token/${token}`);
      if (res.data.valid) {
        setTokenValid(true);
        setUserEmail(res.data.email);
      } else {
        setError('Invalid or expired password reset link');
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Invalid or expired password reset link';
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!newPassword) {
      setError('Please enter a new password');
      return;
    }

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setSubmitting(true);
    setError('');
    setSuccess('');

    try {
      const res = await axios.post('/auth/reset-password', {
        token: token,
        new_password: newPassword
      });

      setSuccess(res.data.message || 'Password reset successful!');
      
      // Redirect to login after 3 seconds
      setTimeout(() => {
        navigate('/login');
      }, 3000);
      
    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Error resetting password. Please try again.';
      setError(errorMsg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSubmit();
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!tokenValid) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', bgcolor: '#f5f5f5' }}>
        <Card sx={{ maxWidth: 500, p: 3 }}>
          <CardContent>
            <Box sx={{ textAlign: 'center', mb: 3 }}>
              <img src={smcLogo} alt="SMC Logo" style={{ height: 60, marginBottom: 20 }} />
              <Typography variant="h5" fontWeight="bold" color="error">
                Invalid Reset Link
              </Typography>
            </Box>
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              This password reset link is invalid or has expired. Password reset links expire after 30 minutes.
            </Typography>
            <Button
              fullWidth
              variant="contained"
              onClick={() => navigate('/login')}
              sx={{
                mt: 2,
                bgcolor: '#5e35b1',
                '&:hover': { bgcolor: '#4527a0' }
              }}
            >
              Back to Login
            </Button>
          </CardContent>
        </Card>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', bgcolor: '#f5f5f5', p: 2 }}>
      <Card sx={{ maxWidth: 500, width: '100%' }}>
        <CardContent sx={{ p: 4 }}>
          {/* Logo and Title */}
          <Box sx={{ textAlign: 'center', mb: 3 }}>
            <img src={smcLogo} alt="SMC Logo" style={{ height: 60, marginBottom: 20 }} />
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1, mb: 1 }}>
              <LockReset sx={{ fontSize: 32, color: '#5e35b1' }} />
              <Typography variant="h5" fontWeight="bold">
                Reset Password
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary">
              Create a new password for {userEmail}
            </Typography>
          </Box>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

          {!success && (
            <>
              <TextField
                fullWidth
                type={showPassword ? 'text' : 'password'}
                label="New Password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={submitting}
                margin="normal"
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        onClick={() => setShowPassword(!showPassword)}
                        edge="end"
                      >
                        {showPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  )
                }}
                helperText="Must be at least 8 characters long"
              />

              <TextField
                fullWidth
                type={showConfirmPassword ? 'text' : 'password'}
                label="Confirm New Password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={submitting}
                margin="normal"
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                        edge="end"
                      >
                        {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  )
                }}
              />

              <Button
                fullWidth
                variant="contained"
                onClick={handleSubmit}
                disabled={submitting}
                sx={{
                  mt: 3,
                  mb: 2,
                  py: 1.5,
                  bgcolor: '#5e35b1',
                  '&:hover': { bgcolor: '#4527a0' }
                }}
              >
                {submitting ? <CircularProgress size={24} color="inherit" /> : 'Reset Password'}
              </Button>

              <Box sx={{ textAlign: 'center' }}>
                <Button
                  onClick={() => navigate('/login')}
                  sx={{ textTransform: 'none', color: '#5e35b1' }}
                >
                  Back to Login
                </Button>
              </Box>
            </>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
