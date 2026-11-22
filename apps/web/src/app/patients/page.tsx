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
  UserPlus,
  Flame,
  ArrowDownToLine,
  Building2,
  Lock,
  PlusCircle,
  CheckCircle2,
  X,
} from "lucide-react";

export default function PatientsPage() {
  const [patients, setPatients] = useState<any[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modals
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [showBreakGlassModal, setShowBreakGlassModal] = useState(false);
  const [showEncounterModal, setShowEncounterModal] = useState(false);

  // Register Form State
  const [newMrn, setNewMrn] = useState("");
  const [newDob, setNewDob] = useState("1985-06-20");
  const [newSex, setNewSex] = useState("M");
  const [registering, setRegistering] = useState(false);

  // Break-Glass Form State
  const [justification, setJustification] = useState("");
  const [breakGlassSuccess, setBreakGlassSuccess] = useState<string | null>(null);
  const [breakingGlass, setBreakingGlass] = useState(false);

  // Encounter Form State
  const [encounterType, setEncounterType] = useState("Outpatient Consultation");
  const [summaryCode, setSummaryCode] = useState("ENC-CARDIO-01");
  const [creatingEncounter, setCreatingEncounter] = useState(false);

  // Exporting FHIR
  const [exportingFhir, setExportingFhir] = useState(false);

  const loadPatients = async () => {
    setLoading(true);
    setError(null);
    try {
      const pts = await ApiClient.getPatients();
      setPatients(pts);
      if (pts.length > 0 && !selectedPatientId) {
        setSelectedPatientId(pts[0].id);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load patient records");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPatients();
  }, []);

  const loadTimeline = async (id: string) => {
    setTimelineLoading(true);
    try {
      const data = await ApiClient.getPatientTimeline(id);
      setTimeline(data);
    } catch (err: any) {
      setTimeline(null);
    } finally {
      setTimelineLoading(false);
    }
  };

  useEffect(() => {
    if (selectedPatientId) {
      loadTimeline(selectedPatientId);
    }
  }, [selectedPatientId]);

  const handleRegisterPatient = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMrn.trim()) return;
    setRegistering(true);
    try {
      const res = await ApiClient.registerPatient({
        display_code: newMrn.trim(),
        date_of_birth: newDob,
        sex: newSex,
      });
      setShowRegisterModal(false);
      setNewMrn("");
      await loadPatients();
      if (res?.id) {
        setSelectedPatientId(res.id);
      }
    } catch (err: any) {
      alert(`Patient registration failed: ${err.message}`);
    } finally {
      setRegistering(false);
    }
  };

  const handleBreakGlass = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPatientId || !justification.trim()) return;
    setBreakingGlass(true);
    try {
      const res = await ApiClient.breakGlassEmergency(selectedPatientId, justification);
      setBreakGlassSuccess(`Emergency access granted for 4 hours. Audit event logged (${res.logged_at}).`);
      setTimeout(() => {
        setShowBreakGlassModal(false);
        setBreakGlassSuccess(null);
        setJustification("");
      }, 2000);
      loadTimeline(selectedPatientId);
    } catch (err: any) {
      alert(`Break-glass override failed: ${err.message}`);
    } finally {
      setBreakingGlass(false);
    }
  };

  const handleCreateEncounter = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPatientId) return;
    setCreatingEncounter(true);
    try {
      await ApiClient.createVisit({
        patient_id: selectedPatientId,
        doctor_id: timeline?.visits?.[0]?.doctor_id || "demo-doctor",
        hospital_id: timeline?.visits?.[0]?.hospital_id || "demo-hospital",
        visit_type: encounterType,
        summary_code: summaryCode,
      });
      setShowEncounterModal(false);
      loadTimeline(selectedPatientId);
    } catch (err: any) {
      alert(`Encounter creation error: ${err.message}`);
    } finally {
      setCreatingEncounter(false);
    }
  };

  const handleExportFhir = async () => {
    if (!selectedPatientId) return;
    setExportingFhir(true);
    try {
      const bundle = await ApiClient.exportPatientFhir(selectedPatientId);
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(bundle, null, 2));
      const downloadAnchor = document.createElement("a");
      downloadAnchor.setAttribute("href", dataStr);
      downloadAnchor.setAttribute("download", `FHIR_R4_Patient_${timeline?.patient?.display_code || "record"}.json`);
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
    } catch (err: any) {
      alert(`FHIR Export failed: ${err.message}`);
    } finally {
      setExportingFhir(false);
    }
  };

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
          Tip: Researchers and Insurance Analysts are restricted from querying raw patient timelines. Use the staff role switcher in the top right to switch to <strong>Attending Physician</strong> or <strong>Patient</strong>.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Title & Action Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
            <Users className="w-6 h-6 text-cyan-400" />
            <span>Patient EHR & Clinical Encounters</span>
          </h1>
          <p className="text-xs text-slate-400">
            Authoritative normalized relational records with HL7 FHIR R4 interoperability & emergency break-glass
          </p>
        </div>

        <div className="flex items-center space-x-2.5">
          <button
            onClick={() => setShowRegisterModal(true)}
            className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs shadow-md shadow-cyan-500/20 active:scale-95 transition-all"
          >
            <UserPlus className="w-3.5 h-3.5" />
            <span>Register Patient</span>
          </button>

          {selectedPatientId && (
            <>
              <button
                onClick={() => setShowBreakGlassModal(true)}
                className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 text-xs font-semibold active:scale-95 transition-all"
                title="Emergency department break-glass access override with mandatory audit log"
              >
                <Flame className="w-3.5 h-3.5 text-amber-400" />
                <span>Emergency Break-Glass</span>
              </button>

              <button
                onClick={handleExportFhir}
                disabled={exportingFhir}
                className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium active:scale-95 transition-all"
                title="Download compliant HL7 FHIR R4 Bundle JSON"
              >
                <ArrowDownToLine className="w-3.5 h-3.5 text-teal-400" />
                <span>{exportingFhir ? "Exporting..." : "Export FHIR R4"}</span>
              </button>
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Searchable Patient Directory */}
        <div className="lg:col-span-4 glass-panel p-4 rounded-2xl border border-slate-800 space-y-4">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <input
              type="text"
              placeholder="Search by MRN or code (e.g. PT-100201)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-900/80 border border-slate-800 text-xs text-white placeholder-slate-400 focus:outline-none focus:border-cyan-500/50"
            />
          </div>

          <div className="space-y-2 max-h-[640px] overflow-y-auto pr-1">
            {loading ? (
              <div className="text-xs text-slate-400 text-center py-8">Loading patient directory...</div>
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
                      {p.display_name && <div className="text-xs font-semibold text-white">{p.display_name}</div>}
                      <div className="text-xs font-bold text-white font-mono flex items-center gap-1.5">
                        <span>{p.display_code}</span>
                        <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">MRN</span>
                        {p.record_status === "MERGED" && (
                          <span className="text-[10px] px-1.5 rounded bg-purple-950 text-purple-300 border border-purple-800">merged</span>
                        )}
                      </div>
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
                    {timeline.patient.display_name && (
                      <div className="text-sm font-bold text-white">{timeline.patient.display_name}</div>
                    )}
                    <div className="text-sm font-bold text-white font-mono flex items-center gap-2">
                      <span>{timeline.patient.display_code}</span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono border ${timeline.patient.record_status === "MERGED"
                        ? "bg-purple-950 text-purple-300 border-purple-800" : "bg-emerald-950 text-emerald-300 border-emerald-800"}`}>
                        {timeline.patient.record_status === "MERGED" ? "Merged record (read-only)" : "Active Patient"}
                      </span>
                    </div>
                    <div className="text-xs text-slate-400">
                      DOB: {timeline.patient.date_of_birth} ({new Date().getFullYear() - new Date(timeline.patient.date_of_birth).getFullYear()} yrs) • Sex: {timeline.patient.sex} • Facility: Metropolitan General
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowEncounterModal(true)}
                    className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs font-semibold hover:bg-cyan-500/30 transition-colors"
                  >
                    <PlusCircle className="w-3.5 h-3.5" />
                    <span>New Encounter</span>
                  </button>
                </div>
              </div>

              {/* Observed Adverse Events if any */}
              {timeline.adverse_events?.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center space-x-1.5">
                    <AlertCircle className="w-3.5 h-3.5" />
                    <span>Reported Adverse Events (Observational Association)</span>
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
                  <span>Clinical Encounters ({timeline.visits?.length || 0})</span>
                </h3>

                {timeline.visits?.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-400 border border-dashed border-slate-800 rounded-xl">
                    No clinical encounters recorded for this patient.
                  </div>
                ) : (
                  <div className="space-y-4">
                    {timeline.visits.map((v: any) => (
                      <div key={v.id} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
                          <div className="flex items-center space-x-2">
                            <Stethoscope className="w-4 h-4 text-cyan-400" />
                            <span className="text-xs font-bold text-white">{v.visit_type}</span>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                              {v.summary_code || "ENC"}
                            </span>
                          </div>
                          <div className="text-xs text-slate-400 flex items-center space-x-3">
                            <span>{new Date(v.visit_at).toLocaleDateString()}</span>
                            <span>•</span>
                            <span>{v.doctor_name || "Attending Physician"}</span>
                            <span>•</span>
                            <span className="font-medium text-slate-300">{v.hospital_name || "Hospital Facility"}</span>
                          </div>
                        </div>

                        {/* Diagnoses */}
                        {v.diagnoses?.length > 0 && (
                          <div className="space-y-1">
                            <span className="text-[10px] uppercase font-bold text-slate-400">Diagnoses:</span>
                            <div className="flex flex-wrap gap-2">
                              {v.diagnoses.map((d: any) => (
                                <span
                                  key={d.id}
                                  className="text-xs px-2.5 py-1 rounded-lg bg-cyan-950/60 text-cyan-200 border border-cyan-800/60 flex items-center space-x-1.5"
                                >
                                  <span className="font-mono font-bold text-cyan-400">{d.disease_code}</span>
                                  <span>{d.disease_name}</span>
                                  <span className="text-[10px] text-slate-400">({d.severity})</span>
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Prescriptions */}
                        {v.prescriptions?.length > 0 && (
                          <div className="space-y-1">
                            <span className="text-[10px] uppercase font-bold text-slate-400">Prescriptions:</span>
                            <div className="flex flex-wrap gap-2">
                              {v.prescriptions.map((p: any) => (
                                <span
                                  key={p.id}
                                  className="text-xs px-2.5 py-1 rounded-lg bg-purple-950/60 text-purple-200 border border-purple-800/60 flex items-center space-x-1.5"
                                >
                                  <Pill className="w-3 h-3 text-purple-400" />
                                  <span className="font-medium">{p.medication_name}</span>
                                  <span className="text-[10px] text-slate-400 font-mono">
                                    {p.dose_text} ({p.frequency_text})
                                  </span>
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Lab Results */}
                        {v.lab_results?.length > 0 && (
                          <div className="space-y-1">
                            <span className="text-[10px] uppercase font-bold text-slate-400">Lab Results:</span>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {v.lab_results.map((l: any) => (
                                <div
                                  key={l.id}
                                  className={`p-2 rounded-lg text-xs flex items-center justify-between border ${
                                    l.is_abnormal
                                      ? "bg-rose-950/30 border-rose-800/40 text-rose-200"
                                      : "bg-slate-950/40 border-slate-800 text-slate-300"
                                  }`}
                                >
                                  <div>
                                    <span className="font-medium">{l.test_name}</span>
                                    <span className="text-[10px] text-slate-400 block">Ref: {l.reference_range}</span>
                                  </div>
                                  <div className="text-right">
                                    <span className="font-mono font-bold">
                                      {l.result_value} {l.unit}
                                    </span>
                                    {l.is_abnormal && (
                                      <span className="text-[10px] text-rose-400 block font-semibold">ABNORMAL</span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Register Patient Modal */}
      {showRegisterModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-panel w-full max-w-md rounded-2xl border border-slate-800 shadow-2xl p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-cyan-400" />
                <span>Hospital Clinical Onboarding</span>
              </h2>
              <button onClick={() => setShowRegisterModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleRegisterPatient} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">
                  Medical Record Number (MRN) / Display Code
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. PT-100220 or MRN-8849"
                  value={newMrn}
                  onChange={(e) => setNewMrn(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-400 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">Date of Birth</label>
                  <input
                    type="date"
                    required
                    value={newDob}
                    onChange={(e) => setNewDob(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">Biological Sex</label>
                  <select
                    value={newSex}
                    onChange={(e) => setNewSex(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="M">Male (M)</option>
                    <option value="F">Female (F)</option>
                    <option value="O">Other (O)</option>
                  </select>
                </div>
              </div>

              <div className="text-[11px] text-slate-400 p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                Patient record will be created in PostgreSQL with primary tenant ownership and prepared for HL7 FHIR encounter reconciliation.
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowRegisterModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={registering}
                  className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow-md shadow-cyan-500/20"
                >
                  {registering ? "Registering..." : "Complete Registration"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Emergency Break-Glass Modal */}
      {showBreakGlassModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-panel w-full max-w-lg rounded-2xl border border-amber-900/60 shadow-2xl p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-amber-900/40 pb-3">
              <h2 className="text-base font-bold text-amber-300 flex items-center gap-2">
                <Flame className="w-5 h-5 text-amber-400" />
                <span>Emergency Break-Glass Access Protocol</span>
              </h2>
              <button onClick={() => setShowBreakGlassModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            {breakGlassSuccess ? (
              <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-800 text-emerald-200 text-xs flex items-center space-x-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                <span>{breakGlassSuccess}</span>
              </div>
            ) : (
              <form onSubmit={handleBreakGlass} className="space-y-4">
                <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-800/40 text-xs text-amber-200/90 leading-relaxed">
                  <strong>WARNING:</strong> This action bypasses consent verification for emergency clinical intervention.
                  A permanent, tamper-evident audit record will be logged with your digital signature and dispatched to the Hospital Compliance Officer.
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">
                    Mandatory Clinical Justification (min 10 characters)
                  </label>
                  <textarea
                    required
                    rows={3}
                    placeholder="e.g. Unconscious patient admitted to ER with severe trauma; urgent history of allergies and anticoagulants required..."
                    value={justification}
                    onChange={(e) => setJustification(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-400 focus:outline-none focus:border-amber-500"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowBreakGlassModal(false)}
                    className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-medium"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={breakingGlass || justification.trim().length < 10}
                    className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow-md shadow-amber-500/20 disabled:opacity-50"
                  >
                    {breakingGlass ? "Logging & Authorizing..." : "Authorize Emergency Access"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* New Encounter Modal */}
      {showEncounterModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-panel w-full max-w-md rounded-2xl border border-slate-800 shadow-2xl p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Stethoscope className="w-5 h-5 text-cyan-400" />
                <span>Log Clinical Encounter</span>
              </h2>
              <button onClick={() => setShowEncounterModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateEncounter} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Encounter Type</label>
                <select
                  value={encounterType}
                  onChange={(e) => setEncounterType(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
                >
                  <option value="Outpatient Consultation">Outpatient Consultation</option>
                  <option value="Inpatient Admission">Inpatient Admission</option>
                  <option value="Emergency Evaluation">Emergency Evaluation</option>
                  <option value="Telehealth Review">Telehealth Review</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Clinical Summary Code</label>
                <input
                  type="text"
                  required
                  value={summaryCode}
                  onChange={(e) => setSummaryCode(e.target.value)}
                  placeholder="e.g. ENC-CARDIO-02 or I10-FOLLOWUP"
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowEncounterModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingEncounter}
                  className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow-md shadow-cyan-500/20"
                >
                  {creatingEncounter ? "Saving..." : "Record Encounter"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
