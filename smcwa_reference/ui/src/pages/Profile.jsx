import React, { useState, useEffect } from 'react';
import {
  Container,
  Card,
  CardHeader,
  CardContent,
  TextField,
  Button,
  Typography,
  Box,
  Alert,
  Grid,
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Paper,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  InputAdornment,
  IconButton,
} from '@mui/material';
import { Visibility, VisibilityOff, CheckCircle, Cancel } from '@mui/icons-material';
import { Person, Lock, Edit, Save } from '@mui/icons-material';
import axios from '../utils/axiosConfig';
import { useNavigate, useLocation } from 'react-router-dom';

const UserProfile = () => {
  const [user, setUser] = useState({
    id: 0,
    email: '',
    mobile: '',
    full_name: '',
    role: '',
    created_at: '',
  });
  const [editMode, setEditMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('info');
  const [showPasswordDialog, setShowPasswordDialog] = useState(false);
  const [passwords, setPasswords] = useState({
    old_password: '',
    new_password: '',
    confirm_password: '',
  });
  const [showPasswords, setShowPasswords] = useState({
    old_password: false,
    new_password: false,
    confirm_password: false,
  });
  const [passwordDialogMessage, setPasswordDialogMessage] = useState('');
  const [passwordDialogMessageType, setPasswordDialogMessageType] = useState('info');
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // Single API endpoint
    axios.defaults.baseURL = '/api';
    
    loadUserProfile();
  }, [location.pathname]);

  const loadUserProfile = async () => {
    try {
      
      const userId = sessionStorage.getItem('lama_user_id');
      
      if (!sessionStorage.getItem('lama_token') || !userId) {
        setMessage('Not authenticated. Please login again.');
        setMessageType('error');
        return;
      }

      // Fetch user data from backend
      const response = await axios.get(`/v1/users/${userId}`, {
        headers: {  },
      });

      const userData = response.data;
      const updatedUser = {
        id: userData.id,
        email: userData.email || '',
        mobile: userData.mobile || '',
        full_name: userData.full_name || '',
        role: userData.role || 'user',
        created_at: userData.created_at ? new Date(userData.created_at).toLocaleDateString() : new Date().toLocaleDateString(),
      };
      setUser(updatedUser);

      // Update localStorage
      if (userData.email) localStorage.setItem('lama_user_email', userData.email);
      if (userData.full_name) localStorage.setItem('lama_user_name', userData.full_name);
      if (userData.mobile) {
        localStorage.setItem('lama_user_mobile', userData.mobile);
      } else {
        localStorage.removeItem('lama_user_mobile');
      }
    } catch (error) {
      console.error('Error loading user profile:', error);
      // Fallback to localStorage if API fails
      const userEmail = sessionStorage.getItem('lama_user_email');
      const userId = sessionStorage.getItem('lama_user_id');
      const userRole = sessionStorage.getItem('lama_user_role');

      if (userEmail && userId) {
        setUser({
          id: parseInt(userId),
          email: userEmail,
          mobile: sessionStorage.getItem('lama_user_mobile') || '',
          full_name: sessionStorage.getItem('lama_user_name') || 'User',
          role: userRole || 'user',
          created_at: new Date().toLocaleDateString(),
        });
      }
    }
  };

  const handleProfileChange = (field, value) => {
    setUser({ ...user, [field]: value });
  };

  const saveProfile = async () => {
    setLoading(true);
    setMessage('');
    try {
      
      const userId = sessionStorage.getItem('lama_user_id');

      if (!sessionStorage.getItem('lama_token') || !userId) {
        setMessage('Not authenticated. Please login again.');
        setMessageType('error');
        setLoading(false);
        return;
      }

      const response = await axios.put(`/v1/users/${user.id}`, {
        full_name: user.full_name || null,
        mobile: user.mobile || null,
      }, {
        headers: {  },
      });

      // Update state with response data
      if (response.data) {
        const updatedUser = {
          id: response.data.id,
          email: response.data.email || '',
          mobile: response.data.mobile || '',
          full_name: response.data.full_name || '',
          role: response.data.role || 'user',
          created_at: response.data.created_at ? new Date(response.data.created_at).toLocaleDateString() : new Date().toLocaleDateString(),
        };
        setUser(updatedUser);

        // Update localStorage
        if (response.data.full_name) localStorage.setItem('lama_user_name', response.data.full_name);
        if (response.data.mobile) {
          localStorage.setItem('lama_user_mobile', response.data.mobile);
        } else {
          localStorage.removeItem('lama_user_mobile');
        }
      }

      setMessage('Profile updated successfully!');
      setMessageType('success');
      setEditMode(false);
      
      // Reload profile to ensure we have latest data
      await loadUserProfile();
    } catch (error) {
      console.error('Profile update error:', error);
      const errorMsg = error.response?.data?.detail || error.message || 'Error updating profile';
      setMessage('Error updating profile: ' + errorMsg);
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const validatePassword = (password) => {
    const errors = [];
    if (password.length < 8) {
      errors.push('At least 8 characters');
    }
    if (!/[A-Z]/.test(password)) {
      errors.push('One uppercase letter');
    }
    if (!/[a-z]/.test(password)) {
      errors.push('One lowercase letter');
    }
    if (!/[0-9]/.test(password)) {
      errors.push('One number');
    }
    if (!/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)) {
      errors.push('One special character (!@#$%^&*()_+-=[]{}|;:,.<>?)');
    }
    return errors;
  };

  const handlePasswordChange = async () => {
    // Clear previous messages
    setPasswordDialogMessage('');
    setMessage('');
    
    // Validate passwords match
    if (passwords.new_password !== passwords.confirm_password) {
      setPasswordDialogMessage('New password and confirm password do not match!');
      setPasswordDialogMessageType('error');
      return;
    }

    // Validate password policy
    const passwordErrors = validatePassword(passwords.new_password);
    if (passwordErrors.length > 0) {
      setPasswordDialogMessage(`Password does not meet the complexity requirements. Missing: ${passwordErrors.join(', ')}`);
      setPasswordDialogMessageType('error');
      return;
    }

    // Check if new password is same as old
    if (passwords.old_password === passwords.new_password) {
      setPasswordDialogMessage('New password must be different from current password');
      setPasswordDialogMessageType('error');
      return;
    }

    setLoading(true);
    setPasswordDialogMessage('');
    try {
      

      if (!sessionStorage.getItem('lama_token')) {
        setPasswordDialogMessage('Not authenticated. Please login again.');
        setPasswordDialogMessageType('error');
        setLoading(false);
        return;
      }

      const response = await axios.post('/auth/change-password', {
        old_password: passwords.old_password,
        new_password: passwords.new_password,
      }, {
        headers: {  },
      });

      // Success message
      setPasswordDialogMessage('Password successfully changed! Please logout and login with your new password.');
      setPasswordDialogMessageType('success');
      
      // Clear password fields
      setPasswords({
        old_password: '',
        new_password: '',
        confirm_password: '',
      });
      
      // Logout after password change for security (after showing success message)
      setTimeout(() => {
        setShowPasswordDialog(false);
        handleLogout();
      }, 3000);
    } catch (error) {
      let errorMsg = 'Password Change Failure. Try again.';
      
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail;
        if (detail.includes('not authenticated') || detail.includes('Not authenticated')) {
          errorMsg = 'Not authenticated. Please login again.';
        } else if (detail.includes('Password policy violation') || detail.includes('complexity')) {
          errorMsg = 'Password does not meet the complexity requirements. Please check all requirements.';
        } else if (detail.includes('Current password is incorrect') || detail.includes('incorrect')) {
          errorMsg = 'Current password is incorrect. Please try again.';
        } else if (detail.includes('Invalid or expired token')) {
          errorMsg = 'Your session has expired. Please login again.';
        } else {
          errorMsg = detail;
        }
      } else if (error.message) {
        if (error.message.includes('Network Error') || error.message.includes('timeout')) {
          errorMsg = 'Network error. Please check your connection and try again.';
        } else {
          errorMsg = `Password Change Failure: ${error.message}`;
        }
      }
      
      setPasswordDialogMessage(errorMsg);
      setPasswordDialogMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await axios.post('/auth/logout');
    } catch (err) {
      console.error("Logout error:", err);
    }
    
    const keysToRemove = [
      'lama_jwt', 'lama_token', 'lama_user_email', 'lama_user_id', 
      'lama_user_role', 'lama_user_name', 'lama_user_mobile'
    ];
    
    keysToRemove.forEach(key => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    });
    
    navigate('/login');
  };

  return (
    <Box sx={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
      <Typography variant="h4" sx={{ mb: 3, fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 1 }}>
        <Person /> My Profile
      </Typography>

      {message && (
        <Alert severity={messageType} sx={{ mb: 3 }} onClose={() => setMessage('')}>
          {message}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* User Profile Card */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardHeader
              title="Profile Information"
              action={
                <Button
                  startIcon={editMode ? <Save /> : <Edit />}
                  onClick={editMode ? saveProfile : () => setEditMode(true)}
                  disabled={loading}
                  variant={editMode ? 'contained' : 'outlined'}
                >
                  {editMode ? 'Save' : 'Edit'}
                </Button>
              }
            />
            <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <TextField
                fullWidth
                label="Email Address"
                value={user.email}
                disabled
                variant="outlined"
                helperText="Email cannot be changed"
              />

              <TextField
                fullWidth
                label="Full Name"
                value={user.full_name}
                onChange={(e) => handleProfileChange('full_name', e.target.value)}
                disabled={!editMode}
                variant="outlined"
              />

              <TextField
                fullWidth
                label="Mobile Number"
                value={user.mobile}
                onChange={(e) => handleProfileChange('mobile', e.target.value)}
                disabled={!editMode}
                variant="outlined"
                type="tel"
                helperText={editMode ? "Enter your mobile number (e.g., +91 9876543210)" : ""}
              />

              <TextField
                fullWidth
                label="Role"
                value={user.role}
                disabled
                variant="outlined"
                helperText="Contact admin to change role"
              />

              <TextField
                fullWidth
                label="Member Since"
                value={user.created_at}
                disabled
                variant="outlined"
              />
            </CardContent>
          </Card>
        </Grid>

        {/* Security Card */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader title="Security" />
            <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<Lock />}
                onClick={() => setShowPasswordDialog(true)}
              >
                Change Password
              </Button>
              
              <Divider sx={{ my: 1 }} />
              
              <Button
                fullWidth
                variant="contained"
                color="error"
                onClick={handleLogout}
              >
                Logout
              </Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Change Password Dialog */}
      <Dialog 
        open={showPasswordDialog} 
        onClose={() => {
          if (!loading) {
            setShowPasswordDialog(false);
            setPasswords({ old_password: '', new_password: '', confirm_password: '' });
            setShowPasswords({ old_password: false, new_password: false, confirm_password: false });
            setPasswordDialogMessage('');
          }
        }} 
         
        fullWidth
        PaperProps={{
          sx: { zIndex: 1300 } // Ensure dialog is above other elements
        }}
      >
        <DialogTitle>Change Password</DialogTitle>
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {/* Error/Success Message - At Top of Dialog */}
          {passwordDialogMessage && (
            <Alert 
              severity={passwordDialogMessageType} 
              sx={{ 
                mb: 1,
                zIndex: 1301, // Ensure alert is visible
                '& .MuiAlert-message': {
                  fontSize: '0.875rem',
                  fontWeight: passwordDialogMessageType === 'success' ? 'bold' : 'normal'
                }
              }}
              onClose={() => setPasswordDialogMessage('')}
            >
              {passwordDialogMessage}
            </Alert>
          )}

          <TextField
            fullWidth
            type={showPasswords.old_password ? 'text' : 'password'}
            label="Current Password"
            value={passwords.old_password}
            onChange={(e) => setPasswords({ ...passwords, old_password: e.target.value })}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={() => setShowPasswords({ ...showPasswords, old_password: !showPasswords.old_password })}
                    edge="end"
                  >
                    {showPasswords.old_password ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          <TextField
            fullWidth
            type={showPasswords.new_password ? 'text' : 'password'}
            label="New Password"
            value={passwords.new_password}
            onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={() => setShowPasswords({ ...showPasswords, new_password: !showPasswords.new_password })}
                    edge="end"
                  >
                    {showPasswords.new_password ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
            helperText={passwords.new_password ? `${passwords.new_password.length} characters` : ''}
          />
          <TextField
            fullWidth
            type={showPasswords.confirm_password ? 'text' : 'password'}
            label="Confirm New Password"
            value={passwords.confirm_password}
            onChange={(e) => setPasswords({ ...passwords, confirm_password: e.target.value })}
            error={passwords.confirm_password !== '' && passwords.new_password !== passwords.confirm_password}
            helperText={
              passwords.confirm_password !== '' && passwords.new_password !== passwords.confirm_password
                ? 'Passwords do not match'
                : ''
            }
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={() => setShowPasswords({ ...showPasswords, confirm_password: !showPasswords.confirm_password })}
                    edge="end"
                  >
                    {showPasswords.confirm_password ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />

          {/* ITIL Password Policy Instructions - At Bottom */}
          <Paper sx={{ p: 2, bgcolor: '#f5f5f5', borderLeft: '4px solid #1976d2', mt: 2 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1.5, color: '#1976d2' }}>
              Password Complexity Requirements (ITIL Best Practices)
            </Typography>
            <Typography variant="caption" sx={{ color: '#666', mb: 1.5, display: 'block' }}>
              Your password must meet all of the following requirements:
            </Typography>
            <List dense sx={{ py: 0 }}>
              <ListItem sx={{ py: 0.5, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {passwords.new_password.length >= 8 ? (
                    <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
                  ) : (
                    <Cancel sx={{ fontSize: 16, color: 'error.main' }} />
                  )}
                </ListItemIcon>
                <ListItemText 
                  primary="Minimum 8 characters (12+ characters recommended for enhanced security)" 
                  primaryTypographyProps={{ variant: 'caption', sx: { fontSize: '0.75rem' } }}
                />
              </ListItem>
              <ListItem sx={{ py: 0.5, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {/[A-Z]/.test(passwords.new_password) ? (
                    <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
                  ) : (
                    <Cancel sx={{ fontSize: 16, color: 'error.main' }} />
                  )}
                </ListItemIcon>
                <ListItemText 
                  primary="At least one uppercase letter (A-Z)" 
                  primaryTypographyProps={{ variant: 'caption', sx: { fontSize: '0.75rem' } }}
                />
              </ListItem>
              <ListItem sx={{ py: 0.5, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {/[a-z]/.test(passwords.new_password) ? (
                    <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
                  ) : (
                    <Cancel sx={{ fontSize: 16, color: 'error.main' }} />
                  )}
                </ListItemIcon>
                <ListItemText 
                  primary="At least one lowercase letter (a-z)" 
                  primaryTypographyProps={{ variant: 'caption', sx: { fontSize: '0.75rem' } }}
                />
              </ListItem>
              <ListItem sx={{ py: 0.5, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {/[0-9]/.test(passwords.new_password) ? (
                    <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
                  ) : (
                    <Cancel sx={{ fontSize: 16, color: 'error.main' }} />
                  )}
                </ListItemIcon>
                <ListItemText 
                  primary="At least one numeric digit (0-9)" 
                  primaryTypographyProps={{ variant: 'caption', sx: { fontSize: '0.75rem' } }}
                />
              </ListItem>
              <ListItem sx={{ py: 0.5, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {/[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(passwords.new_password) ? (
                    <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
                  ) : (
                    <Cancel sx={{ fontSize: 16, color: 'error.main' }} />
                  )}
                </ListItemIcon>
                <ListItemText 
                  primary="At least one special character (! @ # $ % ^ & * ( ) _ + - = [ ] { } | ; : , . < > ?)" 
                  primaryTypographyProps={{ variant: 'caption', sx: { fontSize: '0.75rem' } }}
                />
              </ListItem>
              <ListItem sx={{ py: 0.5, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {passwords.new_password === passwords.confirm_password && passwords.new_password ? (
                    <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
                  ) : (
                    <Cancel sx={{ fontSize: 16, color: 'error.main' }} />
                  )}
                </ListItemIcon>
                <ListItemText 
                  primary="New password and confirm password must match" 
                  primaryTypographyProps={{ variant: 'caption', sx: { fontSize: '0.75rem' } }}
                />
              </ListItem>
              <ListItem sx={{ py: 0.5, px: 0 }}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  {passwords.old_password && passwords.new_password && passwords.old_password !== passwords.new_password ? (
                    <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
                  ) : passwords.old_password && passwords.new_password && passwords.old_password === passwords.new_password ? (
                    <Cancel sx={{ fontSize: 16, color: 'error.main' }} />
                  ) : (
                    <Cancel sx={{ fontSize: 16, color: 'disabled' }} />
                  )}
                </ListItemIcon>
                <ListItemText 
                  primary="New password must be different from current password" 
                  primaryTypographyProps={{ variant: 'caption', sx: { fontSize: '0.75rem' } }}
                />
              </ListItem>
            </List>
            <Box sx={{ mt: 1.5, pt: 1.5, borderTop: '1px solid #ddd' }}>
              <Typography variant="caption" sx={{ color: '#666', fontStyle: 'italic', fontSize: '0.7rem' }}>
                <strong>Security Note:</strong> Do not use personal information (email, name, mobile) in your password. 
                Passwords are encrypted and stored securely. Change your password regularly for enhanced security.
              </Typography>
            </Box>
          </Paper>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button 
            onClick={() => {
              setShowPasswordDialog(false);
              setPasswords({ old_password: '', new_password: '', confirm_password: '' });
              setShowPasswords({ old_password: false, new_password: false, confirm_password: false });
              setPasswordDialogMessage('');
            }}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button
            onClick={handlePasswordChange}
            variant="contained"
            disabled={loading || !passwords.old_password || !passwords.new_password || passwords.new_password !== passwords.confirm_password}
            sx={{ minWidth: 140 }}
          >
            {loading ? 'Changing...' : 'Change Password'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default UserProfile;
