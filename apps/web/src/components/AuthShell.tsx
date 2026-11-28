"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Clock } from "lucide-react";
import { ApiClient, SESSION_EXPIRED_EVENT } from "@/lib/api";
import Sidebar from "@/components/Sidebar";

// Shared by every open tab, so one tab in use keeps the others signed in.
const REFRESH_KEY = "medchain_session_refreshed";
const WARN_BEFORE_MS = 60_000;
const ACTIVITY_EVENTS = ["mousedown", "mousemove", "keydown", "scroll", "touchstart"] as const;

function lastRefresh(): { at: number; ttl: number } | null {
  try { return JSON.parse(window.localStorage.getItem(REFRESH_KEY) || "null"); } catch { return null; }
}

function returnPath() {
  return encodeURIComponent(window.location.pathname + window.location.search);
}

export default function AuthShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  // Public pages: sign-in and account activation / patient-portal sign-up.
  const isLoginPage = pathname === "/login" || pathname === "/signup";
  const [authorized, setAuthorized] = useState(false);
  const [idleWarning, setIdleWarning] = useState(false);
  const lastActivity = useRef(0);  // only real input counts; loading a page is not activity

  const signOut = useCallback((reason: string) => {
    ApiClient.clearLocalUser();
    setIdleWarning(false);
    router.replace(`/login?reason=${reason}&next=${returnPath()}`);
  }, [router]);

  const refresh = useCallback(async () => {
    try {
      const res = await ApiClient.refreshSession();
      window.localStorage.setItem(REFRESH_KEY, JSON.stringify({ at: Date.now(), ttl: res.idle_timeout_seconds * 1000 }));
      setIdleWarning(false);
    } catch (err: any) {
      if (err.status === 401) signOut(/limit/i.test(err.message) ? "limit" : "expired");
    }
  }, [signOut]);

  useEffect(() => {
    let active = true;
    if (isLoginPage) {
      setAuthorized(true);
      return () => { active = false; };
    }

    setAuthorized(false);
    const authorize = async () => {
      try {
        const user = await ApiClient.getCurrentUser();
        localStorage.setItem("medchain_user", JSON.stringify(user));
        const last = lastRefresh();
        // Unknown token age (fresh sign-in or reload): refresh once so the idle clock is accurate.
        if (!last || Date.now() - last.at >= last.ttl / 3) await refresh();
        if (active) setAuthorized(true);
      } catch {
        // Someone who was signed in on this browser is told why; a first visit just sees the sign-in page.
        const wasSignedIn = !!localStorage.getItem("medchain_user");
        ApiClient.clearLocalUser();
        if (active) router.replace(`/login?${wasSignedIn ? "reason=expired&" : ""}next=${returnPath()}`);
      }
    };
    void authorize();
    return () => { active = false; };
  }, [isLoginPage, pathname, router, refresh]);

  // Keep working users signed in; sign idle ones out (shared workstations), with a warning first.
  useEffect(() => {
    if (isLoginPage || !authorized) return;
    const mark = () => { lastActivity.current = Date.now(); };
    ACTIVITY_EVENTS.forEach((name) => window.addEventListener(name, mark, { passive: true }));
    const tick = window.setInterval(() => {
      const last = lastRefresh();
      if (!last) return;
      const age = Date.now() - last.at;
      if (age >= last.ttl) return signOut("idle");
      if (lastActivity.current > last.at && age >= last.ttl / 3) return void refresh();
      setIdleWarning(age >= last.ttl - WARN_BEFORE_MS);
    }, 5000);
    const onExpired = () => signOut("expired");
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => {
      ACTIVITY_EVENTS.forEach((name) => window.removeEventListener(name, mark));
      window.clearInterval(tick);
      window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
    };
  }, [isLoginPage, authorized, refresh, signOut]);

  if (!authorized) {
    return (
      <main className="flex-1 min-h-[50vh] flex flex-col items-center justify-center gap-3 text-sm text-slate-500">
        <span className="w-6 h-6 rounded-full border-2 border-brand-200 border-t-brand-600 animate-spin" />
        Checking your session…
      </main>
    );
  }

  if (isLoginPage) {
    return <main className="flex-1 flex">{children}</main>;
  }

  return (
    <div className="flex flex-1 min-h-0">
      {idleWarning && (
        <div role="alert" className="motion-rise-in fixed inset-x-4 bottom-4 z-[60] mx-auto flex max-w-lg flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 shadow-lg sm:flex-nowrap">
          <Clock className="w-4 h-4 shrink-0" />
          <span className="min-w-0 flex-1">You will be signed out in under a minute because of inactivity.</span>
          <button onClick={() => void refresh()} className="shrink-0 rounded-md bg-brand-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-600 active:scale-[0.97] transition-transform">
            Stay signed in
          </button>
        </div>
      )}
      <Sidebar />
      <main className="flex-1 min-w-0 px-4 py-6 md:px-8 md:py-8">
        <div className="max-w-7xl mx-auto space-y-6">{children}</div>
        <footer className="max-w-7xl mx-auto mt-12 pt-4 border-t border-slate-200 text-xs text-slate-500 flex flex-wrap gap-x-4 gap-y-1">
          <span>MedChain Health · pilot build</span>
          <span>Every access to a patient record is logged and auditable.</span>
          <span>In a medical emergency, call your local emergency number.</span>
        </footer>
      </main>
    </div>
  );
}
