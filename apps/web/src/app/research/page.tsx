"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  FlaskConical,
  Play,
  Plus,
  ShieldCheck,
  ShieldAlert,
  BarChart3,
  Search,
  CheckCircle2,
  AlertCircle,
  FileSpreadsheet,
} from "lucide-react";

export default function ResearchPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [queryType, setQueryType] = useState<string>("disease_distribution");
  const [targetPatientCode, setTargetPatientCode] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [queryResult, setQueryResult] = useState<any>(null);
  const [queryError, setQueryError] = useState<string | null>(null);

  // New Project Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newPurpose, setNewPurpose] = useState("");
  const [creating, setCreating] = useState(false);

  // Access Request Modal State
  const [showReqModal, setShowReqModal] = useState(false);
  const [patients, setPatients] = useState<any[]>([]);
  const [reqPatientId, setReqPatientId] = useState("");
  const [reqPurpose, setReqPurpose] = useState("Longitudinal metabolic study");
  const [reqScopes, setReqScopes] = useState<string[]>(["aggregate_diagnoses", "medication_history"]);
  const [submittingReq, setSubmittingReq] = useState(false);

  const loadProjects = async () => {
    try {
      const projs = await ApiClient.getResearchProjects();
      setProjects(projs);
      if (projs.length > 0 && !selectedProjectId) {
        setSelectedProjectId(projs[0].id);
      }
      const pts = await ApiClient.getPatients().catch(() => []);
      setPatients(pts);
      if (pts.length > 0) setReqPatientId(pts[0].id);
    } catch (err: any) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle || !newPurpose) return;
    setCreating(true);
    try {
      await ApiClient.createResearchProject({ title: newTitle, purpose: newPurpose });
      setShowCreateModal(false);
      setNewTitle("");
      setNewPurpose("");
      await loadProjects();
    } catch (err: any) {
      alert(`Project creation failed: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  const handleCreateAccessRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reqPatientId || !selectedProjectId) return;
    setSubmittingReq(true);
    try {
      await ApiClient.createAccessRequest({
        patient_id: reqPatientId,
        project_id: selectedProjectId,
        purpose: reqPurpose,
        requested_scopes: reqScopes,
      });
      setShowReqModal(false);
      alert("Research access request submitted successfully. The patient can now view and grant it in the Consent Center.");
    } catch (err: any) {
      alert(`Request submission failed: ${err.message}`);
    } finally {
      setSubmittingReq(false);
    }
  };

  const handleRunQuery = async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    setQueryResult(null);
    setQueryError(null);

    let targetPtId = undefined;
    if (targetPatientCode.trim()) {
      const match = patients.find(
        (p) => p.display_code.toLowerCase() === targetPatientCode.trim().toLowerCase()
      );
      if (match) targetPtId = match.id;
    }

    try {
      const res = await ApiClient.executeResearchQuery({
        project_id: selectedProjectId,
        query_type: queryType,
        filters: targetPtId ? { patient_id: targetPtId } : undefined,
      });
      setQueryResult(res);
    } catch (err: any) {
      setQueryError(err.message || "Query rejected by Consent Engine");
    } finally {
      setLoading(false);
    }
  };

  const selectedProjObj = projects.find((p) => p.id === selectedProjectId);

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
            <FlaskConical className="w-6 h-6 text-purple-400" />
            <span>Privacy-Preserving Research Engine</span>
          </h1>
          <p className="text-xs text-slate-400">
            Centralized policy evaluation gating aggregate research queries behind active patient consent
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowReqModal(true)}
            className="px-3.5 py-2 rounded-xl border border-slate-700 hover:bg-slate-900 text-slate-300 text-xs font-medium active:scale-95 transition-all"
          >
            Request Patient Consent
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium active:scale-95 transition-all shadow-md shadow-purple-500/20"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Research Initiative</span>
          </button>
        </div>
      </div>

      {/* Query Runner Control Center */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
        <div className="border-b border-slate-800/80 pb-3 flex items-center justify-between">
          <h2 className="text-sm font-bold text-white flex items-center space-x-2">
            <Play className="w-4 h-4 text-cyan-400" />
            <span>Interactive Consent-Gated Query Runner</span>
          </h2>
          <span className="text-[11px] font-mono text-slate-400">Policy: Deny by Default</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Governing Research Project</label>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Query Analytics Type</label>
            <select
              value={queryType}
              onChange={(e) => setQueryType(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
            >
              <option value="disease_distribution">Disease Distribution Across Consented Cohort</option>
              <option value="medication_utilization">Medication Utilization Frequencies</option>
              <option value="cohort_summary">Overall Cohort Encounters Summary</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">
              Target Patient Code (Optional Test)
            </label>
            <input
              type="text"
              placeholder="e.g. PT-100201 (Leave blank for cohort)"
              value={targetPatientCode}
              onChange={(e) => setTargetPatientCode(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
            />
          </div>
        </div>

        {selectedProjObj && (
          <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-400 space-y-1">
            <span className="font-semibold text-slate-300">Declared Purpose:</span> {selectedProjObj.purpose}
          </div>
        )}

        <div className="flex items-center justify-between pt-2">
          <div className="text-[11px] text-slate-400">
            Evaluating actor role, active consent existence, unexpired validity, and scope matching.
          </div>
          <button
            onClick={handleRunQuery}
            disabled={loading || !selectedProjectId}
            className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold text-xs shadow-lg shadow-cyan-500/20 active:scale-95 transition-all"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{loading ? "Evaluating Policy & Executing..." : "Execute Gated Research Query"}</span>
          </button>
        </div>
      </div>

      {/* Query Result or Denied Banner */}
      {queryError && (
        <div className="glass-panel p-6 rounded-2xl border border-rose-800/60 bg-rose-950/20 space-y-3 animate-in zoom-in-95">
          <div className="flex items-center space-x-2.5 text-rose-400 font-bold text-sm">
            <ShieldAlert className="w-5 h-5 shrink-0" />
            <span>Query Rejected by Central Consent Policy Engine (HTTP 403)</span>
          </div>
          <p className="text-xs text-rose-200/90 leading-relaxed font-mono bg-rose-950/40 p-3 rounded-xl border border-rose-800/40">
            {queryError}
          </p>
          <div className="text-[11px] text-slate-400 pt-1">
            This demonstrates server-side policy enforcement: if the patient has revoked consent or if no active consent exists, data retrieval is completely blocked and logged to the immutable audit trail.
          </div>
        </div>
      )}

      {queryResult && (
        <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-5 animate-in fade-in">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-800/80 pb-3 gap-2">
            <div className="flex items-center space-x-2 text-emerald-400 font-bold text-sm">
              <CheckCircle2 className="w-4 h-4" />
              <span>Query Authorized: Active Consent Scope Verified</span>
            </div>
            <span className="text-[11px] font-mono text-cyan-300 px-2.5 py-0.5 rounded-full bg-cyan-950/60 border border-cyan-800/50">
              {queryResult.disclaimer}
            </span>
          </div>

          {/* Render tabular or metric results */}
          {queryResult.results && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase text-[10px]">
                    <th className="py-2.5 px-3">Catalog Code</th>
                    <th className="py-2.5 px-3">Description / Name</th>
                    {queryResult.results[0]?.drug_class && <th className="py-2.5 px-3">Drug Class</th>}
                    <th className="py-2.5 px-3 text-right">Aggregate Occurrences</th>
                    <th className="py-2.5 px-3 text-right">Consented Patients</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {queryResult.results.map((row: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-900/40">
                      <td className="py-3 px-3 font-mono text-cyan-400">{row.code}</td>
                      <td className="py-3 px-3 font-medium text-white">{row.name}</td>
                      {row.drug_class && <td className="py-3 px-3 text-slate-400">{row.drug_class}</td>}
                      <td className="py-3 px-3 text-right font-mono font-semibold">
                        {row.diagnosis_count || row.prescription_count || 0}
                      </td>
                      <td className="py-3 px-3 text-right font-mono text-slate-400">{row.patient_count || 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {queryResult.cohort_overview && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center">
                <div className="text-2xl font-bold text-white">{queryResult.cohort_overview.total_consented_records}</div>
                <div className="text-xs text-slate-400 mt-1">Consented Patient Records</div>
              </div>
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center">
                <div className="text-2xl font-bold text-cyan-400">{queryResult.cohort_overview.total_diagnoses_observed}</div>
                <div className="text-xs text-slate-400 mt-1">Observed Diagnoses Count</div>
              </div>
              <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center">
                <div className="text-2xl font-bold text-emerald-400">{queryResult.cohort_overview.total_prescriptions_recorded}</div>
                <div className="text-xs text-slate-400 mt-1">Active Prescriptions Recorded</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modal: New Project */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md glass-panel p-6 rounded-2xl border border-slate-700 space-y-4 animate-in zoom-in-95">
            <h2 className="text-base font-bold text-white flex items-center space-x-2">
              <Plus className="w-4 h-4 text-purple-400" />
              <span>Register Research Initiative</span>
            </h2>

            <form onSubmit={handleCreateProject} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Project Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Cardiometabolic Longitudinal Cohort"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Research Purpose Statement</label>
                <textarea
                  rows={4}
                  required
                  placeholder="State the scientific purpose of data processing..."
                  value={newPurpose}
                  onChange={(e) => setNewPurpose(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-800 text-slate-400 hover:bg-slate-900 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-medium shadow-md shadow-purple-500/20"
                >
                  {creating ? "Registering..." : "Register Initiative"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Request Patient Consent */}
      {showReqModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md glass-panel p-6 rounded-2xl border border-slate-700 space-y-4 animate-in zoom-in-95">
            <h2 className="text-base font-bold text-white flex items-center space-x-2">
              <FlaskConical className="w-4 h-4 text-purple-400" />
              <span>Submit Scoped Consent Request</span>
            </h2>

            <form onSubmit={handleCreateAccessRequest} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Target Patient</label>
                <select
                  value={reqPatientId}
                  onChange={(e) => setReqPatientId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                >
                  {patients.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.display_code} ({p.sex}, DOB: {p.date_of_birth})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Project Purpose Declaration</label>
                <input
                  type="text"
                  required
                  value={reqPurpose}
                  onChange={(e) => setReqPurpose(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Requested Data Scopes</label>
                <div className="space-y-1.5 p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                  {["aggregate_diagnoses", "medication_history", "lab_summaries", "deidentified_cohort"].map((sc) => (
                    <label key={sc} className="flex items-center space-x-2 text-slate-300">
                      <input
                        type="checkbox"
                        checked={reqScopes.includes(sc)}
                        onChange={(e) => {
                          if (e.target.checked) setReqScopes([...reqScopes, sc]);
                          else setReqScopes(reqScopes.filter((s) => s !== sc));
                        }}
                        className="rounded border-slate-700 text-cyan-500 focus:ring-0"
                      />
                      <span className="font-mono text-[11px]">{sc}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowReqModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-800 text-slate-400 hover:bg-slate-900 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingReq}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-medium shadow-md shadow-purple-500/20"
                >
                  {submittingReq ? "Submitting..." : "Submit to Patient"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
