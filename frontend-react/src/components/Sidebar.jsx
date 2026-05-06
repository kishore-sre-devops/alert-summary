import React from 'react';
import logo from '../assets/logo.png';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Server, Users, Settings, Activity, Target, History, Smartphone } from 'lucide-react';

const Sidebar = () => {
  const navItems = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard },
    { name: 'Historical Data', path: '/history', icon: History },
    { name: 'Targets', path: '/targets', icon: Target },
    { name: 'Servers', path: '/servers', icon: Server },
    { name: 'Groups', path: '/groups', icon: Users },
    { name: 'Rules', path: '/rules', icon: Settings },
    { name: 'Mobile', path: '/mobile', icon: Smartphone },
  ];

  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col h-screen sticky top-0">
      <div className="p-6 border-b border-slate-800 flex items-center space-x-3">
        <img src={logo} alt="SMC Logo" className="h-10 w-10 object-contain rounded-lg" />
        <span className="text-xl font-bold text-white tracking-tight">SMC Alerts</span>
      </div>
      
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => `
              flex items-center space-x-3 px-4 py-3 rounded-lg transition-all duration-200
              ${isActive 
                ? 'bg-indigo-600/10 text-indigo-400 border border-indigo-500/20' 
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
              }
            `}
          >
            <item.icon size={20} />
            <span className="font-medium">{item.name}</span>
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-slate-800 mt-auto">
        <div className="bg-slate-800/50 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">System Status</span>
            <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
          </div>
          <div className="text-xs text-slate-400">All systems operational</div>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
