"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ApiClient } from "@/lib/api";
import PublicLayout from "@/components/PublicLayout";
import { KeyRound, ShieldCheck, UserPlus } from "lucide-react";

const inputClass =
  "w-full rounded-md bg-white border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100";

type Preview = { purpose: "PATIENT_PORTAL" | "STAFF_ACTIVATION" | "PASSWORD_RESET"; email?: string; role?: string; expires_at: string };

const headings: Record<Preview["purpose"], { title: string; help: string }> = {
  PATIENT_PORTAL: {
    title: "Create your patient portal account",
    help: "Confirm your date of birth so we can link this account to your hospital record.",
  },
  STAFF_ACTIVATION: { title: "Activate your staff account", help: "Choose a password to finish setting up your account." },
  PASSWORD_RESET: { title: "Choose a new password", help: "Your previous sessions have been signed out." },
};

function passwordProblem(password: string, confirm: string): string | null {
  if (password.length < 12) return "Use at least 12 characters.";
  if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return "Use both letters and numbers.";
  if (password !== confirm) return "The passwords do not match.";
  return null;
}

export default function SignupPage() {
  const [token, setToken] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [email, setEmail] = useState("");
  const [dob, setDob] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const lookUp = async (value: string) => {
    setError(null);
    setBusy(true);
    try {
      setPreview(await ApiClient.previewInvitation(value));
    } catch (err: any) {
      setPreview(null);
      setError(err.message || "This code is invalid or has expired.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const fromLink = new URLSearchParams(window.location.search).get("token");
    if (fromLink) {
      setToken(fromLink);
      void lookUp(fromLink);
    }
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!preview) return;
    const problem = passwordProblem(password, confirm);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const isPatient = preview.purpose === "PATIENT_PORTAL";
      const result = await ApiClient.signup({
        token, password,
        ...(isPatient ? { email: email.trim(), date_of_birth: dob } : {}),
      });
      if (result.sign_in_required) {
        setDone("Your password is set. Sign in with it and your authenticator code.");
      } else if (result.mfa_enrollment_required) {
        window.location.assign("/account/security");
      } else {
        window.location.assign("/");
      }
    } catch (err: any) {
      setError(err.message || "Could not complete sign-up.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <PublicLayout>
      <ol className="flex items-center gap-3 mb-4 text-xs font-medium" aria-label="Sign-up progress">
        {["Verify code", "Set up account"].map((label, index) => {
          const current = (preview && !done ? 1 : done ? 2 : 0);
          const state = index < current ? "done" : index === current ? "current" : "todo";
          return (
            <li key={label} className="flex items-center gap-2">
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] ${
                state === "todo" ? "bg-slate-200 text-slate-600" : "bg-brand-600 text-white"}`}>{index + 1}</span>
              <span className={state === "todo" ? "text-slate-500" : "text-slate-900"}>{label}</span>
              {index === 0 && <span className="w-8 h-px bg-slate-300" />}
            </li>
          );
        })}
      </ol>
      <div className="bg-white rounded-xl border border-slate-200 shadow-card p-7 sm:p-8 space-y-6">
        <div className="text-center space-y-2">
          <div className="mx-auto w-12 h-12 rounded-full bg-brand-50 flex items-center justify-center">
            <UserPlus className="w-6 h-6 text-brand-700" />
          </div>
          <h1 className="text-xl font-bold text-slate-900">{preview ? headings[preview.purpose].title : "Create your account"}</h1>
          <p className="text-sm text-slate-600">
            {preview
              ? headings[preview.purpose].help
              : "Patients: enter the activation code from the registration desk. Staff: open the activation link you were given."}
          </p>
        </div>

        {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</p>}

        {done ? (
          <div className="space-y-4 text-center">
            <p className="text-sm text-emerald-700">{done}</p>
            <Link href="/login" className="inline-block rounded-lg bg-brand-700 hover:bg-brand-600 px-4 py-2 text-sm font-semibold text-white">Go to sign in</Link>
          </div>
        ) : !preview ? (
          <form onSubmit={(e) => { e.preventDefault(); void lookUp(token); }} className="space-y-4">
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-700">Activation code</span>
              <input required value={token} onChange={(e) => setToken(e.target.value)} placeholder="ABCD-EFGH-JKLM-NPQR"
                autoComplete="one-time-code" className={`${inputClass} font-mono tracking-wider uppercase`} />
            </label>
            <button type="submit" disabled={busy}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-700 hover:bg-brand-600 disabled:opacity-60 px-4 py-2.5 text-sm font-semibold text-white">
              <KeyRound className="w-4 h-4" /> {busy ? "Checking…" : "Continue"}
            </button>
          </form>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            {preview.purpose !== "PATIENT_PORTAL" && preview.email && (
              <div className="text-xs text-slate-600 rounded-lg bg-white border border-slate-200 px-3 py-2">
                Account: <span className="text-slate-800">{preview.email}</span>
                {preview.role && <> · role <span className="text-slate-800">{preview.role.replace("_", " ")}</span></>}
              </div>
            )}
            {preview.purpose === "PATIENT_PORTAL" && (
              <>
                <label className="block space-y-1.5">
                  <span className="text-xs font-medium text-slate-700">Email (your sign-in name)</span>
                  <input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
                </label>
                <label className="block space-y-1.5">
                  <span className="text-xs font-medium text-slate-700">Date of birth</span>
                  <input type="date" required value={dob} onChange={(e) => setDob(e.target.value)} className={inputClass} />
                </label>
              </>
            )}
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-700">New password</span>
              <input type="password" required autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
              <span className="text-xs text-slate-500">At least 12 characters, with letters and numbers.</span>
            </label>
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-700">Confirm password</span>
              <input type="password" required autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputClass} />
            </label>
            <button type="submit" disabled={busy}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-700 hover:bg-brand-600 disabled:opacity-60 px-4 py-2.5 text-sm font-semibold text-white">
              <ShieldCheck className="w-4 h-4" /> {busy ? "Saving…" : preview.purpose === "PASSWORD_RESET" ? "Set new password" : "Create account"}
            </button>
            <p className="text-xs text-slate-500 text-center">Code expires {new Date(preview.expires_at).toLocaleString()}.</p>
          </form>
        )}

        <div className="border-t border-slate-200 pt-5 text-center text-sm text-slate-600">
          Already have an account? <Link href="/login" className="font-semibold text-brand-700 hover:text-brand-800 hover:underline">Sign in</Link>
        </div>
      </div>
    </PublicLayout>
  );
}
