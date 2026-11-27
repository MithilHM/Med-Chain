"use client";

import React, { useEffect, useState } from "react";
import { ApiClient, utcTime } from "@/lib/api";
import { KeyRound, LogOut, ShieldCheck, Smartphone } from "lucide-react";

export default function AccountSecurityPage() {
  const [me, setMe] = useState<any>(null);
  const [sessions, setSessions] = useState<any[]>([]);
  const [enrollment, setEnrollment] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setMe(await ApiClient.getCurrentUser());
      setSessions(await ApiClient.getMySessions());
    } catch (err: any) {
      setError(err.message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const run = async (action: () => Promise<void>) => {
    setError(null);
    setMessage(null);
    try {
      await action();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const isLocal = me?.auth_source === "LOCAL";

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Account security</h1>
        <p className="text-sm text-slate-600">Multi-factor authentication and active sessions for {me?.email ?? "your account"}.</p>
      </div>

      {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">{error}</p>}
      {message && <p className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">{message}</p>}

      <section className="glass-panel rounded-xl border border-slate-200 p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Smartphone className="w-4 h-4 text-brand-700" />
          <h2 className="text-sm font-semibold text-slate-900">Authenticator app (TOTP)</h2>
          {me && (
            <span className={`ml-auto text-[11px] px-2 py-0.5 rounded-full border ${me.mfa_enabled ? "text-emerald-700 border-emerald-300" : "text-amber-700 border-amber-300"}`}>
              {me.mfa_enabled ? "Enabled" : "Not enabled"}
            </span>
          )}
        </div>

        {!isLocal && me && (
          <p className="text-xs text-slate-600">Your account signs in through hospital SSO; multi-factor authentication is enforced by the hospital identity provider.</p>
        )}

        {isLocal && !me?.mfa_enabled && !enrollment && (
          <button onClick={() => run(async () => setEnrollment(await ApiClient.enrollMfa()))}
            className="rounded-lg bg-brand-700 hover:bg-brand-600 px-4 py-2 text-sm font-semibold text-white">
            Set up authenticator
          </button>
        )}

        {enrollment && !recoveryCodes && (
          <div className="space-y-3 text-sm">
            <p className="text-slate-700">Add this account to your authenticator app, then enter the 6-digit code it shows.</p>
            <div className="rounded-lg bg-white border border-slate-200 p-3 space-y-1 font-mono text-xs break-all">
              <div><span className="text-slate-500">Secret: </span><span className="text-brand-700">{enrollment.secret}</span></div>
              <div><span className="text-slate-500">URI: </span><span className="text-slate-700">{enrollment.otpauth_uri}</span></div>
            </div>
            <div className="flex gap-2">
              <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" placeholder="123456"
                className="w-40 rounded-lg bg-white border border-slate-300 px-3 py-2 text-slate-900 tracking-widest" />
              <button onClick={() => run(async () => {
                const result = await ApiClient.activateMfa(code.trim());
                setRecoveryCodes(result.recovery_codes);
                setCode("");
                await load();
              })} className="rounded-lg bg-brand-700 hover:bg-brand-600 px-4 py-2 text-sm font-semibold text-white">
                Activate
              </button>
            </div>
          </div>
        )}

        {recoveryCodes && (
          <div className="space-y-2">
            <p className="text-sm text-amber-800">Save these recovery codes now. Each works once, and they will not be shown again.</p>
            <div className="grid grid-cols-2 gap-2 font-mono text-sm text-slate-900">
              {recoveryCodes.map((c) => <div key={c} className="rounded bg-white border border-slate-200 px-3 py-1.5">{c}</div>)}
            </div>
            <button onClick={() => { setRecoveryCodes(null); setEnrollment(null); setMessage("Multi-factor authentication is on."); }}
              className="text-xs text-brand-700 hover:text-brand-800">I have saved them</button>
          </div>
        )}

        {isLocal && me?.mfa_enabled && !recoveryCodes && (
          <div className="flex gap-2 items-center">
            <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" placeholder="Current code"
              className="w-40 rounded-lg bg-white border border-slate-300 px-3 py-2 text-slate-900" />
            <button onClick={() => run(async () => {
              await ApiClient.disableMfa(code.trim());
              ApiClient.clearLocalUser();
              window.location.assign("/login");
            })} className="rounded-lg border border-rose-300 text-rose-700 hover:bg-rose-50 px-4 py-2 text-sm">
              Turn off MFA
            </button>
          </div>
        )}
      </section>

      {isLocal && (
        <section className="glass-panel rounded-xl border border-slate-200 p-6 space-y-3">
          <div className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-brand-700" />
            <h2 className="text-sm font-semibold text-slate-900">Change password</h2>
          </div>
          <form className="grid grid-cols-1 md:grid-cols-3 gap-2" onSubmit={(e) => {
            e.preventDefault();
            if (newPassword !== confirmPassword) { setError("The new passwords do not match."); return; }
            void run(async () => {
              await ApiClient.changePassword(currentPassword, newPassword);
              setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
              setMessage("Password changed. Other devices were signed out.");
              await load();
            });
          }}>
            <input type="password" required autoComplete="current-password" placeholder="Current password" value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)} className="rounded-lg bg-white border border-slate-300 px-3 py-2 text-sm text-slate-900" />
            <input type="password" required minLength={12} autoComplete="new-password" placeholder="New password (12+ chars)" value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)} className="rounded-lg bg-white border border-slate-300 px-3 py-2 text-sm text-slate-900" />
            <input type="password" required autoComplete="new-password" placeholder="Confirm new password" value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)} className="rounded-lg bg-white border border-slate-300 px-3 py-2 text-sm text-slate-900" />
            <button className="md:col-span-3 justify-self-start rounded-lg bg-brand-700 hover:bg-brand-600 px-4 py-2 text-sm font-semibold text-white">Update password</button>
          </form>
        </section>
      )}

      <section className="glass-panel rounded-xl border border-slate-200 p-6 space-y-3">
        <div className="flex items-center gap-2">
          <KeyRound className="w-4 h-4 text-brand-700" />
          <h2 className="text-sm font-semibold text-slate-900">Sessions</h2>
          <button onClick={() => run(async () => {
            await ApiClient.revokeAllSessions();
            ApiClient.clearLocalUser();
            window.location.assign("/login");
          })} className="ml-auto flex items-center gap-1 text-xs text-rose-700 hover:text-rose-800">
            <LogOut className="w-3.5 h-3.5" /> Sign out everywhere
          </button>
        </div>
        <ul className="divide-y divide-slate-200 text-xs">
          {sessions.map((s) => (
            <li key={s.id} className="py-2 flex justify-between gap-4">
              <span className="text-slate-700 truncate">{s.user_agent || "Unknown device"} · {s.ip_address || "unknown address"}</span>
              <span className={s.is_revoked ? "text-slate-500" : "text-emerald-700"}>
                {s.is_revoked ? "revoked" : `active until ${new Date(utcTime(s.expires_at)).toLocaleTimeString()}`}
              </span>
            </li>
          ))}
        </ul>
        <p className="flex items-center gap-1 text-[11px] text-slate-500"><ShieldCheck className="w-3 h-3" /> Sessions expire automatically after a short idle period.</p>
      </section>
    </div>
  );
}
