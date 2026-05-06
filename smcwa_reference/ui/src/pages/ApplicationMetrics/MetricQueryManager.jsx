import React, { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import {
  Table, TableBody, TableCell, TableHead, TableRow, TextField, Switch, Button, Alert, Chip
} from '@mui/material';
import axios from '../../utils/axiosConfig';

const METRIC_TYPES = [
  'throughput', 'latency', 'failureTradeApi', 'failureAuthentication', 
  'historicalThroughput', 'historicalLatency', 'log'
];

export default function MetricQueryManager({ source }) {
  const [queries, setQueries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    loadQueries();
  }, [source]);

  const loadQueries = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`/v1/metric-sources/${source.id}/queries`);
      const existingQueries = response.data || [];
      
      // Merge with defaults if missing
      const merged = METRIC_TYPES.map(type => {
        const found = existingQueries.find(q => q.metric_name === type);
        return found || {
          source_id: source.id,
          metric_name: type,
          query_payload: '', // Default empty
          enabled: true,
          isNew: true
        };
      });
      setQueries(merged);
    } catch (error) {
      console.error("Error loading queries:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (query) => {
    try {
      const payload = {
        source_id: source.id,
        metric_name: query.metric_name,
        index_name: query.index_name,
        query_payload: query.query_payload,
        value_field: query.value_field,
        enabled: query.enabled,
        warning_threshold: query.warning_threshold,
        critical_threshold: query.critical_threshold
      };

      await axios.post('/v1/metric-queries', payload);
      setMessage(`Saved ${query.metric_name}`);
      setTimeout(() => setMessage(''), 2000);
      loadQueries(); // Refresh to clear isNew flags
    } catch (error) {
      console.error("Error saving query:", error);
      alert("Failed to save query");
    }
  };

  const handleChange = (index, field, value) => {
    const updated = [...queries];
    updated[index][field] = value;
    setQueries(updated);
  };

  return (
    <Box>
      <Alert severity="info" sx={{ mb: 2 }}>
        Configure queries for <b>{source.name}</b> ({source.type}). 
        {source.type === 'elasticsearch' && " Use JSON query string or Lucene syntax."}
      </Alert>
      
      {message && <Alert severity="success" sx={{ mb: 2 }}>{message}</Alert>}

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell width="15%">Metric</TableCell>
            <TableCell width="15%">Index / Table</TableCell>
            <TableCell width="35%">Query / Payload</TableCell>
            <TableCell width="10%">Value Field (SQL)</TableCell>
            <TableCell width="10%">Warn</TableCell>
            <TableCell width="10%">Crit</TableCell>
            <TableCell width="5%" align="center">Enable</TableCell>
            <TableCell width="5%">Action</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {queries.map((q, idx) => (
            <TableRow key={q.metric_name}>
              <TableCell>
                <Chip label={q.metric_name} size="small" />
              </TableCell>
              <TableCell>
                <TextField
                  fullWidth size="small"
                  value={q.index_name || ''}
                  onChange={(e) => handleChange(idx, 'index_name', e.target.value)}
                  placeholder={source.type === 'elasticsearch' ? 'lama-*' : 'table_name'}
                  error={source.type === 'elasticsearch' && !q.index_name}
                />
              </TableCell>
              <TableCell>
                <TextField
                  fullWidth size="small"
                  multiline maxRows={2}
                  value={q.query_payload}
                  onChange={(e) => handleChange(idx, 'query_payload', e.target.value)}
                  placeholder={source.type === 'elasticsearch' ? 'e.g. topic:"trade" AND status:200' : 'SELECT count(*) ...'}
                />
              </TableCell>
              <TableCell>
                <TextField
                  fullWidth size="small"
                  value={q.value_field || ''}
                  onChange={(e) => handleChange(idx, 'value_field', e.target.value)}
                  placeholder="e.g. avg_val"
                  disabled={source.type === 'elasticsearch'}
                />
              </TableCell>
              <TableCell>
                <TextField
                  size="small" type="number"
                  value={q.warning_threshold || ''}
                  onChange={(e) => handleChange(idx, 'warning_threshold', e.target.value)}
                />
              </TableCell>
              <TableCell>
                <TextField
                  size="small" type="number"
                  value={q.critical_threshold || ''}
                  onChange={(e) => handleChange(idx, 'critical_threshold', e.target.value)}
                />
              </TableCell>
              <TableCell align="center">
                <Switch 
                  checked={q.enabled} 
                  onChange={(e) => handleChange(idx, 'enabled', e.target.checked)} 
                />
              </TableCell>
              <TableCell>
                <Button size="small" variant="contained" onClick={() => handleSave(q)}>
                  Save
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
