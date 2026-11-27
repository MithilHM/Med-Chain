"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  Network,
  Play,
  RotateCcw,
  Sparkles,
  Layers,
  Activity,
  AlertTriangle,
  Info,
  Calendar,
} from "lucide-react";

export default function CohortsPage() {
  const [cohorts, setCohorts] = useState<any[]>([]);
  const [researchProjects, setResearchProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState("");
  const [cohortName, setCohortName] = useState("Metabolic & Hypertension Cohort");
  const [k, setK] = useState(3);
  const [seed, setSeed] = useState(42);
  const [selectedFeatures, setSelectedFeatures] = useState<string[]>([
    "diagnoses",
    "medications",
    "lab_abnormalities",
  ]);
  const [running, setRunning] = useState(false);
  const [currentCohort, setCurrentCohort] = useState<any>(null);

  const loadCohorts = async () => {
    try {
      const list = await ApiClient.getCohorts(projectId || undefined);
      setCohorts(list);
      setCurrentCohort(list[0] || null);
    } catch (err: any) {
      console.error(err);
    }
  };

  useEffect(() => {
    let active = true;
    ApiClient.getResearchProjects()
      .then((projects) => {
        if (!active) return;
        setResearchProjects(projects);
        if (projects.length > 0) setProjectId(projects[0].id);
      })
      .catch((err: any) => console.error(err));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (projectId) loadCohorts();
  }, [projectId]);

  const handleRunClustering = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId) {
      alert("Select a research project with active patient consent before clustering.");
      return;
    }
    setRunning(true);
    try {
      const res = await ApiClient.runCohortClustering({
        project_id: projectId,
        name: cohortName,
        k: Number(k),
        features: selectedFeatures,
        random_state: Number(seed),
      });
      setCurrentCohort(res);
      await loadCohorts();
    } catch (err: any) {
      alert(`Clustering failed: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const colors = ["border-brand-400 bg-brand-50 text-brand-700", "border-purple-400 bg-purple-50 text-purple-700", "border-emerald-400 bg-emerald-50 text-emerald-700", "border-amber-400 bg-amber-50 text-amber-700"];

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center space-x-2.5">
          <Network className="w-6 h-6 text-brand-600" />
          <span>Cohort explorer</span>
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Groups of similar consented patients, built from de-identified data with no direct identifiers.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Clustering Configuration Form */}
        <div className="lg:col-span-4 glass-panel p-6 rounded-xl border border-slate-200 space-y-5">
          <div className="border-b border-slate-200 pb-3">
            <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-brand-700" />
              <span>Configure Clustering Run</span>
            </h2>
          </div>

          <form onSubmit={handleRunClustering} className="space-y-4 text-xs">
            <div>
              <label className="block text-slate-700 font-medium mb-1">Research Project (consent scope)</label>
              <select
                required
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-brand-500"
              >
                <option value="" disabled>Select a project</option>
                {researchProjects.map((project) => (
                  <option key={project.id} value={project.id}>{project.title}</option>
                ))}
              </select>
              {researchProjects.length === 0 && (
                <p className="mt-1 text-amber-700">Create a research project and obtain active cohort consent first.</p>
              )}
            </div>

            <div>
              <label className="block text-slate-700 font-medium mb-1">Cohort Run Name</label>
              <input
                type="text"
                required
                value={cohortName}
                onChange={(e) => setCohortName(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-brand-500"
              />
            </div>

            <div>
              <label className="block text-slate-700 font-medium mb-1">
                Number of Clusters ($k = {k}$)
              </label>
              <input
                type="range"
                min="2"
                max="5"
                value={k}
                onChange={(e) => setK(Number(e.target.value))}
                className="w-full accent-brand-700 cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-600 mt-1">
                <span>2 Groups</span>
                <span>3 Groups</span>
                <span>4 Groups</span>
                <span>5 Groups</span>
              </div>
            </div>

            <div>
              <label className="block text-slate-700 font-medium mb-1">
                Random Seed (Reproducibility: {seed})
              </label>
              <input
                type="number"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-brand-500 font-mono"
              />
            </div>

            <div>
              <label className="block text-slate-700 font-medium mb-1">Active Feature Groups</label>
              <div className="space-y-2 p-3 rounded-xl bg-slate-50 border border-slate-200">
                {[
                  { id: "diagnoses", label: "Diagnosis Code Frequencies" },
                  { id: "medications", label: "Prescription Exposure Counts" },
                  { id: "lab_abnormalities", label: "Abnormal Lab Assays Count" },
                  { id: "age_bracket", label: "Synthetic Demographic Band" },
                ].map((f) => (
                  <label key={f.id} className="flex items-center space-x-2 text-slate-700">
                    <input
                      type="checkbox"
                      checked={selectedFeatures.includes(f.id)}
                      disabled={selectedFeatures.includes(f.id) && selectedFeatures.length === 1}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedFeatures([...selectedFeatures, f.id]);
                        else setSelectedFeatures(selectedFeatures.filter((item) => item !== f.id));
                      }}
                      className="rounded border-slate-300 text-brand-600 focus:ring-0 disabled:opacity-50"
                    />
                    <span>{f.label}</span>
                  </label>
                ))}
              </div>
              <p className="mt-1 text-[10px] text-slate-500">Only selected groups form the clustering feature matrix.</p>
            </div>

            <button
              type="submit"
              disabled={running}
              className="w-full flex items-center justify-center space-x-2 px-4 py-2.5 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-semibold shadow-sm transition-all"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{running ? "Standardizing & Clustering..." : "Execute K-Means Clustering"}</span>
            </button>
          </form>

          {/* Past Cohorts List */}
          {cohorts.length > 0 && (
            <div className="pt-4 border-t border-slate-200 space-y-2">
              <div className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
                Saved Analytics Runs ({cohorts.length})
              </div>
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {cohorts.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setCurrentCohort(c)}
                    className={`w-full p-2.5 rounded-lg border text-left text-xs transition-colors flex items-center justify-between ${
                      currentCohort?.id === c.id
                        ? "bg-brand-50 border-brand-300 text-brand-700 font-semibold"
                        : "bg-slate-50 border-slate-200 text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <span className="truncate">{c.name}</span>
                    <span className="text-[10px] font-mono text-slate-600">
                      {new Date(c.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Cluster Visualizations and Explanations */}
        <div className="lg:col-span-8 space-y-6">
          {!currentCohort ? (
            <div className="glass-panel p-16 rounded-xl border border-slate-200 text-center text-xs text-slate-600">
              Run clustering on the left to generate and inspect synthetic cohorts.
            </div>
          ) : (
            <div className="space-y-6 animate-in fade-in duration-200">
              {/* Header Box */}
              <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-3">
                <div className="flex flex-wrap items-center justify-between border-b border-slate-200 pb-3 gap-2">
                  <div>
                    <h2 className="text-lg font-bold text-slate-900">{currentCohort.name}</h2>
                    <div className="text-xs text-slate-600 flex items-center space-x-2 mt-1">
                      <span>Algorithm: {currentCohort.algorithm}</span>
                      <span>•</span>
                      <span>Inertia: {currentCohort.inertia ? Math.round(currentCohort.inertia) : "N/A"}</span>
                      <span>•</span>
                      <span>{currentCohort.clusters?.length || 0} Distinct Cohorts</span>
                    </div>
                  </div>
                  {currentCohort.features?.length > 0 && (
                    <div className="text-[11px] text-slate-500 mt-2">
                      Input groups: {currentCohort.features.map((feature: string) => feature.replaceAll("_", " ")).join(", ")}
                    </div>
                  )}

                  <span className="px-3 py-1 rounded-full text-xs font-semibold bg-brand-50 text-brand-700 border border-brand-200">
                    Deterministic Reproducibility
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 flex items-start space-x-2.5 text-xs text-amber-800">
                  <Info className="w-4 h-4 shrink-0 text-amber-700 mt-0.5" />
                  <span>
                    <strong>Scientific Disclaimer:</strong> {currentCohort.disclaimer}
                  </span>
                </div>
              </div>

              {/* Cluster Profiles Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {currentCohort.clusters?.map((cluster: any, idx: number) => {
                  const colorClass = colors[idx % colors.length];
                  return (
                    <div
                      key={cluster.cluster_label}
                      className={`p-5 rounded-xl border glass-panel space-y-3 ${colorClass}`}
                    >
                      <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                        <span className="text-sm font-bold">{cluster.cluster_name}</span>
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-slate-50 border border-slate-200">
                          {cluster.patient_count} Patients
                        </span>
                      </div>

                      <div className="space-y-2 text-xs">
                        <div className="flex items-center justify-between text-slate-700">
                          <span className="text-slate-600">Age Band Estimate:</span>
                          <span className="font-semibold">{cluster.avg_age == null ? "Not selected" : `${cluster.avg_age} years`}</span>
                        </div>

                        <div>
                          <div className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1">
                            Dominant Diagnoses
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {currentCohort.features?.includes("diagnoses") ? (
                              cluster.top_diagnoses?.length ? cluster.top_diagnoses.map((d: string, dIdx: number) => (
                                <span
                                  key={dIdx}
                                  className="px-2 py-0.5 rounded bg-slate-50 border border-slate-200 text-[11px] text-slate-800"
                                >
                                  {d}
                                </span>
                              )) : <span className="text-slate-500">No diagnosis patterns observed</span>
                            ) : <span className="text-slate-500">Not selected for this run</span>}
                          </div>
                        </div>

                        <div>
                          <div className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1">
                            Associated Prescriptions
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {currentCohort.features?.includes("medications") ? (
                              cluster.top_medications?.length ? cluster.top_medications.map((m: string, mIdx: number) => (
                                <span
                                  key={mIdx}
                                  className="px-2 py-0.5 rounded bg-slate-50 border border-slate-200 text-[11px] text-slate-800"
                                >
                                  {m}
                                </span>
                              )) : <span className="text-slate-500">No medication patterns observed</span>
                            ) : <span className="text-slate-500">Not selected for this run</span>}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
