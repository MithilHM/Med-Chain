"use client";

import React, { useState } from "react";
import Link from "next/link";
import { ApiClient } from "@/lib/api";
import { KeyRound, ShieldCheck } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await ApiClient.login(email.trim(), password);
      window.location.assign("/");
    } catch (err: any) {
      setError(err.message || "Sign in failed. Check your credentials and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-12">
      <div className="glass-panel rounded-2xl border border-slate-800 p-7 space-y-6">
        <div className="text-center space-y-2">
          <div className="mx-auto w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            <ShieldCheck className="w-6 h-6 text-cyan-300" />
          </div>
          <h1 className="text-xl font-bold text-white">Sign in to MedChain</h1>
          <p className="text-sm text-slate-400">Use your account credentials to access your authorized workspace.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block space-y-1.5">
            <span className="text-xs font-medium text-slate-300">Email</span>
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-500"
            />
          </label>

          <label className="block space-y-1.5">
            <span className="text-xs font-medium text-slate-300">Password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-500"
            />
          </label>

          {error && <p role="alert" className="text-sm text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-60 px-4 py-2.5 text-sm font-semibold text-white transition-colors"
          >
            <KeyRound className="w-4 h-4" />
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="text-center text-xs text-slate-500">
          <Link href="/" className="text-cyan-300 hover:text-cyan-200">Return to dashboard</Link>
        </div>
      </div>
    </div>
  );
}
