import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  Target, 
  Search, 
  ExternalLink, 
  Clock, 
  Server, 
  Building2, 
  Users,
  Box,
  RefreshCw
} from 'lucide-react';

const API_BASE = '/api';

const Targets = () => {
  const [targets, setTargets] = useState([]);
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');

  const fetchData = async () => {
    setLoading(true);
    try {
      const [targetsRes, serversRes] = await Promise.all([
        axios.get(`${API_BASE}/prometheus-targets`),
        axios.get(`${API_BASE}/prometheus-servers`)
      ]);
      setTargets(targetsRes.data);
      setServers(serversRes.data);
    } catch (error) {
      console.error("Error fetching targets:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const getServerName = (serverId) => {
    const server = servers.find(s => s.id === serverId);
    return server ? server.name : `Server #${serverId}`;
  };

  const filteredTargets = targets.filter(t => 
    t.instance.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (t.job || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (t.company || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (t.group_name || '').toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="bg-indigo-600/20 p-2 rounded-lg text-indigo-400">
              <Target size={24} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white uppercase tracking-wider">Infrastructure Targets</h2>
              <p className="text-xs text-slate-500 mt-0.5">Inventory of all discovered instances from Prometheus sources</p>
            </div>
          </div>
          
          <div className="flex items-center space-x-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
              <input 
                type="text" 
                placeholder="Search targets, jobs, groups..." 
                className="bg-slate-950 border border-slate-800 rounded-lg py-2 pl-10 pr-4 text-sm focus:outline-none focus:border-indigo-500 transition-colors w-full md:w-64 text-white"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <button 
              onClick={fetchData} 
              className="bg-slate-800 p-2.5 rounded-lg text-slate-400 hover:text-indigo-400 hover:bg-slate-700 transition-all border border-slate-700"
              title="Refresh Inventory"
            >
              <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-950/50 text-slate-500 text-xs uppercase tracking-wider">
                <th className="px-6 py-4 font-semibold">Instance</th>
                <th className="px-6 py-4 font-semibold">Job / Group</th>
                <th className="px-6 py-4 font-semibold">Company</th>
                <th className="px-6 py-4 font-semibold">Asset</th>
                <th className="px-6 py-4 font-semibold">Source Server</th>
                <th className="px-6 py-4 font-semibold">Last Discovery</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {filteredTargets.map(target => (
                <tr key={target.id} className="hover:bg-slate-800/30 transition-all group">
                  <td className="px-6 py-4">
                    <div className="flex items-center space-x-3">
                      <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]"></div>
                      <code className="text-sm font-mono text-white bg-slate-800/50 px-2 py-1 rounded border border-slate-700">
                        {target.instance}
                      </code>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col">
                      <div className="flex items-center space-x-2 text-indigo-300">
                        <Box size={14} className="text-slate-600" />
                        <span className="font-medium">{target.job || 'default'}</span>
                      </div>
                      <div className="flex items-center space-x-2 text-xs text-slate-500 mt-1">
                        <Users size={12} className="text-slate-700" />
                        <span>{target.group_name || 'Unassigned'}</span>
                        {target.group1 && (
                          <>
                            <span className="text-slate-700">•</span>
                            <span>{target.group1}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center space-x-2 text-slate-300">
                      <Building2 size={16} className="text-slate-600" />
                      <span className="text-sm">{(!target.company || target.company.toLowerCase() === 'unknown') ? '' : target.company}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-sm text-slate-400 font-medium">{target.asset || ''}</span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center space-x-2 text-slate-400">
                      <Server size={14} className="text-slate-600" />
                      <span className="text-xs font-medium uppercase tracking-tight">{getServerName(target.server_id)}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-xs text-slate-500">
                    <div className="flex items-center space-x-2">
                      <Clock size={12} />
                      <span>{new Date(target.last_seen).toLocaleString()}</span>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredTargets.length === 0 && !loading && (
                <tr>
                  <td colSpan="5" className="px-6 py-12 text-center">
                    <div className="flex flex-col items-center justify-center text-slate-600">
                      <Target size={48} className="mb-2 text-slate-800 opacity-20" />
                      <p>No infrastructure targets found</p>
                    </div>
                  </td>
                </tr>
              )}
              {loading && (
                <tr>
                  <td colSpan="5" className="px-6 py-12 text-center">
                    <div className="flex flex-col items-center justify-center text-indigo-500">
                      <RefreshCw size={32} className="animate-spin mb-2" />
                      <p className="text-sm">Scanning infrastructure topology...</p>
                    </div>
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

export default Targets;
