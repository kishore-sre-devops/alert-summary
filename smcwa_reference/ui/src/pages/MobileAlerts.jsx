import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Typography,
  Tabs,
  Tab,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Chip,
  Tooltip,
  Alert,
  CircularProgress,
  Grid,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  ListItemSecondaryAction,
} from '@mui/material';
import {
  Delete as DeleteIcon,
  Edit as EditIcon,
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  GetApp as DownloadIcon,
  PhoneIphone as MobileIcon,
  Group as GroupIcon,
  People as PeopleIcon,
  History as HistoryIcon,
  NotificationsActive as AlertsIcon,
  Settings as SettingsIcon,
  Send as SendIcon,
  Add as AddIcon,
  Close as CloseIcon,
  AssignmentInd as AssignmentIndIcon,
  AccessTime as AccessTimeIcon,
  Comment as CommentIcon,
} from '@mui/icons-material';
import axios from '../utils/axiosConfig';

// Helper to format date (Backend now provides pre-formatted IST strings)
const formatDate = (dateStr) => {
  if (!dateStr) return 'N/A';
  
  // FIXED: If the string already contains a comma and a slash, it's our pre-formatted IST string.
  if (dateStr.toString().includes(',') && dateStr.toString().includes('/')) {
    return dateStr;
  }
  
  try {
    const dateObj = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + 'Z');
    return dateObj.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true
    });
  } catch (e) {
    return dateStr;
  }
};

const formatCommitment = (mins) => {
  if (!mins) return '';
  const m = parseInt(mins);
  if (m === 2880) return '2d';
  if (m === 1440) return '24h';
  if (m === 720) return '12h';
  if (m === 360) return '6h';
  if (m === 180) return '3h';
  if (m === 120) return '2h';
  if (m === 60) return '1h';
  if (m >= 60) return `${Math.floor(m/60)}h ${m%60}m`;
  return `${m}m`;
};

// Tab Panel Component
function TabPanel(props) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`mobile-alerts-tabpanel-${index}`}
      aria-labelledby={`mobile-alerts-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const MobileAlerts = () => {
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  
  // Data States
  const [groups, setGroups] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [activeAlerts, setActiveAlerts] = useState([]);
  const [history, setHistory] = useState([]);
  const [mobileLogs, setMobileLogs] = useState([]);
  const [settings, setSettings] = useState({
    enabled: true,
    default_timeout: 30,
    retry_count: 3,
  });

  // --- CALL FLOW STATE ---
  const [callFlowOpen, setCallFlowOpen] = useState(false);
  const [callFlowData, setCallFlowData] = useState([]);
  const [callFlowLoading, setCallFlowLoading] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState(null);

  // Role check
  const userRole = sessionStorage.getItem('lama_user_role') || 'user';
  const isAdminOrManager = userRole === 'admin' || userRole === 'manager';
  const isReadOnly = !isAdminOrManager;

  // Dialog States
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [currentGroup, setCurrentGroup] = useState(null);

  const fetchGroups = useCallback(async () => {
    try {
      const response = await axios.get('/v1/mobile/groups');
      setGroups(response.data || []);
    } catch (err) {
      console.error('Failed to fetch groups', err);
    }
  }, []);

  const fetchContacts = useCallback(async () => {
    try {
      const response = await axios.get('/v1/mobile/contacts');
      setContacts(response.data || []);
    } catch (err) {
      console.error('Failed to fetch contacts', err);
    }
  }, []);

  const fetchActiveAlerts = useCallback(async () => {
    try {
      const response = await axios.get('/v1/mobile/active-alerts');
      setActiveAlerts(response.data || []);
    } catch (err) {
      console.error('Failed to fetch active alerts', err);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const response = await axios.get('/v1/mobile/alerts?filter=resolved&limit=100');
      setHistory(response.data || []);
    } catch (err) {
      console.error('Failed to fetch history', err);
    }
  }, []);

  const fetchMobileLogs = useCallback(async () => {
    try {
      const response = await axios.get('/v1/logs');
      const allLogs = response.data.logs || response.data || [];
      // Filter for strictly mobile-relevant actions
      const filtered = allLogs.filter(log => 
        log.action === 'Mobile Device Registered' || 
        log.action === 'Mobile APK Logout' ||
        log.action === 'Mobile Google Login' ||
        log.action === 'Acknowledge Alert (Mobile)' ||
        log.action === 'Mobile Lama Credential Authentication' ||
        log.action === 'Mobile Lama Credential Authentication Failed'
      );
      setMobileLogs(filtered);
    } catch (err) {
      console.error('Failed to fetch mobile logs', err);
    }
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const response = await axios.get('/v1/mobile/settings');
      if (response.data) setSettings(response.data);
    } catch (err) {
      console.error('Failed to fetch settings', err);
    }
  }, []);

  useEffect(() => {
    fetchContacts();
    fetchGroups();
    loadTabData(tabValue);
    
    let interval;
    if (tabValue === 2) {
      interval = setInterval(fetchActiveAlerts, 10000);
    }
    return () => clearInterval(interval);
  }, [tabValue, fetchActiveAlerts]);

  const loadTabData = (index) => {
    setLoading(true);
    setError(null);
    let promise;
    switch (index) {
      case 0: promise = fetchGroups(); break;
      case 1: promise = fetchContacts(); break;
      case 2: promise = fetchActiveAlerts(); break;
      case 3: promise = fetchHistory(); break;
      case 4: promise = fetchMobileLogs(); break;
      case 5: promise = fetchSettings(); break;
      default: promise = Promise.resolve();
    }
    promise.finally(() => setLoading(false));
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  // Group Handlers
  const handleOpenGroupDialog = (group = null) => {
    fetchContacts();
    setCurrentGroup(group || {
      name: '',
      escalation_chain: [],
      escalation_timeout: 60,
      severity_mapping: { critical: '', warning: '', info: '' }
    });
    setGroupDialogOpen(true);
  };

  const handleSaveGroup = async () => {
    try {
      if (currentGroup.id) {
        await axios.put(`/v1/mobile/groups/${currentGroup.id}`, currentGroup);
      } else {
        await axios.post('/v1/mobile/groups', currentGroup);
      }
      setSuccess('Group saved successfully');
      setGroupDialogOpen(false);
      fetchGroups();
    } catch (err) {
      setError('Failed to save group');
    }
  };

  const handleDeleteGroup = async (id) => {
    if (!window.confirm('Are you sure you want to delete this group?')) return;
    try {
      await axios.delete(`/v1/mobile/groups/${id}`);
      setSuccess('Group deleted');
      fetchGroups();
    } catch (err) {
      setError('Failed to delete group');
    }
  };

  // Alert Handlers
  const handleAcknowledge = async (alertId) => {
    try {
      await axios.post(`/v1/mobile/alerts/${alertId}/ack`);
      setSuccess('Alert acknowledged');
      fetchActiveAlerts();
    } catch (err) {
      setError('Failed to acknowledge alert');
    }
  };

  const handleExportActive = () => {
    window.open('/v1/alerts/export?is_resolved=false', '_blank');
  };

  const handleExportHistory = () => {
    window.open('/v1/alerts/export?is_resolved=true', '_blank');
  };

  const openCallFlow = async (alert) => {
    setSelectedAlert(alert);
    setCallFlowOpen(true);
    setCallFlowLoading(true);
    try {
        const res = await axios.get(`/v1/mobile/alerts/${alert.id}/call-flow`);
        setCallFlowData(res.data || []);
    } catch (e) { console.error(e); } finally { setCallFlowLoading(false); }
  };

  // Settings Handlers
  const handleSaveSettings = async () => {
    try {
      await axios.post('/v1/mobile/settings', settings);
      setSuccess('Settings updated');
    } catch (err) {
      setError('Failed to update settings');
    }
  };

  const handleTestPush = async () => {
    try {
      await axios.post('/v1/mobile/test-push');
      setSuccess('Test push sent to your registered device');
    } catch (err) {
      setError('Failed to send test push. Is your device registered?');
    }
  };

  const handleTestPushForUser = async (userId, name) => {
    if (!window.confirm(`Trigger a test voice alert call to ${name}'s mobile device?`)) return;
    try {
      setLoading(true);
      await axios.post(`/v1/mobile/test-push/${userId}`);
      setSuccess(`Test call initiated for ${name}`);
    } catch (err) {
      setError(err.response?.data?.detail || `Failed to trigger test for ${name}. Is their device registered?`);
    } finally {
      setLoading(false);
    }
  };

  const getSeverityIcon = (severity) => {
    const s = (severity || '').toLowerCase();
    switch (s) {
      case 'critical': 
      case 'error':
        return <ErrorIcon sx={{ color: 'error.main' }} />;
      case 'warning': return <WarningIcon sx={{ color: 'warning.main' }} />;
      default: return <InfoIcon sx={{ color: 'info.main' }} />;
    }
  };

  const getStatusChip = (status) => {
    let color = 'default';
    if (status === 'acknowledged' || status === 'resolved') color = 'success';
    if (status === 'pending' || status === 'sent') color = 'info';
    if (status === 'failed') color = 'error';
    if (status === 'escalated') color = 'warning';
    
    return <Chip label={status?.toUpperCase()} size="small" color={color} variant="outlined" />;
  };

  return (
    <Box sx={{ p: 0 }}>
      <Paper sx={{ mb: 3, borderRadius: 0 }}>
        <Box sx={{ p: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 'bold', color: '#1a237e', display: 'flex', alignItems: 'center' }}>
              <MobileIcon sx={{ mr: 2, fontSize: 40 }} /> Mobile Alerting System
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Manage mobile notifications, escalation policies, and contact groups. (All times in IST)
            </Typography>
          </Box>
          <Box>
            <Button 
              variant="outlined" 
              startIcon={<RefreshIcon />} 
              onClick={() => loadTabData(tabValue)}
              disabled={loading}
              sx={{ mr: 1 }}
            >
              Refresh
            </Button>
            {tabValue === 0 && isAdminOrManager && (
              <Button 
                variant="contained" 
                startIcon={<AddIcon />} 
                onClick={() => handleOpenGroupDialog()}
              >
                Create Group
              </Button>
            )}
          </Box>
        </Box>

        {error && <Alert severity="error" sx={{ mx: 3, mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mx: 3, mb: 2 }} onClose={() => setSuccess(null)}>{success}</Alert>}

        <Tabs 
          value={tabValue} 
          onChange={handleTabChange} 
          sx={{ borderBottom: 1, borderColor: 'divider', px: 3 }}
          indicatorColor="primary"
          textColor="primary"
        >
          <Tab icon={<GroupIcon />} label="CONTACT GROUPS" iconPosition="start" />
          <Tab icon={<PeopleIcon />} label="CONTACTS" iconPosition="start" />
          <Tab icon={<AlertsIcon />} label="ACTIVE ALERTS" iconPosition="start" />
          <Tab icon={<HistoryIcon />} label="CALL HISTORY" iconPosition="start" />
          <Tab icon={<HistoryIcon />} label="MOBILE LOGS" iconPosition="start" />
          <Tab icon={<SettingsIcon />} label="SETTINGS" iconPosition="start" />
        </Tabs>
      </Paper>

      <Box sx={{ px: 3, pb: 5 }}>
        {loading && <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}><CircularProgress /></Box>}
        
        {/* Tab 1: CONTACT GROUPS */}
        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={3}>
            {groups.map((group) => (
              <Grid item xs={12} md={6} lg={4} key={group.id}>
                <Card variant="outlined" sx={{ height: '100%', borderColor: '#e0e0e0' }}>
                  <CardHeader
                    title={group.name}
                    action={isAdminOrManager && (
                      <Box>
                        <IconButton size="small" onClick={() => handleOpenGroupDialog(group)}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                        <IconButton size="small" onClick={() => handleDeleteGroup(group.id)}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Box>
                    )}
                    sx={{ bgcolor: '#f8f9fa' }}
                  />
                  <CardContent>
                    <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 'bold' }}>Notification Chain:</Typography>
                    <List dense>
                      {group.escalation_chain?.map((step, idx) => (
                        <ListItem key={idx} sx={{ px: 0 }}>
                          <ListItemIcon sx={{ minWidth: 35 }}>
                            <AlertsIcon color={idx === 0 ? "error" : "warning"} fontSize="small" />
                          </ListItemIcon>
                          <ListItemText 
                            primary={idx === 0 ? "Immediate" : `Escalated after ${step.delay}m`}
                            secondary={
                              step.notify?.map(userId => {
                                const contact = contacts.find(c => c.id === userId);
                                return contact?.full_name || userId;
                              }).join(', ') || 'No users assigned'
                            }
                          />
                        </ListItem>
                      ))}
                    </List>
                    
                    {group.escalation_chain?.length === 0 && (
                      <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                        No steps configured.
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            ))}
            {groups.length === 0 && !loading && (
              <Grid item xs={12}>
                <Paper sx={{ p: 5, textAlign: 'center', bgcolor: '#fafafa' }}>
                  <GroupIcon sx={{ fontSize: 60, color: '#ccc', mb: 2 }} />
                  <Typography variant="h6">No Contact Groups Defined</Typography>
                  <Typography variant="body2" color="text.secondary">Create a group to start routing mobile alerts.</Typography>
                </Paper>
              </Grid>
            )}
          </Grid>
        </TabPanel>

        {/* Tab 2: CONTACTS */}
        <TabPanel value={tabValue} index={1}>
          <TableContainer component={Paper} variant="outlined">
            <Table>
              <TableHead sx={{ bgcolor: '#f8f9fa' }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold' }}>Name</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Role</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Device Registered</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Push Enabled</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Mobile App Status</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Group Memberships</TableCell>
                  {isAdminOrManager && <TableCell sx={{ fontWeight: 'bold' }}>Actions</TableCell>}
                </TableRow>
              </TableHead>
              <TableBody>
                {contacts.map((contact) => (
                  <TableRow key={contact.id}>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{contact.full_name}</Typography>
                      <Typography variant="caption" color="text.secondary">{contact.email}</Typography>
                    </TableCell>
                    <TableCell><Chip label={contact.role} size="small" variant="outlined" /></TableCell>
                    <TableCell>
                      {contact.device_id ? (
                        <Box sx={{ display: 'flex', alignItems: 'center', color: 'success.main' }}>
                          <CheckCircleIcon sx={{ fontSize: 16, mr: 0.5 }} />
                          <Typography variant="body2">Registered ({contact.device_os})</Typography>
                        </Box>
                      ) : (
                        <Box sx={{ display: 'flex', alignItems: 'center', color: 'text.disabled' }}>
                          <ErrorIcon sx={{ fontSize: 16, mr: 0.5 }} />
                          <Typography variant="body2">Not Registered</Typography>
                        </Box>
                      )}
                    </TableCell>
                    <TableCell>
                      <Switch 
                        checked={contact.push_enabled !== false} 
                        size="small" 
                        disabled={isReadOnly}
                      />
                    </TableCell>
                    <TableCell>
                      {!contact.device_id ? (
                        <Typography variant="body2" color="text.disabled" sx={{ fontWeight: 'bold' }}>NOT REGISTERED</Typography>
                      ) : (contact.is_online === true) ? (
                        <Box sx={{ display: 'flex', alignItems: 'center', color: 'success.main' }}>
                          <CheckCircleIcon sx={{ fontSize: 18, mr: 0.5 }} />
                          <Typography variant="body2" sx={{ fontWeight: 900, letterSpacing: 0.5 }}>ONLINE</Typography>
                        </Box>
                      ) : (
                        <Box>
                          <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 'bold' }}>{contact.is_logged_in ? "INACTIVE" : "LOGGED OUT"}</Typography>
                          <Typography variant="caption" color="text.disabled" sx={{ fontSize: '0.7rem', display: 'block' }}>
                            {formatDate(contact.last_active_at)}
                          </Typography>
                        </Box>
                      )}
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {contact.groups && contact.groups.length > 0 ? (
                          contact.groups.map((g, idx) => (
                            <Chip key={idx} label={g} size="small" color="primary" variant="filled" sx={{ fontWeight: 'bold', height: 20, fontSize: '0.65rem' }} />
                          ))
                        ) : contact.group_name ? (
                          <Chip label={contact.group_name} size="small" color="primary" variant="filled" sx={{ fontWeight: 'bold', height: 20, fontSize: '0.65rem' }} />
                        ) : (
                          <Typography variant="caption" color="text.disabled">None</Typography>
                        )}
                      </Box>
                    </TableCell>
                    {isAdminOrManager && (
                      <TableCell>
                        <Tooltip title="Trigger Test Voice Alert">
                          <span>
                            <IconButton 
                              size="small" 
                              color="primary" 
                              disabled={!contact.device_id || loading}
                              onClick={() => handleTestPushForUser(contact.id, contact.full_name)}
                            >
                              <SendIcon fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </TabPanel>

        {/* Tab 3: ACTIVE ALERTS */}
        <TabPanel value={tabValue} index={2}>
          <Box sx={{ mb: 2, display: 'flex', justifyContent: 'flex-end' }}>
             <Button variant="outlined" startIcon={<DownloadIcon />} onClick={handleExportActive}>Export to Excel</Button>
          </Box>
          <TableContainer component={Paper} variant="outlined">
            <Table>
              <TableHead sx={{ bgcolor: '#f8f9fa' }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold' }}>Alert</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Location / Server</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Severity</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Sent To</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Status</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Sent At</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Ack By / ERT</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Justification</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {activeAlerts.map((alert) => (
                  <TableRow key={alert.id}>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{alert.title}</Typography>
                      <Typography variant="caption" color="text.secondary" display="block">{alert.body}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{alert.server_name}</Typography>
                      {alert.server_ip && <Typography variant="caption" color="text.secondary">{alert.server_ip}</Typography>}
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        {getSeverityIcon(alert.severity)}
                        <Typography variant="body2" sx={{ ml: 1, fontWeight: 'bold' }}>
                          {(alert.severity?.toLowerCase() === 'error' ? 'CRITICAL' : alert.severity)?.toUpperCase()}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>{alert.group_name || 'N/A'}</TableCell>
                    <TableCell>{getStatusChip(alert.status)}</TableCell>
                    <TableCell>{formatDate(alert.created_at)}</TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{alert.acknowledged_by_name || '-'}</Typography>
                      {alert.ert_at && (
                        <Chip 
                          label={`ERT: ${formatDate(alert.ert_at)}`} 
                          size="small" 
                          color="primary" 
                          variant="outlined" 
                          sx={{ mt: 0.5, fontSize: '0.7rem' }} 
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      {alert.ert_justification ? (
                        <Tooltip title={alert.ert_justification}>
                          <Typography variant="caption" sx={{ fontStyle: 'italic', color: 'text.secondary' }}>
                            {alert.ert_justification.length > 30 ? alert.ert_justification.substring(0, 30) + '...' : alert.ert_justification}
                          </Typography>
                        </Tooltip>
                      ) : '-'}
                    </TableCell>
                    <TableCell>
                      {isAdminOrManager && !alert.acknowledged_at && (
                        <Button 
                          variant="outlined" 
                          size="small" 
                          onClick={() => handleAcknowledge(alert.id)}
                          sx={{ mr: 1 }}
                        >
                          Acknowledge
                        </Button>
                      )}
                      <Tooltip title="View Call Flow">
                        <IconButton size="small" color="primary" onClick={() => openCallFlow(alert)}>
                          <HistoryIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
                {activeAlerts.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={9} align="center" sx={{ py: 3 }}>
                      <Typography variant="body1" color="text.secondary">No active mobile alerts</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </TabPanel>

        {/* Tab 4: CALL HISTORY */}
        <TabPanel value={tabValue} index={3}>
          <Box sx={{ mb: 2, display: 'flex', justifyContent: 'flex-end' }}>
             <Button variant="outlined" startIcon={<DownloadIcon />} onClick={handleExportHistory}>Export to Excel</Button>
          </Box>
          <TableContainer component={Paper} variant="outlined">
            <Table>
              <TableHead sx={{ bgcolor: '#f8f9fa' }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold' }}>Date</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Alert Details</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Location / Server</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Severity</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Group</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Status</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Ack By</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {history.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{formatDate(item.created_at)}</TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>{item.title}</Typography>
                      <Typography variant="caption" color="text.secondary" display="block">{item.body}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{item.server_name || '-'}</Typography>
                      {item.server_ip && <Typography variant="caption" color="text.secondary">{item.server_ip}</Typography>}
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        {getSeverityIcon(item.severity)}
                        <Typography variant="body2" sx={{ ml: 1, fontWeight: 'bold' }}>
                          {(item.severity?.toLowerCase() === 'error' ? 'CRITICAL' : item.severity)?.toUpperCase()}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>{item.group_name}</TableCell>
                    <TableCell>{getStatusChip(item.status)}</TableCell>
                    <TableCell>{item.acknowledged_by_name || '-'}</TableCell>
                    <TableCell>
                      <Tooltip title="View Call Flow">
                        <IconButton size="small" color="primary" onClick={() => openCallFlow(item)}>
                          <HistoryIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </TabPanel>

        {/* Tab 5: MOBILE LOGS */}
        <TabPanel value={tabValue} index={4}>
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead sx={{ bgcolor: '#f8f9fa' }}>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold' }}>Time</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>User</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Action</TableCell>
                  <TableCell sx={{ fontWeight: 'bold' }}>Device Info</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {mobileLogs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell>{formatDate(log.timestamp)}</TableCell>
                    <TableCell>{log.user_email || 'System'}</TableCell>
                    <TableCell>
                       <Chip 
                        label={log.action} 
                        color={
                          log.action === 'Mobile Device Registered' || log.action === 'Mobile Google Login' || log.action === 'Lama Credential Authentication' || log.action === 'Mobile Lama Credential Authentication'
                            ? 'success' 
                            : log.action === 'Acknowledge Alert (Mobile)' 
                              ? 'primary' 
                              : log.action === 'Lama Credential Authentication Failed' || log.action === 'Mobile Lama Credential Authentication Failed'
                                ? 'error'
                                : 'default'
                        } 
                        size="small" 
                        variant="outlined" 
                        sx={{ fontWeight: 'bold' }}
                      />
                    </TableCell>
                    <TableCell>
                      {log.details && typeof log.details === 'object' && (
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                          {Object.entries(log.details).map(([key, value]) => (
                            <Chip 
                              key={key} 
                              label={`${key}: ${value}`} 
                              size="small" 
                              sx={{ height: 20, fontSize: '0.7rem' }} 
                            />
                          ))}
                        </Box>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {mobileLogs.length === 0 && !loading && (
                   <TableRow>
                    <TableCell colSpan={4} align="center" sx={{ py: 3 }}>
                      <Typography variant="body1" color="text.secondary">No mobile logs found</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </TabPanel>

        {/* Tab 6: SETTINGS */}
        <TabPanel value={tabValue} index={5}>
          <Grid container spacing={4}>
            <Grid item xs={12} md={7}>
              <Card variant="outlined">
                <CardHeader title="General Configuration" sx={{ bgcolor: '#f8f9fa' }} />
                <CardContent>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    <FormControlLabel
                      control={
                        <Switch 
                          checked={settings.enabled} 
                          onChange={(e) => setSettings({ ...settings, enabled: e.target.checked })}
                          disabled={isReadOnly}
                        />
                      }
                      label={
                        <Box>
                          <Typography variant="body1">Mobile Channel Enabled</Typography>
                          <Typography variant="caption" color="text.secondary">Global switch to enable/disable mobile push notifications</Typography>
                        </Box>
                      }
                    />
                    
                    <TextField
                      label="Default Escalation Timeout (seconds)"
                      type="number"
                      value={settings.default_timeout}
                      onChange={(e) => setSettings({ ...settings, default_timeout: parseInt(e.target.value) })}
                      disabled={isReadOnly}
                      fullWidth
                    />

                    <TextField
                      label="Push Retry Count"
                      type="number"
                      value={settings.retry_count}
                      onChange={(e) => setSettings({ ...settings, retry_count: parseInt(e.target.value) })}
                      disabled={isReadOnly}
                      fullWidth
                      helperText="Number of times to retry sending if push delivery fails"
                    />

                    {isAdminOrManager && (
                      <Box sx={{ mt: 2 }}>
                        <Button variant="contained" color="primary" onClick={handleSaveSettings}>
                          Save Settings
                        </Button>
                      </Box>
                    )}
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={5}>
              <Card variant="outlined" sx={{ borderStyle: 'dashed', borderColor: '#1976d2' }}>
                <CardHeader title="Connectivity Test" sx={{ bgcolor: '#e3f2fd' }} />
                <CardContent>
                  <Typography variant="body2" paragraph>
                    Verify your device connectivity by sending a test push notification.
                  </Typography>
                  <Button 
                    variant="outlined" 
                    color="primary" 
                    fullWidth 
                    size="large"
                    startIcon={<SendIcon />}
                    onClick={handleTestPush}
                  >
                    Send Test Push
                  </Button>
                  <Typography variant="caption" display="block" sx={{ mt: 2, textAlign: 'center' }}>
                    Note: You must have the SMC-LAMA app installed and be logged in.
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>
      </Box>

      {/* CALL FLOW MODAL */}
      <Dialog open={callFlowOpen} onClose={() => setCallFlowOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ bgcolor: '#f8f9fa', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box><Typography variant="h6" fontWeight="bold">Incident Call Flow</Typography><Typography variant="caption" color="text.secondary">Lifecycle of Alert #{selectedAlert?.id}</Typography></Box>
          <IconButton onClick={() => setCallFlowOpen(false)}><CloseIcon /></IconButton>
        </DialogTitle>
        <DialogContent sx={{ p: 0 }}>
          {callFlowLoading ? <Box sx={{ p: 5, textAlign: 'center' }}><CircularProgress /></Box> : (
            <List sx={{ p: 2 }}>
              {callFlowData.length === 0 ? <Box sx={{ p: 3, textAlign: 'center' }}><Typography color="text.secondary">No flow data recorded for this incident.</Typography></Box> : callFlowData.map((step, idx) => (
                <ListItem key={step.id} sx={{ mb: 2, alignItems: 'flex-start', borderLeft: '2px solid #1a237e', ml: 1, pl: 3 }}>
                  <ListItemIcon sx={{ minWidth: 40, mt: 0.5 }}>
                      {step.action === 'Triggered' && <AlertsIcon color="error" />}
                      {step.action === 'Acknowledge' && <AssignmentIndIcon color="primary" />}
                      {step.action === 'ERT Expired' && <AccessTimeIcon color="warning" />}
                      {step.action === 'Resolved' && <CheckCircleIcon color="success" />}
                  </ListItemIcon>
                  <ListItemText 
                      primary={<Box sx={{ display: 'flex', justifyContent: 'space-between' }}><Typography fontWeight="bold" variant="body1">{step.action}</Typography><Typography variant="caption" color="text.secondary">{step.timestamp}</Typography></Box>}
                      secondary={
                          <Box sx={{ mt: 0.5 }}>
                              <Typography variant="body2" color="text.primary">By: <strong>{step.user}</strong></Typography>
                              {step.details?.ert_minutes && <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}><AccessTimeIcon sx={{ fontSize: 14 }} /> Commitment: {formatCommitment(step.details.ert_minutes)}</Typography>}
                              {step.details?.justification && <Typography variant="body2" sx={{ bgcolor: '#fff9c4', p: 1, borderRadius: 1, mt: 1, fontStyle: 'italic' }}><CommentIcon sx={{ fontSize: 14, mr: 0.5 }} /> "{step.details.justification}"</Typography>}
                              {step.details?.failed_step !== undefined && <Typography variant="body2" color="error">Escalation Level {step.details.failed_step + 1} failed to resolve.</Typography>}
                          </Box>
                      }
                  />
                </ListItem>
              ))}
            </List>
          )}
        </DialogContent>
      </Dialog>

      {/* Group Create/Edit Dialog */}
      <Dialog open={groupDialogOpen} onClose={() => setGroupDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>{currentGroup?.id ? 'Edit Escalation Policy' : 'Create Escalation Policy'}</DialogTitle>
        <DialogContent dividers>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, pt: 1 }}>
            <TextField
              label="Policy / Group Name"
              value={currentGroup?.name || ''}
              onChange={(e) => setCurrentGroup({ ...currentGroup, name: e.target.value })}
              fullWidth
              required
              placeholder="e.g. SRE Mumbai Team"
            />
            
            <Divider />
            <Typography variant="h6" sx={{ fontWeight: 'bold' }}>Escalation Chain</Typography>
            <Typography variant="caption" color="text.secondary">Define who gets notified and after what delay if the alert isn't acknowledged.</Typography>

            {currentGroup?.escalation_chain?.map((step, idx) => (
              <Box key={idx} sx={{ p: 2, bgcolor: '#f9f9f9', borderRadius: 2, border: '1px solid #eee' }}>
                <Grid container spacing={2} alignItems="center">
                  <Grid item xs={12}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1a237e' }}>
                      STEP {idx + 1}: {idx === 0 ? 'Immediate Notification' : `Escalation Level ${idx}`}
                    </Typography>
                  </Grid>
                  
                  {idx > 0 && (
                    <Grid item xs={4}>
                      <TextField
                        label="Delay (Minutes)"
                        type="number"
                        size="small"
                        value={step.delay || 5}
                        onChange={(e) => {
                          const newChain = [...currentGroup.escalation_chain];
                          newChain[idx].delay = parseInt(e.target.value) || 0;
                          setCurrentGroup({ ...currentGroup, escalation_chain: newChain });
                        }}
                        fullWidth
                        helperText="Wait time after previous step"
                      />
                    </Grid>
                  )}

                  <Grid item xs={idx > 0 ? 8 : 12}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Notify Users</InputLabel>
                      <Select
                        multiple
                        value={step.notify || []}
                        label="Notify Users"
                        onChange={(e) => {
                          const newChain = [...currentGroup.escalation_chain];
                          newChain[idx].notify = e.target.value;
                          setCurrentGroup({ ...currentGroup, escalation_chain: newChain });
                        }}
                        renderValue={(selected) => (
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {selected.map((value) => {
                              const contact = contacts.find(c => c.id === value);
                              return <Chip key={value} label={contact?.full_name || value} size="small" />;
                            })}
                          </Box>
                        )}
                      >
                        {contacts.map((contact) => (
                          <MenuItem key={contact.id} value={contact.id}>
                            {contact.full_name} ({contact.email})
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>

                  <Grid item xs={12} sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <Button 
                      size="small" 
                      color="error" 
                      onClick={() => {
                        const newChain = currentGroup.escalation_chain.filter((_, i) => i !== idx);
                        setCurrentGroup({ ...currentGroup, escalation_chain: newChain });
                      }}
                    >
                      Remove Step
                    </Button>
                  </Grid>
                </Grid>
              </Box>
            ))}

            <Button 
              variant="outlined" 
              startIcon={<AddIcon />} 
              onClick={() => {
                const newChain = [...(currentGroup.escalation_chain || []), { delay: 5, notify: [] }];
                setCurrentGroup({ ...currentGroup, escalation_chain: newChain });
              }}
              sx={{ alignSelf: 'center' }}
            >
              Add Escalation Level
            </Button>
          </Box>
        </DialogContent>
        <DialogActions sx={{ p: 3 }}>
          <Button onClick={() => setGroupDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleSaveGroup} variant="contained" color="success" size="large">
            Save Escalation Policy
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default MobileAlerts;
