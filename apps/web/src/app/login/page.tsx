"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ApiClient } from "@/lib/api";
import PublicLayout from "@/components/PublicLayout";
import { Building2, KeyRound, ShieldCheck, Smartphone } from "lucide-react";

const SIGN_OUT_REASONS: Record<string, string> = {
  idle: "You were signed out after a period of inactivity. Sign in to continue where you left off.",
  expired: "Your session ended. Sign in to continue where you left off.",
  limit: "Your session reached its maximum length for one shift. Please sign in again.",
};

const inputClass =
  "w-full rounded-md bg-white border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [ssoUrl, setSsoUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [next, setNext] = useState("/");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const target = params.get("next") || "/";
    // Same-site paths only, so the link cannot bounce a user to another site after sign-in.
    if (target.startsWith("/") && !target.startsWith("//") && !target.startsWith("/login")) setNext(target);
    setNotice(SIGN_OUT_REASONS[params.get("reason") || ""] || null);
  }, []);

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
        window.location.assign(next);
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
      window.location.assign(next);
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
    <PublicLayout>
      <div className="bg-white rounded-xl border border-slate-200 shadow-card p-7 sm:p-8 space-y-6">
        <div className="text-center space-y-2">
          <div className="mx-auto w-12 h-12 rounded-full bg-brand-50 flex items-center justify-center">
            {mfaToken ? <Smartphone className="w-6 h-6 text-brand-700" /> : <ShieldCheck className="w-6 h-6 text-brand-700" />}
          </div>
          <h1 className="text-xl font-bold text-slate-900">{mfaToken ? "Verify it's you" : "Sign in to MedChain"}</h1>
          <p className="text-sm text-slate-600">
            {mfaToken
              ? "Enter the 6-digit code from your authenticator app, or a one-time recovery code."
              : "Hospital staff should use single sign-on. Local accounts use email and password."}
          </p>
        </div>

        {notice && !mfaToken && (
          <p role="status" className="text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">{notice}</p>
        )}

        {!mfaToken && ssoUrl && (
          <>
            <a
              href={ssoUrl}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-700 hover:bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors"
            >
              <Building2 className="w-4 h-4" />
              Sign in with hospital SSO
            </a>
            <div className="flex items-center gap-3 text-[11px] text-slate-500">
              <span className="flex-1 h-px bg-slate-100" />or use a local account<span className="flex-1 h-px bg-slate-100" />
            </div>
          </>
        )}

        {mfaToken ? (
          <form onSubmit={handleCode} className="space-y-4">
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-700">Verification code</span>
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
            {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</p>}
            <button type="submit" disabled={submitting}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-700 hover:bg-brand-600 disabled:opacity-60 px-4 py-2.5 text-sm font-semibold text-white transition-colors">
              <KeyRound className="w-4 h-4" />
              {submitting ? "Verifying…" : "Verify and sign in"}
            </button>
            <button type="button" onClick={() => { setMfaToken(null); setCode(""); setError(null); }}
              className="w-full text-xs text-slate-600 hover:text-slate-800">
              Start over
            </button>
          </form>
        ) : (
          <form onSubmit={handlePassword} className="space-y-4">
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-700">Email</span>
              <input type="email" autoComplete="username" required value={email}
                onChange={(event) => setEmail(event.target.value)} className={inputClass} />
            </label>
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-700">Password</span>
              <input type="password" autoComplete="current-password" required value={password}
                onChange={(event) => setPassword(event.target.value)} className={inputClass} />
            </label>
            {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</p>}
            <button type="submit" disabled={submitting}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-700 hover:bg-brand-600 disabled:opacity-60 px-4 py-2.5 text-sm font-semibold text-white transition-colors">
              <KeyRound className="w-4 h-4" />
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}

        <div className="border-t border-slate-200 pt-5 space-y-3 text-sm">
          <div className="text-center text-slate-600">
            New to the portal?{" "}
            <Link href="/signup" className="font-semibold text-brand-700 hover:text-brand-800 hover:underline">Activate your account</Link>
          </div>
          <p className="text-center text-xs text-slate-500">
            Patients need the activation code from their hospital. Staff use the link sent by their administrator.
            Forgot your password? Contact the hospital help desk for a reset link.
          </p>
        </div>
      </div>
    </PublicLayout>
  );
}
