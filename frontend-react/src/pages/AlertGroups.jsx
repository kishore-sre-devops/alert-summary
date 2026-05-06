import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Users, Mail, MessageSquare, PhoneCall, Plus, Edit2, Trash2, X, Check } from 'lucide-react';

const API_BASE = '/api';

const AlertGroups = () => {
  const [groups, setGroups] = useState([]);
  const [newGroup, setNewGroup] = useState({ name: '', emails: '', slack_webhook: '', voice_enabled: 0 });
  const [editingGroup, setEditingGroup] = useState(null);

  const fetchGroups = async () => {
    try {
      const response = await axios.get(`${API_BASE}/alert-groups`);
      setGroups(response.data);
    } catch (error) {
      console.error("Error fetching groups:", error);
    }
  };

  useEffect(() => { fetchGroups(); }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API_BASE}/alert-groups`, newGroup);
      setNewGroup({ name: '', emails: '', slack_webhook: '', voice_enabled: 0 });
      fetchGroups();
    } catch (error) {
      console.error("Error adding group:", error);
    }
  };

  const handleUpdate = async (e) => {
    e.preventDefault();
    try {
      await axios.put(`${API_BASE}/alert-groups/${editingGroup.id}`, editingGroup);
      setEditingGroup(null);
      fetchGroups();
    } catch (error) {
      console.error("Error updating group:", error);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to delete this group?")) return;
    try {
      await axios.delete(`${API_BASE}/alert-groups/${id}`);
      fetchGroups();
    } catch (error) {
      console.error("Error deleting group:", error);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
        <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
          {editingGroup ? <Edit2 size={20} className="text-indigo-400" /> : <Plus size={20} className="text-indigo-400" />}
          <span>{editingGroup ? `Modify Notification Group: ${editingGroup.name}` : 'Register New Notification Group'}</span>
        </h2>

        <form onSubmit={editingGroup ? handleUpdate : handleAdd} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Group Identity</label>
              <input
                type="text"
                placeholder="e.g. SRE-Team"
                className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-white focus:border-indigo-500 outline-none transition-colors"
                value={editingGroup ? editingGroup.name : newGroup.name}
                onChange={e => editingGroup ? setEditingGroup({...editingGroup, name: e.target.value}) : setNewGroup({...newGroup, name: e.target.value})}
                required
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Email Recipients (CSV)</label>
              <input
                type="text"
                placeholder="e.g. noc@smc.com, ops@smc.com"
                className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-white focus:border-indigo-500 outline-none transition-colors"
                value={editingGroup ? (editingGroup.emails || '') : newGroup.emails}
                onChange={e => editingGroup ? setEditingGroup({...editingGroup, emails: e.target.value}) : setNewGroup({...newGroup, emails: e.target.value})}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Slack Webhook Endpoint</label>
              <input
                type="text"
                placeholder="https://hooks.slack.com/services/..."
                className="bg-slate-950 border border-slate-800 rounded-lg p-2.5 w-full text-white focus:border-indigo-500 outline-none transition-colors"
                value={editingGroup ? (editingGroup.slack_webhook || '') : newGroup.slack_webhook}
                onChange={e => editingGroup ? setEditingGroup({...editingGroup, slack_webhook: e.target.value}) : setNewGroup({...newGroup, slack_webhook: e.target.value})}
              />
            </div>
            <div className="flex items-center space-x-4 pt-6">
              <div 
                className={`flex items-center space-x-3 cursor-pointer select-none group`}
                onClick={() => editingGroup 
                  ? setEditingGroup({...editingGroup, voice_enabled: editingGroup.voice_enabled === 1 ? 0 : 1})
                  : setNewGroup({...newGroup, voice_enabled: newGroup.voice_enabled === 1 ? 0 : 1})
                }
              >
                <div className={`
                  w-10 h-6 rounded-full transition-all relative
                  ${(editingGroup ? editingGroup.voice_enabled : newGroup.voice_enabled) === 1 ? 'bg-indigo-600' : 'bg-slate-800'}
                `}>
                  <div className={`
                    absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-all
                    ${(editingGroup ? editingGroup.voice_enabled : newGroup.voice_enabled) === 1 ? 'translate-x-4' : 'translate-x-0'}
                  `}></div>
                </div>
                <div className="flex flex-col">
                  <span className="text-sm font-medium text-slate-300">Voice Synthesis Alerts</span>
                  <span className="text-xs text-slate-500">Automated phone/speaker calls for incidents</span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex space-x-3 pt-4 border-t border-slate-800/50">
            <button type="submit" className="bg-indigo-600 text-white px-8 py-2.5 rounded-lg hover:bg-indigo-500 font-bold transition-all shadow-lg shadow-indigo-600/20 flex items-center space-x-2">
              <Check size={18} />
              <span>{editingGroup ? 'Update Config' : 'Register Group'}</span>
            </button>
            {editingGroup && (
              <button 
                type="button" 
                onClick={() => setEditingGroup(null)}
                className="bg-slate-800 text-slate-300 px-6 py-2.5 rounded-lg hover:bg-slate-700 font-bold transition-all flex items-center space-x-2"
              >
                <X size={18} />
                <span>Discard Changes</span>
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-6 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <h2 className="text-xl font-bold text-white flex items-center space-x-2">
            <Users size={20} className="text-indigo-400" />
            <span>Operational Target Groups</span>
          </h2>
          <span className="text-xs text-slate-500 font-medium bg-slate-800 px-3 py-1 rounded-full">{groups.length} Groups Configured</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 p-6">
          {groups.map(group => (
            <div key={group.id} className="bg-slate-950 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-all group relative">
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-center space-x-3">
                  <div className="bg-slate-800 p-2 rounded-lg text-indigo-400">
                    <Users size={20} />
                  </div>
                  <h3 className="text-lg font-bold text-white">{group.name}</h3>
                </div>
                <div className="flex space-x-1">
                  <button 
                    onClick={() => setEditingGroup(group)}
                    className="p-1.5 text-slate-500 hover:text-indigo-400 hover:bg-indigo-400/10 rounded-lg transition-all"
                    title="Edit Group"
                  >
                    <Edit2 size={16} />
                  </button>
                  <button 
                    onClick={() => handleDelete(group.id)}
                    className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-400/10 rounded-lg transition-all"
                    title="Delete Group"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-start space-x-3">
                  <Mail size={14} className="mt-1 text-slate-600" />
                  <div className="flex flex-wrap gap-1">
                    {group.emails ? group.emails.split(',').map(email => (
                      <span key={email} className="text-[10px] bg-slate-800 border border-slate-700 text-slate-400 px-2 py-0.5 rounded">
                        {email.trim()}
                      </span>
                    )) : <span className="text-xs text-slate-600 italic">No email recipients</span>}
                  </div>
                </div>

                <div className="flex items-center space-x-3">
                  <MessageSquare size={14} className="text-slate-600" />
                  <span className={`text-xs ${group.slack_webhook ? 'text-emerald-400' : 'text-slate-600 italic'}`}>
                    {group.slack_webhook ? 'Slack Webhook Integrated' : 'Slack Not Configured'}
                  </span>
                </div>

                <div className="flex items-center space-x-3">
                  <PhoneCall size={14} className="text-slate-600" />
                  <span className={`text-xs ${group.voice_enabled ? 'text-amber-400' : 'text-slate-600 italic'}`}>
                    {group.voice_enabled ? 'Voice Overrides Active' : 'Standard Notifications Only'}
                  </span>
                </div>
              </div>
              
              {group.voice_enabled === 1 && (
                <div className="absolute top-0 right-0 p-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]"></div>
                </div>
              )}
            </div>
          ))}
          {groups.length === 0 && (
            <div className="col-span-full py-12 text-center flex flex-col items-center">
              <Users size={48} className="text-slate-800 mb-2" />
              <p className="text-slate-500">No operational groups defined in the system</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AlertGroups;
