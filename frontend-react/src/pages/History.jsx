import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  History as HistoryIcon, 
  Search, 
  Calendar, 
  Filter, 
  TrendingUp, 
  CheckCircle2, 
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  FileSpreadsheet
} from 'lucide-react';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';

const API_BASE = '/api';

const History = () => {
  const [summary, setSummary] = useState([]);
  const [metrics, setMetrics] = useState({ firing: 0, resolved: 0 });
  const [historyData, setHistoryData] = useState([]);
  const [detailedLogs, setDetailedLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [dateRange, setDateRange] = useState('24h');

  const fetchData = async () => {
    setLoading(true);
    try {
      // Calculate start date based on range
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

      const [summaryRes, metricsRes, historyRes] = await Promise.all([
        axios.get(`${API_BASE}/alerts/summary`, { params: { start_date: isoStartDate } }),
        axios.get(`${API_BASE}/metrics`, { params: { start_date: isoStartDate, status: 'all' } }),
        axios.get(`${API_BASE}/alerts/history`, { params: { days: days } })
      ]);
      
      setSummary(summaryRes.data);
      setMetrics(metricsRes.data);
      setDetailedLogs(metricsRes.data.recent_alerts || []);
      setHistoryData(historyRes.data);
    } catch (error) {
      console.error("Error fetching historical data:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [dateRange]);

  const filteredSummary = summary.filter(s => 
    (s.instance || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (s.alertname || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (s.company || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (s.group || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (s.group1 || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (s.asset || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (s.disk_info || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredLogs = detailedLogs.filter(l => 
    (l.instance || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (l.alertname || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (l.company || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (l.group_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (l.group1 || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (l.asset || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Real trend data for the chart
  const chartData = historyData.length > 0 ? historyData.map(d => ({
    time: d.date,
    firing: d.firing,
    resolved: d.resolved
  })) : [
    { time: 'No Data', firing: 0, resolved: 0 }
  ];

  return (
    <div className="space-y-6">
      {/* Header & Filter Controls */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500"></div>
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex items-center space-x-3">
            <div className="bg-emerald-600/20 p-2 rounded-lg text-emerald-400">
              <HistoryIcon size={24} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white uppercase tracking-wider">Historical Intelligence</h2>
              <p className="text-xs text-slate-500 mt-0.5">Aggregate performance metrics and incident resolution summary</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="bg-slate-950 border border-slate-800 rounded-lg p-1 flex">
              {['24h', '7d', '30d'].map(range => (
                <button
                  key={range}
                  onClick={() => setDateRange(range)}
                  className={`px-4 py-1.5 rounded-md text-xs font-bold transition-all ${
                    dateRange === range ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/20' : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {range.toUpperCase()}
                </button>
              ))}
            </div>
            
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={14} />
              <input 
                type="text" 
                placeholder="Filter history..." 
                className="bg-slate-950 border border-slate-800 rounded-lg py-2 pl-9 pr-4 text-sm focus:outline-none focus:border-indigo-500 transition-colors w-full md:w-48 text-white"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>

            <button 
              onClick={() => window.open(`${API_BASE}/alerts/export?start_date=${new Date(Date.now() - 86400000).toISOString()}`, '_blank')}
              className="bg-slate-800 p-2.5 rounded-lg text-slate-300 hover:text-emerald-400 hover:bg-slate-700 transition-all border border-slate-700 flex items-center space-x-2"
              title="Export CSV"
            >
              <FileSpreadsheet size={16} />
              <span className="text-xs font-bold uppercase">Export Detailed</span>
            </button>
          </div>
        </div>
      </div>

      {/* Analytics Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6 h-[300px]">
          <h3 className="text-white font-semibold mb-6 flex items-center space-x-2">
            <TrendingUp size={18} className="text-indigo-400" />
            <span>Resolution Velocity</span>
          </h3>
          <div className="h-[200px] w-full">
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

      {/* Summary Inventory */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
        <div className="p-6 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
          <h3 className="text-white font-bold flex items-center space-x-2">
            <Filter size={18} className="text-indigo-400" />
            <span>Incident Frequency Analysis</span>
          </h3>
          {loading && <RefreshCw size={16} className="text-indigo-400 animate-spin" />}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-950/50 text-slate-500 text-[10px] uppercase tracking-widest font-black">
                <th className="px-6 py-4">Instance / IP</th>
                <th className="px-6 py-4">Alert Definition</th>
                <th className="px-6 py-4">Labels</th>
                <th className="px-6 py-4">Ownership</th>
                <th className="px-6 py-4 text-center">Firing</th>
                <th className="px-6 py-4 text-center">Resolved</th>
                <th className="px-6 py-4">Efficiency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {filteredSummary.map((item, idx) => {
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
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-1">
                        {item.group && <span className="px-1.5 py-0.5 bg-slate-800 text-slate-400 text-[9px] rounded uppercase border border-slate-700">{item.group}</span>}
                        {item.group1 && <span className="px-1.5 py-0.5 bg-indigo-900/30 text-indigo-400 text-[9px] rounded uppercase border border-indigo-500/20">{item.group1}</span>}
                        {item.asset && <span className="px-1.5 py-0.5 bg-emerald-900/30 text-emerald-400 text-[9px] rounded uppercase border border-emerald-500/20">{item.asset}</span>}
                        {item.disk_info && <span className="px-1.5 py-0.5 bg-amber-900/30 text-amber-400 text-[9px] rounded uppercase border border-amber-500/20">{item.disk_info}</span>}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-400">
                      {item.company || '--'}
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
                    <td className="px-6 py-4 min-w-[150px]">
                      <div className="flex items-center space-x-3">
                        <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]" 
                            style={{ width: `${ratio}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-bold text-slate-500 w-8">{Math.round(ratio)}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filteredSummary.length === 0 && !loading && (
                <tr>
                  <td colSpan="6" className="px-6 py-12 text-center text-slate-600">
                    No historical records matching the current parameters
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detailed Incident Logs */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
        <div className="p-6 border-b border-slate-800 bg-slate-900/50 flex items-center justify-between">
          <h3 className="text-white font-bold flex items-center space-x-2">
            <HistoryIcon size={18} className="text-emerald-400" />
            <span>Detailed Incident Timeline</span>
          </h3>
          <span className="text-[10px] font-bold bg-slate-800 px-2 py-1 rounded text-slate-500 uppercase tracking-widest">
            Last {filteredLogs.length} Events
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-950/50 text-slate-500 text-[10px] uppercase tracking-widest font-black">
                <th className="px-6 py-4">Alert Name / Instance</th>
                <th className="px-6 py-4">Labels</th>
                <th className="px-6 py-4">Disk Info</th>
                <th className="px-6 py-4">Asset</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Firing Time</th>
                <th className="px-6 py-4">Resolved Time</th>
                <th className="px-6 py-4">Ack By</th>
                <th className="px-6 py-4">Comments</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {filteredLogs.map((log, idx) => (
                <tr key={idx} className="hover:bg-slate-800/30 transition-all text-xs">
                  <td className="px-6 py-4">
                    <div className="flex flex-col">
                      <span className="font-bold text-white">{log.alertname}</span>
                      <span className="text-slate-500 font-mono">{log.instance}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {log.company && <span className="px-1 text-slate-400 border border-slate-700 rounded text-[9px]">{log.company}</span>}
                      {log.group_name && <span className="px-1 text-indigo-400 border border-indigo-900/50 rounded text-[9px]">{log.group_name}</span>}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-slate-400">
                    {log.disk_info || '--'}
                  </td>
                  <td className="px-6 py-4 text-slate-400">
                    {log.asset || '--'}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                      log.status === 'firing' ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20' : 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                    }`}>
                      {log.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 font-mono text-slate-400">
                    {log.status === 'resolved' ? '--' : (log.starts_at ? new Date(log.starts_at).toLocaleString('en-IN') : new Date(log.received_at).toLocaleString('en-IN'))}
                  </td>
                  <td className="px-6 py-4 font-mono text-slate-400">
                    {log.ends_at && log.status === 'resolved' ? new Date(log.ends_at).toLocaleString('en-IN') : '--'}
                  </td>
                  <td className="px-6 py-4 text-slate-400">
                    {log.acknowledged_by_user ? (
                      <div className="flex items-center space-x-1 text-emerald-400">
                        <CheckCircle2 size={14} />
                        <span>{log.acknowledged_by_user.name}</span>
                      </div>
                    ) : (
                      <span className="text-slate-600">--</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col space-y-2">
                      {log.comments && log.comments.map(c => (
                        <div key={c.id} className="bg-slate-800 p-2 rounded text-slate-300 relative group">
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
                      <button 
                        onClick={() => {
                          const content = prompt("Add a comment:");
                          if (content) {
                            axios.post(`${API_BASE}/alerts/${log.id}/comments`, { content }).then(fetchData);
                          }
                        }}
                        className="text-[10px] text-indigo-400 hover:text-indigo-300 font-bold uppercase tracking-widest flex items-center space-x-1"
                      >
                        <span>+ Add Comment</span>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredLogs.length === 0 && !loading && (
                <tr>
                  <td colSpan="7" className="px-6 py-12 text-center text-slate-600">
                    No detailed logs found for the selected period
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default History;
