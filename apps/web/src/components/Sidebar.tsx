"use client";

import React from "react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Users,
  FileText,
  KeyRound,
  FlaskConical,
  Network,
  Share2,
  DollarSign,
  CheckSquare,
  ScrollText,
  ServerCog,
  Database,
} from "lucide-react";

export default function Sidebar() {
  const pathname = usePathname();
  const [role, setRole] = useState<string | null>(null);

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

  const navItems = [
    { label: "Dashboard", href: "/", icon: LayoutDashboard, roles: ["patient", "doctor", "researcher", "insurance_analyst", "admin"] },
    { label: "Patient Records", href: "/patients", icon: Users, roles: ["patient", "doctor", "admin"] },
    { label: "Clinical Notes", href: "/documents", icon: FileText, roles: ["patient", "doctor", "admin"] },
    { label: "Consent Center", href: "/consent", icon: KeyRound, roles: ["patient", "admin"] },
    { label: "Research Projects", href: "/research", icon: FlaskConical, roles: ["researcher", "admin"] },
    { label: "Cohort Explorer", href: "/cohorts", icon: Network, roles: ["researcher", "admin"] },
    { label: "Disease-Drug Graph", href: "/graph", icon: Share2, roles: ["doctor", "researcher", "admin"] },
    { label: "Insurance Analytics", href: "/insurance", icon: DollarSign, roles: ["insurance_analyst", "admin"] },
    { label: "Record Integrity", href: "/integrity", icon: CheckSquare, roles: ["patient", "doctor", "admin"] },
    { label: "Audit & Ledger", href: "/audit", icon: ScrollText, roles: ["patient", "doctor", "admin"] },
    { label: "System Health", href: "/admin", icon: ServerCog, roles: ["admin"] },
    { label: "DBMS Showcase", href: "/admin/dbms", icon: Database, roles: ["admin"] },
  ];
  const visibleItems = navItems.filter((item) => role && item.roles.includes(role));

  return (
    <aside className="w-64 border-r border-slate-800/80 bg-slate-950/70 backdrop-blur-xl flex flex-col justify-between p-4 shrink-0 min-h-[calc(100vh-61px)]">
      <div className="space-y-1">
        <div className="px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
          Platform Modules
        </div>
        <nav className="space-y-0.5">
          {visibleItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center space-x-3 px-3 py-2 rounded-xl text-xs font-medium transition-all ${
                  isActive
                    ? "bg-gradient-to-r from-cyan-500/20 to-blue-500/10 text-cyan-300 font-semibold border border-cyan-500/30 shadow-sm shadow-cyan-500/10"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "text-cyan-400" : "text-slate-400"}`} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="p-3.5 rounded-xl bg-slate-900/40 border border-slate-800/60 text-[11px] text-slate-400 space-y-1.5">
        <div className="flex items-center space-x-2 text-cyan-400 font-semibold">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span>
          <span>Academic Capstone</span>
        </div>
        <p className="text-[10px] leading-relaxed text-slate-400">
          Synthetic healthcare data only. Demonstrates ACID relational source, document store, graph projection & EVM audit trail.
        </p>
      </div>
    </aside>
  );
}
