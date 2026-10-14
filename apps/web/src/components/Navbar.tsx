"use client";

import React, { useState, useEffect } from "react";
import { ApiClient, UserContext } from "@/lib/api";
import { Shield, Activity, User, RefreshCw, CheckCircle2, AlertTriangle, ChevronDown } from "lucide-react";

export default function Navbar() {
  const [user, setUser] = useState<UserContext | null>(null);
  const [healthStatus, setHealthStatus] = useState<string>("checking");
  const [switching, setSwitching] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const roles = [
    { id: "patient", label: "Patient (PT-100201)", color: "border-emerald-500/30 text-emerald-400 bg-emerald-500/10" },
    { id: "doctor", label: "Doctor (Dr. Chen)", color: "border-sky-500/30 text-sky-400 bg-sky-500/10" },
    { id: "researcher", label: "Researcher (Academic)", color: "border-purple-500/30 text-purple-400 bg-purple-500/10" },
    { id: "insurance_analyst", label: "Insurance Analyst", color: "border-amber-500/30 text-amber-400 bg-amber-500/10" },
    { id: "admin", label: "Administrator", color: "border-rose-500/30 text-rose-400 bg-rose-500/10" },
  ];

  const fetchCurrentContext = async () => {
    try {
      const stored = localStorage.getItem("medchain_user");
      if (stored) {
        setUser(JSON.parse(stored));
      } else {
        // Default to doctor on first load
        const res = await ApiClient.demoSwitch("doctor");
        setUser(res.user);
      }
    } catch (_) {
      try {
        const res = await ApiClient.demoSwitch("doctor");
        setUser(res.user);
      } catch (err) {}
    }

    try {
      const h = await ApiClient.getSystemHealth();
      setHealthStatus(h.status === "healthy" ? "healthy" : "degraded");
    } catch (_) {
      setHealthStatus("offline");
    }
  };

  useEffect(() => {
    fetchCurrentContext();
  }, []);

  const handleRoleSwitch = async (roleId: string) => {
    setSwitching(true);
    setMenuOpen(false);
    try {
      const res = await ApiClient.demoSwitch(roleId);
      setUser(res.user);
      // Reload page to refresh role-filtered views
      window.location.reload();
    } catch (err: any) {
      alert(`Role switch error: ${err.message}`);
    } finally {
      setSwitching(false);
    }
  };

  const currentRoleObj = roles.find((r) => r.id === user?.role) || roles[1];

  return (
    <header className="sticky top-0 z-40 w-full glass-panel border-b border-slate-800/80 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center space-x-3">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-bold tracking-tight text-lg text-white">MED<span className="text-cyan-400">CHAIN</span></span>
            <span className="text-[10px] tracking-widest font-mono uppercase px-2 py-0.5 rounded-full bg-cyan-950/80 text-cyan-300 border border-cyan-800/60">
              DBMS Capstone
            </span>
          </div>
          <p className="text-xs text-slate-400">Privacy-Preserving Healthcare Intelligence & Ledger Audit</p>
        </div>
      </div>

      <div className="flex items-center space-x-4">
        {/* Live System Health Badge */}
        <div className="hidden md:flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800 text-xs">
          <Activity className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
          <span className="text-slate-400">System:</span>
          {healthStatus === "healthy" && (
            <span className="inline-flex items-center text-emerald-400 font-medium">
              <CheckCircle2 className="w-3 h-3 mr-1" /> Multi-Store Online
            </span>
          )}
          {healthStatus === "degraded" && (
            <span className="inline-flex items-center text-amber-400 font-medium">
              <AlertTriangle className="w-3 h-3 mr-1" /> Fallback Mode Active
            </span>
          )}
          {healthStatus === "checking" && <span className="text-slate-400">Checking...</span>}
          {healthStatus === "offline" && <span className="text-rose-400 font-medium">Services Offline</span>}
        </div>

        {/* Demo Role Switcher Dropdown */}
        <div className="relative">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            disabled={switching}
            className={`flex items-center space-x-2.5 px-3.5 py-1.5 rounded-xl border text-xs font-medium transition-all ${currentRoleObj.color} hover:brightness-110 active:scale-95`}
          >
            <User className="w-3.5 h-3.5" />
            <span>Role: {currentRoleObj.label}</span>
            <ChevronDown className="w-3.5 h-3.5 opacity-70" />
          </button>

          {menuOpen && (
            <div className="absolute right-0 mt-2 w-64 glass-panel rounded-xl border border-slate-700/80 shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="px-3 py-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase border-b border-slate-800/80 mb-1">
                Demo Role Switcher (Academic Presentation)
              </div>
              {roles.map((r) => (
                <button
                  key={r.id}
                  onClick={() => handleRoleSwitch(r.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-xs font-medium flex items-center justify-between transition-colors ${
                    user?.role === r.id
                      ? "bg-cyan-500/20 text-cyan-300 font-semibold"
                      : "text-slate-300 hover:bg-slate-800/60 hover:text-white"
                  }`}
                >
                  <span>{r.label}</span>
                  {user?.role === r.id && <span className="w-2 h-2 rounded-full bg-cyan-400"></span>}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
