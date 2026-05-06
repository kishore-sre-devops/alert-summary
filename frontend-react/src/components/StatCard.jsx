import React from 'react';
import { LucideIcon } from 'lucide-react';

const StatCard = ({ title, value, icon: Icon, trend, colorClass }) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition-all duration-300 group">
      <div className="flex justify-between items-start mb-4">
        <div className={`p-2 rounded-lg ${colorClass} bg-opacity-10 group-hover:bg-opacity-20 transition-all duration-300`}>
          <Icon size={24} className={colorClass.replace('bg-', 'text-')} />
        </div>
        {trend && (
          <span className={`text-xs font-medium px-2 py-1 rounded-full ${trend.includes('+') ? 'bg-rose-500/10 text-rose-400' : 'bg-emerald-500/10 text-emerald-400'}`}>
            {trend}
          </span>
        )}
      </div>
      <div>
        <h3 className="text-slate-500 text-sm font-medium uppercase tracking-wider mb-1">{title}</h3>
        <p className="text-2xl font-bold text-white tabular-nums">{value}</p>
      </div>
    </div>
  );
};

export default StatCard;
