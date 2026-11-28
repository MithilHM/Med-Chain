"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import { DialogShell } from "@/components/Modal";
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
  const [reqPatientCode, setReqPatientCode] = useState("");
  const [reqPurpose, setReqPurpose] = useState("Longitudinal metabolic study");
  const [reqScopes, setReqScopes] = useState<string[]>(["aggregate_diagnoses", "medication_history"]);
  const [diseaseCode, setDiseaseCode] = useState("");
  const [submittingReq, setSubmittingReq] = useState(false);

  const loadProjects = async () => {
    try {
      const projs = await ApiClient.getResearchProjects();
      setProjects(projs);
      if (projs.length > 0 && !selectedProjectId) {
        setSelectedProjectId(projs[0].id);
      }
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
    if (!reqPatientCode.trim() || !selectedProjectId) return;
    setSubmittingReq(true);
    try {
      await ApiClient.createAccessRequest({
        patient_id: reqPatientCode.trim(),
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

    try {
      const res = await ApiClient.executeResearchQuery({
        project_id: selectedProjectId,
        query_type: queryType,
        disease_code: queryType === "disease_distribution" && diseaseCode.trim()
          ? diseaseCode.trim().toUpperCase()
          : undefined,
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
          <h1 className="text-2xl font-bold text-slate-900 flex items-center space-x-2.5">
            <FlaskConical className="w-6 h-6 text-brand-600" />
            <span>Research projects</span>
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Run aggregate queries over patients who have consented to your project.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowReqModal(true)}
            className="px-3.5 py-2 rounded-xl border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-medium active:scale-95 transition-all"
          >
            Request Patient Consent
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center space-x-1.5 px-3.5 py-2 rounded-lg bg-brand-700 hover:bg-brand-600 text-white text-xs font-medium transition-all shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Research Initiative</span>
          </button>
        </div>
      </div>

      {/* Query Runner Control Center */}
      <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-6">
        <div className="border-b border-slate-200 pb-3 flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
            <Play className="w-4 h-4 text-brand-700" />
            <span>Interactive Consent-Gated Query Runner</span>
          </h2>
          <span className="text-[11px] font-mono text-slate-600">Policy: Deny by Default</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1.5">Governing Research Project</label>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:border-brand-500"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1.5">Query Analytics Type</label>
            <select
              value={queryType}
              onChange={(e) => setQueryType(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:border-brand-500"
            >
              <option value="disease_distribution">Disease Distribution Across Consented Cohort</option>
              <option value="medication_utilization">Medication Utilization Frequencies</option>
              <option value="lab_summary">Laboratory Result Summary</option>
              <option value="cohort_summary">Overall Cohort Encounters Summary</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1.5">
              Disease Code Filter
            </label>
            <input
              type="text"
              placeholder="Optional, e.g. E11"
              value={diseaseCode}
              disabled={queryType !== "disease_distribution"}
              onChange={(e) => setDiseaseCode(e.target.value)}
              className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-900 focus:outline-none focus:border-brand-500 font-mono disabled:opacity-50"
            />
            <p className="mt-1 text-[10px] text-slate-500">Only applies to disease distribution queries.</p>
          </div>

        </div>

        {selectedProjObj && (
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-1">
            <span className="font-semibold text-slate-700">Declared Purpose:</span> {selectedProjObj.purpose}
          </div>
        )}

        <div className="flex items-center justify-between pt-2">
          <div className="text-[11px] text-slate-600">
            Requires active scope-matched consent from at least five patients. Smaller result groups are suppressed.
          </div>
          <button
            onClick={handleRunQuery}
            disabled={loading || !selectedProjectId}
            className="flex items-center space-x-2 px-5 py-2.5 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-semibold text-xs shadow-sm transition-all"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>{loading ? "Evaluating Policy & Executing..." : "Execute Gated Research Query"}</span>
          </button>
        </div>
      </div>

      {/* Query Result or Denied Banner */}
      {queryError && (
        <div className="glass-panel p-6 rounded-xl border border-rose-200 bg-rose-50 space-y-3 animate-in zoom-in-95">
          <div className="flex items-center space-x-2.5 text-rose-700 font-bold text-sm">
            <ShieldAlert className="w-5 h-5 shrink-0" />
            <span>Query Rejected by Central Consent Policy Engine (HTTP 403)</span>
          </div>
          <p className="text-xs text-rose-800 leading-relaxed font-mono bg-rose-50 p-3 rounded-xl border border-rose-200">
            {queryError}
          </p>
          <div className="text-[11px] text-slate-600 pt-1">
            Server-side policy checks reject queries without active consent and record the decision in the database audit log. Blockchain mirroring is best-effort, and work already in progress is not cancelled by a later revocation.
          </div>
        </div>
      )}

      {queryResult && (
        <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-5 animate-in fade-in">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-200 pb-3 gap-2">
            <div className="flex items-center space-x-2 text-emerald-700 font-bold text-sm">
              <CheckCircle2 className="w-4 h-4" />
              <span>Query Authorized: Active Consent Scope Verified</span>
            </div>
            <span className="text-[11px] font-mono text-brand-700 px-2.5 py-0.5 rounded-full bg-brand-50 border border-brand-200">
              {queryResult.disclaimer}
            </span>
          </div>

          {/* Render tabular or metric results */}
          {queryResult.results && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-600 font-semibold uppercase text-[10px]">
                    {queryResult.query_type === "lab_summary" ? (
                      <>
                        <th className="py-2.5 px-3">Test Code</th>
                        <th className="py-2.5 px-3">Laboratory Test</th>
                        <th className="py-2.5 px-3">Unit</th>
                        <th className="py-2.5 px-3 text-right">Results</th>
                        <th className="py-2.5 px-3 text-right">Patients</th>
                        <th className="py-2.5 px-3 text-right">Abnormal</th>
                        <th className="py-2.5 px-3 text-right">Average</th>
                      </>
                    ) : (
                      <>
                        <th className="py-2.5 px-3">Catalog Code</th>
                        <th className="py-2.5 px-3">Description / Name</th>
                        {queryResult.query_type === "medication_utilization" && <th className="py-2.5 px-3">Drug Class</th>}
                        <th className="py-2.5 px-3 text-right">Aggregate Occurrences</th>
                        <th className="py-2.5 px-3 text-right">Consented Patients</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 text-slate-700">
                  {queryResult.results.length === 0 ? (
                    <tr><td colSpan={queryResult.query_type === "lab_summary" ? 7 : queryResult.query_type === "medication_utilization" ? 5 : 4} className="py-6 text-center text-slate-500">No matching records met the minimum group size.</td></tr>
                  ) : queryResult.results.map((row: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      {queryResult.query_type === "lab_summary" ? (
                        <>
                          <td className="py-3 px-3 font-mono text-brand-700">{row.test_code}</td>
                          <td className="py-3 px-3 font-medium text-slate-900">{row.test_name}</td>
                          <td className="py-3 px-3 text-slate-600">{row.unit}</td>
                          <td className="py-3 px-3 text-right font-mono">{row.result_count}</td>
                          <td className="py-3 px-3 text-right font-mono text-slate-600">{row.patient_count}</td>
                          <td className="py-3 px-3 text-right font-mono text-amber-700">{row.abnormal_result_count ?? "Suppressed"}</td>
                          <td className="py-3 px-3 text-right font-mono">{row.average_result == null ? "—" : Number(row.average_result).toFixed(2)}</td>
                        </>
                      ) : (
                        <>
                          <td className="py-3 px-3 font-mono text-brand-700">{row.code}</td>
                          <td className="py-3 px-3 font-medium text-slate-900">{row.name}</td>
                          {queryResult.query_type === "medication_utilization" && <td className="py-3 px-3 text-slate-600">{row.drug_class || "—"}</td>}
                          <td className="py-3 px-3 text-right font-mono font-semibold">
                            {row.diagnosis_count || row.prescription_count || 0}
                          </td>
                          <td className="py-3 px-3 text-right font-mono text-slate-600">{row.patient_count || 0}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {queryResult.cohort_overview && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center">
                <div className="text-2xl font-bold text-slate-900">{queryResult.cohort_overview.total_consented_records}</div>
                <div className="text-xs text-slate-600 mt-1">Consented Patient Records</div>
              </div>
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center">
                <div className="text-2xl font-bold text-brand-700">{queryResult.cohort_overview.total_diagnoses_observed ?? "Suppressed"}</div>
                <div className="text-xs text-slate-600 mt-1">Observed Diagnoses Count</div>
              </div>
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-center">
                <div className="text-2xl font-bold text-emerald-700">{queryResult.cohort_overview.total_prescriptions_recorded ?? "Suppressed"}</div>
                <div className="text-xs text-slate-600 mt-1">Active Prescriptions Recorded</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modal: New Project */}
      {showCreateModal && (
        <DialogShell onClose={() => setShowCreateModal(false)} label="Register research initiative" className="max-w-md border-slate-300">
            <h2 className="text-base font-bold text-slate-900 flex items-center space-x-2">
              <Plus className="w-4 h-4 text-purple-700" />
              <span>Register Research Initiative</span>
            </h2>

            <form onSubmit={handleCreateProject} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-700 font-medium mb-1">Project Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Cardiometabolic Longitudinal Cohort"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-brand-500"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">Research Purpose Statement</label>
                <textarea
                  rows={4}
                  required
                  placeholder="State the scientific purpose of data processing..."
                  value={newPurpose}
                  onChange={(e) => setNewPurpose(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-brand-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-medium shadow-sm"
                >
                  {creating ? "Registering..." : "Register Initiative"}
                </button>
              </div>
            </form>
        </DialogShell>
      )}

      {/* Modal: Request Patient Consent */}
      {showReqModal && (
        <DialogShell onClose={() => setShowReqModal(false)} label="Submit scoped consent request" className="max-w-md border-slate-300">
            <h2 className="text-base font-bold text-slate-900 flex items-center space-x-2">
              <FlaskConical className="w-4 h-4 text-purple-700" />
              <span>Submit Scoped Consent Request</span>
            </h2>

            <form onSubmit={handleCreateAccessRequest} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-700 font-medium mb-1">Target Patient</label>
                <input
                  type="text"
                  required
                  placeholder="Enter a patient code, e.g. PT-100201"
                  value={reqPatientCode}
                  onChange={(e) => setReqPatientCode(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-brand-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">Project Purpose Declaration</label>
                <input
                  type="text"
                  required
                  value={reqPurpose}
                  onChange={(e) => setReqPurpose(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-brand-500"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">Requested Data Scopes</label>
                <div className="space-y-1.5 p-3 rounded-xl bg-slate-50 border border-slate-200">
                  {["aggregate_diagnoses", "medication_history", "lab_summaries", "deidentified_cohort"].map((sc) => (
                    <label key={sc} className="flex items-center space-x-2 text-slate-700">
                      <input
                        type="checkbox"
                        checked={reqScopes.includes(sc)}
                        onChange={(e) => {
                          if (e.target.checked) setReqScopes([...reqScopes, sc]);
                          else setReqScopes(reqScopes.filter((s) => s !== sc));
                        }}
                        className="rounded border-slate-300 text-brand-600 focus:ring-0"
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
                  className="px-4 py-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingReq}
                  className="px-4 py-2 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-medium shadow-sm"
                >
                  {submittingReq ? "Submitting..." : "Submit to Patient"}
                </button>
              </div>
            </form>
        </DialogShell>
      )}
    </div>
  );
}
