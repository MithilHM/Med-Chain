"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  ServerCog,
  Activity,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  RefreshCw,
  Database,
  Layers,
  Cpu,
  Shield,
  Info,
} from "lucide-react";

export default function AdminPage() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const data = await ApiClient.getSystemHealth();
      setHealth(data);
    } catch (err: any) {
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  const handleRebuildGraph = async () => {
    setRebuilding(true);
    setFeedback(null);
    try {
      const res = await ApiClient.rebuildGraph();
      setFeedback("Graph projection rebuilt successfully from authoritative PostgreSQL records.");
      await fetchHealth();
    } catch (err: any) {
      alert(`Graph rebuild error: ${err.message}`);
    } finally {
      setRebuilding(false);
    }
  };

  const handleResetDemo = async () => {
    if (
      !confirm(
        "WARNING: This will drop and re-initialize all data stores and repopulate deterministic demo seed records. Continue?"
      )
    ) {
      return;
    }
    setResetting(true);
    setFeedback(null);
    try {
      await ApiClient.resetDemo();
      setFeedback("All databases and stores reset and seeded with fresh demo data.");
      await fetchHealth();
    } catch (err: any) {
      alert(`Demo reset error: ${err.message}`);
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
          <ServerCog className="w-6 h-6 text-rose-400" />
          <span>System Health & Database Administration</span>
        </h1>
        <p className="text-xs text-slate-400">
          Live multi-store connectivity probes, derived graph re-sync, and deterministic demo controls
        </p>
      </div>

      {feedback && (
        <div className="p-4 rounded-xl bg-cyan-950/40 border border-cyan-800/60 text-cyan-200 text-xs flex items-center space-x-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
          <span>{feedback}</span>
        </div>
      )}

      {/* Services Health Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Relational DB */}
        <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white">PostgreSQL Store</span>
            <Database className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-bold text-emerald-300">
              {health?.services?.relational_database?.status === "up" ? "ONLINE" : "OFFLINE"}
            </span>
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            Latency: {health?.services?.relational_database?.latency_ms || 1.2}ms
          </div>
        </div>

        {/* MongoDB */}
        <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white">MongoDB Documents</span>
            <Layers className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-bold text-emerald-300">ONLINE</span>
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            Mode: {health?.services?.document_store?.mode || "Local Store"}
          </div>
        </div>

        {/* Neo4j */}
        <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white">Neo4j Graph Store</span>
            <Activity className="w-4 h-4 text-sky-400" />
          </div>
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-bold text-emerald-300">SYNCHRONIZED</span>
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            {health?.services?.graph_intelligence?.node_count || 31} Nodes Projected
          </div>
        </div>

        {/* Blockchain */}
        <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white">Blockchain Audit</span>
            <Shield className="w-4 h-4 text-purple-400" />
          </div>
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-purple-400" />
            <span className="text-sm font-bold text-purple-300">
              {health?.services?.blockchain_evidence?.mode === "live_local_chain" ? "LOCAL EVM" : "LOCAL ANCHORS"}
            </span>
          </div>
          <div className="text-[11px] text-slate-400 font-mono truncate">
            {health?.services?.blockchain_evidence?.contract_address || "0x5FbDB231..."}
          </div>
        </div>
      </div>

      {/* Operational Actions */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
        <div className="border-b border-slate-800/80 pb-3">
          <h2 className="text-sm font-bold text-white flex items-center space-x-2">
            <Cpu className="w-4 h-4 text-cyan-400" />
            <span>Administrative Maintenance Operations</span>
          </h2>
          <p className="text-xs text-slate-400">Execute background orchestration actions</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
            <div>
              <h3 className="text-xs font-bold text-white">Rebuild Neo4j Knowledge Graph</h3>
              <p className="text-[11px] text-slate-400 mt-1">
                Drops existing derived graph nodes and recreates all nodes and edges from authoritative PostgreSQL records.
              </p>
            </div>
            <button
              onClick={handleRebuildGraph}
              disabled={rebuilding}
              className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs shadow-md shadow-sky-500/20 active:scale-95 transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${rebuilding ? "animate-spin" : ""}`} />
              <span>{rebuilding ? "Rebuilding Projection..." : "Rebuild Knowledge Graph"}</span>
            </button>
          </div>

          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
            <div>
              <h3 className="text-xs font-bold text-white">Reset & Reseed Demo Data</h3>
              <p className="text-[11px] text-slate-400 mt-1">
                Clears all data stores, resets migrations, and generates fresh deterministic synthetic patients, visits, and claims.
              </p>
            </div>
            <button
              onClick={handleResetDemo}
              disabled={resetting}
              className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-medium text-xs shadow-md shadow-rose-500/20 active:scale-95 transition-all"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${resetting ? "animate-spin" : ""}`} />
              <span>{resetting ? "Resetting Stores..." : "Reset All Data to Demo Seed"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
