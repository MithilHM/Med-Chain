"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ApiClient } from "@/lib/api";
import LiveClinicalFeed from "@/components/LiveClinicalFeed";
import {
  Users,
  FileCheck2,
  KeyRound,
  Network,
  FlaskConical,
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
  Database,
  Layers,
  Sparkles
} from "lucide-react";

export default function DashboardPage() {
  const [stats, setStats] = useState({
    patients: null as number | null,
    consents: null as number | null,
    documents: null as number | null,
    flaggedClaims: null as number | null,
    graphEdges: null as number | null,
    researchProjects: null as number | null,
    cohorts: null as number | null,
  });
  const [role, setRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    const updateRole = () => {
      try {
        const user = JSON.parse(window.localStorage.getItem("medchain_user") || "null");
        setRole(typeof user?.role === "string" ? user.role : null);
      } catch {
        setRole(null);
      }
    };
    updateRole();
    window.addEventListener("medchain-user-context-changed", updateRole);
    return () => window.removeEventListener("medchain-user-context-changed", updateRole);
  }, []);

  useEffect(() => {
    if (!role) return;
    let active = true;
    const safe = <T,>(promise: Promise<T>) => promise.catch(() => null);

    async function loadDashboard() {
      setLoading(true);
      try {
        const canSeePatients = ["patient", "doctor", "admin"].includes(role!);
        const canSeeConsents = ["patient", "admin"].includes(role!);
        const canSeeDocuments = ["patient", "doctor", "admin"].includes(role!);
        const canSeeClaims = ["insurance_analyst", "admin"].includes(role!);
        const canSeeGraph = ["doctor", "admin"].includes(role!);
        const canSeeResearch = ["researcher", "admin"].includes(role!);

        const [healthResult, patientsResult, consentsResult, documentsResult, claimsResult, graphResult] = await Promise.all([
          safe(ApiClient.getSystemHealth()),
          canSeePatients ? safe(ApiClient.getPatients()) : Promise.resolve(null),
          canSeeConsents ? safe(ApiClient.getConsents()) : Promise.resolve(null),
          canSeeDocuments ? safe(ApiClient.getDocuments()) : Promise.resolve(null),
          canSeeClaims ? safe(ApiClient.getInsuranceClaims(true)) : Promise.resolve(null),
          canSeeGraph ? safe(ApiClient.getGraphOverview()) : Promise.resolve(null),
        ]);

        let projects: any[] | null = null;
        let cohorts: any[] | null = null;
        let researcherGraph: any = null;
        if (canSeeResearch) {
          projects = await safe(ApiClient.getResearchProjects());
          const activeProject = projects?.find((project) => project.status === "ACTIVE") ?? projects?.[0];
          if (activeProject) {
            [researcherGraph, cohorts] = await Promise.all([
              safe(ApiClient.getGraphOverview(activeProject.id)),
              safe(ApiClient.getCohorts(activeProject.id)),
            ]);
          }
        }

        if (!active) return;
        const graphStatus = role === "researcher" ? researcherGraph : graphResult;
        const now = Date.now();
        setStats({
          patients: patientsResult?.length ?? null,
          consents: consentsResult?.filter((consent: any) =>
            consent.status === "GRANTED" &&
            !consent.revoked_at &&
            Date.parse(consent.valid_from) <= now &&
            Date.parse(consent.valid_until) > now
          ).length ?? null,
          documents: documentsResult?.filter((doc: any) => Boolean(doc.commitment_hash)).length ?? null,
          flaggedClaims: claimsResult?.length ?? null,
          graphEdges: graphStatus?.edges?.length ?? null,
          researchProjects: projects?.length ?? null,
          cohorts: cohorts?.length ?? null,
        });
        setHealth(healthResult);
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadDashboard();
    return () => { active = false; };
  }, [role]);

  const metricCards = [
    {
      title: role === "patient" ? "My Patient Record" : role === "doctor" ? "Assigned Patients" : "Synthetic Patients",
      value: loading ? "..." : stats.patients ?? "N/A",
      sub: "Relational ACID Store",
      icon: Users,
      color: "from-blue-500/20 to-cyan-500/10 text-cyan-400 border-cyan-500/30",
      href: "/patients",
      roles: ["patient", "doctor", "admin"],
    },
    {
      title: "Active Consents",
      value: loading ? "..." : stats.consents ?? "N/A",
      sub: "Patient-Governed Scope",
      icon: KeyRound,
      color: "from-purple-500/20 to-indigo-500/10 text-purple-400 border-purple-500/30",
      href: "/consent",
      roles: ["patient", "admin"],
    },
    {
      title: "Integrity Commitments",
      value: loading ? "..." : stats.documents ?? "N/A",
      sub: "Off-chain salted SHA-256 hashes",
      icon: FileCheck2,
      color: "from-emerald-500/20 to-teal-500/10 text-emerald-400 border-emerald-500/30",
      href: "/integrity",
      roles: ["patient", "doctor", "admin"],
    },
    {
      title: "Graph Projections",
      value: loading ? "..." : stats.graphEdges === null ? "N/A" : `${stats.graphEdges} Edges`,
      sub: role === "researcher" ? "Consent scoped relationships" : "Neo4j Derived Knowledge",
      icon: Network,
      color: "from-sky-500/20 to-blue-500/10 text-sky-400 border-sky-500/30",
      href: "/graph",
      roles: ["doctor", "researcher", "admin"],
    },
    {
      title: "Claims For Review",
      value: loading ? "..." : stats.flaggedClaims ?? "N/A",
      sub: "Explainable Anomaly Rules",
      icon: AlertTriangle,
      color: "from-amber-500/20 to-orange-500/10 text-amber-400 border-amber-500/30",
      href: "/insurance",
      roles: ["insurance_analyst", "admin"],
    },
    {
      title: "Research Projects",
      value: loading ? "..." : stats.researchProjects ?? "N/A",
      sub: "Projects you manage",
      icon: FlaskConical,
      color: "from-fuchsia-500/20 to-purple-500/10 text-fuchsia-400 border-fuchsia-500/30",
      href: "/research",
      roles: ["researcher", "admin"],
    },
    {
      title: "Consented Cohorts",
      value: loading ? "..." : stats.cohorts ?? "N/A",
      sub: "Current project scope",
      icon: Layers,
      color: "from-teal-500/20 to-emerald-500/10 text-teal-400 border-teal-500/30",
      href: "/cohorts",
      roles: ["researcher", "admin"],
    },
  ];
  const visibleMetricCards = metricCards.filter((card) => role && card.roles.includes(role));

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
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {visibleMetricCards.map((card) => {
          const Icon = card.icon;
          return (
            <Link
              key={card.title}
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

      {/* Real-time clinical events (care roles only; enforced by the API) */}
      {role && ["doctor", "patient", "admin"].includes(role) && <LiveClinicalFeed />}

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
                Append-only ledger anchoring salted SHA-256 commitments and consent grant/revocation events. Raw medical data and direct identifiers stay off-chain; opaque hashes are used for references.
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
            {role && ["patient", "admin"].includes(role) && <Link
              href="/consent"
              className="p-3 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-cyan-500/40 flex items-center justify-between transition-all group"
            >
              <div>
                <div className="text-xs font-semibold text-slate-200 group-hover:text-cyan-300">1. Consent Grant & Revocation</div>
                <div className="text-[11px] text-slate-400">Patient grants or revokes research access</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-cyan-400 group-hover:translate-x-1 transition-all" />
            </Link>}

            {role && ["researcher", "admin"].includes(role) && <Link
              href="/research"
              className="p-3 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-purple-500/40 flex items-center justify-between transition-all group"
            >
              <div>
                <div className="text-xs font-semibold text-slate-200 group-hover:text-purple-300">2. Research Query Engine</div>
                <div className="text-[11px] text-slate-400">Consent-gated queries with instant 403 denial</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-purple-400 group-hover:translate-x-1 transition-all" />
            </Link>}

            {role && ["patient", "doctor", "admin"].includes(role) && <Link
              href="/integrity"
              className="p-3 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-emerald-500/40 flex items-center justify-between transition-all group"
            >
              <div>
                <div className="text-xs font-semibold text-slate-200 group-hover:text-emerald-300">3. Cryptographic Verification</div>
                <div className="text-[11px] text-slate-400">Salted hash matching & tamper detection</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-emerald-400 group-hover:translate-x-1 transition-all" />
            </Link>}

            {role && ["insurance_analyst", "admin"].includes(role) && <Link
              href="/insurance"
              className="p-3 rounded-xl bg-slate-900/40 border border-slate-800/80 hover:border-amber-500/40 flex items-center justify-between transition-all group"
            >
              <div>
                <div className="text-xs font-semibold text-slate-200 group-hover:text-amber-300">4. Anomaly Review Queue</div>
                <div className="text-[11px] text-slate-400">Explainable duplicate billing detection</div>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-amber-400 group-hover:translate-x-1 transition-all" />
            </Link>}
          </div>
        </div>
      </div>
    </div>
  );
}
