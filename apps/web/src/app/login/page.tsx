"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ApiClient } from "@/lib/api";
import { Building2, KeyRound, ShieldCheck, Smartphone } from "lucide-react";

const inputClass =
  "w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2.5 text-sm text-white outline-none focus:border-cyan-500";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [ssoUrl, setSsoUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    ApiClient.getAuthConfig()
      .then((config) => setSsoUrl(config.oidc_enabled ? config.oidc_login_url : null))
      .catch(() => setSsoUrl(null));
  }, []);

  const handlePassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await ApiClient.login(email.trim(), password);
      if (result.mfa_required && result.mfa_token) {
        setMfaToken(result.mfa_token);
        setPassword("");
      } else {
        window.location.assign("/");
      }
    } catch (err: any) {
      setError(err.message || "Sign in failed. Check your credentials and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCode = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!mfaToken) return;
    setError(null);
    setSubmitting(true);
    try {
      await ApiClient.verifyMfa(mfaToken, code.trim());
      window.location.assign("/");
    } catch (err: any) {
      if (err.status === 401 && /expired/i.test(err.message)) {
        setMfaToken(null);
      }
      setError(err.message || "Invalid verification code.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-md mx-auto py-12">
      <div className="glass-panel rounded-2xl border border-slate-800 p-7 space-y-6">
        <div className="text-center space-y-2">
          <div className="mx-auto w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            {mfaToken ? <Smartphone className="w-6 h-6 text-cyan-300" /> : <ShieldCheck className="w-6 h-6 text-cyan-300" />}
          </div>
          <h1 className="text-xl font-bold text-white">{mfaToken ? "Verify it's you" : "Sign in to MedChain"}</h1>
          <p className="text-sm text-slate-400">
            {mfaToken
              ? "Enter the 6-digit code from your authenticator app, or a one-time recovery code."
              : "Hospital staff should use single sign-on. Local accounts use email and password."}
          </p>
        </div>

        {!mfaToken && ssoUrl && (
          <>
            <a
              href={ssoUrl}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-4 py-2.5 text-sm font-semibold text-white transition-colors"
            >
              <Building2 className="w-4 h-4" />
              Sign in with hospital SSO
            </a>
            <div className="flex items-center gap-3 text-[11px] text-slate-500">
              <span className="flex-1 h-px bg-slate-800" />or use a local account<span className="flex-1 h-px bg-slate-800" />
            </div>
          </>
        )}

        {mfaToken ? (
          <form onSubmit={handleCode} className="space-y-4">
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-300">Verification code</span>
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                autoFocus
                value={code}
                onChange={(event) => setCode(event.target.value)}
                className={`${inputClass} tracking-widest text-center`}
              />
            </label>
            {error && <p role="alert" className="text-sm text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">{error}</p>}
            <button type="submit" disabled={submitting}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-60 px-4 py-2.5 text-sm font-semibold text-white transition-colors">
              <KeyRound className="w-4 h-4" />
              {submitting ? "Verifying…" : "Verify and sign in"}
            </button>
            <button type="button" onClick={() => { setMfaToken(null); setCode(""); setError(null); }}
              className="w-full text-xs text-slate-400 hover:text-slate-200">
              Start over
            </button>
          </form>
        ) : (
          <form onSubmit={handlePassword} className="space-y-4">
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-300">Email</span>
              <input type="email" autoComplete="username" required value={email}
                onChange={(event) => setEmail(event.target.value)} className={inputClass} />
            </label>
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-300">Password</span>
              <input type="password" autoComplete="current-password" required value={password}
                onChange={(event) => setPassword(event.target.value)} className={inputClass} />
            </label>
            {error && <p role="alert" className="text-sm text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">{error}</p>}
            <button type="submit" disabled={submitting}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-60 px-4 py-2.5 text-sm font-semibold text-white transition-colors">
              <KeyRound className="w-4 h-4" />
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}

        <div className="text-center text-xs text-slate-500 space-y-1">
          <div>
            Patient with an activation code, or staff with an activation link?{" "}
            <Link href="/signup" className="text-cyan-300 hover:text-cyan-200">Create your account</Link>
          </div>
          <div>Forgot your password? Ask the hospital help desk for a reset link.</div>
        </div>
      </div>
    </div>
  );
}
