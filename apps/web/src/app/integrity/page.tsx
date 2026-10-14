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
      const res = await ApiClient.tamperDocumentDemo(docId);
      setTamperFeedback(
        "Demonstration tampering injected into MongoDB. Now click 'Run Cryptographic Verification' to observe tamper detection in action."
      );
    } catch (err: any) {
      alert(`Tamper demo error: ${err.message}`);
    } finally {
      setTampering(false);
    }
  };

  const selectedDoc = documents.find((d) => d.id === selectedDocId);

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
          <CheckSquare className="w-6 h-6 text-emerald-400" />
          <span>Record Cryptographic Integrity & Tamper Evidence</span>
        </h1>
        <p className="text-xs text-slate-400">
          Deterministic canonicalization, off-chain salted commitments (SHA-256), and ledger anchors
        </p>
      </div>

      {/* Protocol Explanation Box */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-3">
        <h2 className="text-sm font-bold text-white flex items-center space-x-2">
          <Binary className="w-4 h-4 text-cyan-400" />
          <span>Off-Chain Salted Commitment Protocol</span>
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-slate-300">
          <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <span className="font-semibold text-cyan-300">1. Canonicalization</span>
            <p className="text-[11px] text-slate-400">
              The clinical JSON payload is sorted and formatted deterministically per RFC 8785 to eliminate whitespace variance.
            </p>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <span className="font-semibold text-purple-300">2. Salted SHA-256 Hashing</span>
            <p className="text-[11px] text-slate-400">
              A private 256-bit random salt is combined with the document to prevent dictionary precomputation attacks on medical values.
            </p>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
            <span className="font-semibold text-emerald-300">3. Tamper Evidence</span>
            <p className="text-[11px] text-slate-400">
              Any unauthorized single-character modification inside MongoDB alters the recomputed hash, causing instant verification failure.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Documents Selector */}
        <div className="lg:col-span-5 glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <h2 className="text-sm font-bold text-white">Anchored Records ({documents.length})</h2>
            <span className="text-xs text-slate-400 font-mono">SHA-256 Hashes</span>
          </div>

          <div className="space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
            {loading ? (
              <div className="text-xs text-slate-400 text-center py-10">Loading documents...</div>
            ) : documents.length === 0 ? (
              <div className="text-xs text-slate-400 text-center py-10">No records available</div>
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
                        ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-300 shadow-sm shadow-emerald-500/10"
                        : "bg-slate-900/40 border-slate-800/80 text-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-white capitalize">{d.document_type.replace("_", " ")}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300">
                        {d.verification_status}
                      </span>
                    </div>
                    <div className="font-mono text-[11px] text-slate-400 truncate mt-1">
                      {d.commitment_hash || "No commitment anchored"}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Interactive Verifier & Live Tamper Demo */}
        <div className="lg:col-span-7 glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
          <div className="border-b border-slate-800/80 pb-3">
            <h2 className="text-sm font-bold text-white flex items-center space-x-2">
              <ShieldCheck className="w-4 h-4 text-cyan-400" />
              <span>Verification Workspace</span>
            </h2>
          </div>

          {!selectedDoc ? (
            <div className="text-xs text-slate-400 text-center py-16">Select a record to execute verification.</div>
          ) : (
            <div className="space-y-5 animate-in fade-in duration-200 text-xs">
              <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-400">Document UUID:</span>
                  <span className="font-mono text-cyan-300">{selectedDoc.id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Current Status:</span>
                  <span className="font-bold text-emerald-400">{selectedDoc.verification_status}</span>
                </div>
                <div className="pt-2">
                  <span className="text-slate-400 block mb-1">Anchored Cryptographic Commitment:</span>
                  <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 font-mono text-[11px] text-emerald-300 break-all">
                    {selectedDoc.commitment_hash}
                  </div>
                </div>
              </div>

              {/* Action Buttons: Verify vs Tamper */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                <button
                  onClick={() => handleVerify(selectedDoc.id)}
                  disabled={verifying}
                  className="flex items-center justify-center space-x-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold shadow-lg shadow-emerald-500/20 active:scale-95 transition-all"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${verifying ? "animate-spin" : ""}`} />
                  <span>{verifying ? "Computing Hash..." : "Run Cryptographic Verification"}</span>
                </button>

                <button
                  onClick={() => handleTamperDemo(selectedDoc.id)}
                  disabled={tampering}
                  className="flex items-center justify-center space-x-2 py-2.5 px-4 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 font-semibold active:scale-95 transition-all"
                >
                  <Bug className="w-3.5 h-3.5 text-rose-400" />
                  <span>{tampering ? "Tampering..." : "Simulate Tampering (Demo Action)"}</span>
                </button>
              </div>

              {tamperFeedback && (
                <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-800/50 text-amber-200 text-xs flex items-start space-x-2 animate-in fade-in">
                  <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <span>{tamperFeedback}</span>
                </div>
              )}

              {/* Live Verification Result Banner */}
              {verificationResult && (
                <div
                  className={`p-5 rounded-xl border space-y-3 animate-in zoom-in-95 ${
                    verificationResult.is_valid
                      ? "bg-emerald-950/20 border-emerald-500/40 text-emerald-300"
                      : "bg-rose-950/20 border-rose-500/40 text-rose-300"
                  }`}
                >
                  <div className="flex items-center space-x-2 text-sm font-bold">
                    {verificationResult.is_valid ? (
                      <>
                        <ShieldCheck className="w-5 h-5 text-emerald-400" />
                        <span>Verification PASSED: Record Integrity Confirmed</span>
                      </>
                    ) : (
                      <>
                        <ShieldAlert className="w-5 h-5 text-rose-400" />
                        <span>Verification FAILED: Unauthorized Tampering Detected!</span>
                      </>
                    )}
                  </div>

                  <p className="text-xs leading-relaxed text-slate-300">{verificationResult.explanation}</p>

                  <div className="space-y-1.5 font-mono text-[11px] pt-2 border-t border-slate-800/80">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Anchored Commitment:</span>
                      <span className="text-slate-200">{verificationResult.expected_commitment.slice(0, 24)}...</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Recomputed Hash:</span>
                      <span className={verificationResult.is_valid ? "text-emerald-400" : "text-rose-400 font-bold"}>
                        {verificationResult.computed_commitment.slice(0, 24)}...
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Ledger Status:</span>
                      <span className="text-purple-400 font-semibold">{verificationResult.chain_status}</span>
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
