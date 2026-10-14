"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  FileSpreadsheet,
  Plus,
  ShieldCheck,
  TrendingUp,
  Receipt,
  UserCheck,
} from "lucide-react";

export default function InsurancePage() {
  const [claims, setClaims] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [expenditure, setExpenditure] = useState<any>(null);
  const [selectedClaim, setSelectedClaim] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reviewDecision, setReviewDecision] = useState("APPROVED");
  const [approvedAmount, setApprovedAmount] = useState<string>("");
  const [reviewReason, setReviewReason] = useState("");
  const [submittingReview, setSubmittingReview] = useState(false);

  // New Claim Form State (for transaction demonstration)
  const [showClaimModal, setShowClaimModal] = useState(false);
  const [claimPolicyId, setClaimPolicyId] = useState("");
  const [claimVisitId, setClaimVisitId] = useState("");
  const [itemCode, setItemCode] = useState("CPT-99214");
  const [itemDesc, setItemDesc] = useState("Complex Outpatient Physician Encounter");
  const [itemQty, setItemQty] = useState(1);
  const [itemCost, setItemCost] = useState("250.00");
  const [creatingClaim, setCreatingClaim] = useState(false);
  const [claimFeedback, setClaimFeedback] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [cls, pols, exp] = await Promise.all([
        ApiClient.getInsuranceClaims(),
        ApiClient.getInsurancePolicies(),
        ApiClient.getInsuranceExpenditure().catch(() => null),
      ]);
      setClaims(cls);
      setPolicies(pols);
      setExpenditure(exp);
      if (cls.length > 0 && !selectedClaim) {
        setSelectedClaim(cls[0]);
        setApprovedAmount(cls[0].claimed_amount);
      }
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleReviewSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedClaim || !reviewReason) return;
    setSubmittingReview(true);
    try {
      await ApiClient.reviewClaim(
        selectedClaim.id,
        reviewDecision,
        reviewReason,
        approvedAmount ? Number(approvedAmount) : undefined
      );
      setReviewReason("");
      await loadData();
      alert("Analyst review recorded successfully and claim status updated.");
    } catch (err: any) {
      alert(`Review submission error: ${err.message}`);
    } finally {
      setSubmittingReview(false);
    }
  };

  const handleCreateClaim = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreatingClaim(true);
    setClaimFeedback(null);
    try {
      const created = await ApiClient.createInsuranceClaim({
        policy_id: claimPolicyId || policies[0]?.id,
        visit_id: claimVisitId || claims[0]?.visit_id,
        items: [
          {
            item_code: itemCode,
            description: itemDesc,
            quantity: Number(itemQty),
            unit_cost: itemCost,
          },
        ],
      });
      setShowClaimModal(false);
      setClaimFeedback("Claim committed successfully!");
      await loadData();
      setSelectedClaim(created);
    } catch (err: any) {
      setClaimFeedback(`Transaction Error: ${err.message}`);
    } finally {
      setCreatingClaim(false);
    }
  };

  const flaggedClaims = claims.filter((c) => c.review_flag);

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
            <DollarSign className="w-6 h-6 text-amber-400" />
            <span>Insurance Analytics & Claim Underwriting</span>
          </h1>
          <p className="text-xs text-slate-400">
            Relational expenditure aggregates, transactional claims, and explainable duplicate anomaly detection
          </p>
        </div>

        <button
          onClick={() => setShowClaimModal(true)}
          className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 text-white font-medium text-xs shadow-lg shadow-amber-500/20 hover:brightness-110 active:scale-95 transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>New Claim (Transaction Demo)</span>
        </button>
      </div>

      {/* Aggregate Cost Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-1">
          <span className="text-xs font-medium text-slate-400">Total Billed Claims</span>
          <div className="text-2xl font-bold text-white">${expenditure?.total_claimed || "0.00"}</div>
          <span className="text-[11px] text-slate-400">{claims.length} Total Encounters Billed</span>
        </div>

        <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-1">
          <span className="text-xs font-medium text-slate-400">Approved Reimbursements</span>
          <div className="text-2xl font-bold text-emerald-400">${expenditure?.total_approved || "0.00"}</div>
          <span className="text-[11px] text-slate-400">Underwritten Total</span>
        </div>

        <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-1">
          <span className="text-xs font-medium text-slate-400">Anomaly Review Queue</span>
          <div className="text-2xl font-bold text-amber-400">{flaggedClaims.length} Flagged</div>
          <span className="text-[11px] text-amber-300">Requires Human Review</span>
        </div>

        <div className="p-5 rounded-2xl glass-panel border border-slate-800 space-y-1">
          <span className="text-xs font-medium text-slate-400">Security Boundary</span>
          <div className="text-sm font-bold text-cyan-300 mt-1 flex items-center space-x-1.5">
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
            <span>Clinical Notes Hidden</span>
          </div>
          <span className="text-[11px] text-slate-400">Protected by RBAC</span>
        </div>
      </div>

      {/* Main Review Queue and Detail Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Claims Directory */}
        <div className="lg:col-span-6 glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <h2 className="text-sm font-bold text-white flex items-center space-x-2">
              <Receipt className="w-4 h-4 text-amber-400" />
              <span>Claims Directory ({claims.length})</span>
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              {flaggedClaims.length} Anomalies Flagged
            </span>
          </div>

          <div className="space-y-2.5 max-h-[640px] overflow-y-auto pr-1">
            {loading ? (
              <div className="text-xs text-slate-400 text-center py-10">Loading claims...</div>
            ) : claims.length === 0 ? (
              <div className="text-xs text-slate-400 text-center py-10">No claims submitted</div>
            ) : (
              claims.map((c) => {
                const isSelected = selectedClaim?.id === c.id;
                return (
                  <button
                    key={c.id}
                    onClick={() => {
                      setSelectedClaim(c);
                      setApprovedAmount(c.claimed_amount);
                    }}
                    className={`w-full p-4 rounded-xl border text-left transition-all ${
                      isSelected
                        ? "bg-amber-500/10 border-amber-500/40 text-amber-200 shadow-sm shadow-amber-500/10"
                        : "bg-slate-900/40 border-slate-800/80 text-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono font-bold text-white">{c.policy_reference}</span>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          c.status === "APPROVED"
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                            : c.status === "UNDER_REVIEW"
                            ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                            : "bg-slate-800 text-slate-300 border border-slate-700"
                        }`}
                      >
                        {c.status}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs mt-2">
                      <span className="text-slate-400 font-sans">
                        Claimed: <strong className="text-white">${c.claimed_amount}</strong>
                      </span>
                      <span className="text-slate-400 font-sans">
                        Approved: <strong className="text-emerald-400">${c.approved_amount}</strong>
                      </span>
                    </div>

                    {c.review_flag && (
                      <div className="mt-2.5 p-2 rounded-lg bg-amber-950/40 border border-amber-800/50 text-[11px] text-amber-200 flex items-start space-x-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                        <span>{c.review_reason}</span>
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Claim Inspection & Human Review Form */}
        <div className="lg:col-span-6 glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
          <div className="border-b border-slate-800/80 pb-3">
            <h2 className="text-sm font-bold text-white flex items-center space-x-2">
              <UserCheck className="w-4 h-4 text-cyan-400" />
              <span>Underwriter Review & Adjudication</span>
            </h2>
          </div>

          {!selectedClaim ? (
            <div className="text-xs text-slate-400 text-center py-16">
              Select any claim on the left to review its billing line items and record review decisions.
            </div>
          ) : (
            <div className="space-y-5 animate-in fade-in duration-200 text-xs">
              <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Claim ID:</span>
                  <span className="font-mono text-cyan-300">{selectedClaim.id}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Policy Reference:</span>
                  <span className="font-mono text-white">{selectedClaim.policy_reference}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Submission Date:</span>
                  <span className="text-slate-300">{new Date(selectedClaim.submitted_at).toLocaleDateString()}</span>
                </div>
              </div>

              {/* Line Items Table */}
              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Itemized Service Codes ({selectedClaim.items?.length || 0})
                </div>
                <div className="space-y-1.5">
                  {selectedClaim.items?.map((item: any) => (
                    <div
                      key={item.id}
                      className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between"
                    >
                      <div>
                        <div className="font-bold text-white font-mono">{item.item_code}</div>
                        <div className="text-[11px] text-slate-400">{item.description}</div>
                      </div>
                      <div className="text-right">
                        <div className="font-semibold text-white">${item.line_amount}</div>
                        <div className="text-[10px] text-slate-400">Qty: {item.quantity} @ ${item.unit_cost}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Adjudication Form */}
              <form onSubmit={handleReviewSubmit} className="space-y-4 pt-2 border-t border-slate-800">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-300 font-medium mb-1">Adjudication Decision</label>
                    <select
                      value={reviewDecision}
                      onChange={(e) => setReviewDecision(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-amber-500"
                    >
                      <option value="APPROVED">APPROVE CLAIM</option>
                      <option value="REJECTED">REJECT CLAIM</option>
                      <option value="UNDER_REVIEW">FLAG FOR INVESTIGATION</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-300 font-medium mb-1">Approved Amount ($)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={approvedAmount}
                      onChange={(e) => setApprovedAmount(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-amber-500 font-mono"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Analyst Justification & Explanation</label>
                  <textarea
                    rows={3}
                    required
                    placeholder="Enter human underwriting reasoning..."
                    value={reviewReason}
                    onChange={(e) => setReviewReason(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-amber-500"
                  />
                </div>

                <button
                  type="submit"
                  disabled={submittingReview}
                  className="w-full py-2.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-semibold text-xs shadow-md shadow-amber-500/20 active:scale-95 transition-all"
                >
                  {submittingReview ? "Recording Review..." : "Record Human Underwriter Adjudication"}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>

      {/* Disease-Wise Cost Aggregate Breakdown Table */}
      {expenditure?.disease_costs?.length > 0 && (
        <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
          <div className="border-b border-slate-800/80 pb-3 flex items-center justify-between">
            <h2 className="text-sm font-bold text-white flex items-center space-x-2">
              <TrendingUp className="w-4 h-4 text-cyan-400" />
              <span>Disease-Wise Expenditure & Utilization Report</span>
            </h2>
            <span className="text-xs text-slate-400">Authoritative SQL Aggregate Join</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 uppercase text-[10px]">
                  <th className="py-2.5 px-3">ICD-10 Code</th>
                  <th className="py-2.5 px-3">Disease Category</th>
                  <th className="py-2.5 px-3 text-right">Incurred Claims</th>
                  <th className="py-2.5 px-3 text-right">Total Claimed Expenditure</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {expenditure.disease_costs.map((row: any, idx: number) => (
                  <tr key={idx} className="hover:bg-slate-900/40">
                    <td className="py-3 px-3 font-mono text-cyan-400 font-semibold">{row.disease_code}</td>
                    <td className="py-3 px-3 font-medium text-white">{row.disease_name}</td>
                    <td className="py-3 px-3 text-right font-mono">{row.claim_count}</td>
                    <td className="py-3 px-3 text-right font-mono font-bold text-amber-300">
                      ${row.total_claimed_amount.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal: Create Transactional Claim */}
      {showClaimModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md glass-panel p-6 rounded-2xl border border-slate-700 space-y-4 animate-in zoom-in-95">
            <h2 className="text-base font-bold text-white flex items-center space-x-2">
              <Receipt className="w-4 h-4 text-amber-400" />
              <span>Transactional Claim Submission</span>
            </h2>

            {claimFeedback && (
              <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 text-xs text-cyan-300 font-mono">
                {claimFeedback}
              </div>
            )}

            <form onSubmit={handleCreateClaim} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Target Policy</label>
                <select
                  value={claimPolicyId}
                  onChange={(e) => setClaimPolicyId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-amber-500 font-mono"
                >
                  {policies.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.policy_reference} ({p.coverage_type})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Billing Item Code</label>
                <input
                  type="text"
                  required
                  value={itemCode}
                  onChange={(e) => setItemCode(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-amber-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Item Description</label>
                <input
                  type="text"
                  required
                  value={itemDesc}
                  onChange={(e) => setItemDesc(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Quantity</label>
                  <input
                    type="number"
                    required
                    value={itemQty}
                    onChange={(e) => setItemQty(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-amber-500 font-mono"
                  />
                  <span className="text-[10px] text-slate-400">Set negative (e.g. -1) to test DB rollback</span>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Unit Cost ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={itemCost}
                    onChange={(e) => setItemCost(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-amber-500 font-mono"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowClaimModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-800 text-slate-400 hover:bg-slate-900 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingClaim}
                  className="px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-medium shadow-md shadow-amber-500/20"
                >
                  {creatingClaim ? "Committing..." : "Submit Transactional Claim"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
