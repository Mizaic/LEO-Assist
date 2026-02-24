"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchPatients } from "@/lib/api";
import type { Patient } from "@/lib/types";
import PipelinePanel from "./PipelinePanel";

export default function PatientList() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      setPatients(await fetchPatients());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load patients");
    } finally {
      setLoading(false);
    }
  }

  const normalizedQuery = query.trim().toLowerCase();
  const filteredPatients = normalizedQuery
    ? patients.filter((p) => p.patient_id.toLowerCase().includes(normalizedQuery))
    : patients;

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 24px" }}>
      <h1 style={{
        fontFamily: "var(--font-heading)",
        fontSize: 28,
        fontWeight: 700,
        marginBottom: 24,
        color: "#0f172a",
      }}>
        Clinical Coding Review
      </h1>

      <PipelinePanel />

      {loading && <p style={{ color: "#64748b" }}>Loading patients…</p>}
      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, color: "#334155" }}>Patients</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by patient ID..."
            style={{
              border: "1px solid #cbd5e1",
              borderRadius: 8,
              padding: "6px 10px",
              fontSize: 13,
              minWidth: 220,
              fontFamily: "var(--font-mono)",
            }}
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              style={{
                background: "#fff",
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                padding: "6px 10px",
                fontSize: 12,
                cursor: "pointer",
                color: "#475569",
              }}
            >
              Clear
            </button>
          )}
          <button
            onClick={load}
            style={{
              background: "none",
              border: "1px solid #cbd5e1",
              borderRadius: 8,
              padding: "6px 14px",
              fontSize: 13,
              cursor: "pointer",
              color: "#475569",
            }}
          >
            Refresh
          </button>
        </div>
      </div>
      <p style={{ fontSize: 12, color: "#64748b", marginBottom: 10 }}>
        Showing {filteredPatients.length} of {patients.length} patients
      </p>

      <div style={{ display: "grid", gap: 8 }}>
        {filteredPatients.map((p) => (
          <button
            key={p.patient_id}
            onClick={() => router.push(`/patients/${p.patient_id}`)}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto auto",
              alignItems: "center",
              gap: 16,
              background: "#fff",
              border: "1px solid #e2e8f0",
              borderRadius: 10,
              padding: "14px 20px",
              cursor: "pointer",
              textAlign: "left",
              animation: "cardIn 0.25s ease",
              transition: "box-shadow 0.15s",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.06)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = "none"; }}
          >
            <div>
              <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 15 }}>
                {p.patient_id}
              </span>
              <span style={{ color: "#64748b", fontSize: 13, marginLeft: 12 }}>
                {p.encounter_count} encounters
              </span>
            </div>
            <div style={{ width: 120, height: 6, background: "#e2e8f0", borderRadius: 3, overflow: "hidden" }}>
              <div
                style={{
                  width: `${Math.round(p.progress * 100)}%`,
                  height: "100%",
                  background: p.progress >= 1 ? "#16a34a" : "#4f46e5",
                  borderRadius: 3,
                  transition: "width 0.3s",
                }}
              />
            </div>
            <span style={{ fontSize: 12, color: "#64748b", minWidth: 50, textAlign: "right" }}>
              {p.reviewed_count}/{p.encounter_count}
            </span>
          </button>
        ))}
      </div>

      {!loading && patients.length === 0 && !error && (
        <p style={{ color: "#94a3b8", textAlign: "center", padding: 40 }}>
          No patients found. Run the pipeline to generate review tasks.
        </p>
      )}
      {!loading && patients.length > 0 && filteredPatients.length === 0 && !error && (
        <p style={{ color: "#94a3b8", textAlign: "center", padding: 40 }}>
          No patients match "{query}". Try a different ID fragment.
        </p>
      )}
    </div>
  );
}
