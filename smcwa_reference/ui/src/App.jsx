import React, { useEffect } from 'react';
import { Routes, Route, Navigate, useLocation, Outlet } from 'react-router-dom';
import Box from '@mui/material/Box';
import axios from './utils/axiosConfig';
import Login from './pages/Login';
import ResetPassword from './pages/ResetPassword';
import Users from './pages/Users';
import Servers from './pages/Servers';
import ExchangeActivity from './pages/ExchangeActivity';
import ExchangeConnectivityErrors from './pages/ExchangeConnectivityErrors';
import SchedulerLogs from './pages/SchedulerLogs';
import ConfigWizard from './pages/ConfigWizard';
import Profile from './pages/Profile';
import ActivityLog from './pages/ActivityLog';
import AlertHistory from './pages/AlertHistory';
import Thresholds from './pages/Thresholds';
import AlertConfig from './pages/AlertConfig';
import DatabaseConfig from './pages/DatabaseConfig';
import ApplicationMetrics from './pages/ApplicationMetrics';
import DatabaseMonitoring from './pages/DatabaseMonitoring';
import ApplicationMonitoring from './pages/ApplicationMonitoring';
import RawMetricsValidation from './pages/RawMetricsValidation';
import LamaMonitor from './pages/LamaMonitor';
import Documentation from './pages/Documentation';
import QueryExplorer from './pages/QueryExplorer';
import ProtectedRoute from './components/ProtectedRoute';
import RoleProtectedRoute from './components/RoleProtectedRoute';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import ErrorBoundary from './components/ErrorBoundary';
import { EnvironmentProvider, useEnvironmentContext } from './contexts/EnvironmentContext';
import ServerDetails from './pages/ServerDetails';
import CircularProgress from '@mui/material/CircularProgress';
import MuiBackdrop from '@mui/material/Backdrop';
import Typography from '@mui/material/Typography';
import MobileDownloads from './pages/MobileDownloads';
import MobileAlerts from './pages/MobileAlerts';
import SchedulerConfig from './pages/SchedulerConfig';

// Set axios base URL - single /api/ endpoint
const setApiBaseURL = () => {
  const apiEndpoint = '/api';
  axios.defaults.baseURL = apiEndpoint;
};

setApiBaseURL();

function Layout({ children }) {
  const drawerWidth = 280;
  
  return (
    <Box sx={{ display: 'flex', height: '100vh', bgcolor: '#ffffff', overflow: 'hidden', margin: 0, padding: 0 }}>
      <Sidebar />
      <Box 
        sx={{ 
          flex: 1, 
          display: 'flex', 
          flexDirection: 'column',
          width: `calc(100% - ${drawerWidth}px)`,
          marginLeft: `${drawerWidth}px`,
          overflow: 'hidden',
          bgcolor: '#f5f5f5',
          position: 'relative',
        }}
      >
        <Topbar />
        <Box 
          sx={{ 
            flex: 1, 
            overflow: 'auto', 
            width: '100%',
            bgcolor: '#f5f5f5',
            '&::-webkit-scrollbar': { width: '10px', height: '10px' },
            '&::-webkit-scrollbar-track': { background: '#f1f1f1' },
            '&::-webkit-scrollbar-thumb': { background: '#888', borderRadius: '5px' },
            '&::-webkit-scrollbar-thumb:hover': { background: '#555' },
          }}
        >
          <Box sx={{ width: '100%', boxSizing: 'border-box', position: 'relative', maxWidth: '100%' }}>
            {children}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

// Layout for general protected routes
const MainLayout = () => (
  <ProtectedRoute>
    <Layout>
      <Outlet />
    </Layout>
  </ProtectedRoute>
);

// Layout for admin-only routes
const AdminLayout = () => (
  <RoleProtectedRoute allowedRoles={['admin']}>
    {/* Outlet will be rendered inside the MainLayout's protection and layout */}
    <Outlet />
  </RoleProtectedRoute>
);

// Add a small wrapper to use the environment context
const AppContent = () => {
  const { loading } = useEnvironmentContext();
  
  return (
    <>
      <MuiBackdrop
        sx={{ color: '#fff', zIndex: (theme) => theme.zIndex.drawer + 1300, backgroundColor: 'rgba(0, 0, 0, 0.3)' }}
        open={loading}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
          <CircularProgress color="inherit" />
          <Typography variant="h6" sx={{ color: 'white', fontWeight: 'bold' }}>
            Switching Environment...
          </Typography>
        </Box>
      </MuiBackdrop>
      
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/" element={<Navigate to="/servers" replace />} />
        
        {/* General Protected Routes */}
        <Route element={<MainLayout />}>
          <Route path="/lama-monitor" element={<LamaMonitor />} />
          <Route path="/users" element={<Users />} />
          <Route path="/servers" element={<Servers />} />
          <Route path="/servers/:serverId" element={<ServerDetails />} />
          <Route path="/exchange-activity" element={<ExchangeActivity />} />
          <Route path="/raw-data-validation" element={<RawMetricsValidation />} />
          <Route path="/activity-log" element={<ActivityLog />} />
          <Route path="/exchange-connectivity-errors" element={<ExchangeConnectivityErrors />} />
          <Route path="/scheduler-logs" element={<SchedulerLogs />} />
          <Route path="/alert-history" element={<AlertHistory />} />
          <Route path="/mobile-alerts" element={<MobileAlerts />} />
          <Route path="/database-monitoring" element={<DatabaseMonitoring />} />
          <Route path="/application-monitoring" element={<ApplicationMonitoring />} />
          <Route path="/query-explorer" element={<QueryExplorer />} />
          <Route path="/documentation" element={<Documentation />} />
          <Route path="/downloads" element={<MobileDownloads />} />
          <Route path="/profile" element={<Profile />} />

          {/* Admin-only Routes */}
          <Route element={<AdminLayout />}>
            <Route path="/config" element={<ConfigWizard />} />
            <Route path="/database-config" element={<DatabaseConfig />} />
            <Route path="/application-metrics" element={<ApplicationMetrics />} />
            <Route path="/thresholds" element={<Thresholds />} />
            <Route path="/alert-config" element={<AlertConfig />} />
            <Route path="/scheduler-config" element={<SchedulerConfig />} />
          </Route>
        </Route>
        
        <Route path="*" element={<div style={{padding:20}}>Page Not Found</div>} />
      </Routes>
    </>
  );
};


export default function App(){
  useEffect(() => {
    // Listen for storage changes (when environment is changed in another tab/window)
    const handleStorageChange = (e) => {
      if (e.key === 'lama_environment' || e.key === 'api_endpoint') {
        setApiBaseURL();
      }
    };
    window.addEventListener('storage', handleStorageChange);
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  return (
    <ErrorBoundary>
      <EnvironmentProvider>
        <AppContent />
      </EnvironmentProvider>
    </ErrorBoundary>
  );
}
