"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  FileText,
  Plus,
  ShieldCheck,
  Calendar,
  Lock,
  Search,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  ShieldAlert,
  Edit3,
  History,
  Check,
  X,
  Sparkles,
} from "lucide-react";

function verificationStatusClasses(status: string) {
  if (status === "VERIFIED_MATCH") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  if (status === "TAMPER_DETECTED" || status === "DOCUMENT_NOT_FOUND") return "bg-rose-500/10 text-rose-300 border-rose-500/20";
  return "bg-amber-500/10 text-amber-300 border-amber-500/20";
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<any[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedDocDetail, setSelectedDocDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAmendModal, setShowAmendModal] = useState(false);

  // Form state for new document
  const [patientId, setPatientId] = useState("");
  const [docType, setDocType] = useState("clinical_note");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [patients, setPatients] = useState<any[]>([]);
  const [creating, setCreating] = useState(false);

  // Form state for amendment
  const [amendmentText, setAmendmentText] = useState("");
  const [amendReason, setAmendReason] = useState("Laboratory follow-up addendum");
  const [signature, setSignature] = useState("Dr. Sarah Chen, MD");
  const [amending, setAmending] = useState(false);
  const [amendSuccess, setAmendSuccess] = useState<string | null>(null);

  const loadDocs = async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await ApiClient.getDocuments();
      setDocuments(docs);
      if (docs.length > 0 && !selectedDocId) {
        setSelectedDocId(docs[0].id);
      }
      const pts = await ApiClient.getPatients().catch(() => []);
      setPatients(pts);
      if (pts.length > 0 && !patientId) setPatientId(pts[0].id);
    } catch (err: any) {
      setError(err.message || "Failed to load clinical documents");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDocs();
  }, []);

  const loadDetail = async (id: string) => {
    setDetailLoading(true);
    try {
      const detail = await ApiClient.getDocumentDetail(id);
      setSelectedDocDetail(detail);
    } catch (err: any) {
      setSelectedDocDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    if (selectedDocId) {
      loadDetail(selectedDocId);
    }
  }, [selectedDocId]);

  const handleCreateDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!patientId || !title || !content) return;
    setCreating(true);
    try {
      const created = await ApiClient.createDocument({
        patient_id: patientId,
        document_type: docType,
        title,
        content,
      });
      setShowCreateModal(false);
      setTitle("");
      setContent("");
      await loadDocs();
      if (created?.id) setSelectedDocId(created.id);
    } catch (err: any) {
      alert(`Document creation error: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  const handleAmendDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDocId || !amendmentText.trim()) return;
    setAmending(true);
    try {
      const res = await ApiClient.amendDocument(selectedDocId, {
        amendment_text: amendmentText.trim(),
        reason: amendReason.trim(),
        author_signature: signature.trim(),
      });
      setAmendSuccess(`Amendment v${res.new_version} signed & anchored with commitment hash.`);
      setAmendmentText("");
      setTimeout(() => {
        setShowAmendModal(false);
        setAmendSuccess(null);
      }, 1500);
      await loadDocs();
      await loadDetail(selectedDocId);
    } catch (err: any) {
      alert(`Document amendment error: ${err.message}`);
    } finally {
      setAmending(false);
    }
  };

  if (error) {
    return (
      <div className="glass-panel p-8 rounded-2xl border border-rose-900/50 text-center space-y-4">
        <ShieldAlert className="w-12 h-12 text-rose-400 mx-auto" />
        <h2 className="text-xl font-bold text-white">Clinical Content Access Denied</h2>
        <p className="text-sm text-slate-400 max-w-md mx-auto">{error}</p>
        <div className="text-xs text-slate-400">
          Security policy: Insurance Analysts and Researchers are strictly forbidden from inspecting full narrative clinical text. Use staff role switcher to test as <strong>Attending Physician</strong> or <strong>Patient</strong>.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
            <FileText className="w-6 h-6 text-emerald-400" />
            <span>Clinical Documents & Encrypted Vault</span>
          </h1>
          <p className="text-xs text-slate-400">
            AES-256-GCM encrypted clinical notes in MongoDB with salted SHA-256 commitments & immutable addenda
          </p>
        </div>

        <div className="flex items-center space-x-2.5">
          {selectedDocDetail && (
            <button
              onClick={() => setShowAmendModal(true)}
              className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-cyan-500/30 font-medium text-xs active:scale-95 transition-all"
            >
              <Edit3 className="w-3.5 h-3.5 text-cyan-400" />
              <span>Sign Clinical Addendum</span>
            </button>
          )}

          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 text-white font-medium text-xs shadow-lg shadow-emerald-500/20 hover:brightness-110 active:scale-95 transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>New Clinical Document</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Documents List */}
        <div className="lg:col-span-5 glass-panel p-4 rounded-2xl border border-slate-800 space-y-3">
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wider px-2 flex items-center justify-between">
            <span>Archived Documents ({documents.length})</span>
            <span className="text-[10px] text-emerald-400 font-mono">AES-256</span>
          </div>

          <div className="space-y-2 max-h-[640px] overflow-y-auto pr-1">
            {loading ? (
              <div className="text-xs text-slate-400 text-center py-8">Loading documents...</div>
            ) : documents.length === 0 ? (
              <div className="text-xs text-slate-400 text-center py-8">No documents recorded</div>
            ) : (
              documents.map((d) => {
                const isSelected = d.id === selectedDocId;
                return (
                  <button
                    key={d.id}
                    onClick={() => setSelectedDocId(d.id)}
                    className={`w-full p-3.5 rounded-xl border text-left transition-all flex items-center justify-between ${
                      isSelected
                        ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-300 shadow-sm shadow-emerald-500/10"
                        : "bg-slate-900/40 border-slate-800/80 text-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="text-xs font-bold text-white capitalize">{d.document_type.replace("_", " ")}</div>
                      <div className="text-[11px] text-slate-400 font-mono">Doc ID: {d.id.slice(0, 13)}...</div>
                      <div className="text-[10px] text-slate-400">
                        {new Date(d.created_at).toLocaleString()}
                      </div>
                    </div>

                    <div className="text-right">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${verificationStatusClasses(d.verification_status)}`}>
                        {d.verification_status}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Protected Narrative Viewer */}
        <div className="lg:col-span-7 glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
          {detailLoading ? (
            <div className="text-xs text-slate-400 text-center py-16">Fetching encrypted document payload from MongoDB...</div>
          ) : !selectedDocDetail ? (
            <div className="text-xs text-slate-400 text-center py-16">Select a document to inspect payload</div>
          ) : (
            <div className="space-y-5 animate-in fade-in duration-200">
              <div className="border-b border-slate-800/80 pb-4 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <span>{selectedDocDetail.title}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800 font-mono">
                      v{selectedDocDetail.version}
                    </span>
                  </h2>
                  <div className="text-xs text-slate-400 mt-1 flex items-center space-x-2">
                    <span className="capitalize">{selectedDocDetail.document_type.replace("_", " ")}</span>
                    <span>•</span>
                    <span>Storage: {selectedDocDetail.storage_status}</span>
                    <span>•</span>
                    <span>Created: {new Date(selectedDocDetail.created_at).toLocaleDateString()}</span>
                  </div>
                </div>

                <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border ${verificationStatusClasses(selectedDocDetail.verification_status)}`}>
                  {selectedDocDetail.verification_status === "VERIFIED_MATCH"
                    ? <ShieldCheck className="w-3.5 h-3.5 mr-1" />
                    : <ShieldAlert className="w-3.5 h-3.5 mr-1" />}
                  {selectedDocDetail.verification_status}
                </span>
              </div>

              {/* Cryptographic Commitment Hash Card */}
              <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-xs space-y-1">
                <div className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider flex items-center justify-between">
                  <span>Salted SHA-256 Ledger Anchor (Off-Chain Salt)</span>
                  <span className="text-cyan-400 font-mono">Immutable Hash</span>
                </div>
                <div className="font-mono text-cyan-300 break-all text-[11px]">
                  {selectedDocDetail.commitment_hash || "Computing commitment..."}
                </div>
              </div>

              {/* Clinical Narrative Content Box */}
              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-300 flex items-center justify-between">
                  <span className="flex items-center space-x-1.5">
                    <FileText className="w-4 h-4 text-emerald-400" />
                    <span>Clinical Narrative Payload</span>
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">AES-256 Envelope Decrypted</span>
                </div>
                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 text-xs leading-relaxed text-slate-200 font-sans whitespace-pre-wrap">
                  {selectedDocDetail.content}
                </div>
              </div>

              {/* Structured Data Extract if present */}
              {selectedDocDetail.structured_extract && Object.keys(selectedDocDetail.structured_extract).length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-slate-300">Structured Diagnostic Extract</div>
                  <pre className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-[11px] text-slate-300 overflow-x-auto font-mono">
                    {JSON.stringify(selectedDocDetail.structured_extract, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Modal for Creating New Document */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-lg glass-panel p-6 rounded-2xl border border-slate-700 space-y-4 animate-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white flex items-center space-x-2">
                <FileText className="w-4 h-4 text-emerald-400" />
                <span>Author Clinical Note</span>
              </h2>
              <button onClick={() => setShowCreateModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateDocument} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Target Patient MRN</label>
                <select
                  value={patientId}
                  onChange={(e) => setPatientId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                >
                  {patients.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.display_code} ({p.sex}, DOB: {p.date_of_birth})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Document Category</label>
                <select
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                >
                  <option value="clinical_note">Clinical Encounter Note (SOAP)</option>
                  <option value="diagnostic_report">Diagnostic Imaging / Pathology Report</option>
                  <option value="discharge_summary">Hospital Discharge Summary</option>
                  <option value="operative_report">Operative / Procedural Report</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Document Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Cardiology Consultation & Comprehensive Assessment"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Clinical Narrative Content</label>
                <textarea
                  rows={6}
                  required
                  placeholder="Subjective: Patient reports exertion-induced shortness of breath...&#10;Objective: BP 138/88 mmHg, HR 74 bpm regular...&#10;Assessment: Essential hypertension with mild exertional dyspnea...&#10;Plan: Continue Lisinopril 20mg daily, follow-up echo scheduled..."
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500 font-sans"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-800 text-slate-400 hover:bg-slate-900 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow-md shadow-emerald-500/20"
                >
                  {creating ? "Encrypting & Committing..." : "Sign & Commit Document"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal for Signing Clinical Addendum / Amendment */}
      {showAmendModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-lg glass-panel p-6 rounded-2xl border border-slate-700 space-y-4 animate-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-white flex items-center space-x-2">
                <Edit3 className="w-4 h-4 text-cyan-400" />
                <span>Sign Clinical Addendum / Amendment</span>
              </h2>
              <button onClick={() => setShowAmendModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            {amendSuccess ? (
              <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-800 text-emerald-200 text-xs flex items-center space-x-2">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                <span>{amendSuccess}</span>
              </div>
            ) : (
              <form onSubmit={handleAmendDocument} className="space-y-4 text-xs">
                <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 text-[11px] leading-relaxed">
                  Clinical governance rule: Existing note content cannot be deleted or modified.
                  This amendment will append a signed, timestamped addendum with an incremented version number and updated cryptographic commitment.
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Amendment Reason</label>
                  <select
                    value={amendReason}
                    onChange={(e) => setAmendReason(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="Laboratory follow-up addendum">Laboratory follow-up addendum</option>
                    <option value="Diagnostic imaging report clarification">Diagnostic imaging report clarification</option>
                    <option value="Transcription / typographical correction">Transcription / typographical correction</option>
                    <option value="Post-discharge care coordination note">Post-discharge care coordination note</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Addendum Narrative Text</label>
                  <textarea
                    rows={4}
                    required
                    placeholder="Enter the addendum observations, lab findings, or clarified clinical details..."
                    value={amendmentText}
                    onChange={(e) => setAmendmentText(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500 font-sans"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Attending Physician Electronic Signature</label>
                  <input
                    type="text"
                    required
                    value={signature}
                    onChange={(e) => setSignature(e.target.value)}
                    className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="flex items-center justify-end space-x-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowAmendModal(false)}
                    className="px-4 py-2 rounded-xl border border-slate-800 text-slate-400 hover:bg-slate-900 font-medium"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={amending}
                    className="px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-medium shadow-md shadow-cyan-500/20"
                  >
                    {amending ? "Anchoring Addendum..." : "Sign & Anchor Addendum"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
