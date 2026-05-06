import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Box from '@mui/material/Box';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import InputAdornment from '@mui/material/InputAdornment';
import IconButton from '@mui/material/IconButton';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Divider from '@mui/material/Divider';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import GoogleIcon from '@mui/icons-material/Google';
import RefreshIcon from '@mui/icons-material/Refresh';
import Email from '@mui/icons-material/Email';
import Phone from '@mui/icons-material/Phone';
import LockReset from '@mui/icons-material/LockReset';
import axios from '../utils/axiosConfig';
import smcLogo from '../assets/logo-smc.png';
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';

export default function Login(){
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [tabValue, setTabValue] = useState(0);
  const [forgotPasswordOpen, setForgotPasswordOpen] = useState(false);
  const [forgotPasswordEmail, setForgotPasswordEmail] = useState('');
  const [forgotPasswordLoading, setForgotPasswordLoading] = useState(false);
  const [forgotPasswordError, setForgotPasswordError] = useState('');
  const [forgotPasswordSuccess, setForgotPasswordSuccess] = useState('');
  const [supportOpen, setSupportOpen] = useState(false);
  
  // OTP State
  const [otpSent, setOtpSent] = useState(false);
  const [otp, setOtp] = useState('');
  const [otpMessage, setOtpMessage] = useState('');
  const [pendingEmail, setPendingEmail] = useState('');

  // Single API endpoint
  const getDefaultApiEndpoint = () => {
    return '/api';
  };
  
  const [apiEndpoint, setApiEndpoint] = useState(getDefaultApiEndpoint());
  const navigate = useNavigate();

  useEffect(() => {
    // Single API endpoint - always use /api
    const endpoint = '/api';
    
    setApiEndpoint(endpoint);
    // Explicitly set axios baseURL to /api (not /api/prod or /api/uat)
    axios.defaults.baseURL = endpoint;
    
    // Ensure localStorage is consistent
    localStorage.setItem('api_endpoint', endpoint);
    const environment = localStorage.getItem('lama_environment') || 'prod';
    localStorage.setItem('lama_environment', environment);
    
    // Clear any old environment-specific endpoints from localStorage
    const oldEndpoint = localStorage.getItem('api_endpoint');
    if (oldEndpoint && (oldEndpoint.includes('/prod') || oldEndpoint.includes('/uat'))) {
      localStorage.setItem('api_endpoint', endpoint);
    }
  }, []);


  const submit = async () => {
    if (!password) {
      setError('Please enter password');
      return;
    }

    const credentials = tabValue === 0 ? { email, password } : { mobile, password };
    
    setLoading(true);
    setError('');
    
    try {
      // Ensure axios baseURL is set correctly before making request
      // API endpoint is already set in useEffect from localStorage
  
      
      // Use axios with baseURL set, add environment parameter
      const environment = localStorage.getItem('lama_environment') || 'prod';
      const res = await axios.post(`/auth/login?environment=${environment}`, credentials);
      
      if (res.data.otp_required) {
        setOtpSent(true);
        setOtpMessage(res.data.message || 'Verification code sent to your email');
        setPendingEmail(res.data.user_email);
        setLoading(false);
      } else {
        // VAPT FIX: Sensitive token is now in httpOnly cookie
        sessionStorage.setItem('lama_user_email', res.data.user_email);
        sessionStorage.setItem('lama_user_id', res.data.user_id);
        sessionStorage.setItem('lama_user_role', res.data.role);
        navigate('/servers');
        setLoading(false);
      }
    } catch (e) {
      const errorMsg = e.response?.data?.detail || e.message || 'Login failed. Please try again.';
      setError(errorMsg);
      setLoading(false);
    }
  };

  const verifyOtp = async () => {
    if (!otp) {
      setError('Please enter verification code');
      return;
    }
    
    setLoading(true);
    setError('');
    
    try {
      const res = await axios.post('/auth/verify-otp-login', {
        email: pendingEmail || email,
        otp: otp
      });
      
      // VAPT FIX: Sensitive token is now in httpOnly cookie
      sessionStorage.setItem('lama_user_email', res.data.user_email);
      sessionStorage.setItem('lama_user_id', res.data.user_id);
      sessionStorage.setItem('lama_user_role', res.data.role);
      navigate('/servers');
    } catch (e) {
      const errorMsg = e.response?.data?.detail || e.message || 'Verification failed. Please try again.';
      setError(errorMsg);
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      if (otpSent) {
        verifyOtp();
      } else {
        submit();
      }
    }
  };

  const handleForgotPasswordOpen = () => {
    setForgotPasswordOpen(true);
    setForgotPasswordEmail('');
    setForgotPasswordError('');
    setForgotPasswordSuccess('');
  };

  const handleForgotPasswordClose = () => {
    setForgotPasswordOpen(false);
    setForgotPasswordEmail('');
    setForgotPasswordError('');
    setForgotPasswordSuccess('');
  };

  const handleSupportOpen = () => {
    setSupportOpen(true);
  };

  const handleSupportClose = () => {
    setSupportOpen(false);
  };

  const handleGoogleSuccess = async (credentialResponse) => {
    setLoading(true);
    setError('');
    
    try {
        const environment = localStorage.getItem('lama_environment') || 'prod';
        const res = await axios.post(`/auth/google-login?environment=${environment}`, {
            token: credentialResponse.credential
        });
        
        // VAPT FIX: Sensitive token is now in httpOnly cookie
        sessionStorage.setItem('lama_user_email', res.data.user_email);
        sessionStorage.setItem('lama_user_id', res.data.user_id);
        sessionStorage.setItem('lama_user_role', res.data.role);
        navigate('/servers');
        setLoading(false);
    } catch (e) {
        const errorMsg = e.response?.data?.detail || e.message || 'Google Login failed. Please try again.';
        setError(errorMsg);
        setLoading(false);
    }
  };

  const handleGoogleError = () => {
    setError('Google Login Failed');
  };

  const handleForgotPasswordSubmit = async () => {
    if (!forgotPasswordEmail) {
      setForgotPasswordError('Please enter your email address');
      return;
    }

    setForgotPasswordLoading(true);
    setForgotPasswordError('');
    setForgotPasswordSuccess('');

    try {
      const res = await axios.post('/auth/forgot-password', {
        email: forgotPasswordEmail
      });

      setForgotPasswordSuccess(res.data.message || 'If the email exists, a password reset link has been sent.');
      setForgotPasswordEmail('');

      // Close dialog after 3 seconds
      setTimeout(() => {
        handleForgotPasswordClose();
      }, 3000);

    } catch (err) {
      const errorMsg = err.response?.data?.detail || 'Error sending password reset email. Please try again.';
      setForgotPasswordError(errorMsg);
    } finally {
      setForgotPasswordLoading(false);
    }
  };

  return (
    <Box sx={{ display: 'flex', height: '100vh', bgcolor: '#fff' }}>
      {/* Left Side - Branding & Illustration */}
      <Box sx={{ flex: 1, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', p: 4, color: 'white' }}>
        <Box sx={{ mb: 4, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <img 
            src={smcLogo} 
            alt="SMC Logo" 
        
            onError={(e) => console.error('Logo failed to load', e)}
            style={{ 
              maxWidth: 400, 
              maxHeight: 300,
              width: 'auto',
              height: 'auto',
              display: 'block',
              objectFit: 'contain'
            }} 
          />
        </Box>
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>SMC GLOBAL SECURITIES LTD</Typography>
        <Typography variant="body1" sx={{ mb: 4, opacity: 0.9 }}>LAMA Operating Console</Typography>
        
        <Box sx={{ width: '100%', maxWidth: 400, mb: 4 }}>
          <svg viewBox="0 0 400 300" style={{ width: '100%', height: 'auto' }}>
            {/* Illustration - simplified monitoring dashboard */}
            <circle cx="200" cy="150" r="120" fill="rgba(255,255,255,0.1)" />
            <rect x="80" y="80" width="240" height="140" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="2" rx="10" />
            <line x1="100" y1="180" x2="100" y2="200" stroke="rgba(255,255,255,0.4)" strokeWidth="2" />
            <line x1="150" y1="140" x2="150" y2="200" stroke="rgba(255,255,255,0.4)" strokeWidth="2" />
            <line x1="200" y1="120" x2="200" y2="200" stroke="rgba(255,255,255,0.4)" strokeWidth="2" />
            <line x1="250" y1="160" x2="250" y2="200" stroke="rgba(255,255,255,0.4)" strokeWidth="2" />
            <line x1="300" y1="100" x2="300" y2="200" stroke="rgba(255,255,255,0.4)" strokeWidth="2" />
            <polyline points="100,200 150,140 200,120 250,160 300,100" fill="none" stroke="rgba(255,255,255,0.6)" strokeWidth="2" />
            <circle cx="100" cy="200" r="4" fill="rgba(255,255,255,0.8)" />
            <circle cx="150" cy="140" r="4" fill="rgba(255,255,255,0.8)" />
            <circle cx="200" cy="120" r="4" fill="rgba(255,255,255,0.8)" />
            <circle cx="250" cy="160" r="4" fill="rgba(255,255,255,0.8)" />
            <circle cx="300" cy="100" r="4" fill="rgba(255,255,255,0.8)" />
          </svg>
        </Box>

        <Box sx={{ textAlign: 'center', width: '100%' }}>
          <Typography variant="caption" sx={{ opacity: 0.8, display: 'block', mb: 2 }}>
            Moneywise. Be wise.
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap', opacity: 0.7 }}>
            <Link href="https://www.smcindiaonline.com/copyright/" target="_blank" rel="noopener noreferrer" underline="hover" sx={{ color: 'white', fontSize: '0.85rem' }}>Terms & Conditions</Link>
            <span>•</span>
            <Link href="https://www.smcindiaonline.com/media/" target="_blank" rel="noopener noreferrer" underline="hover" sx={{ color: 'white', fontSize: '0.85rem' }}>Blog</Link>
            <span>•</span>
            <Link 
              component="button"
              onClick={handleSupportOpen}
              underline="hover" 
              sx={{ color: 'white', fontSize: '0.85rem', verticalAlign: 'baseline' }}
            >
              Support
            </Link>
            <span>•</span>
            <Link href="https://www.smcindiaonline.com/" target="_blank" rel="noopener noreferrer" underline="hover" sx={{ color: 'white', fontSize: '0.85rem' }}>Sales</Link>
          </Box>
        </Box>
      </Box>

      {/* Right Side - Login Form */}
      <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', p: 4, bgcolor: '#f9f9f9' }}>
        <Paper sx={{ p: 4, width: '100%', maxWidth: 420, boxShadow: 3 }}>
          <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>Welcome Back!</Typography>

          <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
            {otpSent ? 'Enter Verification Code' : 'Enter your Login credentials'}
          </Typography>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          
          {otpSent ? (
            <>
              {/* OTP View */}
              <Alert severity="info" sx={{ mb: 3 }}>
                {otpMessage}
              </Alert>
              
              <TextField
                fullWidth
                label="Verification Code"
                type="text"
                margin="normal"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={loading}
                placeholder="Enter 6-digit code"
                variant="outlined"
                autoFocus
              />
              
              <Button
                variant="contained"
                fullWidth
                sx={{ 
                  mt: 2, 
                  py: 1.3, 
                  fontSize: '1rem', 
                  fontWeight: 600,
                  background: 'linear-gradient(135deg, #2196F3 0%, #1976D2 100%)',
                  textTransform: 'uppercase'
                }}
                onClick={verifyOtp}
                disabled={loading}
              >
                {loading ? <CircularProgress size={24} sx={{ color: 'white' }} /> : 'VERIFY & LOGIN'}
              </Button>
              
              <Button
                fullWidth
                sx={{ mt: 2 }}
                onClick={() => {
                  setOtpSent(false);
                  setOtp('');
                  setError('');
                }}
                disabled={loading}
              >
                Back to Login
              </Button>
            </>
          ) : (
            <>
              {/* Login View */}
              <Tabs value={tabValue} onChange={(e, val) => setTabValue(val)} sx={{ mb: 2, borderBottom: '1px solid #e0e0e0' }}>
                <Tab label={<Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><Email sx={{ fontSize: 18 }} /> Email</Box>} />
                <Tab label={<Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><Phone sx={{ fontSize: 18 }} /> Mobile</Box>} />
              </Tabs>

              {/* Email Tab */}
              {tabValue === 0 && (
                <Box>
                  <TextField
                    fullWidth
                    label="Email"
                    type="email"
                    margin="normal"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    onKeyPress={handleKeyPress}
                    disabled={loading}
                    placeholder="you@example.com"
                    variant="outlined"
                  />
                </Box>
              )}

              {/* Mobile Tab */}
              {tabValue === 1 && (
                <Box>
                  <TextField
                    fullWidth
                    label="Mobile Number"
                    type="tel"
                    margin="normal"
                    value={mobile}
                    onChange={(e) => setMobile(e.target.value)}
                    onKeyPress={handleKeyPress}
                    disabled={loading}
                    placeholder="+91 XXXXX XXXXX"
                    variant="outlined"
                  />
                </Box>
              )}

              {/* Password */}
              <TextField
                fullWidth
                label="Password"
                type={showPassword ? "text" : "password"}
                margin="normal"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={loading}
                variant="outlined"
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        aria-label="toggle password visibility"
                        onClick={() => setShowPassword(!showPassword)}
                        onMouseDown={(e) => e.preventDefault()}
                        edge="end"
                        sx={{ color: 'text.secondary' }}
                      >
                        {showPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />

              {/* Forgot Password */}
              <Box sx={{ textAlign: 'right', my: 1 }}>
                <Link 
                  href="#" 
                  underline="hover" 
                  sx={{ color: '#2196F3', fontSize: '0.9rem', cursor: 'pointer' }}
                  onClick={(e) => {
                    e.preventDefault();
                    handleForgotPasswordOpen();
                  }}
                >
                  Forgot Password?
                </Link>
              </Box>

              {/* Login Button */}
              <Button
                variant="contained"
                fullWidth
                sx={{ 
                  mt: 2, 
                  py: 1.3, 
                  fontSize: '1rem', 
                  fontWeight: 600,
                  background: 'linear-gradient(135deg, #2196F3 0%, #1976D2 100%)',
                  textTransform: 'uppercase'
                }}
                onClick={submit}
                disabled={loading}
              >
                {loading ? <CircularProgress size={24} sx={{ color: 'white' }} /> : 'LOGIN'}
              </Button>

              <Box sx={{ mt: 3, display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>
                <Divider sx={{ width: '100%', mb: 2 }}>OR</Divider>
                <Box sx={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
                  <GoogleOAuthProvider clientId="655248995621-mf0gp9tb3omc7dfjr71kft8qr30ucjr2.apps.googleusercontent.com">
                    <GoogleLogin
                      onSuccess={handleGoogleSuccess}
                      onError={handleGoogleError}
                      useOneTap
                      width="340" // Approximate width to match form
                      theme="filled_blue"
                      shape="rectangular"
                    />
                  </GoogleOAuthProvider>
                </Box>
              </Box>
            </>
          )}

        </Paper>
      </Box>

      {/* Forgot Password Dialog */}
      <Dialog 
        open={forgotPasswordOpen} 
        onClose={handleForgotPasswordClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <LockReset sx={{ color: '#2196F3' }} />
          <Typography variant="h6">Reset Password</Typography>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Enter your email address and we'll send you a link to reset your password.
          </Typography>

          {forgotPasswordError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {forgotPasswordError}
            </Alert>
          )}

          {forgotPasswordSuccess && (
            <Alert severity="success" sx={{ mb: 2 }}>
              {forgotPasswordSuccess}
            </Alert>
          )}

          {!forgotPasswordSuccess && (
            <TextField
              autoFocus
              margin="dense"
              label="Email Address"
              type="email"
              fullWidth
              variant="outlined"
              value={forgotPasswordEmail}
              onChange={(e) => setForgotPasswordEmail(e.target.value)}
              disabled={forgotPasswordLoading}
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  handleForgotPasswordSubmit();
                }
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Email sx={{ color: 'text.secondary' }} />
                  </InputAdornment>
                )
              }}
            />
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button 
            onClick={handleForgotPasswordClose}
            disabled={forgotPasswordLoading}
          >
            Cancel
          </Button>
          {!forgotPasswordSuccess && (
            <Button 
              onClick={handleForgotPasswordSubmit}
              variant="contained"
              disabled={forgotPasswordLoading}
              sx={{
                background: 'linear-gradient(135deg, #2196F3 0%, #1976D2 100%)',
                minWidth: 100
              }}
            >
              {forgotPasswordLoading ? (
                <CircularProgress size={24} color="inherit" />
              ) : (
                'Send Link'
              )}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Support Dialog */}
      <Dialog
        open={supportOpen}
        onClose={handleSupportClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Email sx={{ color: '#2196F3' }} />
          <Typography variant="h6">Contact Support</Typography>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1" sx={{ mb: 2, textAlign: 'center', py: 2 }}>
            Please contact us at:
            <br />
            <Link href="mailto:sre@smcindiaonline.com" sx={{ fontWeight: 'bold', fontSize: '1.2rem', mt: 1, display: 'inline-block' }}>
              sre@smcindiaonline.com
            </Link>
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleSupportClose}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
