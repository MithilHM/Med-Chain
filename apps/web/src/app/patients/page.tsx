"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  Users,
  Search,
  Calendar,
  Stethoscope,
  Pill,
  Activity,
  AlertCircle,
  FileText,
  Clock,
  ChevronRight,
  ShieldAlert,
} from "lucide-react";

export default function PatientsPage() {
  const [patients, setPatients] = useState<any[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadPatients() {
      setLoading(true);
      setError(null);
      try {
        const pts = await ApiClient.getPatients();
        setPatients(pts);
        if (pts.length > 0) {
          setSelectedPatientId(pts[0].id);
        }
      } catch (err: any) {
        setError(err.message || "Failed to load patient records");
      } finally {
        setLoading(false);
      }
    }
    loadPatients();
  }, []);

  useEffect(() => {
    if (!selectedPatientId) return;
    async function loadTimeline() {
      setTimelineLoading(true);
      try {
        const data = await ApiClient.getPatientTimeline(selectedPatientId!);
        setTimeline(data);
      } catch (err: any) {
        setTimeline(null);
      } finally {
        setTimelineLoading(false);
      }
    }
    loadTimeline();
  }, [selectedPatientId]);

  const filteredPatients = patients.filter((p) =>
    p.display_code.toLowerCase().includes(search.toLowerCase())
  );

  if (error) {
    return (
      <div className="glass-panel p-8 rounded-2xl border border-rose-900/50 text-center space-y-4">
        <ShieldAlert className="w-12 h-12 text-rose-400 mx-auto" />
        <h2 className="text-xl font-bold text-white">Access Denied by Central Policy Engine</h2>
        <p className="text-sm text-slate-400 max-w-md mx-auto">{error}</p>
        <div className="text-xs text-slate-400">
          Tip: Researchers and Insurance Analysts are restricted from querying raw patient timelines. Use the demo role switcher in the top right to switch to <strong>Doctor</strong> or <strong>Patient</strong>.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
            <Users className="w-6 h-6 text-cyan-400" />
            <span>Patient Records & Clinical Encounters</span>
          </h1>
          <p className="text-xs text-slate-400">Authoritative normalized relational records (PostgreSQL)</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Searchable Patient Directory */}
        <div className="lg:col-span-4 glass-panel p-4 rounded-2xl border border-slate-800 space-y-4">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <input
              type="text"
              placeholder="Search by code (e.g. PT-100201)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-900/80 border border-slate-800 text-xs text-white placeholder-slate-400 focus:outline-none focus:border-cyan-500/50"
            />
          </div>

          <div className="space-y-2 max-h-[640px] overflow-y-auto pr-1">
            {loading ? (
              <div className="text-xs text-slate-400 text-center py-8">Loading patients...</div>
            ) : filteredPatients.length === 0 ? (
              <div className="text-xs text-slate-400 text-center py-8">No matching records found</div>
            ) : (
              filteredPatients.map((p) => {
                const isSelected = p.id === selectedPatientId;
                return (
                  <button
                    key={p.id}
                    onClick={() => setSelectedPatientId(p.id)}
                    className={`w-full p-3.5 rounded-xl border text-left transition-all flex items-center justify-between ${
                      isSelected
                        ? "bg-cyan-500/10 border-cyan-500/40 text-cyan-300 shadow-sm shadow-cyan-500/10"
                        : "bg-slate-900/40 border-slate-800/80 text-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <div>
                      <div className="text-xs font-bold text-white font-mono">{p.display_code}</div>
                      <div className="text-[11px] text-slate-400 flex items-center space-x-2 mt-1">
                        <span>DOB: {p.date_of_birth}</span>
                        <span>•</span>
                        <span>Sex: {p.sex}</span>
                      </div>
                    </div>
                    <ChevronRight className={`w-4 h-4 ${isSelected ? "text-cyan-400" : "text-slate-400"}`} />
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Complete Encounter Timeline */}
        <div className="lg:col-span-8 glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
          {timelineLoading ? (
            <div className="text-xs text-slate-400 text-center py-16">Loading clinical timeline...</div>
          ) : !timeline ? (
            <div className="text-xs text-slate-400 text-center py-16">Select a patient to view encounter history</div>
          ) : (
            <div className="space-y-6">
              {/* Patient Header Card */}
              <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 rounded-xl bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center font-mono font-bold text-cyan-300 text-sm">
                    {timeline.patient.display_code.slice(-3)}
                  </div>
                  <div>
                    <div className="text-sm font-bold text-white font-mono">{timeline.patient.display_code}</div>
                    <div className="text-xs text-slate-400">
                      DOB: {timeline.patient.date_of_birth} ({new Date().getFullYear() - new Date(timeline.patient.date_of_birth).getFullYear()} yrs) • Sex: {timeline.patient.sex}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <span className="px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] font-semibold">
                    Relational ACID Source
                  </span>
                </div>
              </div>

              {/* Observed Adverse Events if any */}
              {timeline.adverse_events?.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center space-x-1.5">
                    <AlertCircle className="w-3.5 h-3.5" />
                    <span>Reported Adverse Events (Observational Associations Only)</span>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {timeline.adverse_events.map((ae: any) => (
                      <div key={ae.id} className="p-3 rounded-xl bg-amber-950/20 border border-amber-800/40 text-xs space-y-1">
                        <div className="font-semibold text-amber-200">{ae.side_effect_name} ({ae.side_effect_code})</div>
                        <div className="text-[11px] text-slate-400">Severity: {ae.severity} • Outcome: {ae.outcome}</div>
                        <div className="text-[10px] text-slate-400 font-mono">Evidence: {ae.evidence_quality}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Encounters Chronological List */}
              <div className="space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
                  <Clock className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Chronological Visits & Clinical Encounters</span>
                </h3>

                {timeline.visits.length === 0 ? (
                  <div className="text-xs text-slate-400 p-6 rounded-xl bg-slate-900/30 border border-slate-800/60 text-center">
                    No encounters recorded for this patient.
                  </div>
                ) : (
                  timeline.visits.map((v: any) => (
                    <div key={v.id} className="p-5 rounded-xl bg-slate-900/50 border border-slate-800/80 space-y-4">
                      <div className="flex flex-wrap items-center justify-between border-b border-slate-800/60 pb-3 gap-2">
                        <div>
                          <div className="text-xs font-bold text-white flex items-center space-x-2">
                            <Stethoscope className="w-3.5 h-3.5 text-cyan-400" />
                            <span>{v.visit_type}</span>
                          </div>
                          <div className="text-[11px] text-slate-400 mt-0.5">
                            Attending: {v.doctor_name || "Staff Physician"} • Facility: {v.hospital_name || "General"}
                          </div>
                        </div>
                        <div className="text-xs text-slate-400 font-mono flex items-center space-x-1">
                          <Calendar className="w-3.5 h-3.5" />
                          <span>{new Date(v.visit_at).toLocaleDateString()}</span>
                        </div>
                      </div>

                      {/* Diagnoses */}
                      {v.diagnoses?.length > 0 && (
                        <div className="space-y-1.5">
                          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Diagnoses</div>
                          <div className="flex flex-wrap gap-2">
                            {v.diagnoses.map((d: any) => (
                              <span
                                key={d.id}
                                className="px-2.5 py-1 rounded-lg bg-sky-950/40 border border-sky-800/50 text-sky-300 text-xs"
                              >
                                <strong>{d.disease_code}</strong>: {d.disease_name} ({d.severity})
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Prescriptions */}
                      {v.prescriptions?.length > 0 && (
                        <div className="space-y-1.5">
                          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide flex items-center space-x-1">
                            <Pill className="w-3 h-3 text-emerald-400" />
                            <span>Prescriptions</span>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                            {v.prescriptions.map((pr: any) => (
                              <div key={pr.id} className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800">
                                <div className="font-semibold text-emerald-300">{pr.medication_name}</div>
                                <div className="text-[11px] text-slate-400">{pr.dose_text} • {pr.frequency_text}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Lab Results */}
                      {v.lab_results?.length > 0 && (
                        <div className="space-y-1.5">
                          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide flex items-center space-x-1">
                            <Activity className="w-3 h-3 text-cyan-400" />
                            <span>Lab Results</span>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                            {v.lab_results.map((l: any) => (
                              <div
                                key={l.id}
                                className={`p-2.5 rounded-lg border ${
                                  l.is_abnormal
                                    ? "bg-rose-950/20 border-rose-800/40 text-rose-300"
                                    : "bg-slate-900/80 border-slate-800 text-slate-300"
                                }`}
                              >
                                <div className="text-[11px] text-slate-400 truncate">{l.test_name}</div>
                                <div className="text-sm font-bold mt-0.5">
                                  {l.result_value} <span className="text-[10px] font-normal">{l.unit}</span>
                                </div>
                                <div className="text-[10px] opacity-75">{l.is_abnormal ? "ABNORMAL" : "Normal"}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
