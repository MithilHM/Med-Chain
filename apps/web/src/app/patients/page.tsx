"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  AlertTriangle, ArrowDownToLine, CheckCircle2, Clock, Copy, Flame, FlaskConical, KeyRound, Pencil, Pill,
  PlusCircle, Search, ShieldAlert, Stethoscope, UserPlus, Users, X, UserCog, DoorOpen,
} from "lucide-react";

const input = "w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500";
const label = "text-xs font-semibold text-slate-300 block mb-1";
const primaryButton = "px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-60 text-white text-xs font-semibold";
const ghostButton = "px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-medium";
const ENCOUNTER_TYPES = ["Outpatient Consultation", "Inpatient Admission", "Emergency Evaluation", "Telehealth Review"];

function age(dob: string): number {
  const birth = new Date(dob);
  const now = new Date();
  let years = now.getFullYear() - birth.getFullYear();
  const beforeBirthday = now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate());
  if (beforeBirthday) years -= 1;
  return years;
}

function Modal({ title, icon: Icon, onClose, children, tone = "border-slate-800" }: {
  title: string; icon: React.ElementType; onClose: () => void; children: React.ReactNode; tone?: string;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className={`glass-panel w-full max-w-lg rounded-2xl border ${tone} shadow-2xl p-6 space-y-4 max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h2 className="text-base font-bold text-white flex items-center gap-2"><Icon className="w-5 h-5 text-cyan-400" />{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function OneTimeCode({ code, expires, onClose }: { code: string; expires: string; onClose: () => void }) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-300">Give this patient-portal activation code to the patient in person. They create their account at <code className="text-cyan-300">/signup</code> with this code and their date of birth.</p>
      <div className="flex items-center gap-2">
        <code className="flex-1 text-center text-lg tracking-widest font-mono text-white bg-slate-950 border border-amber-500/40 rounded-xl py-3">{code}</code>
        <button onClick={() => navigator.clipboard.writeText(code)} className="text-cyan-300 text-xs flex items-center gap-1"><Copy className="w-3.5 h-3.5" />Copy</button>
      </div>
      <p className="text-[11px] text-amber-200/80">Shown only once. Expires {new Date(expires).toLocaleString()}.</p>
      <div className="flex justify-end"><button onClick={onClose} className={primaryButton}>Done</button></div>
    </div>
  );
}

export default function PatientsPage() {
  const [role, setRole] = useState<string | null>(null);
  const [patients, setPatients] = useState<any[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Reference data
  const [hospitals, setHospitals] = useState<any[]>([]);
  const [doctors, setDoctors] = useState<any[]>([]);
  const [catalog, setCatalog] = useState<{ diseases: any[]; medications: any[]; labTests: any[] }>({ diseases: [], medications: [], labTests: [] });

  // Modals
  const [modal, setModal] = useState<null | "register" | "edit" | "breakglass" | "encounter" | "careteam" | "allergy">(null);
  const [entry, setEntry] = useState<null | { kind: "diagnosis" | "prescription" | "lab"; visitId: string }>(null);
  const [oneTimeCode, setOneTimeCode] = useState<{ code: string; expires: string } | null>(null);
  const [form, setForm] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const [careTeam, setCareTeam] = useState<any[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  const isAdmin = role === "admin";
  const canChart = role === "doctor" || role === "admin";

  useEffect(() => {
    try {
      setRole(JSON.parse(window.localStorage.getItem("medchain_user") || "null")?.role ?? null);
    } catch {
      setRole(null);
    }
  }, []);

  const loadPatients = useCallback(async (q?: string) => {
    setLoading(true);
    setError(null);
    try {
      const pts = await ApiClient.getPatients(q);
      setPatients(pts);
      setSelectedPatientId((current) => current ?? pts[0]?.id ?? null);
    } catch (err: any) {
      setError(err.message || "Failed to load patient records");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadPatients(); }, [loadPatients]);

  // Server-side search (MRN fragment or exact family name), debounced.
  useEffect(() => {
    const handle = setTimeout(() => { void loadPatients(search.trim() || undefined); }, 300);
    return () => clearTimeout(handle);
  }, [search, loadPatients]);

  useEffect(() => {
    if (!canChart) return;
    const safe = <T,>(p: Promise<T>, fallback: T) => p.catch(() => fallback);
    void (async () => {
      const [d, diseases, medications, labTests, h] = await Promise.all([
        safe(ApiClient.getDoctors(), []), safe(ApiClient.getDiseases(), []), safe(ApiClient.getMedications(), []),
        safe(ApiClient.getLabTests(), []), isAdmin ? safe(ApiClient.getHospitals(), []) : Promise.resolve([]),
      ]);
      setDoctors(d); setHospitals(h); setCatalog({ diseases, medications, labTests });
    })();
  }, [canChart, isAdmin]);

  const loadTimeline = useCallback(async (id: string) => {
    setTimelineLoading(true);
    try {
      setTimeline(await ApiClient.getPatientTimeline(id));
    } catch (err: any) {
      setTimeline(null);
      setActionError(err.message);
    } finally {
      setTimelineLoading(false);
    }
  }, []);

  useEffect(() => { if (selectedPatientId) void loadTimeline(selectedPatientId); }, [selectedPatientId, loadTimeline]);

  const open = (name: typeof modal, initial: Record<string, any> = {}) => {
    setActionError(null);
    setForm(initial);
    setModal(name);
  };
  const close = () => { setModal(null); setEntry(null); setForm({}); };
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? (e.target as HTMLInputElement).checked : e.target.value }));

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setActionError(null);
    try {
      await action();
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const refreshChart = async () => {
    if (selectedPatientId) await loadTimeline(selectedPatientId);
  };

  // ---------------------------------------------------------------- actions
  const submitRegister = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const created = await ApiClient.registerPatient({
        display_code: form.display_code.trim(), date_of_birth: form.date_of_birth, sex: form.sex || "F",
        given_name: form.given_name, family_name: form.family_name, hospital_id: form.hospital_id,
        primary_doctor_id: form.primary_doctor_id || undefined, issue_portal_invitation: !!form.issue_portal_invitation,
      });
      setSearch("");
      await loadPatients();
      setSelectedPatientId(created.id);
      close();
      if (created.portal_activation_code) {
        setOneTimeCode({ code: created.portal_activation_code, expires: created.portal_activation_expires_at });
      } else {
        setNotice(`Registered ${created.display_name || created.display_code}.`);
      }
    });
  };

  const submitEdit = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await ApiClient.updatePatient(selectedPatientId!, {
        given_name: form.given_name, family_name: form.family_name, date_of_birth: form.date_of_birth, sex: form.sex,
      });
      close();
      await loadPatients(search.trim() || undefined);
      await refreshChart();
    });
  };

  const issueCode = () => void run(async () => {
    const res = await ApiClient.issuePortalInvitation(selectedPatientId!);
    setOneTimeCode({ code: res.portal_activation_code, expires: res.expires_at });
  });

  const submitBreakGlass = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const res = await ApiClient.breakGlassEmergency(selectedPatientId!, form.justification);
      close();
      setNotice(`Emergency access granted until ${new Date(res.expires_at).toLocaleTimeString()}. This access is logged for compliance review.`);
      await refreshChart();
    });
  };

  const submitEncounter = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await ApiClient.createVisit({
        patient_id: selectedPatientId, visit_type: form.visit_type || ENCOUNTER_TYPES[0],
        summary_code: form.summary_code || undefined, doctor_id: isAdmin ? form.doctor_id : undefined,
      });
      close();
      await refreshChart();
    });
  };

  const submitEntry = (e: React.FormEvent) => {
    e.preventDefault();
    if (!entry) return;
    void run(async () => {
      if (entry.kind === "diagnosis") {
        await ApiClient.addDiagnosis(entry.visitId, { disease_code: form.disease_code, severity: form.severity || "Moderate", status: form.status || "Active" });
      } else if (entry.kind === "prescription") {
        await ApiClient.addPrescription(entry.visitId, { medication_code: form.medication_code, dose_text: form.dose_text,
          frequency_text: form.frequency_text, end_date: form.end_date || undefined });
      } else {
        await ApiClient.addLabResult(entry.visitId, { lab_test_code: form.lab_test_code, result_value: Number(form.result_value) });
      }
      close();
      await refreshChart();
    });
  };

  const discharge = (visitId: string) => {
    if (!confirm("Close this encounter? Attending access ends after the post-discharge window.")) return;
    void run(async () => { await ApiClient.dischargeVisit(visitId); await refreshChart(); });
  };

  const submitAllergy = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await ApiClient.addAllergy(selectedPatientId!, { substance: form.substance, reaction: form.reaction || undefined, severity: form.severity || "UNKNOWN" });
      close();
      await refreshChart();
    });
  };

  const openCareTeam = () => {
    open("careteam", { relationship_type: "ATTENDING" });
    void ApiClient.getCareTeam(selectedPatientId!).then(setCareTeam).catch((err) => setActionError(err.message));
  };

  const submitCareTeam = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await ApiClient.addCareTeamMember(selectedPatientId!, form.doctor_id, form.relationship_type);
      setCareTeam(await ApiClient.getCareTeam(selectedPatientId!));
      await refreshChart();
    });
  };

  const endCareTeam = (assignmentId: string) => void run(async () => {
    await ApiClient.endCareTeamMember(selectedPatientId!, assignmentId);
    setCareTeam(await ApiClient.getCareTeam(selectedPatientId!));
    await refreshChart();
  });

  const exportFhir = () => void run(async () => {
    const bundle = await ApiClient.exportPatientFhir(selectedPatientId!);
    const anchor = document.createElement("a");
    anchor.href = "data:application/fhir+json;charset=utf-8," + encodeURIComponent(JSON.stringify(bundle, null, 2));
    anchor.download = `FHIR_R4_Patient_${timeline?.patient?.display_code || "record"}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  });

  const selected = timeline?.patient;
  const writable = selected?.record_status !== "MERGED";
  const formatDiagnoses = useMemo(() => catalog.diseases.map((d) => ({ value: d.code, label: `${d.code} · ${d.name}` })), [catalog.diseases]);

  if (error) {
    return (
      <div className="glass-panel p-8 rounded-2xl border border-rose-900/50 text-center space-y-4">
        <ShieldAlert className="w-12 h-12 text-rose-400 mx-auto" />
        <h2 className="text-xl font-bold text-white">Patient records are not available for your role</h2>
        <p className="text-sm text-slate-400 max-w-md mx-auto">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
            <Users className="w-6 h-6 text-cyan-400" />
            <span>{role === "patient" ? "My Health Record" : "Patient Records"}</span>
          </h1>
          <p className="text-xs text-slate-400">
            {isAdmin ? "Register patients, manage care teams, and issue portal access." :
              role === "doctor" ? "Patients on your care team. Use break-the-glass only in an emergency." :
              "Your encounters, results, medications, and allergies."}
          </p>
        </div>
        <div className="flex items-center gap-2.5 flex-wrap">
          {isAdmin && (
            <button onClick={() => open("register", { sex: "F", hospital_id: hospitals[0]?.id, issue_portal_invitation: true })}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs">
              <UserPlus className="w-3.5 h-3.5" /> Register Patient
            </button>
          )}
          {selectedPatientId && role === "doctor" && (
            <button onClick={() => open("breakglass")}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 text-xs font-semibold">
              <Flame className="w-3.5 h-3.5 text-amber-400" /> Emergency Break-Glass
            </button>
          )}
          {selectedPatientId && (
            <button onClick={exportFhir} disabled={busy}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium">
              <ArrowDownToLine className="w-3.5 h-3.5 text-teal-400" /> Export FHIR R4
            </button>
          )}
        </div>
      </div>

      {notice && (
        <div className="flex items-center gap-2 text-xs text-emerald-200 bg-emerald-950/40 border border-emerald-800 rounded-xl px-3 py-2">
          <CheckCircle2 className="w-4 h-4" /> {notice}
          <button onClick={() => setNotice(null)} className="ml-auto text-slate-400"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}
      {actionError && !modal && !entry && (
        <div className="text-xs text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3 py-2">{actionError}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Directory */}
        <div className="lg:col-span-4 glass-panel p-4 rounded-2xl border border-slate-800 space-y-4">
          {role !== "patient" && (
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
              <input type="text" placeholder="Search MRN or family name…" value={search} onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-900/80 border border-slate-800 text-xs text-white placeholder-slate-400 focus:outline-none focus:border-cyan-500/50" />
            </div>
          )}
          <div className="space-y-2 max-h-[640px] overflow-y-auto pr-1">
            {loading ? (
              <div className="text-xs text-slate-400 text-center py-8">Loading patients…</div>
            ) : patients.length === 0 ? (
              <div className="text-xs text-slate-400 text-center py-8">
                {search ? "No matching records." : role === "doctor" ? "No patients are assigned to your care yet." : "No patients registered yet."}
              </div>
            ) : patients.map((p) => (
              <button key={p.id} onClick={() => setSelectedPatientId(p.id)}
                className={`w-full p-3.5 rounded-xl border text-left transition-all ${p.id === selectedPatientId
                  ? "bg-cyan-500/10 border-cyan-500/40" : "bg-slate-900/40 border-slate-800/80 hover:border-slate-700"}`}>
                <div className="text-xs font-semibold text-white">{p.display_name || "Name not recorded"}</div>
                <div className="text-[11px] font-mono text-slate-300 flex items-center gap-1.5">
                  {p.display_code}
                  {p.record_status === "MERGED" && <span className="px-1.5 rounded bg-purple-950 text-purple-300 border border-purple-800">merged</span>}
                  {p.has_portal_account && <span className="px-1.5 rounded bg-slate-800 text-slate-400">portal</span>}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">DOB {p.date_of_birth} · {p.sex}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Chart */}
        <div className="lg:col-span-8 glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
          {timelineLoading ? (
            <div className="text-xs text-slate-400 text-center py-16">Loading chart…</div>
          ) : !timeline ? (
            <div className="text-xs text-slate-400 text-center py-16">Select a patient to view their chart.</div>
          ) : (
            <div className="space-y-6">
              <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-base font-bold text-white">{selected.display_name || "Name not recorded"}</div>
                  <div className="text-xs font-mono text-slate-300 flex items-center gap-2">
                    MRN {selected.display_code}
                    <span className={`text-[10px] px-2 py-0.5 rounded-full border ${writable
                      ? "bg-emerald-950 text-emerald-300 border-emerald-800" : "bg-purple-950 text-purple-300 border-purple-800"}`}>
                      {writable ? "Active record" : "Merged record (read-only)"}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    DOB {selected.date_of_birth} ({age(selected.date_of_birth)} yrs) · Sex {selected.sex}
                    {timeline.facilities?.length > 0 && <> · Seen at {timeline.facilities.join(", ")}</>}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    Care team: {timeline.care_team?.length
                      ? timeline.care_team.map((c: any) => `${c.doctor_name} (${c.relationship_type.toLowerCase().replace("_", " ")})`).join(", ")
                      : <span className="text-amber-300">none assigned</span>}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {canChart && writable && (
                    <button onClick={() => open("encounter", { visit_type: ENCOUNTER_TYPES[0], doctor_id: timeline.care_team?.[0]?.doctor_id })}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs font-semibold">
                      <PlusCircle className="w-3.5 h-3.5" /> New Encounter
                    </button>
                  )}
                  {isAdmin && writable && (
                    <>
                      <button onClick={openCareTeam} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 text-slate-200 border border-slate-700 text-xs">
                        <UserCog className="w-3.5 h-3.5" /> Care team
                      </button>
                      <button onClick={() => open("edit", { given_name: selected.display_name?.split(", ")[1] ?? "",
                        family_name: selected.display_name?.split(", ")[0] ?? "", date_of_birth: selected.date_of_birth, sex: selected.sex })}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 text-slate-200 border border-slate-700 text-xs">
                        <Pencil className="w-3.5 h-3.5" /> Edit details
                      </button>
                      {!selected.has_portal_account && (
                        <button onClick={issueCode} disabled={busy} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 text-slate-200 border border-slate-700 text-xs">
                          <KeyRound className="w-3.5 h-3.5" /> Portal code
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* Allergies */}
              <div className={`p-3 rounded-xl border text-xs ${timeline.allergies?.length ? "bg-rose-950/30 border-rose-800/50" : "bg-slate-900/40 border-slate-800"}`}>
                <div className="flex items-center gap-2">
                  <AlertTriangle className={`w-4 h-4 ${timeline.allergies?.length ? "text-rose-400" : "text-slate-500"}`} />
                  <span className="font-semibold text-white">Allergies</span>
                  {canChart && writable && (
                    <button onClick={() => open("allergy", { severity: "UNKNOWN" })} className="ml-auto text-cyan-300 hover:text-cyan-200">+ Add</button>
                  )}
                </div>
                {timeline.allergies?.length ? (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {timeline.allergies.map((a: any) => (
                      <span key={a.id} className="px-2.5 py-1 rounded-lg bg-rose-900/40 border border-rose-700/50 text-rose-100">
                        <b>{a.substance}</b>{a.reaction ? ` · ${a.reaction}` : ""} · {a.severity.toLowerCase()}
                        {canChart && (
                          <button title="Mark inactive" onClick={() => void run(async () => {
                            await ApiClient.updateAllergyStatus(selectedPatientId!, a.id, "INACTIVE"); await refreshChart();
                          })} className="ml-2 text-rose-300/70 hover:text-white">×</button>
                        )}
                      </span>
                    ))}
                  </div>
                ) : <div className="text-slate-500 mt-1">No known allergies recorded.</div>}
              </div>

              {timeline.adverse_events?.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {timeline.adverse_events.map((ae: any) => (
                    <div key={ae.id} className="p-3 rounded-xl bg-amber-950/20 border border-amber-800/40 text-xs">
                      <div className="font-semibold text-amber-200">Adverse event: {ae.side_effect_name}</div>
                      <div className="text-[11px] text-slate-400">Severity {ae.severity} · Outcome {ae.outcome}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Encounters */}
              <div className="space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-cyan-400" /> Encounters ({timeline.visits?.length || 0})
                </h3>
                {timeline.visits?.length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-400 border border-dashed border-slate-800 rounded-xl">
                    No encounters yet.{canChart && writable ? " Use New Encounter to start one." : ""}
                  </div>
                ) : timeline.visits.map((v: any) => {
                  const open_ = !v.discharged_at;
                  const canEdit = canChart && writable && v.status === "ACTIVE";
                  return (
                    <div key={v.id} className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
                        <div className="flex items-center gap-2">
                          <Stethoscope className="w-4 h-4 text-cyan-400" />
                          <span className="text-xs font-bold text-white">{v.visit_type}</span>
                          {v.summary_code && <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">{v.summary_code}</span>}
                          <span className={`text-[10px] px-2 py-0.5 rounded-full ${open_ ? "bg-emerald-950 text-emerald-300" : "bg-slate-800 text-slate-400"}`}>
                            {open_ ? "open" : `closed ${new Date(v.discharged_at).toLocaleDateString()}`}
                          </span>
                        </div>
                        <div className="text-xs text-slate-400">
                          {new Date(v.visit_at).toLocaleDateString()} · {v.doctor_name || "Attending"} · {v.hospital_name || "—"}
                        </div>
                      </div>

                      {v.diagnoses?.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {v.diagnoses.map((d: any) => (
                            <span key={d.id} className="text-xs px-2.5 py-1 rounded-lg bg-cyan-950/60 text-cyan-200 border border-cyan-800/60">
                              <b className="font-mono text-cyan-400">{d.disease_code}</b> {d.disease_name} <span className="text-[10px] text-slate-400">({d.severity}, {d.status})</span>
                            </span>
                          ))}
                        </div>
                      )}
                      {v.prescriptions?.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {v.prescriptions.map((p: any) => (
                            <span key={p.id} className="text-xs px-2.5 py-1 rounded-lg bg-purple-950/60 text-purple-200 border border-purple-800/60 flex items-center gap-1.5">
                              <Pill className="w-3 h-3 text-purple-400" /> {p.medication_name}
                              <span className="text-[10px] text-slate-400">{p.dose_text}, {p.frequency_text}{p.end_date ? ` until ${p.end_date}` : ""}</span>
                            </span>
                          ))}
                        </div>
                      )}
                      {v.lab_results?.length > 0 && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {v.lab_results.map((l: any) => (
                            <div key={l.id} className={`p-2 rounded-lg text-xs flex items-center justify-between border ${l.is_abnormal
                              ? "bg-rose-950/30 border-rose-800/40 text-rose-200" : "bg-slate-950/40 border-slate-800 text-slate-300"}`}>
                              <div>
                                <span className="font-medium">{l.test_name}</span>
                                <span className="text-[10px] text-slate-400 block">Ref {l.reference_range_text} · {new Date(l.measured_at).toLocaleDateString()}</span>
                              </div>
                              <div className="text-right">
                                <span className="font-mono font-bold">{l.result_value} {l.unit}</span>
                                {l.is_abnormal && <span className="text-[10px] text-rose-400 block font-semibold">ABNORMAL</span>}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                      {canEdit && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          <button onClick={() => { setForm({ severity: "Moderate", status: "Active" }); setEntry({ kind: "diagnosis", visitId: v.id }); }}
                            className="text-[11px] px-2.5 py-1 rounded-lg border border-cyan-800/60 text-cyan-300 hover:bg-cyan-500/10">+ Diagnosis</button>
                          <button onClick={() => { setForm({}); setEntry({ kind: "prescription", visitId: v.id }); }}
                            className="text-[11px] px-2.5 py-1 rounded-lg border border-purple-800/60 text-purple-300 hover:bg-purple-500/10">+ Prescription</button>
                          <button onClick={() => { setForm({}); setEntry({ kind: "lab", visitId: v.id }); }}
                            className="text-[11px] px-2.5 py-1 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 flex items-center gap-1"><FlaskConical className="w-3 h-3" />Lab result</button>
                          {open_ && (
                            <button onClick={() => discharge(v.id)}
                              className="text-[11px] px-2.5 py-1 rounded-lg border border-slate-700 text-slate-400 hover:bg-slate-800 flex items-center gap-1 ml-auto"><DoorOpen className="w-3 h-3" />Close encounter</button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ---------------------------------------------------------- modals */}
      {(modal || entry) && actionError && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] text-xs text-rose-200 bg-rose-950 border border-rose-800 rounded-xl px-4 py-2">{actionError}</div>
      )}

      {modal === "register" && (
        <Modal title="Register patient" icon={UserPlus} onClose={close}>
          <form onSubmit={submitRegister} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><span className={label}>Given name</span><input required value={form.given_name || ""} onChange={set("given_name")} className={input} /></div>
              <div><span className={label}>Family name</span><input required value={form.family_name || ""} onChange={set("family_name")} className={input} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><span className={label}>Date of birth</span><input type="date" required value={form.date_of_birth || ""} onChange={set("date_of_birth")} className={input} /></div>
              <div><span className={label}>Sex</span>
                <select value={form.sex} onChange={set("sex")} className={input}>
                  <option value="F">Female</option><option value="M">Male</option><option value="O">Other</option>
                </select></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><span className={label}>Registering hospital</span>
                <select required value={form.hospital_id || ""} onChange={set("hospital_id")} className={input}>
                  <option value="">Choose…</option>
                  {hospitals.map((h) => <option key={h.id} value={h.id}>{h.name} ({h.facility_code})</option>)}
                </select></div>
              <div><span className={label}>MRN</span><input required value={form.display_code || ""} onChange={set("display_code")} placeholder="as issued by the hospital" className={input} /></div>
            </div>
            <div><span className={label}>Primary doctor (puts the patient on their list)</span>
              <select value={form.primary_doctor_id || ""} onChange={set("primary_doctor_id")} className={input}>
                <option value="">Assign later</option>
                {doctors.map((d) => <option key={d.id} value={d.id}>{d.display_name} · {d.specialty} · {d.hospital_name}</option>)}
              </select></div>
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={!!form.issue_portal_invitation} onChange={set("issue_portal_invitation")} />
              Issue a patient-portal activation code now
            </label>
            {actionError && <p className="text-xs text-rose-300">{actionError}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={close} className={ghostButton}>Cancel</button>
              <button type="submit" disabled={busy} className={primaryButton}>{busy ? "Registering…" : "Register"}</button>
            </div>
          </form>
        </Modal>
      )}

      {modal === "edit" && (
        <Modal title="Correct patient details" icon={Pencil} onClose={close}>
          <form onSubmit={submitEdit} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><span className={label}>Given name</span><input value={form.given_name || ""} onChange={set("given_name")} className={input} /></div>
              <div><span className={label}>Family name</span><input value={form.family_name || ""} onChange={set("family_name")} className={input} /></div>
              <div><span className={label}>Date of birth</span><input type="date" value={form.date_of_birth || ""} onChange={set("date_of_birth")} className={input} /></div>
              <div><span className={label}>Sex</span>
                <select value={form.sex} onChange={set("sex")} className={input}>
                  <option value="F">Female</option><option value="M">Male</option><option value="O">Other</option>
                </select></div>
            </div>
            <p className="text-[11px] text-slate-500">Corrections are audited. Demographics fed from the hospital ADT system may be overwritten by later updates.</p>
            {actionError && <p className="text-xs text-rose-300">{actionError}</p>}
            <div className="flex justify-end gap-2"><button type="button" onClick={close} className={ghostButton}>Cancel</button>
              <button type="submit" disabled={busy} className={primaryButton}>Save</button></div>
          </form>
        </Modal>
      )}

      {modal === "careteam" && (
        <Modal title="Care team" icon={UserCog} onClose={close}>
          <ul className="space-y-2 text-xs">
            {careTeam.length === 0 && <li className="text-slate-500">No care-team history.</li>}
            {careTeam.map((c) => (
              <li key={c.id} className="flex items-center gap-2 p-2 rounded-lg bg-slate-900/60 border border-slate-800">
                <span className={c.active ? "text-white" : "text-slate-500 line-through"}>{c.doctor_name}</span>
                <span className="text-slate-500">{c.relationship_type.toLowerCase().replace("_", " ")} · {c.source.toLowerCase()}</span>
                {c.active && <button onClick={() => endCareTeam(c.id)} disabled={busy} className="ml-auto text-rose-300 hover:text-rose-200">End</button>}
              </li>
            ))}
          </ul>
          <form onSubmit={submitCareTeam} className="grid grid-cols-3 gap-2 items-end">
            <div className="col-span-2"><span className={label}>Doctor</span>
              <select required value={form.doctor_id || ""} onChange={set("doctor_id")} className={input}>
                <option value="">Choose…</option>
                {doctors.map((d) => <option key={d.id} value={d.id}>{d.display_name} · {d.specialty}</option>)}
              </select></div>
            <div><span className={label}>Role</span>
              <select value={form.relationship_type} onChange={set("relationship_type")} className={input}>
                {["ATTENDING", "CONSULTING", "PRIMARY_CARE", "REFERRING"].map((r) => <option key={r} value={r}>{r.toLowerCase().replace("_", " ")}</option>)}
              </select></div>
            <button type="submit" disabled={busy} className={`${primaryButton} col-span-3`}>Add to care team</button>
          </form>
        </Modal>
      )}

      {modal === "breakglass" && (
        <Modal title="Emergency break-the-glass access" icon={Flame} onClose={close} tone="border-amber-900/60">
          <form onSubmit={submitBreakGlass} className="space-y-3">
            <div className="p-3 rounded-xl bg-amber-950/30 border border-amber-800/40 text-xs text-amber-200/90">
              Use only in an emergency for a patient not on your care team. Access lasts a limited time, is logged, and is reviewed by compliance.
            </div>
            <textarea required rows={3} minLength={10} placeholder="Clinical justification (required)" value={form.justification || ""}
              onChange={set("justification")} className={input} />
            {actionError && <p className="text-xs text-rose-300">{actionError}</p>}
            <div className="flex justify-end gap-2"><button type="button" onClick={close} className={ghostButton}>Cancel</button>
              <button type="submit" disabled={busy || (form.justification || "").trim().length < 10}
                className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold disabled:opacity-50">Authorize emergency access</button></div>
          </form>
        </Modal>
      )}

      {modal === "encounter" && (
        <Modal title="New encounter" icon={Stethoscope} onClose={close}>
          <form onSubmit={submitEncounter} className="space-y-3">
            <div><span className={label}>Encounter type</span>
              <select value={form.visit_type} onChange={set("visit_type")} className={input}>
                {ENCOUNTER_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select></div>
            {isAdmin && (
              <div><span className={label}>Attending doctor</span>
                <select required value={form.doctor_id || ""} onChange={set("doctor_id")} className={input}>
                  <option value="">Choose…</option>
                  {doctors.map((d) => <option key={d.id} value={d.id}>{d.display_name} · {d.hospital_name}</option>)}
                </select></div>
            )}
            <div><span className={label}>Reason / summary code (optional)</span>
              <input value={form.summary_code || ""} onChange={set("summary_code")} placeholder="e.g. I10-FOLLOWUP" className={input} /></div>
            {actionError && <p className="text-xs text-rose-300">{actionError}</p>}
            <div className="flex justify-end gap-2"><button type="button" onClick={close} className={ghostButton}>Cancel</button>
              <button type="submit" disabled={busy} className={primaryButton}>Start encounter</button></div>
          </form>
        </Modal>
      )}

      {modal === "allergy" && (
        <Modal title="Record allergy" icon={AlertTriangle} onClose={close}>
          <form onSubmit={submitAllergy} className="space-y-3">
            <div><span className={label}>Substance</span><input required value={form.substance || ""} onChange={set("substance")} placeholder="e.g. Penicillin" className={input} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><span className={label}>Reaction</span><input value={form.reaction || ""} onChange={set("reaction")} placeholder="e.g. Hives" className={input} /></div>
              <div><span className={label}>Severity</span>
                <select value={form.severity} onChange={set("severity")} className={input}>
                  {["MILD", "MODERATE", "SEVERE", "UNKNOWN"].map((s) => <option key={s} value={s}>{s.toLowerCase()}</option>)}
                </select></div>
            </div>
            {actionError && <p className="text-xs text-rose-300">{actionError}</p>}
            <div className="flex justify-end gap-2"><button type="button" onClick={close} className={ghostButton}>Cancel</button>
              <button type="submit" disabled={busy} className={primaryButton}>Save allergy</button></div>
          </form>
        </Modal>
      )}

      {entry && (
        <Modal title={entry.kind === "diagnosis" ? "Add diagnosis" : entry.kind === "prescription" ? "Add prescription" : "Add lab result"}
          icon={entry.kind === "prescription" ? Pill : entry.kind === "lab" ? FlaskConical : Stethoscope} onClose={close}>
          <form onSubmit={submitEntry} className="space-y-3">
            {entry.kind === "diagnosis" && (
              <>
                <div><span className={label}>Diagnosis (ICD-10)</span>
                  <select required value={form.disease_code || ""} onChange={set("disease_code")} className={input}>
                    <option value="">Choose…</option>
                    {formatDiagnoses.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                  </select></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><span className={label}>Severity</span>
                    <select value={form.severity} onChange={set("severity")} className={input}>
                      {["Mild", "Moderate", "Severe", "Critical"].map((s) => <option key={s}>{s}</option>)}
                    </select></div>
                  <div><span className={label}>Status</span>
                    <select value={form.status} onChange={set("status")} className={input}>
                      {["Active", "Resolved", "Remission", "Ruled out"].map((s) => <option key={s}>{s}</option>)}
                    </select></div>
                </div>
              </>
            )}
            {entry.kind === "prescription" && (
              <>
                {timeline?.allergies?.length > 0 && (
                  <p className="text-xs text-rose-300 bg-rose-950/40 border border-rose-800/50 rounded-lg px-3 py-2">
                    Allergies on record: {timeline.allergies.map((a: any) => a.substance).join(", ")}
                  </p>
                )}
                <div><span className={label}>Medication</span>
                  <select required value={form.medication_code || ""} onChange={set("medication_code")} className={input}>
                    <option value="">Choose…</option>
                    {catalog.medications.map((m) => <option key={m.code} value={m.code}>{m.name} ({m.drug_class})</option>)}
                  </select></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><span className={label}>Dose</span><input required value={form.dose_text || ""} onChange={set("dose_text")} placeholder="500 mg" className={input} /></div>
                  <div><span className={label}>Frequency</span><input required value={form.frequency_text || ""} onChange={set("frequency_text")} placeholder="twice daily" className={input} /></div>
                </div>
                <div><span className={label}>End date (optional)</span><input type="date" value={form.end_date || ""} onChange={set("end_date")} className={input} /></div>
              </>
            )}
            {entry.kind === "lab" && (
              <>
                <div><span className={label}>Test</span>
                  <select required value={form.lab_test_code || ""} onChange={set("lab_test_code")} className={input}>
                    <option value="">Choose…</option>
                    {catalog.labTests.map((t) => <option key={t.code} value={t.code}>{t.name} ({t.unit}; ref {t.reference_range_text})</option>)}
                  </select></div>
                <div><span className={label}>Result</span><input required type="number" step="any" value={form.result_value || ""} onChange={set("result_value")} className={input} /></div>
                <p className="text-[11px] text-slate-500">Results outside the reference range are flagged abnormal automatically.</p>
              </>
            )}
            {actionError && <p className="text-xs text-rose-300">{actionError}</p>}
            <div className="flex justify-end gap-2"><button type="button" onClick={close} className={ghostButton}>Cancel</button>
              <button type="submit" disabled={busy} className={primaryButton}>Save</button></div>
          </form>
        </Modal>
      )}

      {oneTimeCode && (
        <Modal title="Patient portal activation code" icon={KeyRound} onClose={() => setOneTimeCode(null)}>
          <OneTimeCode code={oneTimeCode.code} expires={oneTimeCode.expires} onClose={() => setOneTimeCode(null)} />
        </Modal>
      )}
    </div>
  );
}
