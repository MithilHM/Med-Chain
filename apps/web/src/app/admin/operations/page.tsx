"use client";

import React, { useCallback, useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import { AlertTriangle, GitMerge, Inbox, KeyRound, RefreshCw, Send, ShieldAlert } from "lucide-react";

const severityTone: Record<string, string> = {
  critical: "text-red-700 border-red-300 bg-red-50",
  warning: "text-amber-700 border-amber-300 bg-amber-50",
  info: "text-slate-700 border-slate-300 bg-slate-50",
};

function Section({ title, icon: Icon, children, action }: { title: string; icon: React.ElementType; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="glass-panel rounded-xl border border-slate-200 p-5 space-y-3">
      <div className="flex items-center gap-2 border-b border-slate-200 pb-2">
        <Icon className="w-4 h-4 text-brand-700" />
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        <div className="ml-auto">{action}</div>
      </div>
      {children}
    </section>
  );
}

const Empty = ({ text }: { text: string }) => <p className="text-xs text-slate-500">{text}</p>;

export default function OperationsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [integration, setIntegration] = useState<any>(null);
  const [reviewQueue, setReviewQueue] = useState<any[]>([]);
  const [merges, setMerges] = useState<any[]>([]);
  const [grants, setGrants] = useState<any[]>([]);
  const [outbox, setOutbox] = useState<any>(null);
  const [encryption, setEncryption] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const safe = <T,>(p: Promise<T>) => p.catch((err) => { setError(err.message); return null; });
    const [a, i, q, m, g, o, e] = await Promise.all([
      safe(ApiClient.getAlerts()), safe(ApiClient.getIntegrationStatus()), safe(ApiClient.getInboundMessages("NEEDS_REVIEW")),
      safe(ApiClient.getMergeRequests()), safe(ApiClient.getBreakGlassGrants()), safe(ApiClient.getOutboxDelivery("FAILED")),
      safe(ApiClient.getEncryptionStatus()),
    ]);
    setAlerts(a ?? []); setIntegration(i); setReviewQueue(q ?? []); setMerges(m ?? []);
    setGrants(g ?? []); setOutbox(o); setEncryption(e);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const act = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const button = "text-xs px-2.5 py-1 rounded-lg border transition-colors disabled:opacity-50";

  return (
    <div className="space-y-6">
      <div className="flex items-center">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Operations</h1>
          <p className="text-sm text-slate-600">Alerts, interface review queue, merges, emergency-access reviews, and ledger delivery.</p>
        </div>
        <button onClick={() => void load()} className="ml-auto flex items-center gap-1 text-xs text-brand-700 hover:text-brand-800">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</p>}

      <Section title="Open alerts" icon={AlertTriangle}
        action={<button disabled={busy === "eval"} onClick={() => act("eval", ApiClient.evaluateAlerts)}
          className={`${button} border-slate-300 text-slate-700 hover:bg-slate-100`}>Evaluate now</button>}>
        {alerts.length === 0 ? <Empty text="No open alerts." /> : (
          <ul className="space-y-2">
            {alerts.map((a) => (
              <li key={a.id} className={`p-3 rounded-xl border text-xs ${severityTone[a.severity] ?? severityTone.info}`}>
                <div className="font-semibold">{a.summary}</div>
                <div className="text-slate-600">{a.alert_key} · since {new Date(a.first_seen_at).toLocaleString()}
                  {a.notified_at ? " · notified" : ""}</div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Section title="Interface messages needing review" icon={Inbox}>
          {integration && (
            <div className="flex gap-3 text-[11px] text-slate-600">
              {Object.entries(integration.counts ?? {}).map(([k, v]) => <span key={k}>{k}: <b className="text-slate-800">{String(v)}</b></span>)}
              <span className="ml-auto">last message: {integration.last_message_received_at ? new Date(integration.last_message_received_at).toLocaleString() : "none"}</span>
            </div>
          )}
          {reviewQueue.length === 0 ? <Empty text="Nothing waiting for review." /> : (
            <ul className="space-y-2">
              {reviewQueue.map((m) => (
                <li key={m.id} className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-xs space-y-1">
                  <div className="flex gap-2"><b className="text-slate-900">{m.message_type}</b>
                    <span className="text-slate-500">{m.source_system} · {m.message_control_id}</span>
                    <button disabled={busy === m.id} onClick={() => act(m.id, () => ApiClient.reprocessInboundMessage(m.id))}
                      className={`${button} ml-auto border-brand-300 text-brand-700 hover:bg-brand-50`}>Reprocess</button>
                  </div>
                  <div className="text-amber-800">{m.error_detail}</div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Patient merge approvals" icon={GitMerge}>
          {merges.length === 0 ? <Empty text="No pending merges." /> : (
            <ul className="space-y-2">
              {merges.map((m) => (
                <li key={m.id} className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-xs space-y-1">
                  <div className="text-slate-700">Keep <code className="text-brand-700">{m.surviving_patient_id.slice(0, 8)}</code>, retire{" "}
                    <code className="text-rose-700">{m.retiring_patient_id.slice(0, 8)}</code></div>
                  <div className="text-slate-500">{m.reason}</div>
                  <div className="flex gap-2 pt-1">
                    <button disabled={busy === m.id} onClick={() => act(m.id, () => ApiClient.decideMerge(m.id, "approve"))}
                      className={`${button} border-emerald-300 text-emerald-700 hover:bg-emerald-50`}>Approve merge</button>
                    <button disabled={busy === m.id} onClick={() => act(m.id, () => ApiClient.decideMerge(m.id, "reject", "Not the same person"))}
                      className={`${button} border-rose-300 text-rose-700 hover:bg-rose-50`}>Reject</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Break-the-glass reviews" icon={ShieldAlert}>
          {grants.length === 0 ? <Empty text="No emergency access awaiting review." /> : (
            <ul className="space-y-2">
              {grants.map((g) => (
                <li key={g.id} className="p-3 rounded-xl border border-slate-200 bg-slate-50 text-xs space-y-1">
                  <div className="text-slate-700">User <code>{g.user_id.slice(0, 8)}</code> → patient <code>{g.patient_id.slice(0, 8)}</code>
                    <span className={`ml-2 ${g.active ? "text-red-700" : "text-slate-500"}`}>{g.active ? "active" : "expired"}</span></div>
                  <div className="text-slate-600 italic">“{g.justification}”</div>
                  <div className="flex gap-2 pt-1">
                    <button disabled={busy === g.id} onClick={() => act(g.id, () => ApiClient.reviewBreakGlass(g.id, "APPROPRIATE"))}
                      className={`${button} border-emerald-300 text-emerald-700 hover:bg-emerald-50`}>Appropriate</button>
                    <button disabled={busy === g.id} onClick={() => act(g.id, () => ApiClient.reviewBreakGlass(g.id, "INAPPROPRIATE", "Flagged on review"))}
                      className={`${button} border-rose-300 text-rose-700 hover:bg-rose-50`}>Inappropriate (revoke)</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Ledger delivery (outbox)" icon={Send}
          action={<button disabled={busy === "retry" || !outbox?.failed} onClick={() => act("retry", ApiClient.retryFailedOutbox)}
            className={`${button} border-slate-300 text-slate-700 hover:bg-slate-100`}>Retry failed</button>}>
          {outbox && (
            <div className="flex gap-4 text-[11px] text-slate-600">
              {["pending", "processing", "completed", "failed"].map((k) => <span key={k}>{k}: <b className="text-slate-800">{outbox[k]}</b></span>)}
            </div>
          )}
          {(outbox?.events ?? []).length === 0 ? <Empty text="No failed deliveries." /> : (
            <ul className="space-y-1 text-xs">
              {outbox.events.map((e: any) => (
                <li key={e.id} className="flex gap-2"><b className="text-slate-800">{e.event_type}</b>
                  <span className="text-rose-700 truncate">{e.last_error}</span></li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section title="Encryption keys" icon={KeyRound}>
        {encryption ? (
          <div className="text-xs space-y-1 text-slate-700">
            <div>Active key: <b className="text-brand-700">{encryption.active_key_id}</b> · configured: {encryption.configured_key_ids.join(", ")}</div>
            {Object.entries(encryption.fields ?? {}).map(([field, counts]) => (
              <div key={field} className="text-slate-600">{field}: {Object.entries(counts as Record<string, number>).map(([k, v]) => `${k}=${v}`).join(", ") || "none"}</div>
            ))}
          </div>
        ) : <Empty text="Unavailable." />}
      </Section>
    </div>
  );
}
