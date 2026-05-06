import smcLogo from "../assets/logo-smc.png";
import React, { useState, useEffect } from 'react';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import ListItemIcon from '@mui/material/ListItemIcon';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import Typography from '@mui/material/Typography';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import Chip from '@mui/material/Chip';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Link, useLocation } from 'react-router-dom';
import VisibilityIcon from '@mui/icons-material/Visibility';
import SearchIcon from '@mui/icons-material/Search';
import Storage from '@mui/icons-material/Storage';
import People from '@mui/icons-material/People';
import GetApp from '@mui/icons-material/GetApp';
import History from '@mui/icons-material/History';
import Settings from '@mui/icons-material/Settings';
import Assessment from '@mui/icons-material/Assessment';
import DatabaseIcon from '@mui/icons-material/Dns';
import Notifications from '@mui/icons-material/Notifications';
import PhoneIphone from '@mui/icons-material/PhoneIphone';
import AdminPanelSettings from '@mui/icons-material/AdminPanelSettings';
import MenuBook from '@mui/icons-material/MenuBook';
import SyncIcon from '@mui/icons-material/Sync';
import SyncDisabledIcon from '@mui/icons-material/SyncDisabled';
import Tooltip from '@mui/material/Tooltip';
import axios from 'axios';
import { useEnvironment } from '../hooks/useEnvironment';

/**
 * Component to show real-time scheduler status for selected environment
 */
const SchedulerStatusIndicator = ({ environment }) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        setLoading(true);
        const response = await axios.get(`/v1/schedulers/status/environment`);
        setStatus(response.data);
      } catch (error) {
        console.error('Error fetching scheduler status:', error);
        setStatus(null);
      } finally {
        setLoading(false);
      }
    };

    fetchStatus();
    // Refresh every minute
    const interval = setInterval(fetchStatus, 60000);
    return () => clearInterval(interval);
  }, [environment]);

  if (loading && !status) return <Box sx={{ mt: 1, height: 20 }} />;

  const isActive = status?.is_active;
  const lastRun = status?.last_run ? new Date(status.last_run).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Never';

  return (
    <Box sx={{ mt: 1.5, px: 0.5 }}>
      <Tooltip title={isActive ? `Scheduler is active for ${environment.toUpperCase()}` : `Scheduler is inactive for ${environment.toUpperCase()}`}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box 
            sx={{ 
              width: 8, 
              height: 8, 
              borderRadius: '50%', 
              bgcolor: isActive ? '#4CAF50' : '#9e9e9e',
              boxShadow: isActive ? '0 0 4px #4CAF50' : 'none'
            }} 
          />
          <Typography variant="caption" sx={{ color: '#666', fontWeight: 500, fontSize: '0.7rem' }}>
            {isActive ? 'Scheduler Active' : 'Scheduler Inactive'}
          </Typography>
        </Box>
      </Tooltip>
      {isActive && (
        <Typography variant="caption" sx={{ display: 'block', color: '#888', fontSize: '0.65rem', ml: 2 }}>
          Last push: {lastRun}
        </Typography>
      )}
      {!isActive && (
        <Typography variant="caption" sx={{ display: 'block', color: '#d32f2f', fontSize: '0.65rem', ml: 2 }}>
          Configure {environment.toUpperCase()} to activate
        </Typography>
      )}
    </Box>
  );
};

export default function Sidebar(){
  const location = useLocation();
  const { environment, changeEnvironment } = useEnvironment();
  
  // Get current user role - use state to make it reactive
  const [userRole, setUserRole] = useState(() => sessionStorage.getItem('lama_user_role') || 'user');
  const isUser = userRole === 'user';
  
  // Update role when localStorage changes (e.g., after login)
  useEffect(() => {
    const checkRole = () => {
      const currentRole = sessionStorage.getItem('lama_user_role') || 'user';
      if (currentRole !== userRole) {
        setUserRole(currentRole);
      }
    };
    
    // Check on mount and when pathname changes (navigation)
    checkRole();
    
    // Listen for storage events (when role changes in another tab/window)
    window.addEventListener('storage', checkRole);
    
    // Also check periodically (in case localStorage was updated directly)
    const interval = setInterval(checkRole, 1000);
    
    return () => {
      window.removeEventListener('storage', checkRole);
      clearInterval(interval);
    };
  }, [location.pathname, userRole]);
  
  
  // Accordion expanded state (persisted in localStorage)
  const [expandedSections, setExpandedSections] = useState(() => {
    const saved = localStorage.getItem('sidebar_expanded_sections');
    return saved ? JSON.parse(saved) : {
      monitoring: true,
      configuration: true,
      alerts: false,
      administration: false,
      logs: false,
    };
  });

  useEffect(() => {
    // Set single API endpoint (environment is passed as query parameter)
    localStorage.setItem('api_endpoint', '/api');
    axios.defaults.baseURL = '/api';
  }, []);

  const handleEnvironmentChange = (event) => {
    const newEnv = event.target.value;
    changeEnvironment(newEnv);
    // Set API endpoint (no need to change baseURL, but keep consistent)
    localStorage.setItem('api_endpoint', '/api');
    axios.defaults.baseURL = '/api';
  };

  const isActive = (path) => location.pathname === path;

  const handleAccordionChange = (section) => (event, isExpanded) => {
    const newExpanded = { ...expandedSections, [section]: isExpanded };
    setExpandedSections(newExpanded);
    localStorage.setItem('sidebar_expanded_sections', JSON.stringify(newExpanded));
  };

  // Organized menu structure with sections
  const menuSections = [
    {
      id: 'monitoring',
      title: '📊 MONITORING',
      icon: <VisibilityIcon />,
      items: [
        { path: '/lama-monitor', label: 'LAMA Monitor', icon: <Assessment /> },
        { path: '/query-explorer', label: 'Query Explorer', icon: <SearchIcon /> },
        { path: '/servers', label: 'Servers', icon: <Storage /> },
        { path: '/exchange-activity', label: 'Exchange Activity', icon: <Assessment /> },
        { path: '/raw-data-validation', label: 'Raw Data Validation', icon: <SyncIcon /> },
        { path: '/database-monitoring', label: 'Database Monitoring', icon: <DatabaseIcon /> },
        { path: '/application-monitoring', label: 'Application Monitoring', icon: <DatabaseIcon /> },
      ]
    },
    {
      id: 'configuration',
      title: '⚙️ CONFIGURATION',
      icon: <Settings />,
      // Hide configuration section for user role
      items: isUser ? [] : [
        { path: '/config', label: 'LAMA Exchange Config', icon: <Settings /> },
        { path: '/database-config', label: 'Database Config', icon: <DatabaseIcon /> },
        { path: '/application-metrics', label: 'Application Metrics Config', icon: <DatabaseIcon /> },
        { path: '/alert-config', label: 'Alert Configuration', icon: <Settings /> },
        { path: '/scheduler-config', label: 'Scheduler Settings', icon: <Settings /> },
      ]
    },
    {
      id: 'alerts',
      title: '🔔 ALERTS',
      icon: <Notifications />,
      // Hide Alert Thresholds for user role, but keep Alert History visible
      items: [
        ...(isUser ? [] : [{ path: '/thresholds', label: 'Alert Thresholds', icon: <Assessment /> }]),
        { path: '/mobile-alerts', label: 'Mobile Alerts', icon: <PhoneIphone /> },
        { path: '/alert-history', label: 'Alert History', icon: <History /> },
      ]
    },
    {
      id: 'administration',
      title: '👥 ADMINISTRATION',
      icon: <AdminPanelSettings />,
      items: [
        { path: '/users', label: 'Users', icon: <People /> },
        { path: '/downloads', label: 'Mobile App', icon: <GetApp /> },
      ]
    },
    {
      id: 'logs',
      title: '📋 LOGS',
      icon: <MenuBook />,
      items: [
        { path: '/activity-log', label: 'Activity Log', icon: <History /> },
        { path: '/exchange-connectivity-errors', label: 'Exchange Connectivity Errors', icon: <Notifications /> },
        { path: '/scheduler-logs', label: 'Scheduler Logs', icon: <MenuBook /> },
      ]
    },
    {
      id: 'documentation',
      title: '📚 DOCUMENTATION',
      icon: <MenuBook />,
      items: [
        { path: '/documentation', label: 'System Flow Diagrams', icon: <MenuBook /> },
      ]
    },
  ];

  const drawerWidth = 280;
  
  const drawer = (
    <Box sx={{ width: drawerWidth, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ p: 2, bgcolor: '#ffffff', borderBottom: '1px solid #e0e0e0' }}>
        <img 
          src={smcLogo} 
          alt="SMC" 
          style={{ 
            width: 180, 
            height: 'auto',
            display: 'block', 
            objectFit: 'contain',
            maxWidth: '100%',
            backgroundColor: 'transparent'
          }} 
        />
        <Typography variant="h6" display="block" sx={{ mt: 1.5, color: '#333', fontSize: '1.1rem', fontWeight: '600' }}>
          LAMA Management
        </Typography>
      </Box>

      {/* Environment Selector */}
      <Box sx={{ p: 2, borderBottom: '1px solid #e0e0e0', bgcolor: '#f5f5f5' }}>
        <Typography variant="caption" sx={{ display: 'block', mb: 1, fontWeight: 'bold', color: '#666', fontSize: '0.75rem' }}>
          Environment
        </Typography>
        <FormControl fullWidth size="small">
          <Select
            value={environment}
            onChange={handleEnvironmentChange}
            sx={{
              bgcolor: 'white',
              '& .MuiOutlinedInput-notchedOutline': {
                borderColor: environment === 'uat' ? '#FF9800' : '#4CAF50',
              },
              '&:hover .MuiOutlinedInput-notchedOutline': {
                borderColor: environment === 'uat' ? '#FF9800' : '#4CAF50',
              },
              '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                borderColor: environment === 'uat' ? '#FF9800' : '#4CAF50',
              },
            }}
          >
            <MenuItem value="prod">
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip label="PROD" size="small" sx={{ backgroundColor: '#4CAF50', color: 'white', fontWeight: 'bold', height: 20 }} />
                <Typography variant="body2">Production</Typography>
              </Box>
            </MenuItem>
            <MenuItem value="uat">
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip label="UAT" size="small" sx={{ backgroundColor: '#FF9800', color: 'white', fontWeight: 'bold', height: 20 }} />
                <Typography variant="body2">User Acceptance Testing</Typography>
              </Box>
            </MenuItem>
          </Select>
        </FormControl>
        
        {/* Scheduler Status Indicator (RULE 6 UI) */}
        <SchedulerStatusIndicator environment={environment} />
      </Box>
      
      <Box sx={{ flex: 1, overflowY: 'auto', pt: 1 }}>
        {menuSections
          .filter(section => section.items.length > 0) // Hide sections with no items (for user role)
          .map((section) => (
          <Accordion
            key={section.id}
            expanded={expandedSections[section.id]}
            onChange={handleAccordionChange(section.id)}
            sx={{
              boxShadow: 'none',
              border: 'none',
              '&:before': { display: 'none' },
              '&.Mui-expanded': { margin: 0 },
              mx: 0.5,
              mb: 0.5,
            }}
          >
            <AccordionSummary
              expandIcon={<ExpandMoreIcon sx={{ fontSize: '1.2rem', color: '#666' }} />}
              sx={{
                minHeight: 40,
                '&.Mui-expanded': { minHeight: 40 },
                '& .MuiAccordionSummary-content': {
                  margin: '8px 0',
                  '&.Mui-expanded': { margin: '8px 0' },
                },
                px: 1.5,
                py: 0.5,
              }}
            >
              <Typography
                variant="body2"
                sx={{
                  fontWeight: 600,
                  fontSize: '0.8rem',
                  color: '#666',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                {section.title}
              </Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ pt: 0, px: 0, pb: 0.5 }}>
              <List sx={{ py: 0 }}>
                {section.items.map((item) => (
                  <ListItem
                    button
                    component={item.external ? 'a' : Link}
                    to={!item.external ? item.path : undefined}
                    href={item.external ? item.path : undefined}
                    download={item.external}
                    key={item.path}
                    sx={{
                      mx: 0.5,
                      mb: 0.5,
                      borderRadius: 1,
                      bgcolor: isActive(item.path) ? '#e3f2fd' : 'transparent',
                      color: isActive(item.path) ? '#1976d2' : '#666',
                      '&:hover': { bgcolor: isActive(item.path) ? '#e3f2fd' : '#f5f5f5' },
                      py: 1.25,
                      pl: 2.5,
                    }}
                  >
                    <ListItemIcon sx={{ color: isActive(item.path) ? '#1976d2' : '#666', minWidth: 36 }}>
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText 
                      primary={item.label}
                      primaryTypographyProps={{ 
                        fontWeight: isActive(item.path) ? 600 : 400,
                        fontSize: '0.9rem',
                      }}
                    />
                  </ListItem>
                ))}
              </List>
            </AccordionDetails>
          </Accordion>
        ))}
      </Box>

      <Divider />
      <Box sx={{ p: 2, bgcolor: '#ffffff', textAlign: 'center', fontSize: '0.75rem', color: 'textSecondary' }}>
        <Typography variant="caption" sx={{ fontSize: '0.7rem' }}>SMC-LAMA v1.3.0 (API v1.3 Compliant)</Typography>
      </Box>
    </Box>
  );
  
  return (
    <Drawer 
      variant="permanent" 
      anchor="left" 
      sx={{ 
        width: drawerWidth,
        flexShrink: 0,
        '& .MuiDrawer-paper': { 
          width: `${drawerWidth}px`,
          boxSizing: 'border-box', 
          bgcolor: '#ffffff',
          position: 'fixed',
          height: '100vh',
          top: 0,
          left: 0,
          borderRight: '1px solid #e0e0e0',
          boxShadow: '2px 0 4px rgba(0,0,0,0.05)',
          zIndex: 1200,
        } 
      }}
    >
      {drawer}
    </Drawer>
  );
}
