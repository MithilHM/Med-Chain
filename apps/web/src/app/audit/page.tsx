"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import { ScrollText, ShieldCheck, ShieldAlert, Search } from "lucide-react";

type DecisionFilter = "ALL" | "GRANTED" | "DENIED";

const FILTERS: { id: DecisionFilter; label: string; active: string }[] = [
  { id: "ALL", label: "All", active: "bg-slate-100 text-slate-900 border-slate-300" },
  { id: "GRANTED", label: "Granted", active: "bg-emerald-50 text-emerald-800 border-emerald-300" },
  { id: "DENIED", label: "Denied", active: "bg-rose-50 text-rose-800 border-rose-300" },
];

// Times are shown in the viewer's own time zone, and the column header names it.
function timeZoneName() {
  return (
    new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
      .formatToParts(new Date())
      .find((part) => part.type === "timeZoneName")?.value ?? "local time"
  );
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}

function actorOf(e: any) {
  return e.actor_email || e.actor_user_id?.slice(0, 10) || "System";
}

function DecisionBadge({ decision }: { decision: string }) {
  const granted = decision === "GRANTED";
  const Icon = granted ? ShieldCheck : ShieldAlert;
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
        granted ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-rose-50 text-rose-700 border border-rose-200"
      }`}
    >
      <Icon className="w-3 h-3" aria-hidden="true" />
      {granted ? "Granted" : "Denied"}
    </span>
  );
}

function LedgerAnchor({ hash }: { hash?: string | null }) {
  return hash ? (
    <span className="font-mono text-[11px] text-purple-700" title={hash}>
      {hash.slice(0, 12)}…
    </span>
  ) : (
    <span className="text-[11px] text-slate-500">Local record only</span>
  );
}

export default function AuditPage() {
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [decisionFilter, setDecisionFilter] = useState<DecisionFilter>("ALL");
  const [zone, setZone] = useState("local time");

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
    setZone(timeZoneName());
    loadAudit();
  }, []);

  const query = search.toLowerCase();
  const filteredEvents = events.filter((e) => {
    const matchesSearch =
      !query ||
      [e.actor_email, e.action, e.reason_code].some((field) => typeof field === "string" && field.toLowerCase().includes(query));
    const matchesDecision = decisionFilter === "ALL" || e.decision === decisionFilter;
    return matchesSearch && matchesDecision;
  });

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2.5">
          <ScrollText className="w-6 h-6 text-brand-600" aria-hidden="true" />
          <span>Access history</span>
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Every time a record was opened, changed, or refused, with who did it and when.
        </p>
      </div>

      <div className="glass-panel p-4 sm:p-6 rounded-xl space-y-4">
        {/* Filters */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
          <div className="relative flex-1 sm:max-w-sm">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" aria-hidden="true" />
            <input
              type="search"
              aria-label="Filter access history"
              placeholder="Filter by who, action, or reason…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-lg bg-slate-50 border border-slate-200 text-sm sm:text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-brand-500"
            />
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-xs" role="group" aria-label="Filter by decision">
            <span className="text-slate-600 mr-1">Decision:</span>
            {FILTERS.map((filter) => (
              <button
                key={filter.id}
                type="button"
                aria-pressed={decisionFilter === filter.id}
                onClick={() => setDecisionFilter(filter.id)}
                className={`px-3 py-1.5 rounded-lg border font-medium transition-colors ${
                  decisionFilter === filter.id
                    ? filter.active
                    : "border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>

        <div className="pt-2">
          {loading ? (
            <div className="text-sm text-slate-600 text-center py-16">Loading access history…</div>
          ) : filteredEvents.length === 0 ? (
            <div className="text-sm text-slate-600 text-center py-16">
              {events.length === 0 ? "No access has been recorded yet." : "No entries match these filters."}
            </div>
          ) : (
            <>
              {/* Phones: one block per entry, so who, what and the decision are all visible without sideways scrolling. */}
              <ul className="md:hidden divide-y divide-slate-200">
                {filteredEvents.map((e) => (
                  <li key={e.id} className="py-3 space-y-1.5">
                    <div className="flex items-start justify-between gap-3">
                      <span className="min-w-0 text-sm font-medium text-slate-900 break-all">{actorOf(e)}</span>
                      <DecisionBadge decision={e.decision} />
                    </div>
                    <div className="font-mono text-xs text-brand-700 break-all">{e.action}</div>
                    {e.reason_code && <div className="text-xs text-slate-600 break-words">{e.reason_code}</div>}
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
                      <time dateTime={e.occurred_at}>{formatTime(e.occurred_at)}</time>
                      <LedgerAnchor hash={e.chain_tx_hash} />
                    </div>
                  </li>
                ))}
              </ul>

              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-600 uppercase text-[10px] font-semibold tracking-wide">
                      <th scope="col" className="py-2.5 px-3">Time ({zone})</th>
                      <th scope="col" className="py-2.5 px-3">Who</th>
                      <th scope="col" className="py-2.5 px-3">Action</th>
                      <th scope="col" className="py-2.5 px-3">Decision</th>
                      <th scope="col" className="py-2.5 px-3">Policy reason</th>
                      <th scope="col" className="py-2.5 px-3 text-right">Ledger anchor</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 text-slate-700">
                    {filteredEvents.map((e) => (
                      <tr key={e.id} className="hover:bg-slate-50">
                        <td className="py-3 px-3 text-slate-600 whitespace-nowrap">
                          <time dateTime={e.occurred_at}>{formatTime(e.occurred_at)}</time>
                        </td>
                        <td className="py-3 px-3 font-medium text-slate-900">{actorOf(e)}</td>
                        <td className="py-3 px-3 font-mono text-brand-700">{e.action}</td>
                        <td className="py-3 px-3">
                          <DecisionBadge decision={e.decision} />
                        </td>
                        <td className="py-3 px-3 text-slate-700 max-w-xs truncate" title={e.reason_code}>
                          {e.reason_code}
                        </td>
                        <td className="py-3 px-3 text-right">
                          <LedgerAnchor hash={e.chain_tx_hash} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
