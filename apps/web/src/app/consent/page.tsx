"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import { CONSENT_SCOPE_LABELS, scopeLabel } from "@/lib/consentScopes";
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
  const [selectedScopes, setSelectedScopes] = useState<Record<string, string[]>>({});
  const [validDays, setValidDays] = useState<Record<string, number>>({});

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
      const request = requests.find((item) => item.id === requestId);
      const scopes = selectedScopes[requestId] ?? request?.requested_scopes ?? [];
      if (decision === "APPROVED" && scopes.length === 0) {
        alert("Select at least one scope to grant access.");
        return;
      }
      await ApiClient.decideAccessRequest(requestId, decision, validDays[requestId] ?? 30, decision === "APPROVED" ? scopes : undefined);
      await loadData();
    } catch (err: any) {
      alert(`Decision error: ${err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevoke = async (consentId: string) => {
    if (!confirm("Revoke this consent? New research authorization checks will be denied. Work that is already running may finish.")) {
      return;
    }
    setActionLoading(consentId);
    try {
      const result = await ApiClient.revokeConsent(consentId);
      if (result.chain_status === "QUEUED") {
        alert("Consent revoked. New research access is denied immediately; the revocation evidence is queued for the blockchain ledger.");
      } else {
        alert(`Consent revoked in MedChain. Blockchain status: ${result.chain_status || "UNKNOWN"}.`);
      }
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
        <h1 className="text-2xl font-bold text-slate-900 flex items-center space-x-2.5">
          <KeyRound className="w-6 h-6 text-brand-600" />
          <span>Consent & sharing</span>
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Choose which research projects may use your data, for how long, and withdraw at any time.
        </p>
      </div>

      {/* Pending Access Requests Section */}
      <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-4">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 pb-3">
          <div className="flex items-center gap-2 min-w-0">
            <Clock className="w-4 h-4 shrink-0 text-amber-700" aria-hidden="true" />
            <h2 className="text-sm font-bold text-slate-900">Research access requests</h2>
          </div>
          {pendingRequests.length > 0 && (
            <span className="shrink-0 whitespace-nowrap px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
              {pendingRequests.length} to decide
            </span>
          )}
        </div>

        {loading ? (
          <div className="text-xs text-slate-600 text-center py-6">Checking access requests...</div>
        ) : pendingRequests.length === 0 ? (
          <div className="text-xs text-slate-600 text-center py-6">
            No pending requests awaiting your decision.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {pendingRequests.map((req) => (
              <div key={req.id} className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">{req.project_title || "Research Initiative"}</h3>
                  <p className="text-xs text-slate-600 mt-0.5">{req.purpose}</p>
                </div>

                <fieldset className="space-y-2">
                  <legend className="text-xs font-semibold text-slate-700 mb-1.5">What you are sharing</legend>
                  <div className="grid grid-cols-1 gap-1">
                    {req.requested_scopes?.map((sc: string) => {
                      const selected = selectedScopes[req.id] ?? req.requested_scopes;
                      const info = CONSENT_SCOPE_LABELS[sc];
                      return (
                        <label key={sc} className="flex items-start gap-2.5 rounded-lg px-2 py-2 -mx-2 cursor-pointer hover:bg-white">
                          <input
                            type="checkbox"
                            checked={selected.includes(sc)}
                            onChange={(event) => setSelectedScopes((current) => {
                              const next = current[req.id] ?? req.requested_scopes;
                              return { ...current, [req.id]: event.target.checked ? [...next, sc] : next.filter((scope: string) => scope !== sc) };
                            })}
                            className="mt-0.5 h-4 w-4 shrink-0 accent-brand-600"
                          />
                          <span className="min-w-0">
                            <span className="block text-sm text-slate-900">{info?.label ?? scopeLabel(sc)}</span>
                            <span className="block text-xs text-slate-500">
                              {info?.detail && <>{info.detail} · </>}
                              <span className="font-mono text-[11px]">{sc}</span>
                            </span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </fieldset>

                <label className="flex items-center justify-between gap-3 text-xs text-slate-700">
                  For how long
                  <select
                    value={validDays[req.id] ?? 30}
                    onChange={(event) => setValidDays((current) => ({ ...current, [req.id]: Number(event.target.value) }))}
                    className="rounded-lg bg-white border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
                  >
                    {[30, 90, 180, 365].map((days) => <option key={days} value={days}>{days} days</option>)}
                  </select>
                </label>

                <div className="pt-2 border-t border-slate-200 flex items-center justify-end space-x-2">
                  <button
                    onClick={() => handleDecision(req.id, "REJECTED")}
                    disabled={actionLoading === req.id}
                    className="flex items-center space-x-1 px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-medium active:scale-95 transition-all"
                  >
                    <X className="w-3.5 h-3.5 text-rose-700" />
                    <span>Reject</span>
                  </button>
                  <button
                    onClick={() => handleDecision(req.id, "APPROVED")}
                    disabled={actionLoading === req.id}
                    className="flex items-center space-x-1 px-3.5 py-1.5 rounded-lg bg-brand-700 hover:bg-brand-600 text-white text-xs font-medium transition-all shadow-sm"
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
      <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-slate-200 pb-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-700" aria-hidden="true" />
            <h2 className="text-sm font-bold text-slate-900">Active consents ({activeConsents.length})</h2>
          </div>
          <span className="text-xs text-slate-600">Checked again before every research query</span>
        </div>

        {activeConsents.length === 0 ? (
          <div className="text-xs text-slate-600 text-center py-8">
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
                  className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-1.5 max-w-xl">
                    <div className="flex items-start justify-between gap-3 md:justify-start">
                      <h3 className="text-sm font-semibold text-slate-900">{c.project_title || "Research Study"}</h3>
                      <span
                        className={`shrink-0 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide border ${
                          isExpired ? "bg-slate-100 text-slate-700 border-slate-300" : "bg-emerald-50 text-emerald-700 border-emerald-200"
                        }`}
                      >
                        {isExpired ? "Expired" : "Active"}
                      </span>
                    </div>

                    <p className="text-xs text-slate-600">{c.purpose}</p>

                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      <span className="text-xs text-slate-600">Sharing:</span>
                      {scopes.map((sc: string, idx: number) => (
                        <span
                          key={idx}
                          title={sc}
                          className="px-2 py-0.5 rounded bg-white text-slate-800 border border-slate-300 text-xs"
                        >
                          {scopeLabel(sc)}
                        </span>
                      ))}
                    </div>

                    <div className="text-xs text-slate-600 flex flex-wrap items-center gap-x-3 gap-y-1 pt-1">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" aria-hidden="true" />
                        <span>{isExpired ? "Expired" : "Valid until"} {new Date(c.valid_until).toLocaleDateString(undefined, { dateStyle: "medium" })}</span>
                      </span>
                      <span className="font-mono text-[11px] text-purple-700">
                        Grant Tx: {c.chain_tx_hash ? c.chain_tx_hash.slice(0, 16) + "..." : "Not anchored"}
                      </span>
                    </div>
                  </div>

                  <div className="shrink-0 flex items-center">
                    <button
                      onClick={() => handleRevoke(c.id)}
                      disabled={actionLoading === c.id}
                      className="flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-300 text-xs font-semibold active:scale-95 transition-all"
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
        <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-4">
          <div className="flex items-center space-x-2 border-b border-slate-200 pb-3">
            <Ban className="w-4 h-4 text-rose-700" />
            <h2 className="text-sm font-bold text-slate-900">Revoked Consent Audit Archive ({revokedConsents.length})</h2>
          </div>

          <div className="space-y-2">
            {revokedConsents.map((rc) => (
              <div
                key={rc.id}
                className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs"
              >
                <div>
                  <span className="font-semibold text-slate-700">{rc.project_title}</span>
                  <span className="text-[11px] text-slate-600 ml-2">
                    Revoked on: {new Date(rc.revoked_at || rc.valid_until).toLocaleString()}
                  </span>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-rose-50 text-rose-700 border border-rose-200">
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
