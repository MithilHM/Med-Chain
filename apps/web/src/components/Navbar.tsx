"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ApiClient, UserContext } from "@/lib/api";
import { ChevronDown, HeartPulse, Lock, LogOut, Menu, RefreshCw } from "lucide-react";

export const ROLE_LABELS: Record<string, string> = {
  patient: "Patient",
  doctor: "Clinician",
  researcher: "Researcher",
  insurance_analyst: "Insurance analyst",
  admin: "Administrator",
};

const DEMO_ROLES = [
  { id: "patient", label: "Patient (PT-100201)" },
  { id: "doctor", label: "Clinician (Dr. Chen)" },
  { id: "researcher", label: "Researcher" },
  { id: "insurance_analyst", label: "Insurance analyst" },
  { id: "admin", label: "Administrator" },
];

export function initials(email: string) {
  const name = email.split("@")[0].replace(/[^a-zA-Z]+/g, " ").trim();
  const parts = name.split(" ").filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || parts[0]?.[1] || "")).toUpperCase() || "?";
}

export default function Navbar() {
  const pathname = usePathname();
  const [user, setUser] = useState<UserContext | null>(null);
  const [health, setHealth] = useState<"checking" | "healthy" | "degraded" | "offline">("checking");
  const [menuOpen, setMenuOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const isPublicPage = pathname === "/login" || pathname === "/signup";

  useEffect(() => {
    if (isPublicPage) {
      setUser(null);
      return;
    }
    let active = true;
    const load = () => {
      ApiClient.getCurrentUser()
        .then((current) => active && setUser(current))
        .catch(() => active && setUser(null));
    };
    load();
    ApiClient.getSystemHealth()
      .then((h) => active && setHealth(h.status === "healthy" ? "healthy" : "degraded"))
      .catch(() => active && setHealth("offline"));
    window.addEventListener("medchain-user-context-changed", load);
    return () => {
      active = false;
      window.removeEventListener("medchain-user-context-changed", load);
    };
  }, [isPublicPage]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  const switchRole = async (roleId: string) => {
    setSwitching(true);
    setMenuOpen(false);
    try {
      await ApiClient.demoSwitch(roleId);
      window.location.reload();
    } catch (err: any) {
      alert(`Role switch error: ${err.message}`);
      setSwitching(false);
    }
  };

  const signOut = async () => {
    await ApiClient.logout();
    window.location.href = "/login";
  };

  const healthBadge = {
    checking: { dot: "bg-slate-300", text: "Checking services" },
    healthy: { dot: "bg-emerald-500", text: "All services operational" },
    degraded: { dot: "bg-amber-500", text: "Some services degraded" },
    offline: { dot: "bg-rose-500", text: "Services unavailable" },
  }[health];

  return (
    <header className="sticky top-0 z-40 w-full bg-white border-b border-slate-200">
      <div className="h-16 px-4 md:px-6 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {!isPublicPage && (
            <button
              type="button"
              aria-label="Toggle navigation"
              onClick={() => window.dispatchEvent(new Event("medchain-toggle-sidebar"))}
              className="md:hidden p-2 -ml-2 rounded-md text-slate-600 hover:bg-slate-100"
            >
              <Menu className="w-5 h-5" />
            </button>
          )}
          <Link href={isPublicPage ? "/login" : "/"} className="flex items-center gap-2.5">
            <span className="w-9 h-9 rounded-lg bg-brand-600 flex items-center justify-center">
              <HeartPulse className="w-5 h-5 text-white" />
            </span>
            <span className="leading-tight">
              <span className="block text-[17px] font-bold tracking-tight text-slate-900">
                MedChain <span className="text-brand-600">Health</span>
              </span>
              <span className="hidden sm:block text-[11px] text-slate-500">Clinical Records Portal</span>
            </span>
          </Link>
          <span
            className="hidden md:inline-flex ml-2 px-2 py-0.5 rounded-full bg-amber-50 border border-amber-200 text-[11px] font-medium text-amber-800"
            title="Not yet approved for real patient data. Use synthetic records until go-live sign-off."
          >
            Pilot · synthetic data only
          </span>
        </div>

        {isPublicPage ? (
          <div className="hidden sm:flex items-center gap-2 text-xs text-slate-600">
            <Lock className="w-3.5 h-3.5 text-slate-400" />
            Secure sign-in · every access to a record is logged
          </div>
        ) : (
          <div className="flex items-center gap-3">
            {user && user.role !== "patient" && (
              <div className="hidden lg:flex items-center gap-2 text-xs text-slate-600" title="Platform service status">
                <span className={`w-2 h-2 rounded-full ${healthBadge.dot}`} />
                {healthBadge.text}
              </div>
            )}

            {user && (
              <div className="relative" ref={menuRef}>
                <button
                  type="button"
                  onClick={() => setMenuOpen(!menuOpen)}
                  disabled={switching}
                  aria-expanded={menuOpen}
                  className="flex items-center gap-2.5 pl-1 pr-2 py-1 rounded-full hover:bg-slate-100 transition-colors"
                >
                  <span className="w-8 h-8 rounded-full bg-brand-100 text-brand-800 text-xs font-semibold flex items-center justify-center">
                    {initials(user.email)}
                  </span>
                  <span className="hidden sm:block text-left leading-tight">
                    <span className="block text-sm font-medium text-slate-900 max-w-[200px] truncate">{user.email}</span>
                    <span className="block text-[11px] text-slate-500">
                      {ROLE_LABELS[user.role] || user.role}{user.demo_mode ? " · demo" : ""}
                    </span>
                  </span>
                  {switching ? <RefreshCw className="w-4 h-4 text-slate-400 animate-spin" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
                </button>

                {menuOpen && (
                  <div className="absolute right-0 mt-2 w-64 bg-white rounded-lg border border-slate-200 shadow-lg py-1.5 z-50">
                    <div className="px-4 py-2 border-b border-slate-100">
                      <div className="text-sm font-medium text-slate-900 truncate">{user.email}</div>
                      <div className="text-xs text-slate-500">{ROLE_LABELS[user.role] || user.role}</div>
                    </div>
                    <Link href="/account/security" onClick={() => setMenuOpen(false)}
                      className="flex items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">
                      <Lock className="w-4 h-4 text-slate-400" /> Account security
                    </Link>
                    {user.demo_mode && (
                      <div className="border-t border-slate-100 mt-1 pt-1">
                        <div className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                          Demo: view as
                        </div>
                        {DEMO_ROLES.map((r) => (
                          <button key={r.id} type="button" onClick={() => switchRole(r.id)}
                            className={`w-full text-left px-4 py-1.5 text-sm flex items-center justify-between hover:bg-slate-50 ${
                              user.role === r.id ? "text-brand-700 font-medium" : "text-slate-700"}`}>
                            {r.label}
                            {user.role === r.id && <span className="w-1.5 h-1.5 rounded-full bg-brand-600" />}
                          </button>
                        ))}
                      </div>
                    )}
                    <div className="border-t border-slate-100 mt-1 pt-1">
                      <button type="button" onClick={signOut}
                        className="w-full flex items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">
                        <LogOut className="w-4 h-4 text-slate-400" /> Sign out
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
