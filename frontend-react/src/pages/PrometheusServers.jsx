import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Server, Plus, RefreshCw, Trash2, ExternalLink, Activity, CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

const API_BASE = '/api';

const PrometheusServers = () => {
  const [servers, setServers] = useState([]);
  const [newServer, setNewServer] = useState({ name: '', url: '' });
  const [message, setMessage] = useState({ text: '', type: '' });

  const fetchServers = async () => {
    try {
      const response = await axios.get(`${API_BASE}/prometheus-servers`);
      setServers(response.data);
    } catch (error) {
      console.error("Error fetching servers:", error);
    }
  };

  useEffect(() => { fetchServers(); }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API_BASE}/prometheus-servers`, newServer);
      setNewServer({ name: '', url: '' });
      setMessage({ text: 'Infrastructure target added successfully', type: 'success' });
      fetchServers();
    } catch (error) {
      console.error("Error adding server:", error);
      setMessage({ text: 'Failed to register infrastructure target', type: 'error' });
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to delete this infrastructure target?")) return;
    try {
      await axios.delete(`${API_BASE}/prometheus-servers/${id}`);
      setMessage({ text: 'Infrastructure target removed', type: 'success' });
      fetchServers();
    } catch (error) {
      console.error("Error deleting server:", error);
      setMessage({ text: 'Failed to remove infrastructure target', type: 'error' });
    }
  };

  const handleSyncGroups = async (id) => {
    setMessage({ text: 'Synchronizing target groups...', type: 'info' });
    try {
      const response = await axios.post(`${API_BASE}/prometheus-servers/${id}/sync-groups`);
      setMessage({ text: response.data.message, type: 'success' });
    } catch (error) {
      console.error("Error syncing groups:", error);
      setMessage({ text: error.response?.data?.detail || 'Group synchronization failed', type: 'error' });
    }
  };

  const handleSyncRules = async (id) => {
    setMessage({ text: 'Synchronizing alert rules...', type: 'info' });
    try {
      const response = await axios.post(`${API_BASE}/prometheus-servers/${id}/sync-rules`);
      setMessage({ text: response.data.message, type: 'success' });
    } catch (error) {
      console.error("Error syncing rules:", error);
      setMessage({ text: error.response?.data?.detail || 'Rule synchronization failed', type: 'error' });
    }
  };

  return (
    <div className="space-y-6">
      {message.text && (
        <div className={`
          p-4 rounded-xl shadow-lg flex items-center justify-between border animate-in fade-in slide-in-from-top-4 duration-300
          ${message.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 
            message.type === 'error' ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : 
            'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
          }
        `}>
          <div className="flex items-center space-x-3">
            {message.type === 'success' ? <CheckCircle2 size={20} /> : 
             message.type === 'error' ? <AlertCircle size={20} /> : <Info size={20} />}
            <span className="text-sm font-medium">{message.text}</span>
          </div>
          <button onClick={() => setMessage({text: '', type: ''})} className="p-1 hover:bg-white/5 rounded-lg transition-colors">
            <X size={18} />
          </button>
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
        <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
          <Plus size={20} className="text-indigo-400" />
          <span>Register Infrastructure Target</span>
        </h2>
        
        <form onSubmit={handleAdd} className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 space-y-1">
            <label className="text-xs font-semibold text-slate-500 uppercase">Provider Name</label>
            <input
              type="text"
              placeholder="e.g. AWS Production"
              className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-white focus:border-indigo-500 outline-none transition-colors"
              value={newServer.name}
              onChange={e => setNewServer({...newServer, name: e.target.value})}
              required
            />
          </div>
          <div className="flex-1 space-y-1">
            <label className="text-xs font-semibold text-slate-500 uppercase">Prometheus Endpoint URL</label>
            <input
              type="url"
              placeholder="https://prometheus.internal:9090"
              className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-indigo-300 font-mono text-sm focus:border-indigo-500 outline-none transition-colors"
              value={newServer.url}
              onChange={e => setNewServer({...newServer, url: e.target.value})}
              required
            />
          </div>
          <div className="flex items-end">
            <button type="submit" className="bg-indigo-600 text-white px-8 py-2.5 rounded-lg hover:bg-indigo-500 font-bold transition-all shadow-lg shadow-indigo-600/20 h-[45px]">
              Add Target
            </button>
          </div>
        </form>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-6 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <h2 className="text-xl font-bold text-white flex items-center space-x-2">
            <Server size={20} className="text-indigo-400" />
            <span>Infrastructure Source Map</span>
          </h2>
          <span className="text-xs text-slate-500 font-medium bg-slate-800 px-3 py-1 rounded-full">{servers.length} Sources Active</span>
        </div>

        <div className="divide-y divide-slate-800">
          {servers.map(server => (
            <div key={server.id} className="p-6 hover:bg-slate-800/20 transition-all group flex flex-col lg:flex-row lg:items-center justify-between gap-6">
              <div className="flex items-start space-x-4">
                <div className="bg-slate-800 p-3 rounded-xl text-indigo-400 group-hover:bg-indigo-500 group-hover:text-white transition-all">
                  <Server size={24} />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center space-x-3">
                    <h3 className="text-lg font-bold text-white">{server.name}</h3>
                    <span className={`
                      px-2 py-0.5 rounded text-[10px] font-bold uppercase border
                      ${server.status === 'online' 
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                        : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                      }
                    `}>
                      {server.status || 'unknown'}
                    </span>
                  </div>
                  <a 
                    href={server.url} 
                    target="_blank" 
                    rel="noopener noreferrer" 
                    className="text-indigo-400 hover:text-indigo-300 text-sm font-mono flex items-center space-x-1"
                  >
                    <span>{server.url}</span>
                    <ExternalLink size={12} />
                  </a>
                  <div className="flex items-center space-x-2 text-[10px] text-slate-500">
                    <Activity size={10} />
                    <span>Last Telemetry Check: {server.last_checked ? new Date(server.last_checked).toLocaleString() : 'Pending Discovery'}</span>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button 
                  onClick={() => handleSyncGroups(server.id)}
                  className="flex items-center space-x-2 bg-slate-800 text-emerald-400 px-4 py-2 rounded-lg text-xs font-semibold hover:bg-emerald-500 hover:text-white transition-all border border-emerald-500/20"
                >
                  <RefreshCw size={14} />
                  <span>Sync Groups</span>
                </button>
                <button 
                  onClick={() => handleSyncRules(server.id)}
                  className="flex items-center space-x-2 bg-slate-800 text-amber-400 px-4 py-2 rounded-lg text-xs font-semibold hover:bg-amber-500 hover:text-white transition-all border border-amber-500/20"
                >
                  <RefreshCw size={14} />
                  <span>Sync Rules</span>
                </button>
                <button 
                  onClick={() => handleDelete(server.id)}
                  className="flex items-center space-x-2 bg-slate-800 text-rose-400 px-4 py-2 rounded-lg text-xs font-semibold hover:bg-rose-500 hover:text-white transition-all border border-rose-500/20"
                >
                  <Trash2 size={14} />
                  <span>Remove</span>
                </button>
              </div>
            </div>
          ))}
          {servers.length === 0 && (
            <div className="p-12 text-center flex flex-col items-center">
              <Server size={48} className="text-slate-800 mb-2" />
              <p className="text-slate-500">No Prometheus infrastructure sources connected</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PrometheusServers;
