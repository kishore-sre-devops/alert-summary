import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import History from './pages/History';
import Targets from './pages/Targets';
import PrometheusServers from './pages/PrometheusServers';
import AlertGroups from './pages/AlertGroups';
import AlertRules from './pages/AlertRules';
import MobileManagement from './pages/MobileManagement';
import './App.css';

const App = () => {
  return (
    <Router>
      <div className="flex min-h-screen bg-slate-950 text-slate-300">
        <Sidebar />
        
        <div className="flex-1 flex flex-col">
          <header className="h-16 border-b border-slate-800 bg-slate-900/50 backdrop-blur-md sticky top-0 z-10 flex items-center px-8 justify-between">
            <h2 className="text-lg font-semibold text-white uppercase tracking-wider">Operational Command Center</h2>
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2 bg-slate-800 px-3 py-1 rounded-full border border-slate-700">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                <span className="text-xs font-medium">Live Connection</span>
              </div>
            </div>
          </header>

          <main className="flex-1 p-8 overflow-y-auto">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/history" element={<History />} />
              <Route path="/targets" element={<Targets />} />
              <Route path="/servers" element={<PrometheusServers />} />
              <Route path="/groups" element={<AlertGroups />} />
              <Route path="/rules" element={<AlertRules />} />
              <Route path="/mobile" element={<MobileManagement />} />
            </Routes>
          </main>
          
          <footer className="py-4 px-8 border-t border-slate-800 text-xs text-slate-500 flex justify-between">
            <span>&copy; 2026 SMC Alert Summary Engine v2.0</span>
            <div className="flex space-x-4">
              <span>NOC Status: <span className="text-emerald-500">Nominal</span></span>
              <span>IST Time: {new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })}</span>
            </div>
          </footer>
        </div>
      </div>
    </Router>
  );
};

export default App;
