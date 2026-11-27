"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ApiClient } from "@/lib/api";
import LiveClinicalFeed from "@/components/LiveClinicalFeed";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  FileText,
  FlaskConical,
  KeyRound,
  Layers,
  Network,
  Receipt,
  ScrollText,
  ServerCog,
  UserCog,
  UserPlus,
  Users,
} from "lucide-react";

type Tile = {
  title: string;
  value: string | number;
  sub: string;
  icon: React.ComponentType<{ className?: string }>;
  tone: string;
  href: string;
  roles: string[];
};

type Action = { label: string; text: string; href: string; icon: React.ComponentType<{ className?: string }>; roles: string[] };

const ACTIONS: Action[] = [
  { label: "Register a patient", text: "Create a record and issue a portal activation code", href: "/patients", icon: UserPlus, roles: ["admin"] },
  { label: "Open patient list", text: "Charts, encounters, results, and care teams", href: "/patients", icon: Users, roles: ["doctor"] },
  { label: "View my health record", text: "Visits, diagnoses, prescriptions, and lab results", href: "/patients", icon: Users, roles: ["patient"] },
  { label: "Write a clinical note", text: "Encrypted notes linked to an encounter", href: "/documents", icon: FileText, roles: ["doctor"] },
  { label: "Manage research consent", text: "Grant or withdraw access to your data", href: "/consent", icon: KeyRound, roles: ["patient"] },
  { label: "See who viewed my record", text: "Every access is logged", href: "/audit", icon: ScrollText, roles: ["patient"] },
  { label: "Run a consented query", text: "Aggregate results with small-cell suppression", href: "/research", icon: FlaskConical, roles: ["researcher"] },
  { label: "Explore cohorts", text: "Consent-scoped patient groups", href: "/cohorts", icon: Layers, roles: ["researcher"] },
  { label: "Review flagged claims", text: "Explainable anomaly rules", href: "/insurance", icon: Receipt, roles: ["insurance_analyst"] },
  { label: "Manage staff accounts", text: "Activation links, roles, and MFA resets", href: "/admin/users", icon: UserCog, roles: ["admin"] },
  { label: "Verify record integrity", text: "Check documents against their ledger commitments", href: "/integrity", icon: FileCheck2, roles: ["doctor", "admin"] },
  { label: "Check system health", text: "Databases, ledger, integrations, and alerts", href: "/admin", icon: ServerCog, roles: ["admin"] },
];

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

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
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    const updateRole = () => {
      try {
        const user = JSON.parse(window.localStorage.getItem("medchain_user") || "null");
        setRole(typeof user?.role === "string" ? user.role : null);
        setEmail(typeof user?.email === "string" ? user.email : "");
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

  const show = (value: number | null) => (loading ? "…" : value ?? "—");

  const tiles: Tile[] = [
    {
      title: role === "patient" ? "My records" : role === "doctor" ? "Patients in my care" : "Registered patients",
      value: show(stats.patients),
      sub: role === "doctor" ? "Active care-team assignments" : "Patient charts",
      icon: Users, tone: "bg-brand-50 text-brand-700", href: "/patients", roles: ["patient", "doctor", "admin"],
    },
    {
      title: "Active consents", value: show(stats.consents), sub: "Granted and in date",
      icon: KeyRound, tone: "bg-violet-50 text-violet-700", href: "/consent", roles: ["patient", "admin"],
    },
    {
      title: "Verified documents", value: show(stats.documents), sub: "With an integrity commitment",
      icon: FileCheck2, tone: "bg-emerald-50 text-emerald-700", href: "/integrity", roles: ["patient", "doctor", "admin"],
    },
    {
      title: "Graph relationships", value: show(stats.graphEdges),
      sub: role === "researcher" ? "Within your consented scope" : "Disease and drug links",
      icon: Network, tone: "bg-sky-50 text-sky-700", href: "/graph", roles: ["doctor", "researcher", "admin"],
    },
    {
      title: "Claims for review", value: show(stats.flaggedClaims), sub: "Flagged by anomaly rules",
      icon: AlertTriangle, tone: "bg-amber-50 text-amber-700", href: "/insurance", roles: ["insurance_analyst", "admin"],
    },
    {
      title: "Research projects", value: show(stats.researchProjects), sub: "Projects you manage",
      icon: FlaskConical, tone: "bg-violet-50 text-violet-700", href: "/research", roles: ["researcher", "admin"],
    },
    {
      title: "Consented cohorts", value: show(stats.cohorts), sub: "In the current project",
      icon: Layers, tone: "bg-teal-50 text-teal-700", href: "/cohorts", roles: ["researcher", "admin"],
    },
  ];
  const visibleTiles = tiles.filter((tile) => role && tile.roles.includes(role));
  const visibleActions = ACTIONS.filter((action) => role && action.roles.includes(role));
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const healthy = health?.status === "healthy";
  const healthPill = `inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium border ${
    healthy ? "bg-emerald-50 border-emerald-200 text-emerald-800" : "bg-amber-50 border-amber-200 text-amber-800"}`;
  const healthContent = (
    <>
      {healthy ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
      {healthy ? "All services operational" : "Some services degraded"}
    </>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-slate-500">{today}</p>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {greeting()}{email ? `, ${email.split("@")[0]}` : ""}
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            {role === "patient" && "A summary of your health record and who can see it."}
            {role === "doctor" && "An overview of the patients in your care."}
            {role === "researcher" && "Your consented research workspace."}
            {role === "insurance_analyst" && "Claims activity for your insurance provider."}
            {role === "admin" && "Hospital administration overview."}
          </p>
        </div>
        {role === "admin" && health && !healthy && (
          <Link href="/admin" className={healthPill}>{healthContent}</Link>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {visibleTiles.map((tile) => {
          const Icon = tile.icon;
          return (
            <Link key={tile.title} href={tile.href}
              className="bg-white rounded-lg border border-slate-200 shadow-card p-5 hover:border-brand-300 hover:shadow-md transition">
              <div className="flex items-start justify-between">
                <span className="text-sm font-medium text-slate-600">{tile.title}</span>
                <span className={`w-9 h-9 rounded-lg flex items-center justify-center ${tile.tone}`}>
                  <Icon className="w-[18px] h-[18px]" />
                </span>
              </div>
              <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{tile.value}</div>
              <div className="mt-1 text-xs text-slate-500">{tile.sub}</div>
            </Link>
          );
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {role && ["doctor", "patient", "admin"].includes(role) ? (
            <LiveClinicalFeed />
          ) : (
            <div className="bg-white rounded-lg border border-slate-200 shadow-card p-6">
              <h2 className="text-base font-semibold text-slate-900">How your access works</h2>
              <ul className="mt-3 space-y-2 text-sm text-slate-600 list-disc pl-5">
                {role === "researcher" ? (
                  <>
                    <li>You only see data from patients who consented to your project.</li>
                    <li>Groups smaller than the minimum cohort size are suppressed.</li>
                    <li>Every query is recorded in the audit log.</li>
                  </>
                ) : (
                  <>
                    <li>You see claims for your assigned insurance provider only.</li>
                    <li>Flagged claims list the rule that triggered them.</li>
                    <li>Every review action is recorded in the audit log.</li>
                  </>
                )}
              </ul>
            </div>
          )}
        </div>

        <div className="bg-white rounded-lg border border-slate-200 shadow-card self-start">
          <div className="px-5 py-4 border-b border-slate-200">
            <h2 className="text-base font-semibold text-slate-900">Quick actions</h2>
          </div>
          <ul className="divide-y divide-slate-100">
            {visibleActions.map((action) => {
              const Icon = action.icon;
              return (
                <li key={action.label}>
                  <Link href={action.href} className="group flex items-center gap-3 px-5 py-3 hover:bg-slate-50">
                    <Icon className="w-[18px] h-[18px] text-brand-600 shrink-0" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-slate-900 group-hover:text-brand-700">{action.label}</span>
                      <span className="block text-xs text-slate-500 truncate">{action.text}</span>
                    </span>
                    <ArrowRight className="w-4 h-4 text-slate-300 group-hover:text-brand-600" />
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
