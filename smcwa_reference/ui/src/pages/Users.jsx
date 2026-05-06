import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Card,
  CardHeader,
  CardContent,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  IconButton,
  Alert,
  Typography,
  Box,
  Chip,
} from '@mui/material';
import { Add, Edit, Delete as DeleteIcon } from '@mui/icons-material';
import axios from '../utils/axiosConfig';

const Users = () => {
  const [users, setUsers] = useState([]);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('info');
  const [formData, setFormData] = useState({
    email: '',
    mobile: '',
    password: '',
    full_name: '',
    role: 'user',
  });
  
  // Get current user role from localStorage
  const currentUserRole = sessionStorage.getItem('lama_user_role') || 'user';
  const isAdmin = currentUserRole === 'admin';

  const location = useLocation(); // Track navigation changes

  useEffect(() => {
    // Ensure axios baseURL is set correctly
    axios.defaults.baseURL = '/api';
    loadUsers();
  }, [location.pathname]); // Reload when navigating to this page (including browser back/forward)

  const loadUsers = async () => {
    try {
      setLoading(true);
      // Ensure baseURL is correct before making request
      axios.defaults.baseURL = '/api';
      
      
      const response = await axios.get('/v1/users/', {
        headers: {  },
      });
      
      setUsers(response.data || []);
      setMessage('');
    } catch (error) {
      setMessage('Error loading users: ' + (error.response?.data?.detail || error.message));
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleOpenDialog = (user = null) => {
    if (user) {
      setEditingUser(user);
      setFormData({
        email: user.email || '',
        mobile: user.mobile || '',
        password: '',
        full_name: user.full_name || '',
        role: user.role || 'user',
      });
    } else {
      setEditingUser(null);
      setFormData({
        email: '',
        mobile: '',
        password: '',
        full_name: '',
        role: 'user',
      });
    }
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingUser(null);
    setFormData({
      email: '',
      mobile: '',
      password: '',
      full_name: '',
      role: 'user',
    });
  };

  const handleSaveUser = async () => {
    if (!formData.email && !formData.mobile) {
      setMessage('Either email or mobile number is required');
      setMessageType('error');
      return;
    }

    if (editingUser && !formData.password) {
      // For editing, password is optional if not changing
      if (!editingUser.id) {
        setMessage('Password is required');
        setMessageType('error');
        return;
      }
    } else if (!editingUser && !formData.password) {
      setMessage('Password is required for new users');
      setMessageType('error');
      return;
    }

    setLoading(true);
    try {
      

      if (editingUser) {
        // Update existing user
        const updateData = {
          full_name: formData.full_name,
          role: formData.role,
        };
        if (formData.email) updateData.email = formData.email;
        if (formData.mobile) updateData.mobile = formData.mobile;
        if (formData.password) updateData.password = formData.password;
        
        await axios.put(`/v1/users/${editingUser.id}`, updateData, {
          headers: {  },
        });
        
        setMessage('User updated successfully!');
      } else {
        // Create new user
        await axios.post('/v1/users/', {
          email: formData.email || null,
          mobile: formData.mobile || null,
          password: formData.password,
          full_name: formData.full_name,
          role: formData.role,
        }, {
          headers: {  },
        });
        
        setMessage('User created successfully!');
      }

      setMessageType('success');
      handleCloseDialog();
      loadUsers();
    } catch (error) {
      setMessage('Error saving user: ' + (error.response?.data?.detail || error.message));
      setMessageType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteUser = async (userId) => {
    if (userId === 1) {
      setMessage('Cannot delete default admin user');
      setMessageType('error');
      return;
    }

    if (window.confirm('Are you sure you want to delete this user?')) {
      setLoading(true);
      try {
        

        await axios.delete(`/v1/users/${userId}`, {
          headers: {  },
        });

        setMessage('User deleted successfully!');
        setMessageType('success');
        loadUsers();
      } catch (error) {
        setMessage('Error deleting user: ' + (error.response?.data?.detail || error.message));
        setMessageType('error');
      } finally {
        setLoading(false);
      }
    }
  };

  const getRoleColor = (role) => {
    return role === 'admin' ? 'error' : 'default';
  };

  return (
    <Box sx={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
      <Box sx={{ display: 'flex', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 'bold', fontSize: '2rem' }}>User Management</Typography>
        {isAdmin && (
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => handleOpenDialog()}
            size={window.innerWidth < 600 ? 'small' : 'medium'}
          >
            Add User
          </Button>
        )}
        {!isAdmin && (
          <Typography variant="body2" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>
            Read-only access - Admin required for modifications
          </Typography>
        )}
      </Box>

      {message && (
        <Alert severity={messageType} sx={{ mb: 3 }} onClose={() => setMessage('')}>
          {message}
        </Alert>
      )}

      <Card sx={{ boxShadow: 2, ml: 0 }}>
        <CardHeader
          title="All Users"
          subheader={`Total: ${users.length} users`}
          sx={{ 
            '& .MuiCardHeader-title': {
              fontSize: '1.25rem'
            }
          }}
        />
        <CardContent sx={{ p: 0, '&:last-child': { pb: 2 } }}>
          <Box sx={{ overflowX: 'auto', width: '100%', WebkitOverflowScrolling: 'touch' }}>
            <Table sx={{ minWidth: 650 }}>
            <TableHead>
              <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                <TableCell sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>Email</TableCell>
                <TableCell sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>Mobile</TableCell>
                <TableCell sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>Full Name</TableCell>
                <TableCell sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>Role</TableCell>
                <TableCell sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>Created</TableCell>
                {isAdmin && (
                  <TableCell align="center" sx={{ fontWeight: 'bold', fontSize: '0.875rem', padding: '16px' }}>Actions</TableCell>
                )}
              </TableRow>
            </TableHead>
            <TableBody>
              {users.length > 0 ? (
                users.map((user) => (
                  <TableRow key={user.id} sx={{ '&:hover': { backgroundColor: '#fafafa' } }}>
                    <TableCell sx={{ fontSize: '0.875rem', padding: '16px' }}>{user.email || '-'}</TableCell>
                    <TableCell sx={{ fontSize: '0.875rem', padding: '16px' }}>{user.mobile || '-'}</TableCell>
                    <TableCell sx={{ fontSize: '0.875rem', padding: '16px' }}>{user.full_name || '-'}</TableCell>
                    <TableCell sx={{ fontSize: '0.875rem', padding: '16px' }}>
                      <Chip
                        label={user.role}
                        color={getRoleColor(user.role)}
                        size="small"
                        sx={{ fontSize: '0.75rem' }}
                      />
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.875rem', padding: '16px' }}>{user.created_at ? new Date(user.created_at).toLocaleDateString() : '-'}</TableCell>
                    {isAdmin && (
                      <TableCell align="center" sx={{ padding: '16px' }}>
                        <IconButton
                          size="small"
                          onClick={() => handleOpenDialog(user)}
                          color="primary"
                          sx={{ p: 1 }}
                        >
                          <Edit fontSize="small" />
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={() => handleDeleteUser(user.id)}
                          color="error"
                          disabled={user.id === 1}
                          sx={{ p: 1 }}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </TableCell>
                    )}
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={isAdmin ? 6 : 5} sx={{ textAlign: 'center', py: 3, color: '#999' }}>
                    No users found
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
            </Table>
          </Box>
        </CardContent>
      </Card>

      {/* Create/Edit User Dialog */}
      <Dialog open={openDialog} onClose={handleCloseDialog}  fullWidth sx={{ '& .MuiDialog-paper': { m: 2 } }}>
        <DialogTitle>
          {editingUser ? 'Edit User' : 'Create New User'}
        </DialogTitle>
        <DialogContent sx={{ pt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TextField
            fullWidth
            label="Email Address"
            value={formData.email}
            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            type="email"
            helperText={!formData.mobile ? "Either email or mobile is required" : ""}
          />

          <TextField
            fullWidth
            label="Mobile Number"
            value={formData.mobile}
            onChange={(e) => setFormData({ ...formData, mobile: e.target.value })}
            type="tel"
            helperText={!formData.email ? "Either email or mobile is required" : ""}
          />

          <TextField
            fullWidth
            label="Full Name"
            value={formData.full_name}
            onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
          />

          {!editingUser && (
            <TextField
              fullWidth
              label="Password"
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              required
            />
          )}

          {editingUser && (
            <TextField
              fullWidth
              label="New Password (leave blank to keep current)"
              type="password"
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            />
          )}

          <FormControl fullWidth>
            <InputLabel>Role</InputLabel>
            <Select
              value={formData.role}
              label="Role"
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
            >
              <MenuItem value="user">User</MenuItem>
              <MenuItem value="admin">Admin</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button
            onClick={handleSaveUser}
            variant="contained"
            disabled={loading}
          >
            {editingUser ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Users;
