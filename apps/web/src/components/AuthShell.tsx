"use client";

import React, { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ApiClient } from "@/lib/api";
import Sidebar from "@/components/Sidebar";

export default function AuthShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  // Public pages: sign-in and account activation / patient-portal sign-up.
  const isLoginPage = pathname === "/login" || pathname === "/signup";
  const [authorized, setAuthorized] = useState(false);

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
        if (active) setAuthorized(true);
      } catch {
        ApiClient.clearLocalUser();
        if (active) router.replace("/login");
      }
    };
    void authorize();
    return () => { active = false; };
  }, [isLoginPage, pathname, router]);

  if (!authorized) {
    return (
      <main className="flex-1 min-h-[50vh] flex items-center justify-center text-sm text-slate-400">
        Checking your session…
      </main>
    );
  }

  if (isLoginPage) {
    return (
      <main className="flex-1 overflow-y-auto p-6 md:p-8 bg-gradient-to-b from-slate-950 via-slate-900/30 to-slate-950">
        <div className="max-w-7xl mx-auto">{children}</div>
      </main>
    );
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6 md:p-8 bg-gradient-to-b from-slate-950 via-slate-900/30 to-slate-950">
        <div className="max-w-7xl mx-auto space-y-6">{children}</div>
      </main>
    </div>
  );
}
