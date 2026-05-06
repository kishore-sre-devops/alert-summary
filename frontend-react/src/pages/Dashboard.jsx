import logo from '../assets/logo.png';
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  AlertTriangle, 
  ShieldAlert, 
  CheckCircle2, 
  Activity, 
  Clock, 
  ExternalLink,
  Search,
  TrendingUp,
  BarChart3,
  History as HistoryIcon,
  Filter,
  FileSpreadsheet,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';
import StatCard from '../components/StatCard';
import DashboardCharts from '../components/DashboardCharts';

const API_BASE = '/api';

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('overview'); // 'overview', 'history', 'summary'
  const [alerts, setAlerts] = useState([]);
  const [servers, setServers] = useState([]);
  const [metrics, setMetrics] = useState({ firing: 0, resolved: 0 });
  const [searchTerm, setSearchTerm] = useState('');
  
  // Historical state
  const [historySummary, setHistorySummary] = useState([]);
  const [historyData, setHistoryData] = useState([]);
  const [dateRange, setDateRange] = useState('24h');
  const [loading, setLoading] = useState(false);

  const fetchData = async () => {
    try {
      const [alertsRes, serversRes, metricsRes] = await Promise.all([
        axios.get(`${API_BASE}/alert-state`),
        axios.get(`${API_BASE}/prometheus-servers`),
        axios.get(`${API_BASE}/metrics`)
      ]);
      setAlerts(alertsRes.data);
      setServers(serversRes.data);
      setMetrics(metricsRes.data);
    } catch (error) {
      console.error("Error fetching dashboard data:", error);
    }
  };

  const fetchHistory = async () => {
    setLoading(true);
    try {
      let startDate = new Date();
      let days = 1;
      if (dateRange === '24h') {
          startDate.setHours(startDate.getHours() - 24);
          days = 1;
      }
      else if (dateRange === '7d') {
          startDate.setDate(startDate.getDate() - 7);
          days = 7;
      }
      else if (dateRange === '30d') {
          startDate.setDate(startDate.getDate() - 30);
          days = 30;
      }
      
      const isoStartDate = startDate.toISOString();

      const [summaryRes, historyRes] = await Promise.all([
        axios.get(`${API_BASE}/alerts/summary`, { params: { start_date: isoStartDate } }),
        axios.get(`${API_BASE}/alerts/history`, { params: { days: days } })
      ]);
      
      setHistorySummary(summaryRes.data);
      setHistoryData(historyRes.data);
    } catch (error) {
      console.error("Error fetching historical data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activeTab === 'history' || activeTab === 'summary') {
      fetchHistory();
    }
  }, [activeTab, dateRange]);

  // Process data for charts
  const getSeverityData = () => {
    const counts = alerts.reduce((acc, alert) => {
      const sev = alert.severity?.toLowerCase() || 'warning';
      acc[sev] = (acc[sev] || 0) + 1;
      return acc;
    }, {});
    
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  };

  const getInstanceData = () => {
    const counts = alerts.reduce((acc, alert) => {
      acc[alert.instance] = (acc[alert.instance] || 0) + 1;
      return acc;
    }, {});
    
    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);
  };

  const getAlertNameData = () => {
    const counts = alerts.reduce((acc, alert) => {
      acc[alert.alert_name] = (acc[alert.alert_name] || 0) + 1;
      return acc;
    }, {});
    
    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);
  };

  const getClusterLink = (clusterName) => {
    const server = servers.find(s => s.name === clusterName);
    if (server) {
      return (
        <a href={server.url} target="_blank" rel="noopener noreferrer" className="flex items-center space-x-1 text-indigo-400 hover:text-indigo-300">
          <span>{clusterName}</span>
          <ExternalLink size={12} />
        </a>
      );
    }
    return clusterName;
  };

  const filteredAlerts = alerts.filter(alert => 
    alert.alert_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    alert.instance.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (alert.group_name || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredHistorySummary = historySummary.filter(s => 
    (s.instance || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (s.alertname || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  const criticalCount = alerts.filter(a => a.severity?.toLowerCase() === 'critical').length;
  const warningCount = alerts.filter(a => a.severity?.toLowerCase() !== 'critical').length;

  const chartData = historyData.length > 0 ? historyData.map(d => ({
    time: d.date,
    firing: d.firing,
    resolved: d.resolved
  })) : [
    { time: 'No Data', firing: 0, resolved: 0 }
  ];

  return (
    <div className="space-y-6">
      {/* Management Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
        <div className="flex items-center space-x-4">
          <img src={logo} alt="SMC Logo" className="h-12 w-12 object-contain" />
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Executive Dashboard</h1>
            <p className="text-sm text-slate-400 mt-1">High-level infrastructure health and incident response summary.</p>
          </div>
        </div>
        <div className="mt-4 md:mt-0 flex flex-col items-end">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">System Health Score</span>
          <div className="flex items-end space-x-2 mt-1">
            <span className={`text-3xl font-black ${criticalCount > 0 ? 'text-rose-500' : (warningCount > 0 ? 'text-amber-500' : 'text-emerald-500')}`}>
              {criticalCount > 0 ? Math.max(0, 100 - (criticalCount * 5)) : (warningCount > 0 ? Math.max(80, 100 - warningCount) : 100)}%
            </span>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex items-center space-x-1 bg-slate-900/50 p-1 rounded-xl border border-slate-800 w-fit">
        <button 
          onClick={() => setActiveTab('overview')}
          className={`px-6 py-2 rounded-lg text-sm font-bold flex items-center space-x-2 transition-all ${activeTab === 'overview' ? 'bg-indigo-600 text-white shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}
        >
          <BarChart3 size={18} />
          <span>Overview</span>
        </button>
        <button 
          onClick={() => setActiveTab('history')}
          className={`px-6 py-2 rounded-lg text-sm font-bold flex items-center space-x-2 transition-all ${activeTab === 'history' ? 'bg-indigo-600 text-white shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}
        >
          <HistoryIcon size={18} />
          <span>Historical Data</span>
        </button>
        <button 
          onClick={() => setActiveTab('summary')}
          className={`px-6 py-2 rounded-lg text-sm font-bold flex items-center space-x-2 transition-all ${activeTab === 'summary' ? 'bg-indigo-600 text-white shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}
        >
          <Filter size={18} />
          <span>Alert Summary</span>
        </button>
      </div>

      {activeTab === 'overview' && (
        <>
          {/* Metrics Row */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard 
              title="Active Alerts" 
              value={alerts.length} 
              icon={Activity} 
              colorClass="bg-indigo-500"
            />
            <StatCard 
              title="Critical Issues" 
              value={criticalCount} 
              icon={ShieldAlert} 
              colorClass="bg-rose-500"
              trend={criticalCount > 0 ? `+${criticalCount}` : null}
            />
            <StatCard 
              title="Warnings" 
              value={warningCount} 
              icon={AlertTriangle} 
              colorClass="bg-amber-500"
            />
            <StatCard 
              title="Resolved (Total)" 
              value={metrics.resolved || 0} 
              icon={CheckCircle2} 
              colorClass="bg-emerald-500"
            />
          </div>

          {/* Charts Row */}
          <DashboardCharts 
            instanceData={getInstanceData()} 
            severityData={getSeverityData()} 
            alertNameData={getAlertNameData()}
          />

          {/* Alert List Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="p-6 border-b border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <h3 className="text-white font-semibold flex items-center space-x-2">
                <Clock size={18} className="text-indigo-400" />
                <span>Active Incident Log</span>
              </h3>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                <input 
                  type="text" 
                  placeholder="Filter active alerts..." 
                  className="bg-slate-950 border border-slate-800 rounded-lg py-2 pl-10 pr-4 text-sm focus:outline-none focus:border-indigo-500 transition-colors w-full md:w-64"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </div>
            
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-950/50 text-slate-500 text-xs uppercase tracking-wider">
                    <th className="px-6 py-4 font-semibold">Incident Details</th>
                    <th className="px-6 py-4 font-semibold">Instance IP</th>
                    <th className="px-6 py-4 font-semibold">Source Cluster</th>
                    <th className="px-6 py-4 font-semibold">Severity</th>
                    <th className="px-6 py-4 font-semibold">Duration</th>
                    <th className="px-6 py-4 font-semibold">Detected At</th>
                    <th className="px-6 py-4 font-semibold">Ack By</th>
                    <th className="px-6 py-4 font-semibold">Comments</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {filteredAlerts.map(alert => (
                    <tr key={alert.id} className="hover:bg-slate-800/30 transition-colors group">
                      <td className="px-6 py-4">
                        <div className="flex flex-col">
                          <span className="text-white font-medium group-hover:text-indigo-300 transition-colors">
                            {alert.alert_name}
                          </span>
                          <span className="text-xs text-slate-500">{alert.group_name || 'System Default'}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <code className="text-xs bg-slate-800 px-2 py-1 rounded border border-slate-700 text-slate-300">
                          {alert.instance}
                        </code>
                      </td>
                      <td className="px-6 py-4 text-sm">
                        {getClusterLink(alert.cluster)}
                      </td>
                      <td className="px-6 py-4">
                        <span className={`
                          inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border
                          ${alert.severity?.toLowerCase() === 'critical' 
                            ? 'bg-rose-500/10 text-rose-400 border-rose-500/20 animate-pulse-red' 
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                          }
                        `}>
                          {alert.severity || 'warning'}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {Math.floor((new Date() - new Date(alert.starts_at)) / 60000)}m
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-500">
                        {new Date(alert.starts_at).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-400">
                        {alert.acknowledged_by_user ? (
                          <div className="flex items-center space-x-1 text-emerald-400">
                            <CheckCircle2 size={14} />
                            <span>{alert.acknowledged_by_user.name}</span>
                          </div>
                        ) : (
                          <span className="text-slate-600">--</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex flex-col space-y-2">
                          {alert.comments && alert.comments.map(c => (
                            <div key={c.id} className="bg-slate-800 p-2 rounded text-slate-300 text-xs relative group">
                               <p>{c.content}</p>
                               <button 
                                 onClick={() => {
                                   const newContent = prompt("Edit comment:", c.content);
                                   if (newContent && newContent !== c.content) {
                                     axios.put(`${API_BASE}/comments/${c.id}`, { content: newContent }).then(fetchData);
                                   }
                                 }}
                                 className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 text-indigo-400 hover:text-indigo-300"
                               >
                                 Edit
                               </button>
                            </div>
                          ))}
                          {alert.alert_id && (
                            <button 
                              onClick={() => {
                                const content = prompt("Add a comment:");
                                if (content) {
                                  axios.post(`${API_BASE}/alerts/${alert.alert_id}/comments`, { content }).then(fetchData);
                                }
                              }}
                              className="text-[10px] text-indigo-400 hover:text-indigo-300 font-bold uppercase tracking-widest flex items-center space-x-1"
                            >
                              <span>+ Add Comment</span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {activeTab === 'history' && (
        <div className="space-y-6 animate-in fade-in duration-500">
          <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900 p-6 rounded-xl border border-slate-800 shadow-xl">
             <div className="flex items-center space-x-3">
                <div className="bg-indigo-600/20 p-2 rounded-lg text-indigo-400">
                  <TrendingUp size={24} />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white uppercase tracking-wider">Historical Trend</h2>
                  <p className="text-xs text-slate-500 mt-0.5">Visualization of incident frequency over time</p>
                </div>
              </div>

              <div className="flex items-center space-x-3">
                <div className="bg-slate-950 border border-slate-800 rounded-lg p-1 flex">
                  {['24h', '7d', '30d'].map(range => (
                    <button
                      key={range}
                      onClick={() => setDateRange(range)}
                      className={`px-4 py-1.5 rounded-md text-xs font-bold transition-all ${
                        dateRange === range ? 'bg-indigo-600 text-white' : 'text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      {range.toUpperCase()}
                    </button>
                  ))}
                </div>
                <button 
                  onClick={() => window.open(`${API_BASE}/alerts/summary/export?start_date=${new Date(Date.now() - 86400000).toISOString()}`, '_blank')}
                  className="bg-slate-800 p-2.5 rounded-lg text-slate-300 hover:text-emerald-400 hover:bg-slate-700 transition-all border border-slate-700 flex items-center space-x-2"
                >
                  <FileSpreadsheet size={16} />
                  <span className="text-xs font-bold">EXPORT</span>
                </button>
              </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6 h-[400px]">
              <div className="h-full w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="colorFiring" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#f43f5e" stopOpacity={0}/>
                      </linearGradient>
                      <linearGradient id="colorResolved" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="time" stroke="#64748b" fontSize={10} />
                    <YAxis stroke="#64748b" fontSize={10} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                      itemStyle={{ fontSize: '12px' }}
                    />
                    <Area type="monotone" dataKey="firing" stroke="#f43f5e" fillOpacity={1} fill="url(#colorFiring)" name="Firing" />
                    <Area type="monotone" dataKey="resolved" stroke="#10b981" fillOpacity={1} fill="url(#colorResolved)" name="Resolved" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="flex flex-col gap-4">
               <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col justify-between">
                <div className="flex justify-between items-start">
                  <div className="bg-rose-500/10 p-2 rounded-lg text-rose-400">
                    <AlertTriangle size={20} />
                  </div>
                  <div className="flex items-center text-rose-400 text-xs font-bold">
                    <ArrowUpRight size={14} />
                    <span>ACTIVE</span>
                  </div>
                </div>
                <div>
                  <p className="text-slate-500 text-xs font-bold uppercase tracking-widest">Total Firing</p>
                  <h4 className="text-3xl font-black text-white tabular-nums">{metrics.firing}</h4>
                </div>
              </div>

              <div className="flex-1 bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col justify-between">
                <div className="flex justify-between items-start">
                  <div className="bg-emerald-500/10 p-2 rounded-lg text-emerald-400">
                    <CheckCircle2 size={20} />
                  </div>
                  <div className="flex items-center text-emerald-400 text-xs font-bold">
                    <ArrowDownRight size={14} />
                    <span>ARCHIVED</span>
                  </div>
                </div>
                <div>
                  <p className="text-slate-500 text-xs font-bold uppercase tracking-widest">Total Resolved</p>
                  <h4 className="text-3xl font-black text-white tabular-nums">{metrics.resolved}</h4>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'summary' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl animate-in slide-in-from-bottom-4 duration-500">
          <div className="p-6 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
            <h3 className="text-white font-bold flex items-center space-x-2">
              <Filter size={18} className="text-indigo-400" />
              <span>Incident Frequency Analysis</span>
            </h3>
            <div className="flex items-center space-x-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={14} />
                <input 
                  type="text" 
                  placeholder="Filter summary..." 
                  className="bg-slate-950 border border-slate-800 rounded-lg py-1.5 pl-9 pr-4 text-sm focus:outline-none focus:border-indigo-500 transition-colors w-48 text-white"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
              {loading && <RefreshCw size={16} className="text-indigo-400 animate-spin" />}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-950/50 text-slate-500 text-[10px] uppercase tracking-widest font-black">
                  <th className="px-6 py-4">Instance / IP</th>
                  <th className="px-6 py-4">Alert Definition</th>
                  <th className="px-6 py-4 text-center">Firing</th>
                  <th className="px-6 py-4 text-center">Resolved</th>
                  <th className="px-6 py-4">Efficiency Ratio</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {filteredHistorySummary.map((item, idx) => {
                  const total = item.firing + item.resolved;
                  const ratio = total > 0 ? (item.resolved / total) * 100 : 0;
                  
                  return (
                    <tr key={idx} className="hover:bg-slate-800/30 transition-all">
                      <td className="px-6 py-4 font-mono text-xs text-slate-300">
                        {item.instance}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex flex-col">
                          <span className="text-sm font-bold text-white">{item.alertname}</span>
                          <span className="text-[10px] text-slate-500 uppercase">{item.job}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className={`text-sm font-bold ${item.firing > 0 ? 'text-rose-400' : 'text-slate-600'}`}>
                          {item.firing}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className={`text-sm font-bold ${item.resolved > 0 ? 'text-emerald-400' : 'text-slate-600'}`}>
                          {item.resolved}
                        </span>
                      </td>
                      <td className="px-6 py-4 min-w-[200px]">
                        <div className="flex items-center space-x-3">
                          <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-emerald-500" 
                              style={{ width: `${ratio}%` }}
                            />
                          </div>
                          <span className="text-[10px] font-bold text-slate-500 w-8">{Math.round(ratio)}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
