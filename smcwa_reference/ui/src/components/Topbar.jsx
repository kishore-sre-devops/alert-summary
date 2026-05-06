import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Chip from '@mui/material/Chip';
import AccountCircle from '@mui/icons-material/AccountCircle';
import Logout from '@mui/icons-material/Logout';
import Person from '@mui/icons-material/Person';
import { useEnvironment } from '../hooks/useEnvironment';
import axios from '../utils/axiosConfig';

export default function Topbar(){
  const [anchorEl, setAnchorEl] = useState(null);
  const { environment } = useEnvironment();
  const navigate = useNavigate();
  // VAPT FIX: Get display info from sessionStorage
  const userEmail = sessionStorage.getItem('lama_user_email') || sessionStorage.getItem('lama_user_email') || 'User';
  const userRole = sessionStorage.getItem('lama_user_role') || sessionStorage.getItem('lama_user_role') || '';

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleProfile = () => {
    handleMenuClose();
    navigate('/profile');
  };

  const handleLogout = async () => {
    handleMenuClose();
    try {
      // VAPT FIX: Call backend logout to clear httpOnly cookie
      await axios.post('/auth/logout');
    } catch (err) {
      console.error("Logout error:", err);
    }
    
    // Clear all storage
    const keysToRemove = [
      'lama_jwt', 'lama_token', 'lama_user_email', 'lama_user_id', 
      'lama_user_role', 'lama_user_name', 'lama_user_phone', 'lama_user_mobile'
    ];
    
    keysToRemove.forEach(key => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    });
    
    navigate('/login');
  };

  return (
    <AppBar position="static" elevation={1} sx={{ background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)" }}>
      <Toolbar sx={{ px: 3 }}>
        <Typography
          variant="h6"
          sx={{
            flexGrow: 1,
            fontWeight: 600,
            color: 'white',
            fontSize: '1.25rem',
          }}
        >
          SMC-LAMA
        </Typography>
        
        {/* Environment Badge */}
        <Chip
          label={environment.toUpperCase()}
          size="small"
          sx={{
            mr: 2,
            backgroundColor: environment === 'uat' ? '#FF9800' : '#4CAF50',
            color: 'white',
            fontWeight: 'bold',
            height: 28,
            '& .MuiChip-label': {
              px: 1.5,
            },
          }}
        />
        
        <Typography 
          variant="body2" 
          sx={{ 
            mr: 3, 
            opacity: 0.95, 
            color: 'white',
            fontSize: '0.875rem'
          }}
        >
          {userEmail} ({userRole})
        </Typography>
        <IconButton color="inherit" onClick={handleMenuOpen} sx={{ p: 1.5 }}>
          <AccountCircle/>
        </IconButton>
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={handleMenuClose}
        >
          <MenuItem disabled>
            <AccountCircle sx={{ mr: 1 }} /> {userEmail}
          </MenuItem>
          <MenuItem onClick={handleProfile}>
            <Person sx={{ mr: 1 }} /> My Profile
          </MenuItem>
          <MenuItem onClick={handleLogout}>
            <Logout sx={{ mr: 1 }} /> Logout
          </MenuItem>
        </Menu>
      </Toolbar>
    </AppBar>
  );
}
