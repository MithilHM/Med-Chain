"use client";

import React, { useEffect, useRef, useState } from "react";
import { Activity, AlertOctagon, BedDouble, FlaskConical, ShieldAlert, Inbox, FileText, KeyRound } from "lucide-react";

interface ClinicalEvent {
  id: string;
  type: string;
  patient_id: string | null;
  occurred_at: string;
  data: Record<string, any>;
}

const EVENT_TYPES = [
  "lab_result.created",
  "lab_result.corrected",
  "encounter.admitted",
  "encounter.discharged",
  "encounter.recorded",
  "encounter.transferred",
  "encounter.cancelled",
  "encounter.discharge_cancelled",
  "patient.merged",
  "patient.registered",
  "patient.updated",
  "document.created",
  "document.amended",
  "consent.revoked",
  "break_glass.granted",
  "integration.needs_review",
];

function describe(event: ClinicalEvent): { label: string; icon: React.ElementType; tone: string } {
  switch (event.type) {
    case "lab_result.created":
    case "lab_result.corrected":
      if (event.data.critical) {
        return { label: `CRITICAL result ${event.data.test_code}`, icon: AlertOctagon, tone: "text-red-700 border-red-300 bg-red-50" };
      }
      return {
        label: `${event.type.endsWith("corrected") ? "Corrected" : "New"} result ${event.data.test_code}${event.data.abnormal ? " (abnormal)" : ""}`,
        icon: FlaskConical,
        tone: event.data.abnormal ? "text-amber-700 border-amber-300 bg-amber-50" : "text-brand-700 border-slate-300 bg-slate-50",
      };
    case "encounter.admitted":
      return { label: `Admitted (${event.data.visit_type ?? "encounter"})`, icon: BedDouble, tone: "text-emerald-700 border-slate-300 bg-slate-50" };
    case "encounter.discharged":
      return { label: "Discharged", icon: BedDouble, tone: "text-slate-700 border-slate-300 bg-slate-50" };
    case "encounter.transferred":
      return { label: `Transferred to ${event.data.location ?? "new location"}`, icon: BedDouble, tone: "text-brand-700 border-slate-300 bg-slate-50" };
    case "encounter.cancelled":
      return { label: "Admission cancelled (entered in error)", icon: BedDouble, tone: "text-slate-600 border-slate-300 bg-slate-50" };
    case "encounter.discharge_cancelled":
      return { label: "Discharge cancelled; patient still admitted", icon: BedDouble, tone: "text-amber-700 border-amber-300 bg-amber-50" };
    case "patient.merged":
      return { label: "Duplicate record merged into this chart", icon: FileText, tone: "text-purple-700 border-slate-300 bg-slate-50" };
    case "break_glass.granted":
      return { label: "Break-the-glass access opened", icon: ShieldAlert, tone: "text-red-700 border-red-300 bg-red-50" };
    case "integration.needs_review":
      return { label: `Interface message needs review: ${event.data.message_type}`, icon: Inbox, tone: "text-amber-700 border-amber-300 bg-amber-50" };
    case "consent.revoked":
      return { label: "Research consent revoked", icon: KeyRound, tone: "text-purple-700 border-slate-300 bg-slate-50" };
    case "document.created":
    case "document.amended":
      return { label: event.type === "document.amended" ? `Document amended (v${event.data.version})` : "New clinical document", icon: FileText, tone: "text-slate-700 border-slate-300 bg-slate-50" };
    default:
      return { label: event.type.replace(".", " "), icon: Activity, tone: "text-slate-700 border-slate-300 bg-slate-50" };
  }
}

/**
 * Real-time feed from /api/v1/events/stream (Server-Sent Events, HttpOnly session cookie).
 * Events contain identifiers and flags only; opening a patient fetches details through the
 * normal access-checked API, which records an audit event.
 */
export default function LiveClinicalFeed() {
  const [events, setEvents] = useState<ClinicalEvent[]>([]);
  const [state, setState] = useState<"connecting" | "live" | "reconnecting">("connecting");
  const sourceRef = useRef<EventSource | null>(null);
  // Bumped to reconnect: a session refresh retires the token this stream was opened with.
  const [connection, setConnection] = useState(0);

  useEffect(() => {
    const source = new EventSource("/api/v1/events/stream", { withCredentials: true });
    sourceRef.current = source;
    source.onopen = () => setState("live");
    source.onerror = () => setState("reconnecting");
    const onEvent = (message: MessageEvent) => {
      try {
        const payload = JSON.parse(message.data) as ClinicalEvent;
        setEvents((current) => [payload, ...current].slice(0, 25));
      } catch {
        // Ignore malformed frames.
      }
    };
    EVENT_TYPES.forEach((type) => source.addEventListener(type, onEvent as EventListener));
    source.addEventListener("session_expired", () => {
      // Reopen with the current cookie; if the user is really signed out, AuthShell sends them to sign in.
      source.close();
      setState("reconnecting");
      setConnection((n) => n + 1);
    });
    return () => source.close();
  }, [connection]);

  const indicator = {
    connecting: "bg-slate-400",
    live: "bg-emerald-500 animate-pulse",
    reconnecting: "bg-amber-500",
  }[state];

  return (
    <div className="bg-white rounded-lg border border-slate-200 shadow-card p-5 space-y-4">
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div className="flex items-center space-x-2">
          <Activity className="w-4 h-4 text-brand-700" />
          <h2 className="text-base font-semibold text-slate-900">Live clinical activity</h2>
        </div>
        <div className="flex items-center space-x-2 text-[11px] text-slate-600">
          <span className={`w-2 h-2 rounded-full ${indicator}`} />
          <span>{state}</span>
        </div>
      </div>
      {events.length === 0 ? (
        <p className="text-sm text-slate-500">
          Waiting for admissions, lab results, and alerts for patients in your care. Events arrive from hospital
          HL7 feeds and MedChain activity as they happen.
        </p>
      ) : (
        <ul className="space-y-2 max-h-80 overflow-y-auto pr-1">
          {events.map((event) => {
            const { label, icon: Icon, tone } = describe(event);
            return (
              <li key={`${event.id}-${event.occurred_at}`} className={`flex items-start space-x-3 p-3 rounded-md border ${tone}`}>
                <Icon className="w-4 h-4 mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold">{label}</div>
                  <div className="text-[11px] text-slate-600 truncate">
                    {event.patient_id ? (
                      <a className="underline decoration-dotted hover:text-brand-700" href="/patients">
                        Patient {event.patient_id.slice(0, 8)}
                      </a>
                    ) : "Operations"}
                    {" - "}
                    {new Date(event.occurred_at).toLocaleTimeString()}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
