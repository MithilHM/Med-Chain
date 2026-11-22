"use client";

import React, { useEffect, useState } from "react";
import { ApiClient } from "@/lib/api";
import {
  ArrowLeftRight,
  UploadCloud,
  ArrowDownToLine,
  CheckCircle2,
  AlertCircle,
  FileCode,
  Layers,
  Sparkles,
  Server,
  Lock,
  Building2,
  RefreshCw,
  Search,
  ExternalLink,
} from "lucide-react";

const SAMPLE_INPATIENT_BUNDLE = {
  resourceType: "Bundle",
  type: "transaction",
  entry: [
    {
      fullUrl: "urn:uuid:patient-hosp-01",
      resource: {
        resourceType: "Patient",
        id: "PT-FHIR-8820",
        identifier: [
          {
            use: "usual",
            type: { coding: [{ system: "http://terminology.hl7.org/CodeSystem/v2-0203", code: "MR" }] },
            system: "urn:oid:hospital.tenant.mrn",
            value: "PT-FHIR-8820"
          }
        ],
        active: true,
        gender: "female",
        birthDate: "1979-11-23"
      }
    },
    {
      fullUrl: "urn:uuid:enc-hosp-01",
      resource: {
        resourceType: "Encounter",
        id: "ENC-INP-4401",
        status: "finished",
        class: {
          system: "http://terminology.hl7.org/CodeSystem/v3-ActCode",
          code: "IMP",
          display: "Inpatient Admission"
        }
      }
    },
    {
      fullUrl: "urn:uuid:cond-hosp-01",
      resource: {
        resourceType: "Condition",
        id: "COND-I10",
        clinicalStatus: { coding: [{ code: "active" }] },
        code: {
          coding: [
            { system: "http://hl7.org/fhir/sid/icd-10", code: "I10", display: "Essential (primary) hypertension" }
          ],
          text: "Essential Hypertension Stage 2"
        }
      }
    },
    {
      fullUrl: "urn:uuid:doc-hosp-01",
      resource: {
        resourceType: "DocumentReference",
        id: "DOC-DISCH-01",
        status: "current",
        type: { text: "Discharge Summary" },
        description: "Inpatient Cardiology Care Plan and Medication Reconciliation",
        content: [
          {
            attachment: {
              title: "Patient discharged in stable hemodynamic condition. Blood pressure well-controlled on Lisinopril 20mg daily."
            }
          }
        ]
      }
    }
  ]
};

const SAMPLE_OUTPATIENT_BUNDLE = {
  resourceType: "Bundle",
  type: "transaction",
  entry: [
    {
      fullUrl: "urn:uuid:patient-amb-02",
      resource: {
        resourceType: "Patient",
        id: "PT-FHIR-9930",
        identifier: [
          { system: "urn:oid:hospital.tenant.mrn", value: "PT-FHIR-9930" }
        ],
        active: true,
        gender: "male",
        birthDate: "1983-05-14"
      }
    },
    {
      fullUrl: "urn:uuid:enc-amb-02",
      resource: {
        resourceType: "Encounter",
        id: "ENC-AMB-882",
        status: "finished",
        class: { code: "AMB", display: "Outpatient Consultation" }
      }
    },
    {
      fullUrl: "urn:uuid:cond-amb-02",
      resource: {
        resourceType: "Condition",
        id: "COND-E11",
        code: {
          coding: [
            { system: "http://hl7.org/fhir/sid/icd-10", code: "E11.9", display: "Type 2 diabetes mellitus without complications" }
          ]
        }
      }
    }
  ]
};

export default function FhirInteropPage() {
  const [capability, setCapability] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [bundleInput, setBundleInput] = useState(JSON.stringify(SAMPLE_INPATIENT_BUNDLE, null, 2));
  const [importing, setImporting] = useState(false);
  const [reconcileResult, setReconcileResult] = useState<any>(null);
  const [patients, setPatients] = useState<any[]>([]);
  const [exportPatientId, setExportPatientId] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportedJson, setExportedJson] = useState<string | null>(null);

  useEffect(() => {
    async function init() {
      try {
        const [cap, pts] = await Promise.all([
          ApiClient.getFhirMetadata().catch(() => null),
          ApiClient.getPatients().catch(() => []),
        ]);
        setCapability(cap);
        setPatients(pts);
        if (pts.length > 0) setExportPatientId(pts[0].id);
      } catch (_) {
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  const handleImport = async () => {
    setImporting(true);
    setReconcileResult(null);
    try {
      const parsed = JSON.parse(bundleInput);
      const res = await ApiClient.importFhirBundle(parsed);
      setReconcileResult(res);
      const updatedPts = await ApiClient.getPatients();
      setPatients(updatedPts);
    } catch (err: any) {
      alert(`FHIR Ingestion failed: ${err.message}`);
    } finally {
      setImporting(false);
    }
  };

  const handleExport = async () => {
    if (!exportPatientId) return;
    setExporting(true);
    setExportedJson(null);
    try {
      const bundle = await ApiClient.exportPatientFhir(exportPatientId);
      setExportedJson(JSON.stringify(bundle, null, 2));
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    } finally {
      setExporting(false);
    }
  };

  const handleDownloadExport = () => {
    if (!exportedJson) return;
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(exportedJson);
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `FHIR_R4_Bundle_Export_${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-2.5">
            <ArrowLeftRight className="w-6 h-6 text-teal-400" />
            <span>HL7 FHIR R4 Interoperability Gateway</span>
          </h1>
          <p className="text-xs text-slate-400">
            Standardized hospital EHR boundary: ingest clinical feeds, reconcile patient records, and export compliant FHIR R4 bundles
          </p>
        </div>

        <div className="flex items-center space-x-2 text-xs">
          <span className="px-3 py-1 rounded-full bg-teal-500/10 border border-teal-500/30 text-teal-300 font-mono font-semibold flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" /> FHIR 4.0.1 Certified
          </span>
          <span className="px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-slate-300 font-mono">
            RESTful Boundary
          </span>
        </div>
      </div>

      {/* Metadata & Boundary Overview Card */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl glass-panel border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-white">Capability Statement</span>
            <Server className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-sm font-bold text-cyan-300">
            {capability?.software?.name || "MedChain Health OS"}
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            Version {capability?.software?.version || "2.4.0-LTS"} • FHIR {capability?.fhirVersion || "4.0.1"}
          </div>
        </div>

        <div className="p-4 rounded-xl glass-panel border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-white">Supported FHIR Resources</span>
            <FileCode className="w-4 h-4 text-teal-400" />
          </div>
          <div className="text-sm font-bold text-teal-300">
            Patient, Encounter, Condition
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            MedicationRequest, DocumentReference, Bundle
          </div>
        </div>

        <div className="p-4 rounded-xl glass-panel border border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-white">Interoperability Standards</span>
            <Lock className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-sm font-bold text-purple-300">
            21st Century Cures Act
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            HIPAA § 164.524 &amp; GDPR Portability Ready
          </div>
        </div>
      </div>

      {/* Section 1: Ingestion & Reconciliation Sandbox */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800/80 pb-4">
          <div>
            <h2 className="text-sm font-bold text-white flex items-center gap-2">
              <UploadCloud className="w-4 h-4 text-teal-400" />
              <span>Inbound Hospital EHR Ingestion &amp; Patient Matching</span>
            </h2>
            <p className="text-xs text-slate-400">
              Paste or load an HL7 FHIR R4 Bundle. The reconciliation engine matches MRNs, records encounters, maps ICD-10 codes, and anchors documents.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => setBundleInput(JSON.stringify(SAMPLE_INPATIENT_BUNDLE, null, 2))}
              className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] text-slate-300 font-mono transition-colors"
            >
              Load Inpatient Bundle
            </button>
            <button
              onClick={() => setBundleInput(JSON.stringify(SAMPLE_OUTPATIENT_BUNDLE, null, 2))}
              className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] text-slate-300 font-mono transition-colors"
            >
              Load Outpatient Bundle
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7 space-y-2">
            <label className="text-xs font-semibold text-slate-300 block">
              FHIR R4 Bundle Payload (JSON)
            </label>
            <textarea
              rows={14}
              value={bundleInput}
              onChange={(e) => setBundleInput(e.target.value)}
              className="w-full p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-cyan-200 font-mono focus:outline-none focus:border-teal-500 leading-relaxed"
            />
            <div className="flex justify-end pt-1">
              <button
                onClick={handleImport}
                disabled={importing}
                className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-500 text-white font-semibold text-xs shadow-md shadow-teal-500/20 active:scale-95 transition-all"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${importing ? "animate-spin" : ""}`} />
                <span>{importing ? "Reconciling Feed..." : "Reconcile Inbound FHIR Bundle"}</span>
              </button>
            </div>
          </div>

          <div className="lg:col-span-5 space-y-4">
            <label className="text-xs font-semibold text-slate-300 block">
              Reconciliation Engine Outcomes
            </label>

            {reconcileResult ? (
              <div className="p-4 rounded-xl bg-teal-950/30 border border-teal-800/60 space-y-3 animate-in fade-in">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-teal-300 flex items-center gap-1.5">
                    <CheckCircle2 className="w-4 h-4 text-teal-400" />
                    <span>Bundle Status: {reconcileResult.status}</span>
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-teal-900/60 text-teal-200 font-mono">
                    Audited
                  </span>
                </div>

                <div className="text-xs text-slate-300 leading-relaxed">
                  {reconcileResult.message}
                </div>

                <div className="space-y-1.5 pt-2 border-t border-teal-800/40 text-xs">
                  <div className="flex justify-between text-slate-300">
                    <span>Patients Matched / Updated:</span>
                    <strong className="text-teal-300">{reconcileResult.reconciliation_summary?.patients_matched}</strong>
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>New Patients Registered:</span>
                    <strong className="text-teal-300">{reconcileResult.reconciliation_summary?.patients_created}</strong>
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>Clinical Encounters Created:</span>
                    <strong className="text-teal-300">{reconcileResult.reconciliation_summary?.encounters_recorded}</strong>
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>ICD-10 Conditions Indexed:</span>
                    <strong className="text-teal-300">{reconcileResult.reconciliation_summary?.conditions_recorded}</strong>
                  </div>
                  <div className="flex justify-between text-slate-300">
                    <span>Documents Anchored with Hashes:</span>
                    <strong className="text-teal-300">{reconcileResult.reconciliation_summary?.documents_indexed}</strong>
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-8 text-center text-xs text-slate-400 border border-dashed border-slate-800 rounded-xl space-y-2">
                <ArrowLeftRight className="w-8 h-8 text-slate-600 mx-auto" />
                <div>Ready for ingestion</div>
                <p className="text-[11px] text-slate-400 max-w-xs mx-auto">
                  Click &quot;Reconcile Inbound FHIR Bundle&quot; to test transactional ingestion and multi-store anchoring.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Section 2: Outbound FHIR R4 Bundle Export */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6">
        <div className="border-b border-slate-800/80 pb-3">
          <h2 className="text-sm font-bold text-white flex items-center gap-2">
            <ArrowDownToLine className="w-4 h-4 text-cyan-400" />
            <span>HIPAA Right-of-Access &amp; Patient Data Portability Export</span>
          </h2>
          <p className="text-xs text-slate-400">
            Export a certified HL7 FHIR R4 collection bundle containing verified demographics, encounters, conditions, medications, and cryptographic commitments.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3">
          <select
            value={exportPatientId}
            onChange={(e) => setExportPatientId(e.target.value)}
            className="w-full sm:w-80 px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-white focus:outline-none focus:border-cyan-500"
          >
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_code} ({p.sex}, DOB: {p.date_of_birth})
              </option>
            ))}
          </select>

          <button
            onClick={handleExport}
            disabled={exporting || !exportPatientId}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs shadow-md shadow-cyan-500/20 active:scale-95 transition-all whitespace-nowrap"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${exporting ? "animate-spin" : ""}`} />
            <span>{exporting ? "Generating Bundle..." : "Generate FHIR R4 Bundle"}</span>
          </button>

          {exportedJson && (
            <button
              onClick={handleDownloadExport}
              className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-teal-300 border border-teal-500/30 text-xs font-semibold active:scale-95 transition-all whitespace-nowrap"
            >
              <ArrowDownToLine className="w-3.5 h-3.5" />
              <span>Download JSON File</span>
            </button>
          )}
        </div>

        {exportedJson && (
          <div className="space-y-2 animate-in fade-in">
            <div className="text-xs font-semibold text-slate-300 flex items-center justify-between">
              <span>Standardized FHIR R4 Bundle Preview</span>
              <span className="text-[10px] text-cyan-400 font-mono">Format: application/fhir+json</span>
            </div>
            <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 font-mono overflow-x-auto max-h-96">
              {exportedJson}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

