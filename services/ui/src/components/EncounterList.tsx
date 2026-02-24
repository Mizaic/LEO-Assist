"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  fetchPatientEncounters,
  fetchTasks,
  resetPatient,
  syncGoldToPatient,
} from "@/lib/api";
import type { EncounterSummary, ReviewTaskSummary } from "@/lib/types";

interface Props {
  patientId: string;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "#f59e0b",
  approved: "#16a34a",
  rejected: "#dc2626",
  escalated: "#7c3aed",
};

export default function EncounterList({ patientId }: Props) {
  const [tasks, setTasks] = useState<ReviewTaskSummary[]>([]);
  const [encounters, setEncounters] = useState<EncounterSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const router = useRouter();

  async function handleReset() {
    setResetting(true);
    setError(null);
    try {
      await resetPatient(patientId);
      await Promise.all([
        fetchPatientEncounters(patientId),
        fetchTasks(undefined, patientId),
      ]).then(([encounterRows, taskRows]) => {
        setEncounters(encounterRows);
        setTasks(taskRows);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setResetting(false);
    }
  }

  async function handleSyncGold() {
    setSyncing(true);
    setError(null);
    try {
      await syncGoldToPatient(patientId);
      await Promise.all([
        fetchPatientEncounters(patientId),
        fetchTasks(undefined, patientId),
      ]).then(([encounterRows, taskRows]) => {
        setEncounters(encounterRows);
        setTasks(taskRows);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchPatientEncounters(patientId),
      fetchTasks(undefined, patientId),
    ])
      .then(([encounterRows, taskRows]) => {
        setEncounters(encounterRows);
        setTasks(taskRows);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [patientId]);

  const latestTaskByEncounter = tasks.reduce((acc, task) => {
      const encounterKey = String(task.encounter_id).trim();
      const existing = acc.get(encounterKey);
      if (!existing) {
        acc.set(encounterKey, task);
        return acc;
      }
      // Prefer pending tasks, otherwise newest by updated_at.
      if (existing.status !== "pending" && task.status === "pending") {
        acc.set(encounterKey, task);
        return acc;
      }
      if (new Date(task.updated_at).getTime() > new Date(existing.updated_at).getTime()) {
        acc.set(encounterKey, task);
      }
      return acc;
    }, new Map<string, ReviewTaskSummary>());

  const rows = [...encounters]
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .map((encounter) => ({
      encounter,
      task: latestTaskByEncounter.get(String(encounter.encounter_id).trim()),
    }));

  const approved = rows.filter((row) => row.task?.status === "approved").length;
  const withTask = rows.filter((row) => Boolean(row.task)).length;

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 24px" }}>
      <button
        onClick={() => router.push("/patients")}
        style={{
          background: "none",
          border: "none",
          color: "#4f46e5",
          cursor: "pointer",
          fontSize: 14,
          marginBottom: 16,
          padding: 0,
        }}
      >
        ← Back to patients
      </button>

      <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 24, fontWeight: 700, marginBottom: 4 }}>
        Patient {patientId}
      </h1>
      <p style={{ color: "#64748b", fontSize: 14, marginBottom: 16 }}>
        {rows.length} encounters &middot; {withTask} processed &middot; {approved} reviewed
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        <button
          onClick={handleReset}
          disabled={resetting || loading}
          style={{
            padding: "8px 16px",
            border: "1px solid #e2e8f0",
            borderRadius: 8,
            background: "#fff",
            fontSize: 13,
            fontWeight: 500,
            cursor: resetting || loading ? "not-allowed" : "pointer",
            color: "#64748b",
          }}
        >
          {resetting ? "Resetting…" : "Reset patient"}
        </button>
        <button
          onClick={handleSyncGold}
          disabled={syncing || loading || approved === 0}
          style={{
            padding: "8px 16px",
            border: "1px solid #16a34a",
            borderRadius: 8,
            background: approved > 0 ? "#fff" : "#f1f5f9",
            fontSize: 13,
            fontWeight: 500,
            cursor: syncing || loading || approved === 0 ? "not-allowed" : "pointer",
            color: approved > 0 ? "#16a34a" : "#94a3b8",
          }}
        >
          {syncing ? "Syncing…" : "Sync gold to patient"}
        </button>
      </div>

      {loading && <p style={{ color: "#64748b" }}>Loading encounters…</p>}
      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <div style={{ display: "grid", gap: 8 }}>
        {rows.map(({ encounter, task }) => {
          const status = task?.status ?? "not_processed";
          const isClickable = true;
          return (
            <button
              key={String(encounter.encounter_id)}
              onClick={() => {
                if (task?.task_id) {
                  router.push(`/patients/${patientId}/encounters/${task.task_id}`);
                } else {
                  router.push(`/patients/${patientId}/encounters/view/${encounter.encounter_id}`);
                }
              }}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr auto auto",
                alignItems: "center",
                gap: 16,
                background: "#fff",
                border: "1px solid #e2e8f0",
                borderRadius: 10,
                padding: "14px 20px",
                cursor: isClickable ? "pointer" : "default",
                textAlign: "left",
                animation: "cardIn 0.25s ease",
                transition: "box-shadow 0.15s",
              }}
              onMouseEnter={(e) => {
                if (isClickable) {
                  e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.06)";
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.boxShadow = "none";
              }}
            >
              <div>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 500 }}>
                  {String(encounter.encounter_id)}
                </span>
                {task && (
                  <span
                    style={{
                      marginLeft: 10,
                      fontSize: 11,
                      color: "#94a3b8",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    task {task.task_id.slice(0, 8)}
                  </span>
                )}
                {task && task.warning_count > 0 && (
                  <span
                    style={{
                      marginLeft: 10,
                      fontSize: 11,
                      background: "#fef3c7",
                      color: "#92400e",
                      padding: "2px 6px",
                      borderRadius: 4,
                    }}
                  >
                    {task.warning_count} warning{task.warning_count > 1 ? "s" : ""}
                  </span>
                )}
                {typeof encounter.coded_count === "number" && encounter.coded_count > 0 && (
                  <span
                    style={{
                      marginLeft: 10,
                      fontSize: 11,
                      color: "#059669",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {encounter.coded_count} coded
                  </span>
                )}
              </div>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: status === "not_processed" ? "#64748b" : STATUS_COLORS[status] || "#64748b",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                }}
              >
                {status === "not_processed" ? "not processed" : status}
              </span>
              <span style={{ fontSize: 12, color: "#94a3b8" }}>
                {task ? `P${task.priority}` : "--"}
              </span>
            </button>
          );
        })}
      </div>

      {!loading && rows.length === 0 && !error && (
        <p style={{ color: "#94a3b8", textAlign: "center", padding: 40 }}>
          No encounters found for this patient.
        </p>
      )}
    </div>
  );
}
