import React, { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import Grid from '@mui/material/Grid';
import IconButton from '@mui/material/IconButton';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Collapse from '@mui/material/Collapse';
import Tooltip from '@mui/material/Tooltip';
import axios from 'axios';
import Search from '@mui/icons-material/Search';
import AddCircleOutline from '@mui/icons-material/AddCircleOutline';
import Delete from '@mui/icons-material/Delete';
import Add from '@mui/icons-material/Add';
import FilterList from '@mui/icons-material/FilterList';
import StorageIcon from '@mui/icons-material/Storage';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import DnsIcon from '@mui/icons-material/Dns';
import TerminalIcon from '@mui/icons-material/Terminal';
import WindowIcon from '@mui/icons-material/Window'; 
import AppleIcon from '@mui/icons-material/Apple';
import Storage from '@mui/icons-material/Storage';

// --- Sub-component for individual Source Discovery ---
const SourceDiscoveryRow = ({ source, environment, onDelete }) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [targets, setTargets] = useState([]);
  const [filterText, setFilterText] = useState('');
  const [selectedTargets, setSelectedTargets] = useState([]);
  const [metricSource, setMetricSource] = useState('auto');
  const [locationId, setLocationId] = useState('1');
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [bulkDialogOpen, setBulkDialogOpen] = useState(false);
  const [bulkIpText, setBulkIpText] = useState('');

  // --- Allowed Accounts State ---
  const [accountsDialogOpen, setAccountsDialogOpen] = useState(false);
  const [discoveredAccounts, setDiscoveredAccounts] = useState([]);
  const [selectedAccountIds, setSelectedAccountIds] = useState(new Set());
  const [accountNames, setAccountNames] = useState({});
  const [savedAccounts, setSavedAccounts] = useState(source.config?.allowed_accounts || []);
  const [accountsLoading, setAccountsLoading] = useState(false);

  const handleDiscoverAccounts = async () => {
    setAccountsLoading(true);
    setError(null);
    try {
      const resp = await axios.get(`/v1/metric-sources/${source.id}/discover-accounts`);
      const accs = resp.data.accounts || [];
      setDiscoveredAccounts(accs);
      // Pre-select already saved accounts
      const existing = new Set(savedAccounts.map(a => a.account_id));
      setSelectedAccountIds(existing);
      // Preserve names
      const names = {};
      savedAccounts.forEach(a => { if (a.name) names[a.account_id] = a.name; });
      accs.forEach(a => { if (a.name && !names[a.account_id]) names[a.account_id] = a.name; });
      setAccountNames(names);
      setAccountsDialogOpen(true);
    } catch (err) {
      setError(`Failed to discover accounts: ${err.response?.data?.detail || err.message}`);
    } finally {
      setAccountsLoading(false);
    }
  };

  const handleSaveAccounts = async () => {
    setAccountsLoading(true);
    try {
      const payload = Array.from(selectedAccountIds).map(id => ({
        account_id: id,
        name: accountNames[id] || ''
      }));
      await axios.put(`/v1/metric-sources/${source.id}/allowed-accounts`, { allowed_accounts: payload });
      setSavedAccounts(payload);
      setAccountsDialogOpen(false);
      setMessage(`Saved ${payload.length} allowed account(s). Schedulers will only collect metrics for these accounts.`);
    } catch (err) {
      setError(`Failed to save: ${err.response?.data?.detail || err.message}`);
    } finally {
      setAccountsLoading(false);
    }
  };

  const toggleAccount = (accId) => {
    setSelectedAccountIds(prev => {
      const next = new Set(prev);
      if (next.has(accId)) next.delete(accId); else next.add(accId);
      return next;
    });
  };

  // --- AI Metric Probe State ---
  const [probeDialogOpen, setProbeDialogOpen] = useState(false);
  const [probeTarget, setProbeTarget] = useState(null);
  const [probeResult, setProbeResult] = useState(null);
  const [probeLoading, setProbeLoading] = useState(false);
  const [metricSelections, setMetricSelections] = useState({});
  // metricSelections: { "instance_key": { hardware: true, network: true, application: false, database: false } }

  const handleProbeTarget = async (target) => {
    setProbeTarget(target);
    setProbeDialogOpen(true);
    setProbeLoading(true);
    setProbeResult(null);
    try {
      const resp = await axios.post('/v1/probe-target-metrics', {
        url: source.config.url,
        target: target.ecs_service || target.name || target.ip,
        resource_type: target.resource_type || 'server',
        ecs_cluster: target.ecs_cluster || '',
        ecs_service: target.ecs_service || ''
      });
      setProbeResult(resp.data);
      // Auto-select recommended categories
      const cats = resp.data.categories || {};
      const sel = {};
      Object.entries(cats).forEach(([cat, info]) => {
        if (info) sel[cat] = info.recommended || false;
      });
      setMetricSelections(prev => ({ ...prev, [target.instance]: sel }));
    } catch (err) {
      setError(`Probe failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setProbeLoading(false);
    }
  };

  const toggleMetricCategory = (instance, category) => {
    setMetricSelections(prev => ({
      ...prev,
      [instance]: { ...(prev[instance] || {}), [category]: !(prev[instance] || {})[category] }
    }));
  };
  const handleDiscover = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);
    setTargets([]);
    
    try {
      
      // Pass allowed accounts as account_filter so only those accounts' targets show
      const accountFilter = savedAccounts.length > 0 ? savedAccounts.map(a => a.account_id) : undefined;
      const response = await axios.post('/v1/discover-targets', 
        { 
          url: source.config.url,
          use_iam: source.config.use_iam || false,
          role_arn: source.config.role_arn || '',
          region: source.config.region || 'ap-south-1',
          account_filter: accountFilter
        },
        { headers: {  } }
      );

      if (response.data?.status === 'success') {
        const uniqueTargets = response.data.targets || [];
        setTargets(uniqueTargets);
        
        if (uniqueTargets.length === 0) {
           setMessage('No active targets found.');
        } else {
           setMessage(`Discovered ${uniqueTargets.length} targets.`);
           setOpen(true); // Auto-expand on success
        }
      }
    } catch (err) {
      console.error(err);
      setError(`Discovery failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const filteredTargets = targets.filter(t => 
    t.instance.toLowerCase().includes(filterText.toLowerCase()) ||
    t.ip?.toLowerCase().includes(filterText.toLowerCase()) ||
    t.job?.toLowerCase().includes(filterText.toLowerCase()) ||
    t.name?.toLowerCase().includes(filterText.toLowerCase()) ||
    (t.resource_type || '').toLowerCase().includes(filterText.toLowerCase()) ||
    (t.account_id || '').includes(filterText) ||
    (t.account_name || '').toLowerCase().includes(filterText.toLowerCase()) ||
    (t.ecs_service || '').toLowerCase().includes(filterText.toLowerCase())
  );

  const handleSelectAll = (event) => {
    if (event.target.checked) {
      const filteredIds = filteredTargets.map(t => t.instance);
      setSelectedTargets([...new Set([...selectedTargets, ...filteredIds])]);
    } else {
      const filteredIds = filteredTargets.map(t => t.instance);
      setSelectedTargets(selectedTargets.filter(id => !filteredIds.includes(id)));
    }
  };

  const handleSelectOne = (instance) => {
    const selectedIndex = selectedTargets.indexOf(instance);
    let newSelected = [];

    if (selectedIndex === -1) {
      newSelected = newSelected.concat(selectedTargets, instance);
    } else if (selectedIndex === 0) {
      newSelected = newSelected.concat(selectedTargets.slice(1));
    } else if (selectedIndex === selectedTargets.length - 1) {
      newSelected = newSelected.concat(selectedTargets.slice(0, -1));
    } else if (selectedIndex > 0) {
      newSelected = newSelected.concat(
        selectedTargets.slice(0, selectedIndex),
        selectedTargets.slice(selectedIndex + 1),
      );
    }
    setSelectedTargets(newSelected);
  };

  const handleOnboard = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);

    const serversToOnboard = targets
      .filter(t => selectedTargets.includes(t.instance))
      .map(t => {
        const sel = metricSelections[t.instance] || {};
        return {
          name: t.name, 
          ip: t.ip || t.instance.split(':')[0],
          environment: environment,
          metric_source: metricSource,
          detected_os: t.detected_os,
          detected_apps: t.detected_apps,
          source_id: source.id,
          resource_type: t.resource_type || 'server',
          account_id: t.account_id || '',
          ecs_cluster: t.ecs_cluster || '',
          ecs_service: t.ecs_service || '',
          location_id: (t.resource_type === 'ecs' || t.resource_type === 'rds' || t.resource_type === 'ec2') ? 3 : parseInt(locationId) || 1,
          send_hardware_metrics: sel.hardware !== false,
          send_network_metrics: sel.network !== false,
          send_application_metrics: sel.application || false,
          send_database_metrics: sel.database || false,
        };
      });

    if (serversToOnboard.length === 0) {
      setError('Please select at least one server to onboard.');
      setLoading(false);
      return;
    }

    try {
      
      const response = await axios.post('/v1/onboard-discovered-servers', 
        { 
          servers: serversToOnboard,
          metric_source: metricSource,
          source_id: source.id
        },
        { headers: {  } }
      );
      
      if (response.data.status === 'success') {
        setMessage(response.data.message);
        if (response.data.errors?.length > 0) {
          setError(`Partial success. Errors: ${response.data.errors.join(', ')}`);
        }
        setSelectedTargets([]);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to onboard servers.');
    } finally {
      setLoading(false);
    }
  };

  const getOsIcon = (os) => {
    if (!os) return <TerminalIcon fontSize="small" />;
    if (os.toLowerCase().includes('win')) return <WindowIcon fontSize="small" color="primary" />;
    if (os.toLowerCase().includes('mac') || os.toLowerCase().includes('darwin')) return <AppleIcon fontSize="small" />;
    return <TerminalIcon fontSize="small" />;
  };

  return (
    <>
      <TableRow sx={{ '& > *': { borderBottom: 'unset' }, bgcolor: open ? '#f8f9fa' : 'inherit' }}>
        <TableCell>
          <IconButton
            aria-label="expand row"
            size="small"
            onClick={() => setOpen(!open)}
          >
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>
        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
           {source.name}
        </TableCell>
        <TableCell sx={{ fontFamily: 'monospace' }}>{source.config.url}</TableCell>
        <TableCell>
          {savedAccounts.length > 0 ? (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {savedAccounts.map(a => (
                <Chip key={a.account_id} label={a.name || a.account_id} size="small" color="primary" variant="outlined" sx={{ fontSize: '0.7rem' }} />
              ))}
            </Box>
          ) : (
            <Chip label="All Accounts" size="small" color="default" variant="outlined" sx={{ fontSize: '0.7rem' }} />
          )}
        </TableCell>
        <TableCell align="right">
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1 }}>
                <Button
                    variant="outlined"
                    size="small"
                    color="secondary"
                    startIcon={accountsLoading ? <CircularProgress size={16} /> : <FilterList />}
                    onClick={handleDiscoverAccounts}
                    disabled={accountsLoading}
                >
                    Accounts
                </Button>
                <Button 
                    variant="outlined" 
                    size="small" 
                    startIcon={loading ? <CircularProgress size={16} /> : <Search />}
                    onClick={handleDiscover}
                    disabled={loading}
                >
                    Scan Targets
                </Button>
                <IconButton size="small" color="error" onClick={() => onDelete(source.id)}>
                    <Delete fontSize="small" />
                </IconButton>
            </Box>
        </TableCell>
      </TableRow>
      <TableRow>
        <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={6}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ margin: 2, border: '1px solid #eee', borderRadius: 1, p: 2, bgcolor: '#fff' }}>
                <Typography variant="subtitle2" gutterBottom component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                   <DnsIcon fontSize="small" color="action" /> Discovery Results for {source.config.url}
                </Typography>
                
                {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}
                {message && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMessage(null)}>{message}</Alert>}

                {targets.length > 0 ? (
                    <>
                        <Box sx={{ mb: 2, mt: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                            <FilterList color="action" fontSize="small" />
                            <TextField
                                fullWidth
                                placeholder="Quick filter..."
                                value={filterText}
                                onChange={(e) => setFilterText(e.target.value)}
                                size="small"
                                variant="standard"
                            />
                            <Tooltip title="Bulk IP Paste">
                                <Button 
                                    size="small" 
                                    variant="outlined" 
                                    startIcon={<Add />}
                                    onClick={() => setBulkDialogOpen(true)}
                                    sx={{ whiteSpace: 'nowrap' }}
                                >
                                    Bulk IP Select
                                </Button>
                            </Tooltip>
                        </Box>

                        {/* Bulk IP Dialog */}
                        <Dialog open={bulkDialogOpen} onClose={() => setBulkDialogOpen(false)} maxWidth="xs" fullWidth>
                            <DialogTitle sx={{ fontSize: '1rem', fontWeight: 'bold' }}>Bulk IP Paste</DialogTitle>
                            <DialogContent>
                                <Typography variant="caption" color="textSecondary" sx={{ mb: 1, display: 'block' }}>
                                    Paste a list of IP addresses (one per line) to automatically select matching discovered targets.
                                </Typography>
                                <TextField
                                    multiline
                                    rows={8}
                                    fullWidth
                                    placeholder="192.168.1.1\n192.168.1.2..."
                                    value={bulkIpText}
                                    onChange={(e) => setBulkIpText(e.target.value)}
                                    sx={{ mt: 1, fontFamily: 'monospace' }}
                                    variant="outlined"
                                />
                            </DialogContent>
                            <DialogActions>
                                <Button onClick={() => setBulkDialogOpen(false)}>Cancel</Button>
                                <Button 
                                    onClick={() => {
                                        const ips = bulkIpText.split(/[\s,]+/).filter(ip => ip.trim());
                                        const matches = targets.filter(t => ips.includes(t.ip) || ips.includes(t.instance.split(':')[0]));
                                        const matchIds = matches.map(m => m.instance);
                                        setSelectedTargets([...new Set([...selectedTargets, ...matchIds])]);
                                        setBulkDialogOpen(false);
                                        setBulkIpText('');
                                        setMessage(`Auto-selected ${matchIds.length} matching servers.`);
                                    }} 
                                    variant="contained" 
                                    color="primary"
                                >
                                    Select Matches
                                </Button>
                            </DialogActions>
                        </Dialog>

                        <TableContainer sx={{ maxHeight: 300 }}>
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell padding="checkbox">
                                            <Checkbox
                                                indeterminate={selectedTargets.length > 0 && selectedTargets.length < filteredTargets.length}
                                                checked={filteredTargets.length > 0 && selectedTargets.length >= filteredTargets.length}
                                                onChange={handleSelectAll}
                                            />
                                        </TableCell>
                                        <TableCell>Instance</TableCell>
                                        <TableCell>Type</TableCell>
                                        <TableCell>Account</TableCell>
                                        <TableCell>Metrics to Send</TableCell>
                                        <TableCell align="center">Probe</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {filteredTargets.map((target) => {
                                        const isSelected = selectedTargets.indexOf(target.instance) !== -1;
                                        const typeColor = target.resource_type === 'ecs' ? 'success' : target.resource_type === 'rds' ? 'warning' : target.resource_type === 'server' ? 'default' : 'info';
                                        const sel = metricSelections[target.instance] || {};
                                        return (
                                            <TableRow
                                                hover
                                                role="checkbox"
                                                aria-checked={isSelected}
                                                tabIndex={-1}
                                                key={target.instance}
                                                selected={isSelected}
                                            >
                                                <TableCell padding="checkbox">
                                                    <Checkbox checked={isSelected} onChange={() => handleSelectOne(target.instance)} />
                                                </TableCell>
                                                <TableCell sx={{ fontFamily: 'monospace', cursor: 'pointer' }} onClick={() => handleSelectOne(target.instance)}>
                                                    {target.name || target.instance}
                                                    <Typography variant="caption" display="block" color="textSecondary">
                                                        {target.resource_type === 'ecs' ? (target.ecs_cluster || target.ip) : target.ip}
                                                    </Typography>
                                                </TableCell>
                                                <TableCell>
                                                    <Chip label={(target.resource_type || 'server').toUpperCase()} size="small" color={typeColor} variant="outlined" sx={{ fontSize: '0.7rem', fontWeight: 600 }} />
                                                </TableCell>
                                                <TableCell>
                                                    <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                                                        {target.account_id ? `${target.account_name || target.account_id}` : '-'}
                                                    </Typography>
                                                </TableCell>
                                                <TableCell>
                                                    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                                                        {Object.keys(sel).length > 0 ? (
                                                            Object.entries(sel).map(([cat, enabled]) => (
                                                                <Chip
                                                                    key={cat}
                                                                    label={cat.charAt(0).toUpperCase() + cat.slice(1)}
                                                                    size="small"
                                                                    color={enabled ? 'success' : 'default'}
                                                                    variant={enabled ? 'filled' : 'outlined'}
                                                                    onClick={(e) => { e.stopPropagation(); toggleMetricCategory(target.instance, cat); }}
                                                                    sx={{ fontSize: '0.65rem', height: 22, cursor: 'pointer', opacity: enabled ? 1 : 0.5 }}
                                                                />
                                                            ))
                                                        ) : (
                                                            <Typography variant="caption" color="textSecondary">Click Probe →</Typography>
                                                        )}
                                                    </Box>
                                                </TableCell>
                                                <TableCell align="center">
                                                    <IconButton size="small" color="secondary" onClick={(e) => { e.stopPropagation(); handleProbeTarget(target); }}>
                                                        <Search fontSize="small" />
                                                    </IconButton>
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })}
                                    {filteredTargets.length === 0 && (
                                        <TableRow>
                                            <TableCell colSpan={7} align="center">No matching targets</TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </TableContainer>

                        <Box sx={{ mt: 2, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
                            <Grid container spacing={2} alignItems="center">
                                <Grid item xs={12} md={4}>
                                    <FormControl fullWidth size="small">
                                        <InputLabel>Metric Source for Onboarding</InputLabel>
                                        <Select
                                            value={metricSource}
                                            label="Metric Source for Onboarding"
                                            onChange={(e) => setMetricSource(e.target.value)}
                                        >
                                            <MenuItem value="auto">Auto Discover</MenuItem>
                                            <MenuItem value="aws">AWS Account</MenuItem>
                                            <MenuItem value="onprem">On-Prem Account</MenuItem>
                                        </Select>
                                    </FormControl>
                                </Grid>
                                <Grid item xs={12} md={3}>
                                    <FormControl fullWidth size="small">
                                        <InputLabel>Location (On-Prem Servers)</InputLabel>
                                        <Select
                                            value={locationId}
                                            label="Location (On-Prem Servers)"
                                            onChange={(e) => setLocationId(e.target.value)}
                                        >
                                            <MenuItem value="1">DC (Data Center)</MenuItem>
                                            <MenuItem value="2">DR (Disaster Recovery)</MenuItem>
                                        </Select>
                                    </FormControl>
                                </Grid>
                                <Grid item xs={12} md={5}>
                                    <Button
                                        variant="contained"
                                        color="secondary"
                                        onClick={handleOnboard}
                                        disabled={loading || selectedTargets.length === 0}
                                        startIcon={<AddCircleOutline />}
                                        fullWidth
                                    >
                                        Onboard {selectedTargets.length} Servers
                                    </Button>
                                </Grid>
                            </Grid>
                        </Box>
                    </>
                ) : (
                    <Typography variant="body2" color="textSecondary" align="center" sx={{ py: 3 }}>
                        Click "Scan Targets" to retrieve active endpoints from this source.
                    </Typography>
                )}
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>

      {/* Allowed Accounts Dialog */}
      <Dialog open={accountsDialogOpen} onClose={() => setAccountsDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 'bold' }}>
          Allowed AWS Accounts
          <Typography variant="body2" color="textSecondary">
            Select which AWS accounts' metrics should be collected and sent to LAMA Exchange.
            Unselected accounts will be ignored by all schedulers.
          </Typography>
        </DialogTitle>
        <DialogContent>
          {discoveredAccounts.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 3 }}>
              <CircularProgress size={24} />
              <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>Discovering accounts from Mimir...</Typography>
            </Box>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox">
                    <Checkbox
                      checked={selectedAccountIds.size === discoveredAccounts.length}
                      indeterminate={selectedAccountIds.size > 0 && selectedAccountIds.size < discoveredAccounts.length}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedAccountIds(new Set(discoveredAccounts.map(a => a.account_id)));
                        else setSelectedAccountIds(new Set());
                      }}
                    />
                  </TableCell>
                  <TableCell>Account ID</TableCell>
                  <TableCell>Display Name</TableCell>
                  <TableCell align="center">Resources</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {discoveredAccounts.map(acc => (
                  <TableRow key={acc.account_id} hover onClick={() => toggleAccount(acc.account_id)} sx={{ cursor: 'pointer' }}>
                    <TableCell padding="checkbox">
                      <Checkbox checked={selectedAccountIds.has(acc.account_id)} />
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600 }}>{acc.account_id}</TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        variant="standard"
                        placeholder="e.g. SMC-PRE-TRADING-PROD"
                        value={accountNames[acc.account_id] || ''}
                        onChange={(e) => {
                          e.stopPropagation();
                          setAccountNames(prev => ({ ...prev, [acc.account_id]: e.target.value }));
                        }}
                        onClick={(e) => e.stopPropagation()}
                        fullWidth
                        sx={{ fontSize: '0.85rem' }}
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'center', flexWrap: 'wrap' }}>
                        {acc.ec2_count > 0 && <Chip label={`${acc.ec2_count} EC2`} size="small" color="info" variant="outlined" />}
                        {acc.ecs_count > 0 && <Chip label={`${acc.ecs_count} ECS`} size="small" color="success" variant="outlined" />}
                        {acc.rds_count > 0 && <Chip label={`${acc.rds_count} RDS`} size="small" color="warning" variant="outlined" />}
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {selectedAccountIds.size === 0 && discoveredAccounts.length > 0 && (
            <Alert severity="warning" sx={{ mt: 2 }}>No accounts selected — schedulers will send metrics for ALL accounts.</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAccountsDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleSaveAccounts} variant="contained" color="primary" disabled={accountsLoading}>
            {accountsLoading ? <CircularProgress size={20} /> : `Save ${selectedAccountIds.size} Account(s)`}
          </Button>
        </DialogActions>
      </Dialog>

      {/* AI Metric Probe Dialog */}
      <Dialog open={probeDialogOpen} onClose={() => setProbeDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 'bold', pb: 0 }}>
          🤖 AI Metric Discovery
          {probeTarget && (
            <Typography variant="body2" color="textSecondary">
              {probeTarget.name || probeTarget.instance} ({(probeTarget.resource_type || 'ec2').toUpperCase()})
            </Typography>
          )}
        </DialogTitle>
        <DialogContent>
          {probeLoading ? (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <CircularProgress size={32} />
              <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>Probing Mimir for available metrics...</Typography>
            </Box>
          ) : probeResult ? (
            <Box sx={{ mt: 1 }}>
              {!probeResult.found && (
                <Alert severity="warning" sx={{ mb: 2 }}>No metrics found in Mimir for this target. It may not have an agent installed.</Alert>
              )}
              {probeResult.found && (
                <Alert severity="info" sx={{ mb: 2 }} icon={false}>
                  Detected: <strong>{probeResult.detected_os?.toUpperCase()}</strong> via label <code>{probeResult.discovery_label}</code> matching <code>{probeResult.discovery_pattern}</code>
                </Alert>
              )}
              {Object.entries(probeResult.categories || {}).map(([category, info]) => {
                if (!info) return null;
                const sel = (metricSelections[probeTarget?.instance] || {})[category];
                const catLabel = category.charAt(0).toUpperCase() + category.slice(1);
                return (
                  <Paper key={category} variant="outlined" sx={{ mb: 1.5, p: 1.5, bgcolor: info.available ? (sel ? '#e8f5e9' : '#fff') : '#fafafa', opacity: info.available ? 1 : 0.6 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Checkbox
                          checked={!!sel}
                          disabled={!info.available}
                          onChange={() => probeTarget && toggleMetricCategory(probeTarget.instance, category)}
                          size="small"
                        />
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                          {info.available ? '✅' : '❌'} {catLabel} Metrics
                        </Typography>
                      </Box>
                      <Chip
                        label={info.available ? 'AVAILABLE' : 'NOT FOUND'}
                        size="small"
                        color={info.available ? 'success' : 'default'}
                        variant="outlined"
                        sx={{ fontSize: '0.65rem' }}
                      />
                    </Box>
                    {info.metrics && (
                      <Box sx={{ pl: 4.5 }}>
                        {Object.entries(info.metrics).filter(([key, m]) => m.available).map(([key, m]) => (
                          <Box key={key} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.3 }}>
                            <Typography variant="caption" sx={{ color: m.available ? 'success.main' : 'text.disabled', fontWeight: 600, minWidth: 12 }}>
                              {m.available ? '●' : '○'}
                            </Typography>
                            <Chip
                              label={m.metric}
                              size="small"
                              variant="outlined"
                              color={m.available ? 'primary' : 'default'}
                              sx={{ fontFamily: 'monospace', fontSize: '0.6rem', height: 20, opacity: m.available ? 1 : 0.5 }}
                            />
                            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.7rem' }}>→</Typography>
                            <Chip
                              label={`LAMA: ${m.lama_key} (${m.unit})`}
                              size="small"
                              color={m.available ? 'success' : 'default'}
                              variant={m.available ? 'filled' : 'outlined'}
                              sx={{ fontSize: '0.6rem', height: 20, fontWeight: 700, opacity: m.available ? 1 : 0.4 }}
                            />
                            {m.available && (
                              <Chip label={`${m.series} series`} size="small" variant="outlined" sx={{ height: 18, fontSize: '0.55rem' }} />
                            )}
                          </Box>
                        ))}
                      </Box>
                    )}
                  </Paper>
                );
              })}
            </Box>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setProbeDialogOpen(false)}>Close</Button>
          {probeTarget && probeResult?.found && (
            <Button
              variant="contained"
              color="primary"
              onClick={() => {
                // Auto-select this target for onboarding
                if (!selectedTargets.includes(probeTarget.instance)) {
                  handleSelectOne(probeTarget.instance);
                }
                setProbeDialogOpen(false);
                setMessage(`Metric selections saved for ${probeTarget.name}. Select more targets or click Onboard.`);
              }}
            >
              Confirm Selections
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
};


// --- Main Component ---
const PrometheusDiscovery = ({ environment }) => {
  const [savedSources, setSavedSources] = useState([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [openDialog, setOpenDialog] = useState(false);
  const [newUrl, setNewUrl] = useState('');
  const [newName, setNewName] = useState('');
  const [useIAM, setUseIAM] = useState(false);
  const [roleArn, setRoleArn] = useState('');
  const [region, setRegion] = useState('ap-south-1');
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSources();
  }, [environment]);

  const fetchSources = async () => {
    setLoadingSources(true);
    try {
      
      const response = await axios.get(`/v1/metric-sources?environment=${environment}`, {
        headers: {  }
      });
      
      if (Array.isArray(response.data)) {
        // Filter for Prometheus/LGTM sources
        const prometheusSources = response.data.filter(s => s.type === 'prometheus');
        setSavedSources(prometheusSources);
      }
    } catch (err) {
      console.error("Failed to fetch metric sources:", err);
    } finally {
      setLoadingSources(false);
    }
  };

  const handleAddSource = async () => {
    if (!newUrl || !newUrl.trim()) return;
    
    setLoadingSources(true);
    try {
      
      const name = newName.trim() || `Prometheus - ${newUrl.trim()}`;
      
      await axios.post('/v1/metric-sources', {
        name: name,
        type: 'prometheus',
        config: { 
          url: newUrl.trim(),
          use_iam: useIAM,
          role_arn: useIAM ? roleArn.trim() : '',
          region: useIAM ? region.trim() : 'ap-south-1'
        },
        environment: environment,
        enabled: true
      }, {
        headers: {  }
      });
      
      setNewUrl('');
      setNewName('');
      setUseIAM(false);
      setRoleArn('');
      setOpenDialog(false);
      setError(null);
      fetchSources(); 
    } catch (err) {
      setError(`Failed to add source: ${err.response?.data?.detail || err.message}`);
    } finally {
      setLoadingSources(false);
    }
  };

  const handleDeleteSource = async (id) => {
    if (!window.confirm("Are you sure you want to remove this data source?")) return;
    
    try {
      
      await axios.delete(`/v1/metric-sources/${id}`, {
        headers: {  }
      });
      fetchSources(); 
    } catch (err) {
      alert(`Failed to delete source: ${err.response?.data?.detail || err.message}`);
    }
  };

  return (
    <Paper sx={{ p: 3, mt: 4, border: '1px solid #e0e0e0' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 1 }}>
            <StorageIcon color="primary" /> Prometheus/LGTM Discovery
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Manage Prometheus endpoints and discover targets from each source independently.
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => setOpenDialog(true)}
          sx={{ background: 'linear-gradient(135deg, #E91E63 0%, #C2185B 100%)' }}
        >
          Add Prometheus Source
        </Button>
      </Box>
      
      {loadingSources && savedSources.length === 0 ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}><CircularProgress /></Box>
      ) : savedSources.length === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4, bgcolor: '#fcfcfc', borderRadius: 1, border: '1px dashed #ddd' }}>
            <Typography color="textSecondary">No Prometheus sources configured for {environment.toUpperCase()}</Typography>
          </Box>
      ) : (
        <TableContainer component={Paper} elevation={0} variant="outlined">
          <Table aria-label="collapsible table">
            <TableHead>
              <TableRow>
                <TableCell width={50} />
                <TableCell>Source Name</TableCell>
                <TableCell>URL</TableCell>
                <TableCell>Allowed Accounts</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {savedSources.map((source) => (
                <SourceDiscoveryRow 
                    key={source.id} 
                    source={source} 
                    environment={environment}
                    onDelete={handleDeleteSource}
                />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Add Source Dialog */}
      <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add Prometheus/LGTM Source</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              fullWidth
              label="Display Name (Optional)"
              placeholder="e.g. Production Prometheus"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              size="small"
            />
            <TextField
              fullWidth
              label="Prometheus URL"
              placeholder="http://localhost:9090"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              size="small"
              required
            />

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
              <input
                type="checkbox"
                id="useIAMProm"
                checked={useIAM}
                onChange={(e) => setUseIAM(e.target.checked)}
                style={{ width: 18, height: 18 }}
              />
              <label htmlFor="useIAMProm" style={{ cursor: 'pointer', fontWeight: 500, fontSize: '0.9rem' }}>
                Use AWS IAM Auth (SigV4)
              </label>
            </Box>

            {useIAM && (
              <>
                <TextField
                  fullWidth
                  label="Role ARN (Optional)"
                  placeholder="arn:aws:iam::123456789012:role/CrossAccountRole"
                  value={roleArn}
                  onChange={(e) => setRoleArn(e.target.value)}
                  size="small"
                  helperText="Enter ARN for cross-account access."
                />
                <TextField
                  fullWidth
                  label="AWS Region"
                  placeholder="ap-south-1"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  size="small"
                />
              </>
            )}

            {error && <Alert severity="error">{error}</Alert>}
            <Alert severity="info" icon={<StorageIcon />}>
              LAMA will query the <code>/api/v1/targets</code> endpoint of this URL to discover servers.
            </Alert>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDialog(false)}>Cancel</Button>
          <Button 
            onClick={handleAddSource} 
            variant="contained" 
            color="primary"
            disabled={!newUrl.trim() || loadingSources}
          >
            {loadingSources ? <CircularProgress size={24} /> : 'Add Source'}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default PrometheusDiscovery;