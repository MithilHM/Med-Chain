"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  Share2,
  Filter,
  RefreshCw,
  Info,
  Network,
  Activity,
  Layers,
  Sparkles,
} from "lucide-react";

export default function GraphPage() {
  const [graphData, setGraphData] = useState<any>({ nodes: [], edges: [], disclaimer: "" });
  const [filterMode, setFilterMode] = useState<"all" | "cooccurrence" | "side_effects">("all");
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);
  const [selectedNode, setSelectedNode] = useState<any>(null);

  const fetchGraph = async (mode: string) => {
    setLoading(true);
    try {
      let res;
      if (mode === "cooccurrence") {
        res = await ApiClient.getDiseaseCooccurrence();
      } else if (mode === "side_effects") {
        res = await ApiClient.getDrugSideEffects();
      } else {
        res = await ApiClient.getGraphOverview();
      }
      setGraphData(res);
      if (res.nodes?.length > 0) {
        setSelectedNode(res.nodes[0]);
      }
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraph(filterMode);
  }, [filterMode]);

  const handleRebuildGraph = async () => {
    setRebuilding(true);
    try {
      await ApiClient.rebuildGraph();
      await fetchGraph(filterMode);
      alert("Neo4j knowledge graph successfully rebuilt from authoritative relational database.");
    } catch (err: any) {
      alert(`Rebuild error: ${err.message}`);
    } finally {
      setRebuilding(false);
    }
  };

  const getNodeColor = (label: string) => {
    switch (label) {
      case "Disease":
        return "bg-rose-500/20 text-rose-300 border-rose-500/40";
      case "Medication":
        return "bg-sky-500/20 text-sky-300 border-sky-500/40";
      case "SideEffect":
        return "bg-amber-500/20 text-amber-300 border-amber-500/40";
      case "Patient":
        return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
      default:
        return "bg-slate-800 text-slate-300 border-slate-700";
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
            <Share2 className="w-6 h-6 text-sky-400" />
            <span>Disease–Drug Knowledge Graph Intelligence</span>
          </h1>
          <p className="text-xs text-slate-400">
            Derived graph projection (Neo4j) tracking comorbidities and reported adverse symptom associations
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1 p-1 rounded-xl bg-slate-900 border border-slate-800 text-xs">
            <button
              onClick={() => setFilterMode("all")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors ${
                filterMode === "all" ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30" : "text-slate-400"
              }`}
            >
              Full Graph
            </button>
            <button
              onClick={() => setFilterMode("cooccurrence")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors ${
                filterMode === "cooccurrence" ? "bg-rose-500/20 text-rose-300 border border-rose-500/30" : "text-slate-400"
              }`}
            >
              Comorbidity Links
            </button>
            <button
              onClick={() => setFilterMode("side_effects")}
              className={`px-3 py-1.5 rounded-lg font-medium transition-colors ${
                filterMode === "side_effects" ? "bg-amber-500/20 text-amber-300 border border-amber-500/30" : "text-slate-400"
              }`}
            >
              Drug–Side Effect
            </button>
          </div>

          <button
            onClick={handleRebuildGraph}
            disabled={rebuilding}
            className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 active:scale-95 transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${rebuilding ? "animate-spin text-cyan-400" : ""}`} />
            <span>{rebuilding ? "Rebuilding..." : "Rebuild Graph"}</span>
          </button>
        </div>
      </div>

      {/* Required Association Caveat Banner */}
      <div className="p-3.5 rounded-xl bg-amber-950/20 border border-amber-800/40 flex items-start space-x-3 text-xs text-amber-200">
        <Info className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
        <div>
          <span className="font-bold">Association Disclaimer:</span> {graphData.disclaimer || "Graph edges represent synthetic observed co-occurrences, not proven pharmacological causation."}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Nodes and Edges Interactive Grid */}
        <div className="lg:col-span-8 glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <h2 className="text-sm font-bold text-white flex items-center space-x-2">
              <Network className="w-4 h-4 text-cyan-400" />
              <span>Projected Knowledge Nodes ({graphData.nodes?.length || 0})</span>
            </h2>
            <span className="text-[11px] text-slate-400 font-mono">
              {graphData.edges?.length || 0} Relationships Connected
            </span>
          </div>

          {loading ? (
            <div className="text-xs text-slate-400 text-center py-20">Loading graph topology...</div>
          ) : (
            <div className="space-y-6">
              {/* Nodes Cloud / Selector */}
              <div className="flex flex-wrap gap-2 max-h-56 overflow-y-auto p-1">
                {graphData.nodes?.map((node: any) => {
                  const isSelected = selectedNode?.id === node.id;
                  const labelColor = getNodeColor(node.label);
                  return (
                    <button
                      key={node.id}
                      onClick={() => setSelectedNode(node)}
                      className={`px-3 py-1.5 rounded-xl border text-xs font-medium transition-all ${labelColor} ${
                        isSelected ? "ring-2 ring-cyan-400 scale-105 shadow-md shadow-cyan-500/20" : "hover:brightness-125"
                      }`}
                    >
                      <span className="opacity-70 text-[10px] mr-1.5 uppercase">{node.label}:</span>
                      <span>{node.properties.name || node.properties.display_code || node.id}</span>
                    </button>
                  );
                })}
              </div>

              {/* Connected Relationships Stream */}
              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Top Graph Traversal Edges
                </div>
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                  {graphData.edges?.slice(0, 30).map((edge: any) => (
                    <div
                      key={edge.id}
                      className="p-3 rounded-xl bg-slate-900/50 border border-slate-800/80 text-xs flex items-center justify-between"
                    >
                      <div className="flex items-center space-x-2 font-mono">
                        <span className="text-slate-300 font-semibold">{edge.source}</span>
                        <span className="text-cyan-400 text-[11px] px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-800/40">
                          -[:{edge.type}]-&gt;
                        </span>
                        <span className="text-slate-300 font-semibold">{edge.target}</span>
                      </div>
                      <div className="text-[11px] text-slate-400 font-mono">
                        {edge.properties ? JSON.stringify(edge.properties).replace(/["{}]/g, "") : ""}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Node Inspector */}
        <div className="lg:col-span-4 glass-panel p-6 rounded-2xl border border-slate-800 space-y-5">
          <div className="border-b border-slate-800/80 pb-3">
            <h2 className="text-sm font-bold text-white flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              <span>Node Inspector & Provenance</span>
            </h2>
          </div>

          {!selectedNode ? (
            <div className="text-xs text-slate-400 text-center py-12">
              Select any graph node on the left to inspect its properties and relational source.
            </div>
          ) : (
            <div className="space-y-4 animate-in fade-in duration-200 text-xs">
              <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
                <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Node Label</div>
                <div className="text-base font-bold text-white flex items-center space-x-2">
                  <span className={`px-2 py-0.5 rounded text-xs border ${getNodeColor(selectedNode.label)}`}>
                    {selectedNode.label}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 font-mono break-all pt-1">
                  Graph ID: {selectedNode.id}
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                  Projected Properties
                </div>
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-1.5 font-mono text-[11px]">
                  {Object.entries(selectedNode.properties || {}).map(([key, val]) => (
                    <div key={key} className="flex justify-between">
                      <span className="text-slate-400">{key}:</span>
                      <span className="text-cyan-300 font-semibold">{String(val)}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-900/40 border border-slate-800 text-[11px] text-slate-400 leading-relaxed">
                <strong>Provenance Guarantee:</strong> This graph node is dynamically projected from the authoritative PostgreSQL database. No medical data originates in Neo4j.
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
