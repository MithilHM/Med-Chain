"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  CheckSquare,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  Bug,
  Info,
  CheckCircle2,
  Lock,
  Binary,
  Layers,
} from "lucide-react";

export default function IntegrityPage() {
  const [documents, setDocuments] = useState<any[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [verificationResult, setVerificationResult] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [tampering, setTampering] = useState(false);
  const [tamperFeedback, setTamperFeedback] = useState<string | null>(null);
  // The tamper demo is clinician/admin only (the API enforces this too).
  const [canTamper, setCanTamper] = useState(false);
  useEffect(() => {
    try {
      const role = JSON.parse(window.localStorage.getItem("medchain_user") || "null")?.role;
      setCanTamper(role === "doctor" || role === "admin");
    } catch {
      setCanTamper(false);
    }
  }, []);

  const statusClasses = (status: string) => {
    if (status === "VERIFIED_MATCH") return "text-emerald-700";
    if (status === "TAMPER_DETECTED" || status === "DOCUMENT_NOT_FOUND") return "text-rose-700";
    return "text-amber-700";
  };

  const loadDocs = async () => {
    setLoading(true);
    try {
      const docs = await ApiClient.getDocuments();
      setDocuments(docs);
      if (docs.length > 0 && !selectedDocId) {
        setSelectedDocId(docs[0].id);
      }
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocs();
  }, []);

  const handleVerify = async (docId: string) => {
    setVerifying(true);
    setTamperFeedback(null);
    setVerificationResult(null);
    try {
      const res = await ApiClient.verifyDocument(docId);
      setVerificationResult(res);
      await loadDocs();
    } catch (err: any) {
      alert(`Verification error: ${err.message}`);
    } finally {
      setVerifying(false);
    }
  };

  const handleTamperDemo = async (docId: string) => {
    setTampering(true);
    try {
      await ApiClient.tamperDocumentDemo(docId);
      setVerificationResult(null);
      setTamperFeedback(
        "Demonstration tampering injected into MongoDB. Now click 'Run Cryptographic Verification' to observe tamper detection in action."
      );
      await loadDocs();
    } catch (err: any) {
      setVerificationResult(null);
      await loadDocs();
      alert(`Tamper demo error: ${err.message}`);
    } finally {
      setTampering(false);
    }
  };

  const selectedDoc = documents.find((d) => d.id === selectedDocId);
  const chainVerified = Boolean(
    verificationResult?.is_valid && verificationResult?.chain_status === "CONFIRMED"
  );

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center space-x-2.5">
          <CheckSquare className="w-6 h-6 text-brand-600" />
          <span>Record integrity</span>
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Confirm that a clinical document has not been changed since it was recorded.
        </p>
      </div>

      {/* Protocol Explanation Box */}
      <div className="glass-panel p-6 rounded-xl border border-slate-200 space-y-3">
        <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
          <Binary className="w-4 h-4 text-brand-700" />
          <span>Off-Chain Salted Commitment Protocol</span>
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-slate-700">
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
            <span className="font-semibold text-brand-700">1. Canonicalization</span>
            <p className="text-[11px] text-slate-600">
              The clinical JSON payload is serialized with sorted keys and compact formatting to eliminate key-order and whitespace variance.
            </p>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
            <span className="font-semibold text-purple-700">2. Salted SHA-256 Hashing</span>
            <p className="text-[11px] text-slate-600">
              A private 256-bit random salt is combined with the document to prevent dictionary precomputation attacks on medical values.
            </p>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
            <span className="font-semibold text-emerald-700">3. Tamper Evidence</span>
            <p className="text-[11px] text-slate-600">
              Any unauthorized single-character modification inside MongoDB alters the recomputed hash, causing instant verification failure.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Documents Selector */}
        <div className="lg:col-span-5 glass-panel p-6 rounded-xl border border-slate-200 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-200 pb-3">
            <h2 className="text-sm font-bold text-slate-900">Integrity Records ({documents.length})</h2>
            <span className="text-xs text-slate-600 font-mono">SHA-256 Hashes</span>
          </div>

          <div className="space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
            {loading ? (
              <div className="text-xs text-slate-600 text-center py-10">Loading documents...</div>
            ) : documents.length === 0 ? (
              <div className="text-xs text-slate-600 text-center py-10">No records available</div>
            ) : (
              documents.map((d) => {
                const isSelected = selectedDocId === d.id;
                return (
                  <button
                    key={d.id}
                    onClick={() => {
                      setSelectedDocId(d.id);
                      setVerificationResult(null);
                      setTamperFeedback(null);
                    }}
                    className={`w-full p-3.5 rounded-xl border text-left transition-all ${
                      isSelected
                        ? "bg-emerald-50 border-emerald-300 text-emerald-700 shadow-sm "
                        : "bg-slate-50 border-slate-200 text-slate-700 hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-900 capitalize">{d.document_type.replace("_", " ")}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                        {d.verification_status}
                      </span>
                    </div>
                    <div className="font-mono text-[11px] text-slate-600 truncate mt-1">
                      {d.commitment_hash || "No integrity commitment recorded"}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Interactive Verifier & Live Tamper Demo */}
        <div className="lg:col-span-7 glass-panel p-6 rounded-xl border border-slate-200 space-y-6">
          <div className="border-b border-slate-200 pb-3">
            <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 text-brand-700" />
              <span>Verification Workspace</span>
            </h2>
          </div>

          {!selectedDoc ? (
            <div className="text-xs text-slate-600 text-center py-16">Select a record to execute verification.</div>
          ) : (
            <div className="space-y-5 animate-in fade-in duration-200 text-xs">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-600">Document UUID:</span>
                  <span className="font-mono text-brand-700">{selectedDoc.id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600">Current Status:</span>
                  <span className={`font-bold ${statusClasses(selectedDoc.verification_status)}`}>{selectedDoc.verification_status}</span>
                </div>
                <div className="pt-2">
                  <span className="text-slate-600 block mb-1">Stored Integrity Commitment:</span>
                  <div className="p-2.5 rounded-lg bg-white border border-slate-200 font-mono text-[11px] text-emerald-700 break-all">
                    {selectedDoc.commitment_hash}
                  </div>
                </div>
              </div>

              {/* Action Buttons: Verify vs Tamper */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                <button
                  onClick={() => handleVerify(selectedDoc.id)}
                  disabled={verifying}
                  className="flex items-center justify-center space-x-2 py-2.5 px-4 rounded-lg bg-brand-700 hover:bg-brand-600 text-white font-semibold shadow-sm transition-all"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${verifying ? "animate-spin" : ""}`} />
                  <span>{verifying ? "Computing Hash..." : "Run Cryptographic Verification"}</span>
                </button>

                {canTamper && (
                  <button
                    onClick={() => handleTamperDemo(selectedDoc.id)}
                    disabled={tampering}
                    className="flex items-center justify-center space-x-2 py-2.5 px-4 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-300 font-semibold active:scale-95 transition-all"
                  >
                    <Bug className="w-3.5 h-3.5 text-rose-700" />
                    <span>{tampering ? "Tampering..." : "Simulate Tampering (Demo Action)"}</span>
                  </button>
                )}
              </div>

              {tamperFeedback && (
                <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-start space-x-2 animate-in fade-in">
                  <Info className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                  <span>{tamperFeedback}</span>
                </div>
              )}

              {/* Live Verification Result Banner */}
              {verificationResult && (
                <div
                  className={`p-5 rounded-xl border space-y-3 animate-in zoom-in-95 ${
                    chainVerified
                      ? "bg-emerald-50 border-emerald-300 text-emerald-700"
                      : verificationResult.is_valid
                        ? "bg-amber-50 border-amber-300 text-amber-800"
                        : "bg-rose-50 border-rose-300 text-rose-700"
                  }`}
                >
                  <div className="flex items-center space-x-2 text-sm font-bold">
                    {chainVerified ? (
                      <>
                        <ShieldCheck className="w-5 h-5 text-emerald-700" />
                        <span>Verification PASSED: Record Integrity Confirmed</span>
                      </>
                    ) : verificationResult.is_valid ? (
                      <>
                        <Info className="w-5 h-5 text-amber-700" />
                        <span>Local hash matches; blockchain confirmation is {verificationResult.chain_status.toLowerCase()}.</span>
                      </>
                    ) : (
                      <>
                        <ShieldAlert className="w-5 h-5 text-rose-700" />
                        <span>
                          {verificationResult.verification_status === "DOCUMENT_NOT_FOUND"
                            ? "Verification FAILED: Stored document payload is missing."
                            : "Verification FAILED: Stored payload does not match its integrity commitment."}
                        </span>
                      </>
                    )}
                  </div>

                  <p className="text-xs leading-relaxed text-slate-700">{verificationResult.explanation}</p>

                  <div className="space-y-1.5 font-mono text-[11px] pt-2 border-t border-slate-200">
                    <div className="flex justify-between">
                      <span className="text-slate-600">Integrity Commitment:</span>
                      <span className="text-slate-800">{verificationResult.expected_commitment.slice(0, 24)}...</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-600">Recomputed Hash:</span>
                      <span className={verificationResult.is_valid ? "text-emerald-700" : "text-rose-700 font-bold"}>
                        {verificationResult.computed_commitment.slice(0, 24)}...
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-600">Ledger Status:</span>
                      <span className="text-purple-700 font-semibold">{verificationResult.chain_status}</span>
                    </div>
                    <div className="flex justify-between items-start gap-4">
                      <span className="text-slate-600 shrink-0">Chain Transaction:</span>
                      <span className="text-slate-800 text-right break-all">
                        {verificationResult.chain_tx_hash || "Not anchored"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-600">Block Number:</span>
                      <span className="text-slate-800">
                        {verificationResult.chain_block_number ?? "—"}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
