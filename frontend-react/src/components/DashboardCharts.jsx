import React from 'react';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, 
  Cell, PieChart, Pie 
} from 'recharts';

const DashboardCharts = ({ instanceData, severityData, alertNameData }) => {
  const COLORS = {
    critical: '#f43f5e', // rose-500
    warning: '#f59e0b',  // amber-500
    info: '#3b82f6',     // blue-500
    resolved: '#10b981'  // emerald-500
  };

  return (
    <div className="space-y-8 mb-8">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Failing Instances Chart */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h3 className="text-white font-semibold mb-6 flex items-center justify-between">
            <span>Top Problematic Instances</span>
            <span className="text-xs font-normal text-slate-500">by alert count</span>
          </h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={instanceData} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                <XAxis type="number" stroke="#64748b" fontSize={12} />
                <YAxis dataKey="name" type="category" stroke="#64748b" fontSize={11} width={100} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                  itemStyle={{ color: '#818cf8' }}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {instanceData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.count > 5 ? '#f43f5e' : '#818cf8'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Severity Distribution Chart */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <h3 className="text-white font-semibold mb-6 flex items-center justify-between">
            <span>Severity Distribution</span>
            <span className="text-xs font-normal text-slate-500">active alerts</span>
          </h3>
          <div className="h-64 w-full flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={severityData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {severityData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[entry.name.toLowerCase()] || '#818cf8'} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                  itemStyle={{ color: '#818cf8' }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-col space-y-2 ml-4">
              {severityData.map((entry) => (
                <div key={entry.name} className="flex items-center space-x-2">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[entry.name.toLowerCase()] || '#818cf8' }}></div>
                  <span className="text-xs text-slate-400 capitalize">{entry.name}: {entry.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Top Alert Types Bar Chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
        <h3 className="text-white font-semibold mb-6 flex items-center justify-between">
          <span>Top Alert Types</span>
          <span className="text-xs font-normal text-slate-500">by active frequency</span>
        </h3>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={alertNameData} margin={{ bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="name" stroke="#64748b" fontSize={10} angle={-15} textAnchor="end" />
              <YAxis stroke="#64748b" fontSize={12} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                itemStyle={{ color: '#818cf8' }}
              />
              <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]}>
                {alertNameData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={index === 0 ? '#4f46e5' : '#6366f1'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default DashboardCharts;
