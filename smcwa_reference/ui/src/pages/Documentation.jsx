import React, { useState } from 'react';
import {
  Container, Typography, Box, Paper, Accordion, AccordionSummary, AccordionDetails,
  Chip, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Divider, Tabs, Tab, Alert
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

const D = ({ title, diagram }) => (
  <Paper sx={{ p: 2, mb: 2, bgcolor: '#0d1117', borderRadius: 2, overflow: 'auto', border: '1px solid #30363d' }}>
    <Typography variant="subtitle2" sx={{ color: '#58a6ff', mb: 1, fontWeight: 600 }}>{title}</Typography>
    <pre style={{ color: '#c9d1d9', fontSize: '11.5px', fontFamily: "'JetBrains Mono', monospace", margin: 0, whiteSpace: 'pre', lineHeight: 1.5 }}>{diagram}</pre>
  </Paper>
);

const MT = ({ rows, headers }) => (
  <TableContainer component={Paper} sx={{ mb: 2, borderRadius: 2 }}>
    <Table size="small">
      <TableHead>
        <TableRow sx={{ bgcolor: '#1565c0' }}>
          {(headers || ['Key', 'Format', 'Source', 'Details']).map((h, i) => (
            <TableCell key={i} sx={{ color: '#fff', fontWeight: 600, fontSize: '0.78rem' }}>{h}</TableCell>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((r, i) => (
          <TableRow key={i} sx={{ bgcolor: i % 2 === 0 ? '#f8f9fa' : '#fff' }}>
            {r.map((c, j) => (
              <TableCell key={j} sx={{ fontSize: '0.8rem', fontFamily: j === 0 ? 'monospace' : 'inherit', fontWeight: j === 0 ? 600 : 400, color: j === 0 ? '#1565c0' : 'inherit' }}>{c}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </TableContainer>
);

const Sec = ({ icon, title, color, children, defaultExpanded }) => (
  <Accordion defaultExpanded={defaultExpanded} sx={{ mb: 1, '&:before': { display: 'none' }, borderRadius: '8px !important', border: '1px solid #e0e0e0' }}>
    <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ bgcolor: '#fafafa' }}>
      <Typography variant="h6" sx={{ fontWeight: 600, color: color || '#1976d2', fontSize: '1rem' }}>{icon} {title}</Typography>
    </AccordionSummary>
    <AccordionDetails>{children}</AccordionDetails>
  </Accordion>
);

function TabPanel({ children, value, index }) {
  return value === index ? <Box sx={{ pt: 2 }}>{children}</Box> : null;
}

export default function Documentation() {
  const [tab, setTab] = useState(0);
  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Paper sx={{ p: 3, mb: 3, background: 'linear-gradient(135deg, #1565c0 0%, #0d47a1 100%)', color: '#fff', borderRadius: 3 }}>
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 0.5 }}>📚 SMC LAMA — System Documentation</Typography>
        <Typography variant="subtitle1" sx={{ opacity: 0.9 }}>Log Analytics & Monitoring Application — AI-Driven, Fully Automated Observability Platform</Typography>
        <Box sx={{ display: 'flex', gap: 1, mt: 1.5, flexWrap: 'wrap' }}>
          {['React 18', 'FastAPI', 'PostgreSQL 15', 'ClickHouse', 'Redis 7', 'Mimir/Prometheus', 'Docker'].map(t => (
            <Chip key={t} label={t} size="small" sx={{ bgcolor: 'rgba(255,255,255,0.2)', color: '#fff', fontWeight: 600 }} />
          ))}
        </Box>
      </Paper>

      <Tabs value={tab} onChange={(e, v) => setTab(v)} variant="scrollable" scrollButtons="auto" sx={{ mb: 2, bgcolor: '#fff', borderRadius: 2, boxShadow: 1 }}>
        <Tab label="🏗️ Architecture" />
        <Tab label="🤖 AI Discovery" />
        <Tab label="⚙️ Schedulers" />
        <Tab label="📊 Metrics Spec" />
        <Tab label="🗄️ Database Schema" />
        <Tab label="🔔 Alerts" />
        <Tab label="🔄 Lifecycle" />
      </Tabs>

      {/* TAB 0: Architecture */}
      <TabPanel value={tab} index={0}>
        <Sec icon="🏗️" title="System Architecture Overview" color="#1565c0" defaultExpanded>
          <D title="High-Level Architecture" diagram={`
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SMC LAMA PLATFORM                                  │
├─────────────┬──────────────┬──────────────┬──────────────┬─────────────────────┤
│   FRONTEND  │   BACKEND    │  SCHEDULERS  │  DATA STORES │   EXTERNAL          │
│  (React 18) │  (FastAPI)   │ (APScheduler)│              │                     │
│             │              │              │              │                     │
│  Dashboard  │  REST APIs   │  Hardware    │  PostgreSQL  │  NSE LAMA API       │
│  Monitoring │  WebSocket   │  Network     │  (Config &   │  BSE LAMA API       │
│  Config     │  Auth (JWT)  │  Application │   Metadata)  │  MCX LAMA API       │
│  AI Probe   │  AI Probe    │  Database    │              │  NCDEX LAMA API     │
│  Alerts     │  CRUD APIs   │  Historical  │  ClickHouse  │                     │
│             │              │              │  (Time-Series│  Mimir/Prometheus   │
│  Nginx      │  Uvicorn     │  Prom Coll.  │   Metrics)   │  (Metric Source)    │
│  (Proxy)    │  (ASGI)      │  DB Coll.    │              │                     │
│             │              │              │  Redis 7     │  Slack / Email      │
│             │              │              │  (Hot Store  │  Android Push       │
│             │              │              │   & Cache)   │  (FCM)              │
└─────────────┴──────────────┴──────────────┴──────────────┴─────────────────────┘`} />
          <D title="Data Flow — End to End" diagram={`
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ DATA SOURCES │────▶│  SCHEDULERS  │────▶│  DATA STORES │────▶│   OUTPUTS    │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘

 Mimir (Cloud)        Hardware Sched.      PostgreSQL            LAMA Exchange API
 ├─ node_*            ├─ Every 5 min       ├─ server_status      ├─ NSE (601 OK)
 ├─ aws_ecs_*         ├─ Mimir-first       ├─ application_status ├─ BSE
 ├─ aws_rds_*         ├─ CW fallback       ├─ database_status    ├─ MCX
 │                    │                    ├─ metric_sources     └─ NCDEX
 Prometheus (DC/DR)   Network Sched.       ├─ exchange_txns
 ├─ node_*            ├─ Every 5 min       │                     Dashboards (UI)
 ├─ windows_*         ├─ Bandwidth/Pkt     ClickHouse            ├─ Servers
 │                    │                    ├─ server_metrics      ├─ App Monitoring
 Python Exporters     Application Sched.   ├─ hourly aggregates  ├─ DB Monitoring
 ├─ throughput_avg    ├─ Every 5 min       │                     ├─ Historical
 ├─ latency_avg       ├─ Prom/ES/CW        Redis                 └─ Raw Validation
 ├─ bandwidth_avg     │                    ├─ Hot store (live)
 ├─ db_status         Database Sched.      ├─ Token cache        Alerts
                      ├─ Every 5 min       └─ Session cache      ├─ Slack
                      ├─ RDS/MySQL/PG                            ├─ Email
                                                                 ├─ Android Push
                      Prom Collector                             └─ Voice Escalation
                      ├─ Every 2 min
                      ├─ ClickHouse write
                      └─ Alert checks`} />
        </Sec>

        <Sec icon="🐳" title="Docker Infrastructure" color="#0277bd">
          <MT headers={['Container', 'Image', 'Port', 'Purpose']} rows={[
            ['lama_nginx', 'React build + Nginx', '443/80', 'UI + Reverse proxy to API'],
            ['lama_api', 'Python 3.11 + FastAPI', '8000', 'REST API, WebSocket, Auth'],
            ['lama_scheduler', 'Python 3.11 + APScheduler', '-', 'All metric schedulers'],
            ['lama_postgres', 'PostgreSQL 15', '5432', 'Config, metadata, transactions'],
            ['lama_clickhouse', 'ClickHouse 23.8', '8123/9000', 'Time-series metrics (34M+ rows)'],
            ['lama_redis', 'Redis 7', '6379', 'Hot store, caching, pub/sub'],
            ['lama_piper', 'Wyoming Piper', '10200', 'TTS for voice alerts'],
          ]} />
        </Sec>

        <Sec icon="🔐" title="Security Architecture" color="#c62828">
          <Typography variant="body2" sx={{ mb: 1 }}>
            <strong>Authentication:</strong> AES-256 encrypted password transmission → JWT session tokens (configurable expiry)
          </Typography>
          <Typography variant="body2" sx={{ mb: 1 }}>
            <strong>Authorization:</strong> Role-based (admin/user) — admin required for config changes, source management, deletions
          </Typography>
          <Typography variant="body2" sx={{ mb: 1 }}>
            <strong>LAMA Exchange Auth:</strong> Per-exchange credentials (Member ID, Login ID, encrypted password, secret key) → Session token per exchange
          </Typography>
          <Typography variant="body2">
            <strong>Cross-Account AWS:</strong> IAM AssumeRole with SigV4 for Mimir/Prometheus auth
          </Typography>
        </Sec>
      </TabPanel>

      {/* TAB 1: AI Discovery */}
      <TabPanel value={tab} index={1}>
        <Alert severity="info" sx={{ mb: 2 }}>
          <strong>AI-Driven Discovery</strong> — LAMA automatically discovers AWS accounts, probes Mimir/Prometheus for available metrics,
          maps them to LAMA API keys, and lets you control exactly what gets collected and sent. Zero code changes required.
        </Alert>

        <Sec icon="🔍" title="End-to-End Discovery Flow" color="#7b1fa2" defaultExpanded>
          <D title="AI Discovery Pipeline" diagram={`
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    AI-DRIVEN SOURCE DISCOVERY                          │
  ├─────────────────────────────────────────────────────────────────────────┤
  │                                                                        │
  │  STEP 1: Configure Accounts                                           │
  │  ┌──────────────────────────────────────────────────────────┐         │
  │  │ Click "Accounts" → AI queries Mimir:                     │         │
  │  │   • aws_ecs_info ARNs → extract account IDs + clusters   │         │
  │  │   • aws_rds_info ARNs → extract account IDs + DB names   │         │
  │  │   • node_uname_info{account_id} → EC2 host counts        │         │
  │  │ Shows: Account ID | Name | EC2 count | ECS count | RDS   │         │
  │  │ User selects accounts → Saved to metric_sources config   │         │
  │  └──────────────────────────────────────────────────────────┘         │
  │                              ▼                                        │
  │  STEP 2: Scan Targets (filtered by selected accounts)                 │
  │  ┌──────────────────────────────────────────────────────────┐         │
  │  │ POST /v1/discover-targets {account_filter: [...]}        │         │
  │  │   • Queries Prometheus /api/v1/targets (up metric)       │         │
  │  │   • Resolves hostnames via node_uname_info               │         │
  │  │   • Detects resource_type: EC2 / ECS / RDS               │         │
  │  │   • Maps cluster → account via aws_ecs_info              │         │
  │  │   • Detects OS (Linux/Windows) and installed apps        │         │
  │  │ Shows: Name | Type | Account | Probe button              │         │
  │  └──────────────────────────────────────────────────────────┘         │
  │                              ▼                                        │
  │  STEP 3: AI Metric Probe (per target)                                 │
  │  ┌──────────────────────────────────────────────────────────┐         │
  │  │ POST /v1/probe-target-metrics                            │         │
  │  │                                                          │         │
  │  │ Phase 1: Sequential Label Discovery                      │         │
  │  │   Try labels: service_name, ecs_service_name, job,       │         │
  │  │   instance, instance_id, nodename                        │         │
  │  │   × patterns: exact name, short DNS, IP, dashed IP       │         │
  │  │   → Find first combo that returns data                   │         │
  │  │                                                          │         │
  │  │ Phase 2: Standard Metric Probes                          │         │
  │  │   Hardware: node_cpu_*, node_memory_*, node_filesystem_* │         │
  │  │   Network:  node_network_receive/transmit_bytes_total    │         │
  │  │   App:      http_requests_total, http_request_duration_* │         │
  │  │   Database: aws_rds_cpuutilization_average, etc.         │         │
  │  │                                                          │         │
  │  │ Phase 3: Custom LAMA Exporter Detection                  │         │
  │  │   throughput_avg, latency_avg, bandwidth_avg, db_status  │         │
  │  │   packetcount, lookupcount, db_qsize_avg, db_latency_avg │         │
  │  │                                                          │         │
  │  │ Returns per metric:                                      │         │
  │  │   ● node_cpu_seconds_total → LAMA: cpu (%) — 64 series  │         │
  │  │   ○ http_requests_total → LAMA: throughput — NOT FOUND   │         │
  │  └──────────────────────────────────────────────────────────┘         │
  │                              ▼                                        │
  │  STEP 4: Select & Onboard                                            │
  │  ┌──────────────────────────────────────────────────────────┐         │
  │  │ User checks: ✅ Hardware  ✅ Network  ☐ Application       │         │
  │  │ Click "Onboard" → POST /v1/onboard-discovered-servers    │         │
  │  │                                                          │         │
  │  │ EC2 → server_status + exchange_selection                 │         │
  │  │ ECS → application_status + metric_sources (with flags)   │         │
  │  │       + exchange_selection                               │         │
  │  │ RDS → database_status + database_config                  │         │
  │  │                                                          │         │
  │  │ Flags stored: send_hardware_metrics: true                │         │
  │  │               send_network_metrics: true                 │         │
  │  │               send_application_metrics: false            │         │
  │  └──────────────────────────────────────────────────────────┘         │
  │                              ▼                                        │
  │  AUTOMATIC (no user action needed):                                   │
  │  ┌──────────────────────────────────────────────────────────┐         │
  │  │ • Target appears on respective dashboard immediately     │         │
  │  │ • Next scheduler cycle (≤5 min) collects from Mimir      │         │
  │  │ • Writes to PostgreSQL (status), Redis (hot), CH (charts)│         │
  │  │ • Sends to LAMA Exchange API                             │         │
  │  │ • Threshold alerts fire if configured                    │         │
  │  │ • Raw Data Validation audit trail created                │         │
  │  └──────────────────────────────────────────────────────────┘         │
  └─────────────────────────────────────────────────────────────────────────┘`} />
        </Sec>

        <Sec icon="🎛️" title="Post-Onboarding Control" color="#00695c">
          <MT headers={['Action', 'Where', 'Effect']} rows={[
            ['Toggle HW/NET/APP flags', 'Data Sources → Scheduler Flags chips', 'Scheduler skips disabled categories'],
            ['Re-probe metrics', 'Prometheus Discovery → 🔍 Probe button', 'See current metric availability'],
            ['Enable/Disable source', 'Data Sources → Status toggle', 'Scheduler ignores disabled sources'],
            ['Move to PROD/UAT', 'Any monitoring dashboard → swap icon', 'All linked data moves together'],
            ['Delete target', 'Any monitoring dashboard → delete icon', 'Full cascade: status + sources + selection + ignore list'],
            ['Change accounts', 'Prometheus Discovery → Accounts button', 'Re-scan shows filtered targets'],
          ]} />
        </Sec>
      </TabPanel>

      {/* TAB 2: Schedulers */}
      <TabPanel value={tab} index={2}>
        <Sec icon="⚙️" title="Scheduler Architecture" color="#e65100" defaultExpanded>
          <D title="Scheduler Execution Flow" diagram={`
┌─────────────────────────────────────────────────────────────────────┐
│                    SCHEDULER EXECUTION CYCLE                        │
│                     (Every 5 minutes)                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. COLLECT ──────────────────────────────────────────────────────  │
│     │ Query metric_sources WHERE type='ecs' AND enabled=TRUE        │
│     │ Check send_*_metrics flags → skip if false                    │
│     │ For each target:                                              │
│     │   Priority 1: MimirCollector (sequential label discovery)     │
│     │   Priority 2: AWSCollector (CloudWatch fallback)              │
│     │   Priority 3: PrometheusCollector (LAMA Python exporters)     │
│     │   Fallback:   Zero-Filing Protocol (report 0.0)              │
│     ▼                                                               │
│  2. CALCULATE ───────────────────────────────────────────────────── │
│     │ Aggregate: min, max, avg, med from raw points                 │
│     │ Worst-case aggregation across fleet per location              │
│     │ Stage raw data → lama_prepared_metrics (audit trail)          │
│     ▼                                                               │
│  3. STORE ───────────────────────────────────────────────────────── │
│     │ PostgreSQL: Update *_status tables (dashboard values)         │
│     │ Redis: Update hot store (real-time display)                   │
│     │ ClickHouse: Write time-series points (charts)                 │
│     ▼                                                               │
│  4. ALERT ───────────────────────────────────────────────────────── │
│     │ check_and_create_alert() for each metric                      │
│     │ Compare against thresholds table                              │
│     │ If crossed → create alert → send_alert()                      │
│     │   → Slack + Email + Android Push + Voice Escalation           │
│     │ If normal → auto-resolve any active alerts                    │
│     ▼                                                               │
│  5. SEND TO LAMA EXCHANGE ───────────────────────────────────────── │
│     │ Get/refresh session token per exchange                        │
│     │ Build LAMA V1.2 payload with sequence ID                      │
│     │ POST to exchange API                                          │
│     │ Handle 601 (OK), 704 (seq mismatch → retry), 705 (dup)       │
│     │ Log to exchange_transactions                                  │
│     └─ Update staged results status                                 │
└─────────────────────────────────────────────────────────────────────┘`} />
          <MT headers={['Scheduler', 'Interval', 'Sources', 'Metrics Collected', 'Flag Check']} rows={[
            ['Hardware', '5 min', 'server_status + metric_sources(ecs)', 'cpu, memory, disk, uptime', 'send_hardware_metrics'],
            ['Network', '5 min', 'server_status + metric_sources(ecs)', 'bandwidth, packetCount', 'send_network_metrics'],
            ['Application', '5 min', 'metric_sources(ecs, prometheus_app, elasticsearch)', 'throughput, latency, failureTradeApi, failureAuth', 'send_application_metrics'],
            ['Database', '5 min', 'database_status + database_config', 'status, qSize, bandwidth, latency', 'database_config.enabled'],
            ['Historical App', '6 hours', 'metric_sources(ecs, prometheus_app)', '21-day historical throughput/latency', 'historical_precalculated flag'],
            ['Prom Collector', '2 min', 'server_status (on-prem)', 'All HW/NET metrics → ClickHouse + alerts', 'exchange_selection.enabled'],
            ['DB Collector', '2 min', 'database_config (on-prem)', 'status, qSize, bandwidth, latency → ClickHouse', 'database_config.enabled'],
          ]} />
        </Sec>

        <Sec icon="🔄" title="Sequence ID Management" color="#4a148c">
          <Typography variant="body2" sx={{ mb: 1 }}>
            Each exchange requires strictly incrementing sequence IDs per metric type. LAMA manages this via the <code>lama_sequence</code> table.
          </Typography>
          <D title="Sequence Flow" diagram={`
  get_next_sequence_id(env, exchange_id, metric_type)
    │
    ├─ Read current from lama_sequence table
    ├─ Increment by 1
    ├─ Send with payload
    │
    ├─ 601 (Success) → sequence confirmed
    ├─ 704 (Mismatch) → read expectedSequenceId from response
    │   └─ Retry with corrected sequence → update_sequence_cache_after_704()
    └─ 705 (Duplicate) → skip, already sent`} />
        </Sec>
      </TabPanel>

      {/* TAB 3: Metrics Spec */}
      <TabPanel value={tab} index={3}>
        <Alert severity="info" sx={{ mb: 2 }}>LAMA API Specification Version 1.2 — All metrics sent as batched payload with applicationId and metricData array.</Alert>

        <Sec icon="🖥️" title="Hardware Metrics" color="#1b5e20" defaultExpanded>
          <MT headers={['LAMA Key', 'Data Type', 'Mimir Source', 'Python Exporter', 'Unit']} rows={[
            ['cpu', '{ min, max, avg, med }', 'node_cpu_seconds_total (100-idle%)', '—', '% (0-100)'],
            ['memory', '{ min, max, avg, med }', '100*(1-MemAvailable/MemTotal)', '—', '% (0-100)'],
            ['disk', '{ min, max, avg, med }', 'max(1-avail/size) per partition', '—', '% (0-100)'],
            ['uptime', '{ min, max, avg, med }', '(time()-node_boot_time_seconds)/60', '—', 'minutes'],
          ]} />
        </Sec>

        <Sec icon="🌐" title="Network Metrics" color="#01579b">
          <MT headers={['LAMA Key', 'Data Type', 'Mimir Source', 'Python Exporter', 'Unit']} rows={[
            ['bandwidth', '{ min, max, avg, med }', '(rx+tx bytes/s) / speed * 100', 'bandwidth_avg/max/min/med', '% (0-100)'],
            ['packetCount', 'integer', 'node_network_receive_errs_total', 'packetcount', 'error count'],
          ]} />
        </Sec>

        <Sec icon="📱" title="Application Metrics" color="#4a148c">
          <MT headers={['LAMA Key', 'Data Type', 'Mimir Source', 'Python Exporter', 'Unit']} rows={[
            ['throughput', '{ min, max, avg, med }', 'rate(http_requests_total[5m])', 'throughput_avg/max/min/med', 'req/s'],
            ['latency', '{ min, max, avg, med }', 'histogram_quantile(0.95, http_request_duration_seconds_bucket)*1000', 'latency_avg/max/min/med', 'ms'],
            ['historicalThroughput', '{ min, max, avg, med }', '21-day avg from Prometheus recording rules', 'historicalThroughput_avg/max/min/med', 'req/s'],
            ['historicalLatency', '{ min, max, avg, med }', '21-day avg from Prometheus recording rules', 'historicalLatency_avg/max/min/med', 'ms'],
            ['failureTradeApi', 'integer', '—', 'failureTradeApi', 'count'],
            ['failureAuthentication', 'integer', '—', 'failureAuthentication', 'count'],
          ]} />
        </Sec>

        <Sec icon="🗄️" title="Database Metrics" color="#bf360c">
          <MT headers={['LAMA Key', 'Data Type', 'RDS Source (YACE)', 'MySQL Direct', 'Unit']} rows={[
            ['status', 'integer (1/0)', 'DBInstanceStatus', 'SELECT 1 + IO/SQL thread check', '1=Up, 0=Down'],
            ['qSize', '{ min, max, avg, med }', 'DatabaseConnections / ReplicaLag', 'Seconds_Behind_Master', 'count or seconds'],
            ['bandwidth', '{ min, max, avg, med }', 'CPUUtilization', '(Read_Pos-Exec_Pos)/1GB*100', '% (0-100)'],
            ['latency', '{ min, max, avg, med }', 'DiskQueueDepth / ReplicaLag*1000', 'Seconds_Behind*1000', 'ms'],
          ]} />
        </Sec>

        <Sec icon="📦" title="LAMA Exchange Payload Format" color="#263238">
          <D title="V1.2 Batched Payload Structure" diagram={`
  POST /api/V1/metrics/{metricType}
  Headers:
    Authorization: Bearer {sessionToken}
    Content-Type: application/json

  Body:
  {
    "memberId": "12345",
    "instanceId": "loc_3_hw",
    "sequenceId": 1042,
    "sentAt": "2026-04-09T10:30:00Z",
    "nseTimestamp": 1744183800000,
    "payload": [
      {
        "applicationId": -1,          // -1 = fleet aggregate
        "metricData": [
          { "key": "cpu",    "value": { "min": 12.5, "max": 78.3, "avg": 45.2, "med": 43.1 } },
          { "key": "memory", "value": { "min": 55.0, "max": 72.1, "avg": 63.4, "med": 62.8 } },
          { "key": "disk",   "value": { "min": 30.0, "max": 45.0, "avg": 37.5, "med": 36.2 } },
          { "key": "uptime", "value": { "min": 43200, "max": 43200, "avg": 43200, "med": 43200 } }
        ]
      }
    ]
  }

  Response Codes:
    601 → Success
    704 → Sequence mismatch (retry with expectedSequenceId)
    705 → Duplicate (already received)
    801 → Authentication failure`} />
        </Sec>
      </TabPanel>

      {/* TAB 4: Database Schema */}
      <TabPanel value={tab} index={4}>
        <Sec icon="🗄️" title="PostgreSQL Tables (37 tables)" color="#1565c0" defaultExpanded>
          <MT headers={['Table', 'Purpose', 'Key Columns', 'Used By']} rows={[
            ['server_status', 'EC2/physical server registry', 'id, name, ip, environment, os_type, location_id, source_id, external_id', 'Servers dashboard, Hardware/Network schedulers'],
            ['application_status', 'ECS/App service registry', 'id, name, environment, source_id, throughput, latency_ms, cpu, memory', 'App Monitoring dashboard, App scheduler'],
            ['database_status', 'RDS/DB registry', 'id, name, engine, environment, source_id, external_id', 'DB Monitoring dashboard, DB scheduler'],
            ['database_config', 'DB connection configs', 'host, port, username, password, db_type, is_replication, environment', 'DB scheduler (direct MySQL/PG connections)'],
            ['metric_sources', 'All data source configs', 'name, type, config(JSON), environment, enabled, location_id', 'All schedulers, AI probe, discovery'],
            ['metric_queries', 'ES/SQL queries per source', 'source_id, metric_name, query_payload, value_field', 'App scheduler (ES/SQL sources)'],
            ['lama_exchange_server_selection', 'Which servers send to exchange', 'environment, server_id, enabled, metric_source', 'All schedulers (JOIN filter)'],
            ['lama_exchange_config', 'Exchange enable/disable', 'exchange_id, environment, enabled', 'is_exchange_enabled() check'],
            ['lama_config', 'Exchange credentials', 'member_id, login_id, password(AES), secret_key, api_url', 'get_exchange_credentials()'],
            ['lama_sequence', 'Sequence IDs per exchange', 'exchange_id, metric_type, current_sequence', 'get_next_sequence_id()'],
            ['lama_tokens', 'Cached exchange session tokens', 'exchange_id, environment, token, expires_at', 'get_lama_exchange_token()'],
            ['lama_prepared_metrics', 'Staged metrics (audit trail)', 'environment, metric_type, raw_snapshot, calculated_stats, status', 'Raw Data Validation page'],
            ['exchange_transactions', 'Sent metric log (217K+ rows)', 'environment, metric_type, sequence_id, status_code, metrics_sent', 'Exchange Activity, validation'],
            ['alert_thresholds', 'Threshold rules', 'metric_type, metric_key, warning_threshold, error_threshold, enabled', 'check_threshold() in all schedulers'],
            ['alerts', 'Active/resolved alerts', 'server_id, alert_type, severity, message, is_resolved', 'Alert dashboard, send_alert()'],
            ['alert_config', 'Notification channels', 'channel(slack/email), config(JSON), enabled', 'send_email_alert(), send_slack_alert()'],
            ['users', 'User accounts', 'email, password_hash, role(admin/user)', 'JWT auth, role-based access'],
            ['scheduler_config', 'Scheduler intervals/toggles', 'job_id, interval_minutes, enabled', 'APScheduler configuration'],
            ['scheduler_logs', 'Scheduler execution logs (304K+)', 'scheduler_name, environment, status, duration_ms', 'Scheduler Logs page'],
            ['aws_ignore_list', 'Deleted AWS resources', 'external_id, resource_type', 'Prevents re-discovery on next scan'],
          ]} />
        </Sec>

        <Sec icon="📊" title="ClickHouse Tables" color="#ff6f00">
          <MT headers={['Table', 'Engine', 'Rows', 'TTL', 'Purpose']} rows={[
            ['lama.server_metrics', 'ReplacingMergeTree', '34.5M+', '30 days', 'Raw time-series: server_id, metric_name, value, ts'],
            ['lama.server_metrics_hourly', 'AggregatingMergeTree', '1M+', '730 days (2yr)', 'Hourly aggregates: min, max, sum, count'],
            ['lama.server_metrics_hourly_mv', 'Materialized View', '—', '—', 'Auto-aggregates raw → hourly'],
          ]} />
        </Sec>

        <Sec icon="⚡" title="metric_sources.config JSON Structure" color="#00695c">
          <D title="ECS Source Config (with AI flags)" diagram={`
  {
    "type": "ecs",
    "cluster": "smc-pre-trade-ecs-ec2",
    "service": "smc-pre-trade-algo-api-service",
    "account_id": "396913716058",
    "albArn": "arn:aws:elasticloadbalancing:...",
    "targetGroupArn": "arn:aws:elasticloadbalancing:...",
    "send_hardware_metrics": true,       ← Hardware scheduler checks this
    "send_network_metrics": true,        ← Network scheduler checks this
    "send_application_metrics": true,    ← App scheduler checks this
    "send_database_metrics": false       ← DB scheduler checks this
  }`} />
          <D title="Prometheus/Mimir Source Config (with allowed accounts)" diagram={`
  {
    "url": "http://10.236.26.167:9009",
    "use_iam": false,
    "role_arn": "",
    "region": "ap-south-1",
    "allowed_accounts": [
      { "account_id": "396913716058", "name": "SMC-PRE-TRADING-PROD" },
      { "account_id": "509399639526", "name": "SMC-TRADING-MIDDLEWARE-PROD" },
      { "account_id": "762233762082", "name": "SMC-TRADING-PROD" }
    ]
  }`} />
        </Sec>
      </TabPanel>

      {/* TAB 5: Alerts */}
      <TabPanel value={tab} index={5}>
        <Sec icon="🔔" title="Alert Pipeline" color="#c62828" defaultExpanded>
          <D title="Alert Flow — Threshold to Notification" diagram={`
  Scheduler collects metric value
          │
          ▼
  check_and_create_alert(server_id, metric_type, metric_key, value)
          │
          ├─ check_threshold() → query alert_thresholds table
          │   ├─ value >= error_threshold → severity = 'error' (🔴 CRITICAL)
          │   ├─ value >= warning_threshold → severity = 'warning' (⚠️ WARNING)
          │   └─ value < warning → resolve_alert_if_normal()
          │                         ├─ Mark alert is_resolved = true
          │                         └─ Stop active escalations
          │
          ├─ create_alert() → INSERT into alerts table
          │   ├─ Dedup: if same server+type already active, update severity
          │   └─ Format professional message with metric details
          │
          └─ send_alert(alert_id)
              │
              ├─ 📱 Mobile Escalation (Primary)
              │   └─ start_escalation() → background thread
              │       ├─ Push notification via FCM
              │       ├─ Voice call via Piper TTS + Wyoming
              │       └─ Escalation policy (retry, next contact)
              │
              ├─ 📧 Email (Secondary)
              │   └─ send_email_alert() → SMTP
              │
              ├─ 💬 Slack (Secondary)
              │   └─ send_slack_alert() → Webhook
              │
              └─ 🔄 WebSocket Broadcast
                  └─ broadcast_ui_update("new_alert") → live UI refresh`} />
          <MT headers={['Metric Type', 'Metrics Checked', 'Checked By']} rows={[
            ['hardware', 'cpu, memory, disk, uptime', 'hardware_scheduler + prom_metrics_collector'],
            ['network', 'bandwidth, packetCount', 'prom_metrics_collector (on-prem)'],
            ['application', 'throughput, latency, failureTradeApi, failureAuthentication', 'application_scheduler'],
            ['database', 'status, qSize, bandwidth, latency', 'database_scheduler + database_metrics_collector'],
          ]} />
        </Sec>
      </TabPanel>

      {/* TAB 6: Lifecycle */}
      <TabPanel value={tab} index={6}>
        <Sec icon="🔄" title="Resource Lifecycle — Add / Edit / Move / Delete" color="#2e7d32" defaultExpanded>
          <D title="Complete Lifecycle Automation" diagram={`
  ┌─────────────────────────────────────────────────────────────────────┐
  │                        RESOURCE LIFECYCLE                          │
  ├─────────────────────────────────────────────────────────────────────┤
  │                                                                     │
  │  ADD (AI Probe → Onboard)                                          │
  │  ┌───────────────────────────────────────────────────────────────┐ │
  │  │ EC2 → server_status + exchange_selection                      │ │
  │  │ ECS → application_status + metric_sources + exchange_selection │ │
  │  │ RDS → database_status + database_config                       │ │
  │  │ Auto: dashboard ✓ scheduler ✓ charts ✓ alerts ✓ LAMA API ✓   │ │
  │  └───────────────────────────────────────────────────────────────┘ │
  │                                                                     │
  │  EDIT (UI-controlled flags)                                        │
  │  ┌───────────────────────────────────────────────────────────────┐ │
  │  │ Toggle HW/NET/APP chips → PUT /metric-sources/{id}/metric-flags│ │
  │  │ Enable/Disable source → scheduler respects immediately        │ │
  │  │ Change exchange credentials → next cycle uses new creds       │ │
  │  │ Update thresholds → next metric check uses new values         │ │
  │  └───────────────────────────────────────────────────────────────┘ │
  │                                                                     │
  │  MOVE (UAT ↔ PROD)                                                │
  │  ┌───────────────────────────────────────────────────────────────┐ │
  │  │ Server:      server_status + exchange_selection               │ │
  │  │ Application: application_status + metric_sources + selection  │ │
  │  │ Database:    database_status + database_config                │ │
  │  │ Data Source: metric_sources + ALL linked status tables        │ │
  │  │ Target env scheduler picks up automatically                   │ │
  │  └───────────────────────────────────────────────────────────────┘ │
  │                                                                     │
  │  DELETE (Full Cascade)                                             │
  │  ┌───────────────────────────────────────────────────────────────┐ │
  │  │ Server:      server_status + exchange_selection + ignore list │ │
  │  │ Application: app_status + metric_sources + selection + ignore │ │
  │  │ Database:    db_status + db_config + ignore list              │ │
  │  │ Data Source: metric_sources + ALL linked tables (CASCADE)     │ │
  │  │ Scheduler stops collecting within 5 minutes                   │ │
  │  │ AWS ignore list prevents re-discovery on next scan            │ │
  │  └───────────────────────────────────────────────────────────────┘ │
  └─────────────────────────────────────────────────────────────────────┘`} />
        </Sec>

        <Sec icon="🌍" title="Environment Architecture" color="#1565c0">
          <D title="UAT / PROD Isolation" diagram={`
  ┌─────────────────────────┐     ┌─────────────────────────┐
  │       UAT ENVIRONMENT   │     │      PROD ENVIRONMENT   │
  ├─────────────────────────┤     ├─────────────────────────┤
  │ server_status (env=uat) │     │ server_status (env=prod)│
  │ application_status      │     │ application_status      │
  │ database_status         │     │ database_status         │
  │ metric_sources          │     │ metric_sources          │
  │ exchange_selection      │     │ exchange_selection      │
  │ lama_config (uat)       │     │ lama_config (prod)      │
  │ exchange_config (uat)   │     │ exchange_config (prod)  │
  │                         │     │                         │
  │ Schedulers filter by    │     │ Schedulers filter by    │
  │ environment = 'uat'     │     │ environment = 'prod'    │
  │                         │     │                         │
  │ Sends to UAT LAMA APIs  │     │ Sends to PROD LAMA APIs │
  │ (lama.uat.nseindia.com) │     │ (lama.nseindia.com)     │
  └────────────┬────────────┘     └────────────┬────────────┘
               │                                │
               │  "Clone All → PROD" button     │
               │  Individual "Move" buttons     │
               └────────────────────────────────┘`} />
        </Sec>

        <Sec icon="📋" title="API Reference Summary" color="#37474f">
          <MT headers={['Method', 'Endpoint', 'Purpose']} rows={[
            ['POST', '/v1/discover-targets', 'Discover targets from Prometheus/Mimir URL'],
            ['POST', '/v1/probe-target-metrics', 'AI probe: check metric availability per target'],
            ['POST', '/v1/onboard-discovered-servers', 'Onboard targets (EC2/ECS/RDS) with metric flags'],
            ['GET', '/v1/metric-sources/{id}/discover-accounts', 'Discover AWS accounts from Mimir'],
            ['PUT', '/v1/metric-sources/{id}/allowed-accounts', 'Set allowed accounts filter'],
            ['PUT', '/v1/metric-sources/{id}/metric-flags', 'Toggle HW/NET/APP/DB scheduler flags'],
            ['PUT', '/v1/metric-sources/{id}/environment', 'Move source + linked data between UAT/PROD'],
            ['PUT', '/v1/dashboard/application-monitoring/{id}/move', 'Move app between environments'],
            ['PUT', '/v1/dashboard/database-monitoring/{id}/move', 'Move database between environments'],
            ['POST', '/v1/servers/{id}/move', 'Move server between environments'],
            ['DELETE', '/v1/dashboard/application-monitoring/{id}', 'Delete app (cascades all linked data)'],
            ['DELETE', '/v1/dashboard/database-monitoring/{id}', 'Delete database (cascades all linked data)'],
            ['DELETE', '/v1/servers/{id}', 'Delete server (cascades + ignore list)'],
            ['GET', '/v1/raw-metrics-validation', '3-stage audit trail for sent metrics'],
          ]} />
        </Sec>
      </TabPanel>

      <Box sx={{ mt: 3, p: 2, bgcolor: '#f5f5f5', borderRadius: 2, textAlign: 'center' }}>
        <Typography variant="caption" color="textSecondary">
          SMC LAMA v2.0 — AI-Driven, Fully Automated, Environment-Aware Observability Platform
          <br />Last updated: April 2026 | API Spec: v1.2 | Built with React 18, FastAPI, PostgreSQL 15, ClickHouse, Redis 7
        </Typography>
      </Box>
    </Container>
  );
}
