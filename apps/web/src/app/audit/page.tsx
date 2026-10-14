"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  ScrollText,
  ShieldCheck,
  ShieldAlert,
  Search,
  ExternalLink,
  Clock,
  Layers,
  Filter,
} from "lucide-react";

export default function AuditPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [decisionFilter, setDecisionFilter] = useState<"ALL" | "GRANTED" | "DENIED">("ALL");

  const loadAudit = async () => {
    setLoading(true);
    try {
      const data = await ApiClient.getAuditEvents();
      setEvents(data);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAudit();
  }, []);

  const filteredEvents = events.filter((e) => {
    const matchesSearch =
      (e.actor_email && e.actor_email.toLowerCase().includes(search.toLowerCase())) ||
      (e.action && e.action.toLowerCase().includes(search.toLowerCase())) ||
      (e.reason_code && e.reason_code.toLowerCase().includes(search.toLowerCase()));

    const matchesDecision = decisionFilter === "ALL" || e.decision === decisionFilter;
    return matchesSearch && matchesDecision;
  });

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
            <ScrollText className="w-6 h-6 text-cyan-400" />
            <span>Immutable Audit Trail & Ledger Commitments</span>
          </h1>
          <p className="text-xs text-slate-400">
            Append-only record of all authorized and denied sensitive healthcare data access attempts
          </p>
        </div>
      </div>

      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
        {/* Filters */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Filter by actor, action, or reason..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-400 focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div className="flex items-center space-x-2 text-xs">
            <span className="text-slate-400">Decision:</span>
            <button
              onClick={() => setDecisionFilter("ALL")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors ${
                decisionFilter === "ALL"
                  ? "bg-slate-800 text-white border border-slate-700"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              All
            </button>
            <button
              onClick={() => setDecisionFilter("GRANTED")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors ${
                decisionFilter === "GRANTED"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Granted Only
            </button>
            <button
              onClick={() => setDecisionFilter("DENIED")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors ${
                decisionFilter === "DENIED"
                  ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Denied Only
            </button>
          </div>
        </div>

        {/* Audit Log Table */}
        <div className="overflow-x-auto pt-2">
          {loading ? (
            <div className="text-xs text-slate-400 text-center py-16">Loading audit events...</div>
          ) : filteredEvents.length === 0 ? (
            <div className="text-xs text-slate-400 text-center py-16">No audit records matched filters.</div>
          ) : (
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 uppercase text-[10px] font-semibold">
                  <th className="py-2.5 px-3">Timestamp (UTC)</th>
                  <th className="py-2.5 px-3">Actor Identity</th>
                  <th className="py-2.5 px-3">Requested Action</th>
                  <th className="py-2.5 px-3">Decision</th>
                  <th className="py-2.5 px-3">Policy Reason</th>
                  <th className="py-2.5 px-3 text-right">Ledger Anchor</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {filteredEvents.map((e) => (
                  <tr key={e.id} className="hover:bg-slate-900/40">
                    <td className="py-3 px-3 font-mono text-slate-400 whitespace-nowrap">
                      {new Date(e.occurred_at).toLocaleString()}
                    </td>
                    <td className="py-3 px-3 font-medium text-white">{e.actor_email || e.actor_user_id.slice(0, 10)}</td>
                    <td className="py-3 px-3 font-mono text-cyan-300">{e.action}</td>
                    <td className="py-3 px-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${
                          e.decision === "GRANTED"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                            : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                        }`}
                      >
                        {e.decision === "GRANTED" ? (
                          <ShieldCheck className="w-3 h-3 mr-1" />
                        ) : (
                          <ShieldAlert className="w-3 h-3 mr-1" />
                        )}
                        {e.decision}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-slate-300 max-w-xs truncate" title={e.reason_code}>
                      {e.reason_code}
                    </td>
                    <td className="py-3 px-3 text-right font-mono text-purple-400 text-[11px]">
                      {e.chain_tx_hash ? (
                        <span title={e.chain_tx_hash}>
                          {e.chain_tx_hash.slice(0, 12)}...
                        </span>
                      ) : (
                        <span className="text-slate-400">Local Evidentiary Record</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
