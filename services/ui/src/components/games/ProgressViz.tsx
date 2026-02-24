"use client";

import type { PipelineRunResponse } from "@/lib/types";
import type { WorkerState } from "@/hooks/usePipelineStream";

interface Props {
  status: string | null;
  live: PipelineRunResponse | null;
  workerStates: Record<number, WorkerState>;
}

const STEPS = [
  { key: "load", label: "Load", icon: "1" },
  { key: "deid", label: "De-ID", icon: "2" },
  { key: "split", label: "Split", icon: "3" },
  { key: "extract", label: "Extract", icon: "4" },
  { key: "code", label: "Code", icon: "5" },
  { key: "validate", label: "Validate", icon: "6" },
  { key: "persist", label: "Persist", icon: "7" },
] as const;

const STEP_INDEX: Record<string, number> = {};
STEPS.forEach((s, i) => {
  STEP_INDEX[s.key] = i;
});

function stepIdx(key: string): number {
  return STEP_INDEX[key] ?? -1;
}

const WORKER_COLORS = [
  "#6366f1",
  "#22c55e",
  "#f59e0b",
  "#38bdf8",
  "#ec4899",
  "#a78bfa",
  "#f97316",
  "#14b8a6",
];

function WorkerRow({ ws, color }: { ws: WorkerState; color: string }) {
  const active = stepIdx(ws.step);
  const isDone = ws.step === "done";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          width: 28,
          fontFamily: "var(--font-mono, monospace)",
          fontSize: 11,
          color,
          fontWeight: 700,
          textAlign: "right",
          flexShrink: 0,
        }}
      >
        W{ws.workerId}
      </span>
      <div style={{ display: "flex", gap: 3, flex: 1 }}>
        {STEPS.map((step, i) => {
          const isActive = !isDone && i === active;
          const stepDone = isDone || i < active;
          return (
            <div
              key={step.key}
              style={{
                flex: 1,
                height: 28,
                borderRadius: 4,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 10,
                fontFamily: "var(--font-mono, monospace)",
                fontWeight: isActive ? 700 : 500,
                color: stepDone ? "#fff" : isActive ? "#fff" : "#64748b",
                background: stepDone
                  ? "#22c55e"
                  : isActive
                    ? color
                    : "rgba(255,255,255,0.06)",
                border: isActive
                  ? `2px solid ${color}`
                  : "1px solid rgba(255,255,255,0.08)",
                boxShadow: isActive ? `0 0 10px ${color}55` : "none",
                transition: "all 0.2s ease",
              }}
            >
              {step.label}
            </div>
          );
        })}
      </div>
      <span
        style={{
          width: 80,
          fontSize: 10,
          color: "#94a3b8",
          fontFamily: "var(--font-mono, monospace)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          flexShrink: 0,
        }}
        title={ws.encounterId}
      >
        {ws.statusText}
      </span>
    </div>
  );
}

function StatBadge({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "4px 12px",
        background: "rgba(255,255,255,0.04)",
        borderRadius: 6,
        minWidth: 60,
      }}
    >
      <span
        style={{
          fontSize: 20,
          fontWeight: 700,
          color,
          fontFamily: "var(--font-mono, monospace)",
        }}
      >
        {value}
      </span>
      <span style={{ fontSize: 10, color: "#94a3b8" }}>{label}</span>
    </div>
  );
}

export default function ProgressViz({ status, live, workerStates }: Props) {
  const sorted = Object.values(workerStates).sort(
    (a, b) => a.workerId - b.workerId,
  );
  const processed = live?.processed_encounters ?? 0;
  const queued = live?.queued_for_review ?? 0;
  const rejected = live?.rejected_hard_fail ?? 0;
  const warnings = live?.warnings_only ?? 0;
  const hasWorkers = sorted.length > 0;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 16,
        width: 520,
        maxWidth: "90vw",
      }}
    >
      {/* Stats row */}
      <div style={{ display: "flex", gap: 10 }}>
        <StatBadge label="Processed" value={processed} color="#e2e8f0" />
        <StatBadge label="Queued" value={queued} color="#22c55e" />
        <StatBadge label="Rejected" value={rejected} color="#ef4444" />
        <StatBadge label="Warnings" value={warnings} color="#f59e0b" />
      </div>

      {/* Worker pipelines */}
      <div
        style={{
          width: "100%",
          display: "flex",
          flexDirection: "column",
          gap: 6,
          padding: "12px 16px",
          background: "rgba(15,23,42,0.8)",
          borderRadius: 10,
          border: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            marginBottom: 4,
          }}
        >
          <span style={{ width: 28 }} />
          <div style={{ display: "flex", gap: 3, flex: 1 }}>
            {STEPS.map((step) => (
              <div
                key={step.key}
                style={{
                  flex: 1,
                  textAlign: "center",
                  fontSize: 9,
                  color: "#64748b",
                  fontFamily: "var(--font-mono, monospace)",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                }}
              >
                {step.label}
              </div>
            ))}
          </div>
          <span style={{ width: 80 }} />
        </div>

        {hasWorkers ? (
          sorted.map((ws) => (
            <WorkerRow
              key={ws.workerId}
              ws={ws}
              color={WORKER_COLORS[(ws.workerId - 1) % WORKER_COLORS.length]}
            />
          ))
        ) : (
          <div
            style={{
              textAlign: "center",
              padding: "20px 0",
              color: "#64748b",
              fontSize: 13,
            }}
          >
            Waiting for workers…
          </div>
        )}
      </div>

      {/* Status text */}
      {status && (
        <p
          style={{
            color: "#64748b",
            fontSize: 12,
            fontFamily: "var(--font-mono, monospace)",
            textAlign: "center",
            maxWidth: 400,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            margin: 0,
          }}
        >
          {status}
        </p>
      )}
    </div>
  );
}
