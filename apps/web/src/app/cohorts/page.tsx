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
      const list = await ApiClient.getCohorts();
      setCohorts(list);
      if (list.length > 0 && !currentCohort) {
        setCurrentCohort(list[0]);
      }
    } catch (err: any) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadCohorts();
  }, []);

  const handleRunClustering = async (e: React.FormEvent) => {
    e.preventDefault();
    setRunning(true);
    try {
      const res = await ApiClient.runCohortClustering({
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

  const colors = ["border-cyan-500/50 bg-cyan-950/20 text-cyan-300", "border-purple-500/50 bg-purple-950/20 text-purple-300", "border-emerald-500/50 bg-emerald-950/20 text-emerald-300", "border-amber-500/50 bg-amber-950/20 text-amber-300"];

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
          <Network className="w-6 h-6 text-cyan-400" />
          <span>Patient Cohort Analytics Explorer</span>
        </h1>
        <p className="text-xs text-slate-400">
          Unsupervised K-Means clustering on de-identified synthetic feature matrices. Zero direct identifiers.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Clustering Configuration Form */}
        <div className="lg:col-span-4 glass-panel p-6 rounded-2xl border border-slate-800 space-y-5">
          <div className="border-b border-slate-800/80 pb-3">
            <h2 className="text-sm font-bold text-white flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              <span>Configure Clustering Run</span>
            </h2>
          </div>

          <form onSubmit={handleRunClustering} className="space-y-4 text-xs">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Cohort Run Name</label>
              <input
                type="text"
                required
                value={cohortName}
                onChange={(e) => setCohortName(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">
                Number of Clusters ($k = {k}$)
              </label>
              <input
                type="range"
                min="2"
                max="5"
                value={k}
                onChange={(e) => setK(Number(e.target.value))}
                className="w-full accent-cyan-400 cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-400 mt-1">
                <span>2 Groups</span>
                <span>3 Groups</span>
                <span>4 Groups</span>
                <span>5 Groups</span>
              </div>
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">
                Random Seed (Reproducibility: {seed})
              </label>
              <input
                type="number"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500 font-mono"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">Active Feature Groups</label>
              <div className="space-y-2 p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                {[
                  { id: "diagnoses", label: "Diagnosis Code Frequencies" },
                  { id: "medications", label: "Prescription Exposure Counts" },
                  { id: "lab_abnormalities", label: "Abnormal Lab Assays Count" },
                  { id: "age_bracket", label: "Synthetic Demographic Band" },
                ].map((f) => (
                  <label key={f.id} className="flex items-center space-x-2 text-slate-300">
                    <input
                      type="checkbox"
                      checked={selectedFeatures.includes(f.id)}
                      onChange={(e) => {
                        if (e.target.checked) setSelectedFeatures([...selectedFeatures, f.id]);
                        else setSelectedFeatures(selectedFeatures.filter((item) => item !== f.id));
                      }}
                      className="rounded border-slate-700 text-cyan-500 focus:ring-0"
                    />
                    <span>{f.label}</span>
                  </label>
                ))}
              </div>
            </div>

            <button
              type="submit"
              disabled={running}
              className="w-full flex items-center justify-center space-x-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold shadow-lg shadow-cyan-500/20 active:scale-95 transition-all"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{running ? "Standardizing & Clustering..." : "Execute K-Means Clustering"}</span>
            </button>
          </form>

          {/* Past Cohorts List */}
          {cohorts.length > 0 && (
            <div className="pt-4 border-t border-slate-800/80 space-y-2">
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Saved Analytics Runs ({cohorts.length})
              </div>
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {cohorts.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setCurrentCohort(c)}
                    className={`w-full p-2.5 rounded-lg border text-left text-xs transition-colors flex items-center justify-between ${
                      currentCohort?.id === c.id
                        ? "bg-cyan-500/10 border-cyan-500/40 text-cyan-300 font-semibold"
                        : "bg-slate-900/40 border-slate-800 text-slate-400 hover:text-white"
                    }`}
                  >
                    <span className="truncate">{c.name}</span>
                    <span className="text-[10px] font-mono text-slate-400">
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
            <div className="glass-panel p-16 rounded-2xl border border-slate-800 text-center text-xs text-slate-400">
              Run clustering on the left to generate and inspect synthetic cohorts.
            </div>
          ) : (
            <div className="space-y-6 animate-in fade-in duration-200">
              {/* Header Box */}
              <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-3">
                <div className="flex flex-wrap items-center justify-between border-b border-slate-800/80 pb-3 gap-2">
                  <div>
                    <h2 className="text-lg font-bold text-white">{currentCohort.name}</h2>
                    <div className="text-xs text-slate-400 flex items-center space-x-2 mt-1">
                      <span>Algorithm: {currentCohort.algorithm}</span>
                      <span>•</span>
                      <span>Inertia: {currentCohort.inertia ? Math.round(currentCohort.inertia) : "N/A"}</span>
                      <span>•</span>
                      <span>{currentCohort.clusters?.length || 0} Distinct Cohorts</span>
                    </div>
                  </div>

                  <span className="px-3 py-1 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                    Deterministic Reproducibility
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-800/30 flex items-start space-x-2.5 text-xs text-amber-200/90">
                  <Info className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
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
                      className={`p-5 rounded-2xl border glass-panel space-y-3 ${colorClass}`}
                    >
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                        <span className="text-sm font-bold">{cluster.cluster_name}</span>
                        <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-slate-900/80 border border-slate-800">
                          {cluster.patient_count} Patients
                        </span>
                      </div>

                      <div className="space-y-2 text-xs">
                        <div className="flex items-center justify-between text-slate-300">
                          <span className="text-slate-400">Average Age:</span>
                          <span className="font-semibold">{cluster.avg_age} years</span>
                        </div>

                        <div>
                          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                            Dominant Diagnoses
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {cluster.top_diagnoses?.map((d: string, dIdx: number) => (
                              <span
                                key={dIdx}
                                className="px-2 py-0.5 rounded bg-slate-900/80 border border-slate-800 text-[11px] text-slate-200"
                              >
                                {d}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div>
                          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                            Associated Prescriptions
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {cluster.top_medications?.map((m: string, mIdx: number) => (
                              <span
                                key={mIdx}
                                className="px-2 py-0.5 rounded bg-slate-900/80 border border-slate-800 text-[11px] text-slate-200"
                              >
                                {m}
                              </span>
                            ))}
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
