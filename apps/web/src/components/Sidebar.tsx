"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  CheckSquare,
  Database,
  FileText,
  FlaskConical,
  KeyRound,
  LayoutDashboard,
  Lock,
  Network,
  Receipt,
  ScrollText,
  ServerCog,
  Share2,
  UserCog,
  Users,
  X,
} from "lucide-react";

type NavItem = { label: string; href: string; icon: React.ComponentType<{ className?: string }>; roles: string[] };

const ALL = ["patient", "doctor", "researcher", "insurance_analyst", "admin"];

const SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Overview",
    items: [{ label: "Dashboard", href: "/", icon: LayoutDashboard, roles: ALL }],
  },
  {
    title: "Clinical care",
    items: [
      { label: "Patients", href: "/patients", icon: Users, roles: ["doctor", "admin"] },
      { label: "My health record", href: "/patients", icon: Users, roles: ["patient"] },
      { label: "Clinical notes", href: "/documents", icon: FileText, roles: ["patient", "doctor", "admin"] },
      { label: "Consent & sharing", href: "/consent", icon: KeyRound, roles: ["patient", "admin"] },
      { label: "Record integrity", href: "/integrity", icon: CheckSquare, roles: ["patient", "doctor", "admin"] },
      { label: "Access history", href: "/audit", icon: ScrollText, roles: ["patient", "doctor", "admin"] },
    ],
  },
  {
    title: "Research",
    items: [
      { label: "Research projects", href: "/research", icon: FlaskConical, roles: ["researcher", "admin"] },
      { label: "Cohort explorer", href: "/cohorts", icon: Network, roles: ["researcher", "admin"] },
      { label: "Disease–drug graph", href: "/graph", icon: Share2, roles: ["doctor", "researcher", "admin"] },
    ],
  },
  {
    title: "Billing",
    items: [{ label: "Claims & analytics", href: "/insurance", icon: Receipt, roles: ["insurance_analyst", "admin"] }],
  },
  {
    title: "Administration",
    items: [
      { label: "Users & hospitals", href: "/admin/users", icon: UserCog, roles: ["admin"] },
      { label: "System health", href: "/admin", icon: ServerCog, roles: ["admin"] },
      { label: "Operations", href: "/admin/operations", icon: Activity, roles: ["admin"] },
      { label: "Database console", href: "/admin/dbms", icon: Database, roles: ["admin"] },
    ],
  },
  {
    title: "Account",
    items: [{ label: "Account security", href: "/account/security", icon: Lock, roles: ALL }],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [role, setRole] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const updateRole = () => {
      try {
        const user = JSON.parse(window.localStorage.getItem("medchain_user") || "null");
        setRole(typeof user?.role === "string" ? user.role : null);
      } catch {
        setRole(null);
      }
    };
    const toggle = () => setOpen((value) => !value);
    updateRole();
    window.addEventListener("medchain-user-context-changed", updateRole);
    window.addEventListener("medchain-toggle-sidebar", toggle);
    return () => {
      window.removeEventListener("medchain-user-context-changed", updateRole);
      window.removeEventListener("medchain-toggle-sidebar", toggle);
    };
  }, []);

  useEffect(() => setOpen(false), [pathname]);

  const sections = SECTIONS
    .map((section) => ({ ...section, items: section.items.filter((item) => role && item.roles.includes(role)) }))
    .filter((section) => section.items.length > 0);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname === href || (href !== "/admin" && pathname.startsWith(`${href}/`)));

  return (
    <>
      {open && <div className="fixed inset-0 z-50 bg-slate-900/40 md:hidden" onClick={() => setOpen(false)} />}
      <aside
        className={`fixed inset-y-0 left-0 z-50 md:sticky md:top-16 md:z-auto md:h-[calc(100vh-4rem)] w-64 shrink-0 bg-white border-r border-slate-200 flex flex-col
          transform transition-transform md:transform-none ${open ? "translate-x-0" : "-translate-x-full md:translate-x-0"}`}
      >
        <div className="md:hidden h-16 px-4 flex items-center justify-between border-b border-slate-200">
          <span className="text-sm font-semibold text-slate-900">Menu</span>
          <button type="button" aria-label="Close navigation" onClick={() => setOpen(false)} className="p-2 rounded-md text-slate-500 hover:bg-slate-100">
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5" aria-label="Main">
          {sections.map((section) => (
            <div key={section.title}>
              <div className="px-3 mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{section.title}</div>
              <ul className="space-y-0.5">
                {section.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(item.href);
                  return (
                    <li key={`${item.href}-${item.label}`}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={`relative flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                          active ? "bg-brand-50 text-brand-800 font-semibold" : "text-slate-700 hover:bg-slate-50 hover:text-slate-900"
                        }`}
                      >
                        {active && <span className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-brand-600" />}
                        <Icon className={`w-[18px] h-[18px] ${active ? "text-brand-600" : "text-slate-400"}`} />
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
