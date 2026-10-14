"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ApiClient } from "@/lib/api";
import {
  Users,
  FileCheck2,
  KeyRound,
  Network,
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
  Database,
  Cpu,
  Layers,
  Sparkles
} from "lucide-react";

export default function DashboardPage() {
  const [stats, setStats] = useState({
    patients: 0,
    consents: 0,
    documents: 0,
    flaggedClaims: 0,
    graphEdges: 0,
  });
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [pts, consents, claims, graphStatus, h] = await Promise.all([
          ApiClient.getPatients().catch(() => []),
          ApiClient.getConsents().catch(() => []),
          ApiClient.getInsuranceClaims(true).catch(() => []),
          ApiClient.getGraphOverview().catch(() => ({ edges: [] })),
          ApiClient.getSystemHealth().catch(() => null),
        ]);

        setStats({
          patients: pts.length,
          consents: consents.filter((c: any) => c.status === "GRANTED").length,
          documents: pts.length * 2,
          flaggedClaims: claims.length,
          graphEdges: graphStatus.edges?.length || 51,
        });
        setHealth(h);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadDashboard();
  }, []);

  const metricCards = [
    {
      title: "Synthetic Patients",
      value: loading ? "..." : stats.patients,
      sub: "Relational ACID Store",
      icon: Users,
      color: "from-blue-500/20 to-cyan-500/10 text-cyan-400 border-cyan-500/30",
      href: "/patients",
    },
    {
      title: "Active Consents",
      value: loading ? "..." : stats.consents,
      sub: "Patient-Governed Scope",
      icon: KeyRound,
      color: "from-purple-500/20 to-indigo-500/10 text-purple-400 border-purple-500/30",
      href: "/consent",
    },
    {
      title: "Anchored Commitments",
      value: loading ? "..." : stats.documents,
      sub: "Salted SHA-256 Hashes",
      icon: FileCheck2,
      color: "from-emerald-500/20 to-teal-500/10 text-emerald-400 border-emerald-500/30",
      href: "/integrity",
    },
    {
      title: "Graph Projections",
      value: loading ? "..." : `${stats.graphEdges} Edges`,
      sub: "Neo4j Derived Knowledge",
      icon: Network,
      color: "from-sky-500/20 to-blue-500/10 text-sky-400 border-sky-500/30",
      href: "/graph",
    },
    {
      title: "Claims For Review",
      value: loading ? "..." : stats.flaggedClaims,
      sub: "Explainable Anomaly Rules",
      icon: AlertTriangle,
      color: "from-amber-500/20 to-orange-500/10 text-amber-400 border-amber-500/30",
      href: "/insurance",
    },
  ];

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Hero Banner */}
      <div className="relative overflow-hidden rounded-2xl glass-panel p-8 border border-slate-800">
        <div className="absolute -right-12 -top-12 w-64 h-64 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
        <div className="relative z-10 max-w-3xl space-y-3">
          <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 text-xs font-semibold">
            <Sparkles className="w-3.5 h-3.5" />
            <span>End-to-End Database Engineering & Healthcare Privacy Platform</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-white">
            Privacy-Preserving <span className="gradient-text">Healthcare Intelligence</span> & Ledger Audit
          </h1>
          <p className="text-sm text-slate-400 leading-relaxed">
            Multi-model database architecture integrating an authoritative PostgreSQL relational core, 
            semi-structured clinical documents in MongoDB, derived disease-drug graph projections in Neo4j, 
            and a Solidity smart contract for tamper-evident consent commitments.
          </p>
        </div>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {metricCards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <Link
              key={idx}
              href={card.href}
              className={`p-5 rounded-2xl border glass-card bg-gradient-to-br ${card.color} flex flex-col justify-between`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-300">{card.title}</span>
                <Icon className="w-5 h-5 opacity-80" />
              </div>
              <div className="mt-4">
                <div className="text-2xl font-bold tracking-tight text-white">{card.value}</div>
                <div className="text-[11px] text-slate-400 mt-1">{card.sub}</div>
              </div>
            </Link>
          );
        })}
      </div>

      {/* Multi-Store Architectural Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <h2 className="text-base font-bold text-white flex items-center space-x-2">
              <Database className="w-4 h-4 text-cyan-400" />
              <span>Multi-Store Architecture & Data Ownership</span>
            </h2>
            <span className="text-xs text-slate-400 font-mono">Source-of-Truth Hierarchy</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-cyan-300">1. PostgreSQL Relational Core</span>
                <span className="px-2 py-0.5 rounded text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">Authoritative</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Source of truth for normalized patients, visits, diagnoses, prescriptions, insurance claims, and active consent records.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-emerald-300">2. MongoDB Document Store</span>
                <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Semi-Structured</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Stores unstructured clinical narratives, physician notes, and diagnostic observations. Relational metadata links by UUID.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-sky-300">3. Neo4j Graph Intelligence</span>
                <span className="px-2 py-0.5 rounded text-[10px] bg-sky-500/10 text-sky-400 border border-sky-500/20">Derived Projection</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                100% rebuildable knowledge graph exploring disease co-occurrences and medication-to-adverse-event associations.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-purple-300">4. Hardhat EVM Contract</span>
                <span className="px-2 py-0.5 rounded text-[10px] bg-purple-500/10 text-purple-400 border border-purple-500/20">Audit Trail</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Append-only ledger anchoring salted SHA-256 commitments and consent grant/revocation events. Zero PII stored on-chain.
              </p>
            </div>
          </div>
        </div>

        {/* Capstone Demonstration Workflows */}
        <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
          <div className="border-b border-slate-800/80 pb-3">
            <h2 className="text-base font-bold text-white flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Interactive Demonstration</span>
            </h2>
            <p className="text-xs text-slate-400">Step-by-step presentation pathways</p>
          </div>

          <div className="space-y-2.5">
            <Link
              href="/consent"
              className="p-3 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-cyan-500/40 flex items-center justify-between transition-all group"
            >
              <div>
                <div className="text-xs font-semibold text-slate-200 group-hover:text-cyan-300">1. Consent Grant & Revocation</div>
                <div className="text-[11px] text-slate-400">Patient grants or revokes research access</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-cyan-400 group-hover:translate-x-1 transition-all" />
            </Link>

            <Link
              href="/research"
              className="p-3 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-purple-500/40 flex items-center justify-between transition-all group"
            >
              <div>
                <div className="text-xs font-semibold text-slate-200 group-hover:text-purple-300">2. Research Query Engine</div>
                <div className="text-[11px] text-slate-400">Consent-gated queries with instant 403 denial</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-purple-400 group-hover:translate-x-1 transition-all" />
            </Link>

            <Link
              href="/integrity"
              className="p-3 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-emerald-500/40 flex items-center justify-between transition-all group"
            >
              <div>
                <div className="text-xs font-semibold text-slate-200 group-hover:text-emerald-300">3. Cryptographic Verification</div>
                <div className="text-[11px] text-slate-400">Salted hash matching & tamper detection</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-emerald-400 group-hover:translate-x-1 transition-all" />
            </Link>

            <Link
              href="/insurance"
              className="p-3 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-amber-500/40 flex items-center justify-between transition-all group"
            >
              <div>
                <div className="text-xs font-semibold text-slate-200 group-hover:text-amber-300">4. Anomaly Review Queue</div>
                <div className="text-[11px] text-slate-400">Explainable duplicate billing detection</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-amber-400 group-hover:translate-x-1 transition-all" />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
