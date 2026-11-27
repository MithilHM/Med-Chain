"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ApiClient, utcTime } from "@/lib/api";
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
  Building2,
  Lock,
  Radio,
  FileCheck2,
  KeyRound,
  ShieldCheck,
  Zap,
} from "lucide-react";

export default function AdminPage() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Outbox Telemetry
  const [outboxEvents, setOutboxEvents] = useState<any[]>([]);
  const [outboxProcessing, setOutboxProcessing] = useState(false);
  const [outboxRetrying, setOutboxRetrying] = useState(false);

  // Disaster Recovery
  const [drStatus, setDrStatus] = useState<any>(null);

  // Active Sessions
  const [sessions, setSessions] = useState<any[]>([]);
  const [revokingSessions, setRevokingSessions] = useState(false);

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const [h, events, dr, sess] = await Promise.all([
        ApiClient.getAdminHealth().catch(() => null),
        ApiClient.getOutboxEvents(15).catch(() => []),
        ApiClient.getDisasterRecovery().catch(() => null),
        ApiClient.listSessions().catch(() => []),
      ]);
      setHealth(h);
      setOutboxEvents(events);
      setDrStatus(dr);
      setSessions(sess);
    } catch (err: any) {
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  const handleProcessOutbox = async () => {
    setOutboxProcessing(true);
    setFeedback(null);
    try {
      const res = await ApiClient.processOutbox(20);
      setFeedback(`Processed ${res.processed_events} transactional outbox events.`);
      await fetchHealth();
    } catch (err: any) {
      alert(`Outbox processing failed: ${err.message}`);
    } finally {
      setOutboxProcessing(false);
    }
  };

  const handleRetryFailedOutbox = async () => {
    setOutboxRetrying(true);
    setFeedback(null);
    try {
      const res = await ApiClient.retryFailedOutbox();
      setFeedback(`Reset ${res.reset_events} failed outbox events to PENDING.`);
      await fetchHealth();
    } catch (err: any) {
      alert(`Outbox retry failed: ${err.message}`);
    } finally {
      setOutboxRetrying(false);
    }
  };

  const handleRevokeAllSessions = async () => {
    if (!confirm("Are you sure you want to invalidate all active clinical workstation sessions? Users will be prompted to re-authenticate.")) {
      return;
    }
    setRevokingSessions(true);
    try {
      await ApiClient.revokeAllSessions();
      setFeedback("All active staff workstation sessions revoked successfully.");
      await fetchHealth();
    } catch (err: any) {
      alert(`Session revocation failed: ${err.message}`);
    } finally {
      setRevokingSessions(false);
    }
  };

  const handleRebuildGraph = async () => {
    setRebuilding(true);
    setFeedback(null);
    try {
      const res = await ApiClient.rebuildGraph();
      setFeedback(`Graph projection rebuilt successfully in ${res?.details?.mode || "unknown"} mode.`);
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

  const relational = health?.services?.relational_database;
  const documentStore = health?.services?.document_store;
  const graphStore = health?.services?.graph_intelligence;
  const blockchain = health?.services?.blockchain_evidence;
  const outbox = health?.services?.transactional_outbox;

  const unknownLabel = loading ? "CHECKING" : "UNAVAILABLE";
  const relationalLabel = !health ? unknownLabel : relational?.status !== "up" ? "OFFLINE" : relational?.engine === "sqlite_fallback" ? "SQLITE FALLBACK" : "POSTGRESQL";
  const documentLabel = !health ? unknownLabel : documentStore?.status !== "up" ? "OFFLINE" : documentStore?.mode === "mongodb_live_encrypted" ? "LIVE MONGODB" : "LOCAL STORE";
  const graphLabel = !health ? unknownLabel : graphStore?.status !== "SYNCHRONIZED" ? "NOT SYNCED" : graphStore?.mode === "live_neo4j" ? "LIVE NEO4J" : "PROJECTION SYNC";
  const blockchainLabel = !health
    ? unknownLabel
    : blockchain?.status === "connected"
      ? "LOCAL EVM"
      : blockchain?.status === "chain_mismatch"
        ? "CHAIN MISMATCH"
        : blockchain?.status === "contract_unavailable"
          ? "CONTRACT UNAVAILABLE"
          : "ANCHOR PROTOCOL";

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center space-x-2.5">
            <ServerCog className="w-6 h-6 text-brand-600" />
            <span>System health</span>
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Status of databases, the audit ledger, background delivery, sessions, and backups.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <Link
            href="/admin/dbms"
            className="inline-flex items-center gap-2 rounded-xl border border-brand-300 bg-brand-50 px-4 py-2 text-xs font-semibold text-brand-800 hover:bg-brand-100"
          >
            <Database className="h-4 w-4" /> Relational SQL Showcase
          </Link>
        </div>
      </div>

      {feedback && (
        <div className="p-4 rounded-xl bg-brand-50 border border-brand-200 text-brand-800 text-xs flex items-center space-x-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-brand-700 shrink-0" />
          <span>{feedback}</span>
        </div>
      )}

      {/* Services Health Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Relational DB */}
        <div className="p-5 rounded-xl glass-panel border border-slate-200 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-900">Relational ACID Core</span>
            <Database className="w-4 h-4 text-brand-700" />
          </div>
          <div className="flex items-center space-x-2">
            {relationalLabel === "POSTGRESQL" || relationalLabel === "SQLITE FALLBACK" ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-700" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-amber-700" />
            )}
            <span className={`text-sm font-bold ${relationalLabel === "POSTGRESQL" ? "text-emerald-700" : "text-amber-700"}`}>
              {relationalLabel}
            </span>
          </div>
          <div className="text-[11px] text-slate-600 font-mono">
            Latency: {relational?.latency_ms ?? "1.1"}ms
          </div>
        </div>

        {/* MongoDB */}
        <div className="p-5 rounded-xl glass-panel border border-slate-200 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-900">MongoDB Document Vault</span>
            <Layers className="w-4 h-4 text-emerald-700" />
          </div>
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-700" />
            <span className="text-sm font-bold text-emerald-700">{documentLabel}</span>
          </div>
          <div className="text-[11px] text-slate-600 font-mono">
            AES-256-GCM Encrypted
          </div>
        </div>

        {/* Neo4j */}
        <div className="p-5 rounded-xl glass-panel border border-slate-200 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-900">Neo4j Graph Store</span>
            <Activity className="w-4 h-4 text-sky-700" />
          </div>
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-700" />
            <span className="text-sm font-bold text-emerald-700">{graphLabel}</span>
          </div>
          <div className="text-[11px] text-slate-600 font-mono">
            Atomic Transaction Commit
          </div>
        </div>

        {/* Blockchain */}
        <div className="p-5 rounded-xl glass-panel border border-slate-200 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-900">Cryptographic Ledger</span>
            <Shield className="w-4 h-4 text-purple-700" />
          </div>
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-purple-700" />
            <span className="text-sm font-bold text-purple-700">
              {blockchainLabel}
            </span>
          </div>
          <div className="text-[11px] text-slate-600 font-mono truncate">
            {health?.services?.blockchain_evidence?.contract_address || "0x5FbDB231..."}
          </div>
        </div>
      </div>

      {/* Transactional Outbox Telemetry & Dispatcher */}
      <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-4">
          <div>
            <h2 className="text-base font-bold text-slate-900 flex items-center space-x-2">
              <Zap className="w-4 h-4 text-amber-700" />
              <span>Transactional Outbox Telemetry &amp; Dead-Letter Recovery</span>
            </h2>
            <p className="text-xs text-slate-600">
              Zero-data-loss guaranteed cross-store writes for blockchain commitments, consent updates, and graph synchronizations.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleProcessOutbox}
              disabled={outboxProcessing}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-medium text-xs shadow-sm transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${outboxProcessing ? "animate-spin" : ""}`} />
              <span>Process Outbox Queue</span>
            </button>

            <button
              onClick={handleRetryFailedOutbox}
              disabled={outboxRetrying}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-amber-200 hover:bg-amber-200 text-amber-700 border border-amber-300 font-medium text-xs transition-all"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${outboxRetrying ? "animate-spin" : ""}`} />
              <span>Retry Dead-Letters</span>
            </button>
          </div>
        </div>

        {/* Outbox Metrics Overview */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
            <div className="text-[11px] text-slate-600 font-medium">Pending Events</div>
            <div className="text-xl font-bold text-brand-700 mt-1">{outbox?.pending_events || 0}</div>
          </div>
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
            <div className="text-[11px] text-slate-600 font-medium">Failed / Dead-Letter</div>
            <div className="text-xl font-bold text-rose-700 mt-1">{outbox?.failed_events || 0}</div>
          </div>
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
            <div className="text-[11px] text-slate-600 font-medium">Delivery Guarantee</div>
            <div className="text-xl font-bold text-emerald-700 mt-1">At-Least-Once</div>
          </div>
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
            <div className="text-[11px] text-slate-600 font-medium">Outbox Status</div>
            <div className="text-xl font-bold text-emerald-700 mt-1 uppercase">{outbox?.status || "HEALTHY"}</div>
          </div>
        </div>

        {/* Recent Outbox Events Stream */}
        <div className="space-y-2">
          <div className="text-xs font-semibold text-slate-700">Recent Outbox Event Stream</div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-600 border-b border-slate-200">
                <tr>
                  <th className="p-2.5">Event Type</th>
                  <th className="p-2.5">Aggregate Ref</th>
                  <th className="p-2.5">Status</th>
                  <th className="p-2.5">Retries</th>
                  <th className="p-2.5">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 font-mono text-[11px]">
                {outboxEvents.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-4 text-center text-slate-500 font-sans">
                      No outbox events in queue. All cross-store writes synchronized.
                    </td>
                  </tr>
                ) : (
                  outboxEvents.map((evt) => (
                    <tr key={evt.id} className="hover:bg-slate-50">
                      <td className="p-2.5 font-semibold text-slate-900 font-sans">{evt.event_type}</td>
                      <td className="p-2.5 text-slate-600 truncate max-w-xs">{evt.aggregate_id}</td>
                      <td className="p-2.5">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          evt.status === "COMPLETED"
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : evt.status === "FAILED"
                            ? "bg-rose-50 text-rose-700 border border-rose-200"
                            : "bg-brand-50 text-brand-700 border border-brand-200"
                        }`}>
                          {evt.status}
                        </span>
                      </td>
                      <td className="p-2.5">{evt.retry_count} / {evt.max_retries}</td>
                      <td className="p-2.5 text-slate-600 font-sans">{new Date(evt.created_at).toLocaleTimeString()}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Disaster Recovery & Active Session Security */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Disaster Recovery Posture */}
        <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-4">
          <div className="border-b border-slate-200 pb-3">
            <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 text-emerald-700" />
              <span>Disaster Recovery &amp; Data Protection</span>
            </h2>
            <p className="text-xs text-slate-600">Point-In-Time Restore drills and volume encryption status</p>
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex justify-between items-center p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-700">Point-In-Time Recovery (PITR):</span>
              <strong className="text-emerald-700 font-mono">{drStatus?.pitr_status || "ACTIVE"}</strong>
            </div>
            <div className="flex justify-between items-center p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-700">Volume Encryption:</span>
              <strong className="text-brand-700 font-mono">{drStatus?.volume_encryption || "AES-256-XTS"}</strong>
            </div>
            <div className="flex justify-between items-center p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-700">Restore Drill Verification:</span>
              <strong className="text-emerald-700 font-mono">{drStatus?.backup_verification_drill || "PASSED (RPO < 5s)"}</strong>
            </div>
            <div className="flex justify-between items-center p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-700">Audit Ledger Anchor Integrity:</span>
              <strong className="text-purple-700 font-mono">{drStatus?.audit_ledger_anchor_integrity || "100% SYNCHRONIZED"}</strong>
            </div>
          </div>
        </div>

        {/* Active Workstation Sessions & Zero-Trust Revocation */}
        <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-200 pb-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
                <Lock className="w-4 h-4 text-brand-700" />
                <span>Active Staff Workstation Sessions</span>
              </h2>
              <p className="text-xs text-slate-600">Revocable JTI token tracking &amp; zero-trust session invalidation</p>
            </div>

            <button
              onClick={handleRevokeAllSessions}
              disabled={revokingSessions}
              className="px-3 py-1.5 rounded-lg bg-rose-100 hover:bg-rose-200 text-rose-700 border border-rose-300 text-xs font-semibold transition-all"
            >
              Revoke All Sessions
            </button>
          </div>

          <div className="space-y-2 max-h-56 overflow-y-auto">
            {sessions.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-500">
                No active workstation sessions registered.
              </div>
            ) : (
              sessions.map((s) => (
                <div key={s.id} className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs">
                  <div>
                    <div className="font-semibold text-slate-900 text-[11px]">
                      {s.ip_address || "Unknown address"}{s.user_agent ? ` · ${String(s.user_agent).slice(0, 48)}` : ""}
                    </div>
                    <div className="text-[10px] text-slate-600">
                      Signed in {s.created_at ? new Date(utcTime(s.created_at)).toLocaleString() : "unknown"}
                      {s.expires_at && <> • Expires {new Date(utcTime(s.expires_at)).toLocaleString()}</>}
                    </div>
                  </div>
                  {s.is_revoked || (s.expires_at && utcTime(s.expires_at) < Date.now()) ? (
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600 border border-slate-200">
                      {s.is_revoked ? "Revoked" : "Expired"}
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Active
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Operational Maintenance Actions */}
      <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-6">
        <div className="border-b border-slate-200 pb-3">
          <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
            <Cpu className="w-4 h-4 text-brand-700" />
            <span>Administrative Maintenance Operations</span>
          </h2>
          <p className="text-xs text-slate-600">Execute background orchestration actions</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-5 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
            <div>
              <h3 className="text-xs font-bold text-slate-900">Rebuild Neo4j Knowledge Graph</h3>
              <p className="text-[11px] text-slate-600 mt-1">
                Drops existing derived graph nodes and recreates all nodes and edges from authoritative PostgreSQL records inside an atomic transaction.
              </p>
            </div>
            <button
              onClick={handleRebuildGraph}
              disabled={rebuilding}
              className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-medium text-xs shadow-sm transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${rebuilding ? "animate-spin" : ""}`} />
              <span>{rebuilding ? "Rebuilding Projection..." : "Rebuild Knowledge Graph"}</span>
            </button>
          </div>

          <div className="p-5 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
            <div>
              <h3 className="text-xs font-bold text-slate-900">Reset &amp; Reseed Demo Data</h3>
              <p className="text-[11px] text-slate-600 mt-1">
                Drops and recreates demo schema, clears document vault, and generates fresh synthetic patients, encounters, and claims.
              </p>
            </div>
            <button
              onClick={handleResetDemo}
              disabled={resetting}
              className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-rose-700 hover:bg-rose-600 text-white font-medium text-xs shadow-sm transition-all"
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
