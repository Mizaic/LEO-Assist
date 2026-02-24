"use client";

import { useState } from "react";
import { exportMedSpaCyTraining } from "@/lib/api";
import { usePipelineStream } from "@/hooks/usePipelineStream";
import PipelineModal from "./PipelineModal";

export default function PipelinePanel() {
  const [patientIds, setPatientIds] = useState("");
  const [maxEnc, setMaxEnc] = useState("50");
  const [dryRun, setDryRun] = useState(false);
  const [workers, setWorkers] = useState("4");
  const [showModal, setShowModal] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [exportName, setExportName] = useState("medspacy_v1");
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<{
    entity_count: number;
    kb_count: number;
    encounter_count: number;
  } | null>(null);

  const stream = usePipelineStream();

  async function handleExportMedSpaCy() {
    setExporting(true);
    setExportResult(null);
    try {
      const ids = patientIds.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
      const result = await exportMedSpaCyTraining({
        export_name: exportName,
        patient_ids: ids.length > 0 ? ids : undefined,
      });
      setExportResult({
        entity_count: result.entity_count,
        kb_count: result.kb_count,
        encounter_count: result.encounter_count,
      });
    } catch (e) {
      setExportResult(null);
      console.error(e);
    } finally {
      setExporting(false);
    }
  }

  function handleRun() {
    const ids = patientIds
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (ids.length === 0) return;

    const maxEncVal = parseInt(maxEnc, 10);
    const workerVal = Math.max(1, Math.min(8, parseInt(workers, 10) || 4));

    stream.start({
      patientIds: ids,
      maxEncountersPerPatient: Number.isNaN(maxEncVal) ? undefined : maxEncVal,
      dryRun,
      workers: workerVal,
    });
    setShowModal(true);
    setMinimized(false);
  }

  return (
    <>
      <div
        style={{
          background: "#fff",
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          padding: 20,
          marginBottom: 24,
        }}
      >
        <h3
          style={{
            fontFamily: "var(--font-heading)",
            fontSize: 18,
            marginBottom: 12,
          }}
        >
          Run Pipeline
        </h3>
        <div
          style={{
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
            alignItems: "end",
          }}
        >
          <label style={{ display: "flex", flexDirection: "column", gap: 4, flex: "1 1 200px" }}>
            <span style={{ fontSize: 13, color: "#64748b" }}>Patient IDs (comma-separated)</span>
            <input
              value={patientIds}
              onChange={(e) => setPatientIds(e.target.value)}
              placeholder="e.g. 4202301609, 4203796334"
              style={inputStyle}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, width: 100 }}>
            <span style={{ fontSize: 13, color: "#64748b" }}>Max enc.</span>
            <input
              type="number"
              value={maxEnc}
              onChange={(e) => setMaxEnc(e.target.value)}
              style={inputStyle}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, width: 80 }}>
            <span style={{ fontSize: 13, color: "#64748b" }}>Workers</span>
            <input
              type="number"
              value={workers}
              min={1}
              max={8}
              onChange={(e) => setWorkers(e.target.value)}
              style={inputStyle}
            />
          </label>
          <label style={{ display: "flex", gap: 6, alignItems: "center", paddingBottom: 4 }}>
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
            <span style={{ fontSize: 13 }}>Dry run</span>
          </label>
          <button
            onClick={handleRun}
            disabled={stream.running}
            style={{
              background: stream.running ? "#94a3b8" : "#4f46e5",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "8px 20px",
              fontSize: 14,
              fontWeight: 600,
              cursor: stream.running ? "not-allowed" : "pointer",
            }}
          >
            {stream.running ? "Running…" : "Run Pipeline"}
          </button>
        </div>

        {/* Inline summary when modal is minimized */}
        {minimized && stream.running && stream.live && (
          <div
            style={{
              marginTop: 12,
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "#22c55e",
                animation: "pulse 1.5s infinite",
              }}
            />
            <span style={{ fontSize: 13, color: "#334155", fontFamily: "var(--font-mono)" }}>
              {stream.status} — Processed: {stream.live.processed_encounters}
            </span>
            <button
              onClick={() => { setShowModal(true); setMinimized(false); }}
              style={{
                background: "#4f46e5",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                padding: "4px 12px",
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              Expand
            </button>
          </div>
        )}

        {/* Show last result when not running */}
        {stream.result && !stream.running && (
          <div
            style={{
              marginTop: 12,
              padding: 12,
              background: "#f0fdf4",
              borderRadius: 8,
              fontSize: 13,
              fontFamily: "var(--font-mono)",
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
              gap: 8,
            }}
          >
            <span>Processed: {stream.result.processed_encounters}</span>
            <span>Queued: {stream.result.queued_for_review}</span>
            <span>Rejected: {stream.result.rejected_hard_fail}</span>
            <span>Warnings: {stream.result.warnings_only}</span>
          </div>
        )}

        {stream.error && !stream.running && (
          <p style={{ color: "#b91c1c", fontSize: 13, marginTop: 8 }}>{stream.error}</p>
        )}

        <h3 style={{ fontFamily: "var(--font-heading)", fontSize: 18, marginTop: 24, marginBottom: 12 }}>
          Export MedSpaCy Training
        </h3>
        <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 13, color: "#64748b" }}>Export name</span>
            <input
              value={exportName}
              onChange={(e) => setExportName(e.target.value)}
              placeholder="medspacy_v1"
              style={inputStyle}
            />
          </label>
          <button
            onClick={handleExportMedSpaCy}
            disabled={exporting}
            style={{
              background: exporting ? "#94a3b8" : "#16a34a",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "8px 20px",
              fontSize: 14,
              fontWeight: 600,
              cursor: exporting ? "not-allowed" : "pointer",
            }}
          >
            {exporting ? "Exporting…" : "Export MedSpaCy training"}
          </button>
        </div>
        <p style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
          Uses patient IDs above if set; otherwise exports all approved gold.
        </p>
        {exportResult && (
          <div style={{ marginTop: 8, padding: 12, background: "#f0fdf4", borderRadius: 8, fontSize: 13 }}>
            Exported: {exportResult.entity_count} entities, {exportResult.kb_count} KB rows, {exportResult.encounter_count} encounters
          </div>
        )}
      </div>

      {showModal && !minimized && (
        <PipelineModal
          running={stream.running}
          status={stream.status}
          live={stream.live}
          result={stream.result}
          error={stream.error}
          workerStates={stream.workerStates}
          onClose={() => setShowModal(false)}
          onMinimize={() => setMinimized(true)}
        />
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </>
  );
}

const inputStyle: React.CSSProperties = {
  border: "1px solid #cbd5e1",
  borderRadius: 8,
  padding: "8px 12px",
  fontSize: 14,
  fontFamily: "var(--font-mono)",
};
