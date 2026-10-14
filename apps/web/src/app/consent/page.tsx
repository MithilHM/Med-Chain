"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  KeyRound,
  ShieldCheck,
  Check,
  X,
  AlertTriangle,
  Clock,
  ExternalLink,
  Ban,
  Calendar,
  Layers,
} from "lucide-react";

export default function ConsentPage() {
  const [requests, setRequests] = useState<any[]>([]);
  const [consents, setConsents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [reqs, cons] = await Promise.all([
        ApiClient.getAccessRequests(),
        ApiClient.getConsents(),
      ]);
      setRequests(reqs);
      setConsents(cons);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleDecision = async (requestId: string, decision: "APPROVED" | "REJECTED") => {
    setActionLoading(requestId);
    try {
      await ApiClient.decideAccessRequest(requestId, decision, 30);
      await loadData();
    } catch (err: any) {
      alert(`Decision error: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevoke = async (consentId: string) => {
    if (!confirm("Are you sure you want to revoke this consent? All subsequent researcher queries targeting your records will be immediately blocked with HTTP 403.")) {
      return;
    }
    setActionLoading(consentId);
    try {
      await ApiClient.revokeConsent(consentId);
      await loadData();
    } catch (err: any) {
      alert(`Revocation error: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const pendingRequests = requests.filter((r) => r.status === "PENDING");
  const activeConsents = consents.filter((c) => c.status === "GRANTED");
  const revokedConsents = consents.filter((c) => c.status === "REVOKED");

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
          <KeyRound className="w-6 h-6 text-purple-400" />
          <span>Patient Consent Center & Scope Governance</span>
        </h1>
        <p className="text-xs text-slate-400">
          Enforces patient data sovereignty, time-scoped permissions, and tamper-evident blockchain anchors
        </p>
      </div>

      {/* Pending Access Requests Section */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center space-x-2">
            <Clock className="w-4 h-4 text-amber-400" />
            <h2 className="text-sm font-bold text-white">Pending Research Access Requests</h2>
          </div>
          <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            {pendingRequests.length} Action Needed
          </span>
        </div>

        {loading ? (
          <div className="text-xs text-slate-400 text-center py-6">Checking access requests...</div>
        ) : pendingRequests.length === 0 ? (
          <div className="text-xs text-slate-400 text-center py-6">
            No pending requests awaiting your decision.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {pendingRequests.map((req) => (
              <div key={req.id} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                <div>
                  <div className="text-xs font-bold text-white">{req.project_title || "Research Initiative"}</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">{req.purpose}</div>
                </div>

                <div className="space-y-1">
                  <div className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider">
                    Requested Scopes
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {req.requested_scopes?.map((sc: string, idx: number) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20 text-[10px] font-mono"
                      >
                        {sc}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-800/80 flex items-center justify-end space-x-2">
                  <button
                    onClick={() => handleDecision(req.id, "REJECTED")}
                    disabled={actionLoading === req.id}
                    className="flex items-center space-x-1 px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 text-xs font-medium active:scale-95 transition-all"
                  >
                    <X className="w-3.5 h-3.5 text-rose-400" />
                    <span>Reject</span>
                  </button>
                  <button
                    onClick={() => handleDecision(req.id, "APPROVED")}
                    disabled={actionLoading === req.id}
                    className="flex items-center space-x-1 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium active:scale-95 transition-all shadow-md shadow-emerald-500/20"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>{actionLoading === req.id ? "Anchoring..." : "Grant Consent"}</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active Granted Consents Section */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <h2 className="text-sm font-bold text-white">Active Scoped Consents ({activeConsents.length})</h2>
          </div>
          <span className="text-xs text-slate-400">Enforced immediately before each query</span>
        </div>

        {activeConsents.length === 0 ? (
          <div className="text-xs text-slate-400 text-center py-8">
            No active consents currently granted.
          </div>
        ) : (
          <div className="space-y-3">
            {activeConsents.map((c) => {
              const scopes = c.scope_json?.scopes || c.scope_json || [];
              const isExpired = new Date(c.valid_until) < new Date();
              return (
                <div
                  key={c.id}
                  className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-1.5 max-w-xl">
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold text-white">{c.project_title || "Research Study"}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {isExpired ? "EXPIRED" : "ACTIVE"}
                      </span>
                    </div>

                    <div className="text-[11px] text-slate-400">{c.purpose}</div>

                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      <span className="text-[10px] text-slate-400 uppercase font-semibold">Scope:</span>
                      {scopes.map((sc: string, idx: number) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded bg-slate-800/80 text-cyan-300 border border-slate-700 text-[10px] font-mono"
                        >
                          {sc}
                        </span>
                      ))}
                    </div>

                    <div className="text-[11px] text-slate-400 flex items-center space-x-3 pt-1">
                      <span className="flex items-center space-x-1">
                        <Calendar className="w-3 h-3" />
                        <span>Valid Until: {new Date(c.valid_until).toLocaleDateString()}</span>
                      </span>
                      <span>•</span>
                      <span className="font-mono text-[10px] text-purple-400">
                        Tx: {c.chain_tx_hash ? c.chain_tx_hash.slice(0, 16) + "..." : "Local Anchor"}
                      </span>
                    </div>
                  </div>

                  <div className="shrink-0 flex items-center">
                    <button
                      onClick={() => handleRevoke(c.id)}
                      disabled={actionLoading === c.id}
                      className="flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs font-semibold active:scale-95 transition-all"
                    >
                      <Ban className="w-3.5 h-3.5" />
                      <span>{actionLoading === c.id ? "Revoking..." : "Revoke Consent"}</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Revocation History */}
      {revokedConsents.length > 0 && (
        <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
          <div className="flex items-center space-x-2 border-b border-slate-800/80 pb-3">
            <Ban className="w-4 h-4 text-rose-400" />
            <h2 className="text-sm font-bold text-white">Revoked Consent Audit Archive ({revokedConsents.length})</h2>
          </div>

          <div className="space-y-2">
            {revokedConsents.map((rc) => (
              <div
                key={rc.id}
                className="p-3 rounded-xl bg-slate-900/30 border border-slate-800/60 flex items-center justify-between text-xs"
              >
                <div>
                  <span className="font-semibold text-slate-300">{rc.project_title}</span>
                  <span className="text-[11px] text-slate-400 ml-2">
                    Revoked on: {new Date(rc.revoked_at || rc.valid_until).toLocaleString()}
                  </span>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-rose-500/10 text-rose-400 border border-rose-500/20">
                  BLOCKED (HTTP 403)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
