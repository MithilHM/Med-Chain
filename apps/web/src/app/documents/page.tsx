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
} from "lucide-react";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<any[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedDocDetail, setSelectedDocDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Form state
  const [patientId, setPatientId] = useState("");
  const [docType, setDocType] = useState("clinical_note");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [patients, setPatients] = useState<any[]>([]);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    async function loadDocs() {
      setLoading(true);
      setError(null);
      try {
        const docs = await ApiClient.getDocuments();
        setDocuments(docs);
        if (docs.length > 0) {
          setSelectedDocId(docs[0].id);
        }
        const pts = await ApiClient.getPatients().catch(() => []);
        setPatients(pts);
        if (pts.length > 0) setPatientId(pts[0].id);
      } catch (err: any) {
        setError(err.message || "Failed to load clinical documents");
      } finally {
        setLoading(false);
      }
    }
    loadDocs();
  }, []);

  useEffect(() => {
    if (!selectedDocId) return;
    async function loadDetail() {
      setDetailLoading(true);
      try {
        const detail = await ApiClient.getDocumentDetail(selectedDocId!);
        setSelectedDocDetail(detail);
      } catch (err: any) {
        setSelectedDocDetail(null);
      } finally {
        setDetailLoading(false);
      }
    }
    loadDetail();
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
      // Reload documents
      const docs = await ApiClient.getDocuments();
      setDocuments(docs);
      setSelectedDocId(created.id);
    } catch (err: any) {
      alert(`Document creation error: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  if (error) {
    return (
      <div className="glass-panel p-8 rounded-2xl border border-rose-900/50 text-center space-y-4">
        <ShieldAlert className="w-12 h-12 text-rose-400 mx-auto" />
        <h2 className="text-xl font-bold text-white">Clinical Content Access Denied</h2>
        <p className="text-sm text-slate-400 max-w-md mx-auto">{error}</p>
        <div className="text-xs text-slate-400">
          Security policy: Insurance Analysts and Researchers are strictly forbidden from inspecting full narrative clinical text. Use demo role switcher to test as <strong>Doctor</strong> or <strong>Patient</strong>.
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
            <span>Clinical Documents & Narrative Store</span>
          </h1>
          <p className="text-xs text-slate-400">
            Semi-structured medical reports stored in MongoDB with salted commitments in PostgreSQL
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 text-white font-medium text-xs shadow-lg shadow-emerald-500/20 hover:brightness-110 active:scale-95 transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>New Clinical Document</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Documents List */}
        <div className="lg:col-span-5 glass-panel p-4 rounded-2xl border border-slate-800 space-y-3">
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wider px-2">
            Archived Clinical Documents ({documents.length})
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
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
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
            <div className="text-xs text-slate-400 text-center py-16">Fetching document payload from MongoDB...</div>
          ) : !selectedDocDetail ? (
            <div className="text-xs text-slate-400 text-center py-16">Select a document to inspect payload</div>
          ) : (
            <div className="space-y-5 animate-in fade-in duration-200">
              <div className="border-b border-slate-800/80 pb-4 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-base font-bold text-white">{selectedDocDetail.title}</h2>
                  <div className="text-xs text-slate-400 mt-1 flex items-center space-x-2">
                    <span className="capitalize">{selectedDocDetail.document_type.replace("_", " ")}</span>
                    <span>•</span>
                    <span>Version {selectedDocDetail.version}</span>
                    <span>•</span>
                    <span>Storage: {selectedDocDetail.storage_status}</span>
                  </div>
                </div>

                <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  <ShieldCheck className="w-3.5 h-3.5 mr-1" />
                  {selectedDocDetail.verification_status}
                </span>
              </div>

              {/* Cryptographic Commitment Hash Card */}
              <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-xs space-y-1">
                <div className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider">
                  Salted SHA-256 Cryptographic Commitment (Off-Chain Salt)
                </div>
                <div className="font-mono text-cyan-300 break-all text-[11px]">
                  {selectedDocDetail.commitment_hash || "Computing commitment..."}
                </div>
              </div>

              {/* Raw Clinical Narrative Box */}
              <div className="space-y-2">
                <div className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5">
                  <FileText className="w-4 h-4 text-emerald-400" />
                  <span>Clinical Narrative Payload (MongoDB)</span>
                </div>
                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 text-xs leading-relaxed text-slate-200 font-sans whitespace-pre-wrap">
                  {selectedDocDetail.content}
                </div>
              </div>

              {selectedDocDetail.structured_extract && Object.keys(selectedDocDetail.structured_extract).length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-slate-300">Structured Data Extract</div>
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
            <h2 className="text-base font-bold text-white flex items-center space-x-2">
              <FileText className="w-4 h-4 text-emerald-400" />
              <span>Create Synthetic Clinical Document</span>
            </h2>

            <form onSubmit={handleCreateDocument} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Target Patient</label>
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
                <label className="block text-slate-300 font-medium mb-1">Document Type</label>
                <select
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                >
                  <option value="clinical_note">Clinical Encounter Note</option>
                  <option value="diagnostic_report">Diagnostic Imaging / Lab Narrative</option>
                  <option value="discharge_summary">Discharge Summary</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Document Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Follow-up Assessment"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-white focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Clinical Narrative Text (Synthetic Only)</label>
                <textarea
                  rows={5}
                  required
                  placeholder="Enter synthetic physician observations..."
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
                  {creating ? "Persisting & Committing..." : "Commit Document"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
