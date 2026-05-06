import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Smartphone, Users, Download, Plus, Trash2, ShieldCheck, Mail, HardDrive, Settings } from 'lucide-react';

const API_BASE = '/api';

const MobileManagement = () => {
  const [users, setUsers] = useState([]);
  const [allGroups, setAllGroups] = useState([]);
  const [newUser, setNewUser] = useState({ name: '', email: '' });
  const [loading, setLoading] = useState(false);

  const [pendingChanges, setPendingChanges] = useState({});

  const fetchData = async () => {
    try {
      const [usersRes, groupsRes] = await Promise.all([
        axios.get(`${API_BASE}/users`),
        axios.get(`${API_BASE}/groups`)
      ]);
      setUsers(usersRes.data);
      setAllGroups(groupsRes.data);
      setPendingChanges({}); // Reset pending changes on fetch
    } catch (error) {
      console.error("Error fetching data:", error);
    }
  };

  const toggleGroup = (userId, group, checked) => {
    const user = users.find(u => u.id === userId);
    const currentGroups = pendingChanges[userId] || user.groups.map(g => g.group_name);
    
    const newGroups = checked 
      ? [...currentGroups, group]
      : currentGroups.filter(g => g !== group);
      
    setPendingChanges({ ...pendingChanges, [userId]: newGroups });
  };

  const handleUpdateGroups = async (userId) => {
    const groupsToApply = pendingChanges[userId];
    if (!groupsToApply) return;
    
    try {
      await axios.put(`${API_BASE}/users/${userId}/groups`, { groups: groupsToApply });
      setPendingChanges({ ...pendingChanges, [userId]: null });
      fetchData();
    } catch (error) {
      console.error("Error applying groups:", error);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleAddUser = async (e) => {
    e.preventDefault();
    if (!newUser.name || !newUser.email) return;
    setLoading(true);
    try {
      await axios.post(`${API_BASE}/users`, newUser);
      setNewUser({ name: '', email: '' });
      fetchData();
    } catch (error) {
      console.error("Error adding user:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteUser = async (id) => {
    try {
      await axios.delete(`${API_BASE}/users/${id}`);
      fetchData();
    } catch (error) {
      console.error("Error deleting user:", error);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* Mobile App Download Section */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500"></div>
        <div className="flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center space-x-4">
            <div className="bg-emerald-500/10 p-3 rounded-lg text-emerald-400">
              <Smartphone size={24} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-white">Mobile Application</h2>
              <p className="text-sm text-slate-400">Download the latest SMC Alert APK for Android devices.</p>
            </div>
          </div>
          <a 
            href="/static/smcalert.apk" 
            download="smcalert.apk"
            className="bg-emerald-600 text-white px-6 py-3 rounded-lg hover:bg-emerald-500 font-bold transition-all flex items-center space-x-2 shadow-lg shadow-emerald-900/20"
          >
            <Download size={20} />
            <span>Download APK</span>
          </a>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
        <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
          <Users size={20} className="text-indigo-400" />
          <span>Mobile App User & Group Management</span>
        </h2>
        
        {/* User Addition Form */}
        <form onSubmit={handleAddUser} className="flex gap-4 mb-8 bg-slate-950 p-4 rounded-xl border border-slate-800">
            <div className="flex-1 space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase">Full Name</label>
              <input
                type="text"
                className="bg-slate-900 border border-slate-800 rounded-lg p-2 w-full text-white"
                value={newUser.name}
                onChange={e => setNewUser({...newUser, name: e.target.value})}
                required
              />
            </div>
            <div className="flex-1 space-y-1">
              <label className="text-xs font-semibold text-slate-500 uppercase">Email Address</label>
              <input
                type="email"
                className="bg-slate-900 border border-slate-800 rounded-lg p-2 w-full text-white"
                value={newUser.email}
                onChange={e => setNewUser({...newUser, email: e.target.value})}
                required
              />
            </div>
            <div className="flex items-end">
              <button type="submit" disabled={loading} className="bg-indigo-600 text-white px-6 py-2 rounded-lg hover:bg-indigo-500 font-bold transition-all flex items-center space-x-2">
                <Plus size={18} />
                <span>Add User</span>
              </button>
            </div>
        </form>

        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-950/50 text-slate-500 text-xs uppercase tracking-wider font-semibold">
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Groups</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {users.map(user => (
                <tr key={user.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-3 text-white font-medium">{user.name}</td>
                  <td className="px-4 py-3 text-slate-400 text-sm">{user.email}</td>
                  <td className="px-4 py-3 text-white text-sm">
                    <div className="flex flex-col gap-1">
                      {allGroups.map(group => {
                        const currentAssigned = pendingChanges[user.id] || user.groups.map(g => g.group_name);
                        const isChecked = currentAssigned.includes(group);
                        return (
                          <label key={group} className="flex items-center space-x-2 cursor-pointer text-xs">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={(e) => toggleGroup(user.id, group, e.target.checked)}
                              className="accent-indigo-500"
                            />
                            <span>{group}</span>
                          </label>
                        );
                      })}
                      {pendingChanges[user.id] && (
                        <button 
                          onClick={() => handleUpdateGroups(user.id)}
                          className="mt-2 bg-indigo-600 text-white px-3 py-1 rounded text-[10px] font-bold hover:bg-indigo-500 transition-all"
                        >
                          Apply
                        </button>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => handleDeleteUser(user.id)} className="text-slate-500 hover:text-rose-400">
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default MobileManagement;