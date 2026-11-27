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
            unit_cost: Number(itemCost) || 0,
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
          <h1 className="text-2xl font-bold text-slate-900 flex items-center space-x-2.5">
            <DollarSign className="w-6 h-6 text-brand-600" />
            <span>Claims & analytics</span>
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Review submitted claims, adjudicate flagged items, and see spending by diagnosis.
          </p>
        </div>

        <button
          onClick={() => setShowClaimModal(true)}
          className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-medium text-xs shadow-sm transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>New Claim (Transaction Demo)</span>
        </button>
      </div>

      {/* Aggregate Cost Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-xl glass-panel border border-slate-200 space-y-1">
          <span className="text-xs font-medium text-slate-600">Total Billed Claims</span>
          <div className="text-2xl font-bold text-slate-900">${expenditure?.total_claimed || "0.00"}</div>
          <span className="text-[11px] text-slate-600">{claims.length} Total Encounters Billed</span>
        </div>

        <div className="p-5 rounded-xl glass-panel border border-slate-200 space-y-1">
          <span className="text-xs font-medium text-slate-600">Approved Reimbursements</span>
          <div className="text-2xl font-bold text-emerald-700">${expenditure?.total_approved || "0.00"}</div>
          <span className="text-[11px] text-slate-600">Underwritten Total</span>
        </div>

        <div className="p-5 rounded-xl glass-panel border border-slate-200 space-y-1">
          <span className="text-xs font-medium text-slate-600">Anomaly Review Queue</span>
          <div className="text-2xl font-bold text-amber-700">{flaggedClaims.length} Flagged</div>
          <span className="text-[11px] text-amber-700">Requires Human Review</span>
        </div>

        <div className="p-5 rounded-xl glass-panel border border-slate-200 space-y-1">
          <span className="text-xs font-medium text-slate-600">Security Boundary</span>
          <div className="text-sm font-bold text-brand-700 mt-1 flex items-center space-x-1.5">
            <ShieldCheck className="w-4 h-4 text-brand-700" />
            <span>Clinical Notes Hidden</span>
          </div>
          <span className="text-[11px] text-slate-600">Protected by RBAC</span>
        </div>
      </div>

      {/* Main Review Queue and Detail Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Claims Directory */}
        <div className="lg:col-span-6 glass-panel p-6 rounded-xl border border-slate-200 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-200 pb-3">
            <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <Receipt className="w-4 h-4 text-amber-700" />
              <span>Claims Directory ({claims.length})</span>
            </h2>
            <span className="text-xs text-slate-600 font-mono">
              {flaggedClaims.length} Anomalies Flagged
            </span>
          </div>

          <div className="space-y-2.5 max-h-[640px] overflow-y-auto pr-1">
            {loading ? (
              <div className="text-xs text-slate-600 text-center py-10">Loading claims...</div>
            ) : claims.length === 0 ? (
              <div className="text-xs text-slate-600 text-center py-10">No claims submitted</div>
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
                        ? "bg-amber-50 border-amber-300 text-amber-800 shadow-sm "
                        : "bg-slate-50 border-slate-200 text-slate-700 hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono font-bold text-slate-900">{c.policy_reference}</span>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          c.status === "APPROVED"
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-300"
                            : c.status === "UNDER_REVIEW"
                            ? "bg-amber-50 text-amber-700 border border-amber-300"
                            : "bg-slate-100 text-slate-700 border border-slate-300"
                        }`}
                      >
                        {c.status}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs mt-2">
                      <span className="text-slate-600 font-sans">
                        Claimed: <strong className="text-slate-900">${c.claimed_amount}</strong>
                      </span>
                      <span className="text-slate-600 font-sans">
                        Approved: <strong className="text-emerald-700">${c.approved_amount}</strong>
                      </span>
                    </div>

                    {c.review_flag && (
                      <div className="mt-2.5 p-2 rounded-lg bg-amber-50 border border-amber-200 text-[11px] text-amber-800 flex items-start space-x-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-700 shrink-0 mt-0.5" />
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
        <div className="lg:col-span-6 glass-panel p-6 rounded-xl border border-slate-200 space-y-6">
          <div className="border-b border-slate-200 pb-3">
            <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <UserCheck className="w-4 h-4 text-brand-700" />
              <span>Underwriter Review & Adjudication</span>
            </h2>
          </div>

          {!selectedClaim ? (
            <div className="text-xs text-slate-600 text-center py-16">
              Select any claim on the left to review its billing line items and record review decisions.
            </div>
          ) : (
            <div className="space-y-5 animate-in fade-in duration-200 text-xs">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600">Claim ID:</span>
                  <span className="font-mono text-brand-700">{selectedClaim.id}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-600">Policy Reference:</span>
                  <span className="font-mono text-slate-900">{selectedClaim.policy_reference}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-600">Submission Date:</span>
                  <span className="text-slate-700">{new Date(selectedClaim.submitted_at).toLocaleDateString()}</span>
                </div>
              </div>

              {/* Line Items Table */}
              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-600 uppercase tracking-wider">
                  Itemized Service Codes ({selectedClaim.items?.length || 0})
                </div>
                <div className="space-y-1.5">
                  {selectedClaim.items?.map((item: any) => (
                    <div
                      key={item.id}
                      className="p-3 rounded-xl bg-white border border-slate-200 flex items-center justify-between"
                    >
                      <div>
                        <div className="font-bold text-slate-900 font-mono">{item.item_code}</div>
                        <div className="text-[11px] text-slate-600">{item.description}</div>
                      </div>
                      <div className="text-right">
                        <div className="font-semibold text-slate-900">${item.line_amount}</div>
                        <div className="text-[10px] text-slate-600">Qty: {item.quantity} @ ${item.unit_cost}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Adjudication Form */}
              <form onSubmit={handleReviewSubmit} className="space-y-4 pt-2 border-t border-slate-200">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-700 font-medium mb-1">Adjudication Decision</label>
                    <select
                      value={reviewDecision}
                      onChange={(e) => setReviewDecision(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-amber-500"
                    >
                      <option value="APPROVED">APPROVE CLAIM</option>
                      <option value="REJECTED">REJECT CLAIM</option>
                      <option value="UNDER_REVIEW">FLAG FOR INVESTIGATION</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-700 font-medium mb-1">Approved Amount ($)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={approvedAmount}
                      onChange={(e) => setApprovedAmount(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-amber-500 font-mono"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-slate-700 font-medium mb-1">Analyst Justification & Explanation</label>
                  <textarea
                    rows={3}
                    required
                    placeholder="Enter human underwriting reasoning..."
                    value={reviewReason}
                    onChange={(e) => setReviewReason(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-amber-500"
                  />
                </div>

                <button
                  type="submit"
                  disabled={submittingReview}
                  className="w-full py-2.5 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-semibold text-xs shadow-sm transition-all"
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
        <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-4">
          <div className="border-b border-slate-200 pb-3 flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <TrendingUp className="w-4 h-4 text-brand-700" />
              <span>Disease-Wise Expenditure & Utilization Report</span>
            </h2>
            <span className="text-xs text-slate-600">Authoritative SQL Aggregate Join</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-600 uppercase text-[10px]">
                  <th className="py-2.5 px-3">ICD-10 Code</th>
                  <th className="py-2.5 px-3">Disease Category</th>
                  <th className="py-2.5 px-3 text-right">Incurred Claims</th>
                  <th className="py-2.5 px-3 text-right">Total Claimed Expenditure</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 text-slate-700">
                {expenditure.disease_costs.map((row: any, idx: number) => (
                  <tr key={idx} className="hover:bg-slate-50">
                    <td className="py-3 px-3 font-mono text-brand-700 font-semibold">{row.disease_code}</td>
                    <td className="py-3 px-3 font-medium text-slate-900">{row.disease_name}</td>
                    <td className="py-3 px-3 text-right font-mono">{row.claim_count}</td>
                    <td className="py-3 px-3 text-right font-mono font-bold text-amber-700">
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
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md glass-panel p-6 rounded-xl border border-slate-300 space-y-4 animate-in zoom-in-95">
            <h2 className="text-base font-bold text-slate-900 flex items-center space-x-2">
              <Receipt className="w-4 h-4 text-amber-700" />
              <span>Transactional Claim Submission</span>
            </h2>

            {claimFeedback && (
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-brand-700 font-mono">
                {claimFeedback}
              </div>
            )}

            <form onSubmit={handleCreateClaim} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-700 font-medium mb-1">Target Policy</label>
                <select
                  value={claimPolicyId}
                  onChange={(e) => setClaimPolicyId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-amber-500 font-mono"
                >
                  {policies.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.policy_reference} ({p.coverage_type})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">Billing Item Code</label>
                <input
                  type="text"
                  required
                  value={itemCode}
                  onChange={(e) => setItemCode(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-amber-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-medium mb-1">Item Description</label>
                <input
                  type="text"
                  required
                  value={itemDesc}
                  onChange={(e) => setItemDesc(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-amber-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-medium mb-1">Quantity</label>
                  <input
                    type="number"
                    required
                    value={itemQty}
                    onChange={(e) => setItemQty(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-amber-500 font-mono"
                  />
                  <span className="text-[10px] text-slate-600">Set negative (e.g. -1) to test DB rollback</span>
                </div>

                <div>
                  <label className="block text-slate-700 font-medium mb-1">Unit Cost ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={itemCost}
                    onChange={(e) => setItemCost(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-900 focus:outline-none focus:border-amber-500 font-mono"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowClaimModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingClaim}
                  className="px-4 py-2 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-medium shadow-sm"
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
