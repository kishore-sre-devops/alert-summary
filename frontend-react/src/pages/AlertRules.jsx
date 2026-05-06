import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Settings, Plus, Edit2, Trash2, X, AlertCircle, Activity } from 'lucide-react';

const API_BASE = '/api';

const AlertRules = () => {
  const [rules, setRules] = useState([]);
  const [groups, setGroups] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [newRule, setNewRule] = useState({ 
    name: '', promql: '', severity: 'warning', group_ids: [], duration: '60s', summary: '', description: '' 
  });

  const fetchData = async () => {
    try {
      const [rulesRes, groupsRes] = await Promise.all([
        axios.get(`${API_BASE}/alert-rules`),
        axios.get(`${API_BASE}/alert-groups`)
      ]);
      setRules(rulesRes.data);
      setGroups(groupsRes.data);
      if (groupsRes.data.length > 0 && newRule.group_ids.length === 0) {
        setNewRule(prev => ({ ...prev, group_ids: [groupsRes.data[0].id] }));
      }
    } catch (error) {
      console.error("Error fetching data:", error);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    try {
      if (editingId) {
        await axios.put(`${API_BASE}/alert-rules/${editingId}`, newRule);
        setEditingId(null);
      } else {
        await axios.post(`${API_BASE}/alert-rules`, newRule);
      }
      setNewRule({ ...newRule, name: '', promql: '', summary: '', description: '' });
      fetchData();
    } catch (error) {
      console.error("Error saving rule:", error);
    }
  };

  const handleEdit = (rule) => {
    setEditingId(rule.id);
    setNewRule({
      name: rule.name,
      promql: rule.promql,
      severity: rule.severity,
      group_ids: rule.notification_groups?.length > 0 ? rule.notification_groups.map(g => g.id) : (rule.group_id ? [rule.group_id] : []),
      duration: rule.duration,
      summary: rule.summary || '',
      description: rule.description || ''
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCancel = () => {
    setEditingId(null);
    setNewRule({ ...newRule, name: '', promql: '', summary: '', description: '' });
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`${API_BASE}/alert-rules/${id}`);
      fetchData();
    } catch (error) {
      console.error("Error deleting rule:", error);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
        <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
          {editingId ? <Edit2 size={20} className="text-indigo-400" /> : <Plus size={20} className="text-indigo-400" />}
          <span>{editingId ? 'Modify Alert Strategy' : 'Define New Alert Rule'}</span>
        </h2>
        
        <form onSubmit={handleAdd} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase">Rule Name</label>
              <input
                type="text"
                placeholder="e.g. HighCpuUsage"
                className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-white focus:border-indigo-500 outline-none transition-colors"
                value={newRule.name}
                onChange={e => setNewRule({...newRule, name: e.target.value})}
                required
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase">Summary</label>
              <input
                type="text"
                placeholder="e.g. CPU is high"
                className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-white focus:border-indigo-500 outline-none transition-colors"
                value={newRule.summary}
                onChange={e => setNewRule({...newRule, summary: e.target.value})}
              />
            </div>
            <div className="col-span-1 md:col-span-2 space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase">PromQL Query</label>
              <input
                type="text"
                placeholder="e.g. node_cpu_seconds_total > 0.8"
                className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-indigo-300 font-mono text-sm focus:border-indigo-500 outline-none transition-colors"
                value={newRule.promql}
                onChange={e => setNewRule({...newRule, promql: e.target.value})}
                required
              />
            </div>
            <div className="col-span-1 md:col-span-2 space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase">Description</label>
              <textarea
                placeholder="Detailed explanation of the alert..."
                className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-white focus:border-indigo-500 outline-none transition-colors min-h-[80px]"
                value={newRule.description}
                onChange={e => setNewRule({...newRule, description: e.target.value})}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase">Incident Severity</label>
              <select
                className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-white focus:border-indigo-500 outline-none transition-colors"
                value={newRule.severity}
                onChange={e => setNewRule({...newRule, severity: e.target.value})}
              >
                <option value="warning" className="bg-slate-900">Warning</option>
                <option value="critical" className="bg-slate-900 text-rose-400">Critical</option>
                <option value="Critical-50%" className="bg-slate-900 text-rose-500">Critical-50%</option>
                <option value="Critical-90%" className="bg-slate-900 text-rose-500">Critical-90%</option>
                <option value="Critical-95%" className="bg-slate-900 text-rose-500">Critical-95%</option>
                <option value="Critical-InstanceDown" className="bg-slate-900 text-rose-500">Critical-InstanceDown</option>
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase">Wait Duration</label>
              <input
                type="text"
                placeholder="e.g. 5m"
                className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-white focus:border-indigo-500 outline-none transition-colors"
                value={newRule.duration}
                onChange={e => setNewRule({...newRule, duration: e.target.value})}
              />
            </div>
          </div>
          <div className="flex space-x-3 pt-4">
            <button type="submit" className="bg-indigo-600 text-white px-8 py-2.5 rounded-lg hover:bg-indigo-500 font-bold transition-all shadow-lg shadow-indigo-600/20">
              {editingId ? 'Update Strategy' : 'Deploy Rule'}
            </button>
            {editingId && (
              <button 
                type="button" 
                onClick={handleCancel}
                className="bg-slate-800 text-slate-300 px-6 py-2.5 rounded-lg hover:bg-slate-700 font-bold transition-all flex items-center space-x-2"
              >
                <X size={18} />
                <span>Cancel</span>
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-6 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <h2 className="text-xl font-bold text-white flex items-center space-x-2">
            <Settings size={20} className="text-indigo-400" />
            <span>Active Alert Inventory</span>
          </h2>
          <span className="text-xs text-slate-500 font-medium bg-slate-800 px-3 py-1 rounded-full">{rules.length} Rules Active</span>
        </div>
        
        <div className="divide-y divide-slate-800">
          {rules.map(rule => (
            <div key={rule.id} className="p-6 hover:bg-slate-800/20 transition-all group">
              <div className="flex justify-between items-start mb-3">
                <div className="space-y-1">
                  <h3 className="text-lg font-bold text-white group-hover:text-indigo-400 transition-colors">{rule.name}</h3>
                  <div className="flex items-center space-x-4 text-xs text-slate-500 uppercase tracking-widest">
                    {rule.summary && (
                      <span className="flex items-center space-x-1">
                        <span className="text-slate-600">Summary:</span>
                        <span className="text-slate-300">{rule.summary}</span>
                      </span>
                    )}
                    <span className="flex items-center space-x-1">
                      <span className="text-slate-600">Severity:</span>
                      <span className={`${rule.severity?.toLowerCase().includes('critical') ? 'text-rose-400' : 'text-amber-400'}`}>{rule.severity}</span>
                    </span>
                    <span className="flex items-center space-x-1">
                      <span className="text-slate-600">Period:</span>
                      <span className="text-slate-300">{rule.duration}</span>
                    </span>
                  </div>
                </div>
                <div className="flex space-x-2">
                  <button 
                    onClick={() => handleEdit(rule)}
                    className="p-2 text-slate-400 hover:text-indigo-400 hover:bg-indigo-400/10 rounded-lg transition-all"
                    title="Edit Rule"
                  >
                    <Edit2 size={18} />
                  </button>
                  <button 
                    onClick={() => handleDelete(rule.id)}
                    className="p-2 text-slate-400 hover:text-rose-400 hover:bg-rose-400/10 rounded-lg transition-all"
                    title="Delete Rule"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
              <div className="bg-slate-950 border border-slate-800 p-3 rounded-lg font-mono text-xs text-indigo-300 relative group-hover:border-indigo-500/30 transition-all">
                <div className="absolute top-2 right-2">
                  <Activity size={12} className="text-slate-700" />
                </div>
                {rule.promql}
              </div>
              {rule.description && (
                <div className="mt-2 text-xs text-slate-400 italic">
                  {rule.description}
                </div>
              )}
            </div>
          ))}
          {rules.length === 0 && (
            <div className="p-12 text-center flex flex-col items-center">
              <AlertCircle size={48} className="text-slate-800 mb-2" />
              <p className="text-slate-500">No alert rules configured in the deployment</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AlertRules;
