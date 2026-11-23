"use client";

import React, { useCallback, useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import { Building2, Copy, KeyRound, RefreshCw, ShieldOff, UserPlus, Users } from "lucide-react";

const input = "w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-xs text-white outline-none focus:border-cyan-500";
const roles = ["doctor", "researcher", "insurance_analyst", "admin"];

export default function UsersAdminPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [hospitals, setHospitals] = useState<any[]>([]);
  const [providers, setProviders] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ title: string; link: string; expires: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, string>>({ role: "doctor" });
  const [hospitalForm, setHospitalForm] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const [u, h, p] = await Promise.all([ApiClient.listUsers(), ApiClient.getHospitals(), ApiClient.getInsuranceProviders()]);
      setUsers(u); setHospitals(h); setProviders(p);
    } catch (err: any) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const act = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const showLink = (title: string, path: string, expires: string) =>
    setSecret({ title, link: `${window.location.origin}${path}`, expires });

  const createUser = (e: React.FormEvent) => {
    e.preventDefault();
    void act("create", async () => {
      const payload: Record<string, any> = { email: form.email, role: form.role };
      if (form.role === "doctor") {
        Object.assign(payload, { display_name: form.display_name, specialty: form.specialty, hospital_id: form.hospital_id,
          external_provider_id: form.external_provider_id || undefined });
      }
      if (form.role === "insurance_analyst") payload.insurance_provider_id = form.insurance_provider_id;
      const res = await ApiClient.createStaffUser(payload);
      showLink(`Activation link for ${res.user.email}`, res.activation_link, res.expires_at);
      setForm({ role: form.role });
    });
  };

  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white flex items-center gap-2"><Users className="w-5 h-5 text-cyan-400" /> Users & Hospitals</h1>
        <p className="text-sm text-slate-400">Staff accounts are created here (or by hospital SSO). Patients sign up with the code issued at registration.</p>
      </div>
      {error && <p role="alert" className="text-sm text-rose-300 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">{error}</p>}

      {secret && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 space-y-2">
          <div className="text-sm font-semibold text-amber-200">{secret.title}</div>
          <div className="flex gap-2 items-center">
            <code className="flex-1 text-xs text-white bg-slate-950 border border-slate-800 rounded px-2 py-1.5 break-all">{secret.link}</code>
            <button onClick={() => navigator.clipboard.writeText(secret.link)} className="text-xs text-cyan-300 flex items-center gap-1"><Copy className="w-3.5 h-3.5" />Copy</button>
          </div>
          <p className="text-[11px] text-amber-200/80">Shown only once. Give it to the person through a trusted channel. Expires {new Date(secret.expires).toLocaleString()}.</p>
          <button onClick={() => setSecret(null)} className="text-[11px] text-slate-400 hover:text-slate-200">Dismiss</button>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <form onSubmit={createUser} className="glass-panel rounded-2xl border border-slate-800 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2"><UserPlus className="w-4 h-4 text-cyan-400" /> New staff account</h2>
          <input required type="email" placeholder="work email" value={form.email || ""} onChange={set("email")} className={input} />
          <select value={form.role} onChange={set("role")} className={input}>
            {roles.map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
          </select>
          {form.role === "doctor" && (
            <>
              <input required placeholder="Display name (e.g. Dr. A. Shah, MD)" value={form.display_name || ""} onChange={set("display_name")} className={input} />
              <input required placeholder="Specialty" value={form.specialty || ""} onChange={set("specialty")} className={input} />
              <select required value={form.hospital_id || ""} onChange={set("hospital_id")} className={input}>
                <option value="">Hospital…</option>
                {hospitals.map((h) => <option key={h.id} value={h.id}>{h.name} ({h.facility_code})</option>)}
              </select>
              <input placeholder="Provider ID used in HL7 feeds (optional)" value={form.external_provider_id || ""} onChange={set("external_provider_id")} className={input} />
            </>
          )}
          {form.role === "insurance_analyst" && (
            <select required value={form.insurance_provider_id || ""} onChange={set("insurance_provider_id")} className={input}>
              <option value="">Insurance provider…</option>
              {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          )}
          <button disabled={busy === "create"} className="w-full rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-60 px-3 py-2 text-xs font-semibold text-white">
            Create and get activation link
          </button>
        </form>

        <div className="xl:col-span-2 glass-panel rounded-2xl border border-slate-800 p-5 space-y-3">
          <div className="flex items-center">
            <h2 className="text-sm font-semibold text-white">Staff accounts</h2>
            <button onClick={() => void load()} className="ml-auto text-xs text-cyan-300 flex items-center gap-1"><RefreshCw className="w-3.5 h-3.5" />Refresh</button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-slate-500 text-left">
                <tr><th className="py-1.5">Account</th><th>Role</th><th>Status</th><th>Sign-in</th><th className="text-right">Actions</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {users.map((u) => (
                  <tr key={u.id} className="text-slate-300">
                    <td className="py-2">
                      <div className="text-white">{u.email}</div>
                      {u.doctor && <div className="text-[11px] text-slate-500">{u.doctor.display_name} · {u.doctor.specialty}</div>}
                    </td>
                    <td>
                      <select value={u.role} disabled={busy === u.id}
                        onChange={(e) => act(u.id, async () => { await ApiClient.updateUser(u.id, { role: e.target.value }); })}
                        className="bg-slate-950 border border-slate-800 rounded px-1 py-0.5">
                        {roles.map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
                      </select>
                    </td>
                    <td>
                      {!u.is_active ? <span className="text-rose-300">disabled</span>
                        : u.activation_pending ? <span className="text-amber-300">awaiting activation</span>
                        : u.locked ? <span className="text-amber-300">locked</span>
                        : <span className="text-emerald-300">active</span>}
                    </td>
                    <td className="text-[11px] text-slate-400">{u.auth_source}{u.mfa_enabled ? " · MFA" : ""}
                      <div>{u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : "never"}</div></td>
                    <td className="text-right space-x-2 whitespace-nowrap">
                      {u.auth_source === "LOCAL" && (
                        <button title="Issue password reset / activation link" disabled={busy === u.id}
                          onClick={() => act(u.id, async () => {
                            const r = await ApiClient.issuePasswordReset(u.id);
                            showLink(`${r.purpose === "PASSWORD_RESET" ? "Password reset" : "Activation"} link for ${u.email}`, r.activation_link, r.expires_at);
                          })} className="text-cyan-300 hover:text-cyan-200"><KeyRound className="w-3.5 h-3.5 inline" /></button>
                      )}
                      {u.mfa_enabled && (
                        <button title="Reset MFA (lost authenticator)" disabled={busy === u.id}
                          onClick={() => confirm(`Reset MFA for ${u.email}?`) && act(u.id, async () => { await ApiClient.resetUserMfa(u.id); })}
                          className="text-amber-300 hover:text-amber-200"><ShieldOff className="w-3.5 h-3.5 inline" /></button>
                      )}
                      <button disabled={busy === u.id}
                        onClick={() => act(u.id, async () => { await ApiClient.updateUser(u.id, { is_active: !u.is_active }); })}
                        className={u.is_active ? "text-rose-300 hover:text-rose-200" : "text-emerald-300 hover:text-emerald-200"}>
                        {u.is_active ? "Disable" : "Enable"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="glass-panel rounded-2xl border border-slate-800 p-5 space-y-3">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Building2 className="w-4 h-4 text-cyan-400" /> Hospitals</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
          {hospitals.map((h) => (
            <div key={h.id} className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
              <div className="text-white">{h.name}</div>
              <div className="text-slate-500">{h.region} · facility code <code className="text-cyan-300">{h.facility_code}</code>
                {!h.served_by_installation && <span className="text-amber-300"> · not served by this installation</span>}</div>
            </div>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); void act("hospital", async () => {
          await ApiClient.createHospital({ name: hospitalForm.name, region: hospitalForm.region, facility_code: hospitalForm.facility_code });
          setHospitalForm({});
        }); }} className="flex flex-wrap gap-2">
          <input required placeholder="Hospital name" value={hospitalForm.name || ""} onChange={(e) => setHospitalForm({ ...hospitalForm, name: e.target.value })} className={`${input} max-w-xs`} />
          <input required placeholder="Region" value={hospitalForm.region || ""} onChange={(e) => setHospitalForm({ ...hospitalForm, region: e.target.value })} className={`${input} max-w-[10rem]`} />
          <input required placeholder="Facility code (HL7 MSH-4)" value={hospitalForm.facility_code || ""} onChange={(e) => setHospitalForm({ ...hospitalForm, facility_code: e.target.value })} className={`${input} max-w-[14rem]`} />
          <button disabled={busy === "hospital"} className="rounded-lg bg-slate-800 hover:bg-slate-700 px-3 py-2 text-xs text-white">Add hospital</button>
        </form>
      </div>
    </div>
  );
}
