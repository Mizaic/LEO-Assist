"use client";

import type { PipelineRunResponse } from "@/lib/types";
import type { WorkerState } from "@/hooks/usePipelineStream";

interface Props {
  status: string | null;
  live: PipelineRunResponse | null;
  workerStates: Record<number, WorkerState>;
}

const STEPS = [
  { key: "load", label: "Load" },
  { key: "deid", label: "De-ID" },
  { key: "split", label: "Split" },
  { key: "extract", label: "Extract" },
  { key: "code", label: "Code" },
  { key: "validate", label: "Validate" },
  { key: "persist", label: "Persist" },
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
  const shortId = ws.encounterId ? ws.encounterId.slice(0, 8) : "—";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 12px",
        background: "rgba(255,255,255,0.03)",
        borderRadius: 8,
        border: `1px solid ${isDone ? "rgba(34,197,94,0.2)" : `${color}33`}`,
      }}
    >
      {/* Worker badge */}
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 8,
          background: isDone ? "rgba(34,197,94,0.15)" : `${color}22`,
          border: `2px solid ${isDone ? "#22c55e" : color}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--font-mono, monospace)",
          fontSize: 13,
          fontWeight: 700,
          color: isDone ? "#22c55e" : color,
          flexShrink: 0,
        }}
      >
        W{ws.workerId}
      </div>

      {/* Step pipeline */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
          <span
            style={{
              fontSize: 11,
              fontFamily: "var(--font-mono, monospace)",
              color: "#94a3b8",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={ws.encounterId}
          >
            {shortId}…
          </span>
          {ws.completedCount > 0 && (
            <span
              style={{
                fontSize: 9,
                fontFamily: "var(--font-mono, monospace)",
                color: "#22c55e",
                background: "rgba(34,197,94,0.12)",
                padding: "1px 5px",
                borderRadius: 4,
                fontWeight: 600,
              }}
            >
              {ws.completedCount} done
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 2 }}>
          {STEPS.map((step, i) => {
            const isActive = !isDone && i === active;
            const stepDone = isDone || i < active;
            return (
              <div
                key={step.key}
                style={{
                  flex: 1,
                  height: 22,
                  borderRadius: 3,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 9,
                  fontFamily: "var(--font-mono, monospace)",
                  fontWeight: isActive ? 700 : 500,
                  color: stepDone ? "#fff" : isActive ? "#fff" : "#475569",
                  background: stepDone
                    ? "#22c55e"
                    : isActive
                      ? color
                      : "rgba(255,255,255,0.04)",
                  border: isActive
                    ? `2px solid ${color}`
                    : "1px solid rgba(255,255,255,0.06)",
                  boxShadow: isActive ? `0 0 8px ${color}44` : "none",
                  transition: "all 0.25s ease",
                }}
              >
                {step.label}
              </div>
            );
          })}
        </div>
      </div>

      {/* Status text */}
      <span
        style={{
          width: 70,
          fontSize: 10,
          color: isDone ? "#22c55e" : "#94a3b8",
          fontFamily: "var(--font-mono, monospace)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          textAlign: "right",
          flexShrink: 0,
          fontWeight: isDone ? 600 : 400,
        }}
      >
        {ws.statusText}
      </span>
    </div>
  );
}

export default function ProgressViz({ status, live, workerStates }: Props) {
  const sorted = Object.values(workerStates).sort(
    (a, b) => a.workerId - b.workerId,
  );
  const hasWorkers = sorted.length > 0;
  const total = live?.processed_encounters ?? 0;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 12,
        width: 560,
        maxWidth: "92vw",
      }}
    >
      {/* Column headers */}
      {hasWorkers && (
        <div
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 12px",
          }}
        >
          <span style={{ width: 36 }} />
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 0 }}>
            <div style={{ display: "flex", gap: 2 }}>
              {STEPS.map((step) => (
                <div
                  key={step.key}
                  style={{
                    flex: 1,
                    textAlign: "center",
                    fontSize: 8,
                    color: "#475569",
                    fontFamily: "var(--font-mono, monospace)",
                    textTransform: "uppercase",
                    letterSpacing: 0.8,
                  }}
                >
                  {step.label}
                </div>
              ))}
            </div>
          </div>
          <span style={{ width: 70 }} />
        </div>
      )}

      {/* Worker rows */}
      <div
        style={{
          width: "100%",
          display: "flex",
          flexDirection: "column",
          gap: 6,
        }}
      >
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
              padding: "32px 0",
              color: "#475569",
              fontSize: 13,
              fontFamily: "var(--font-mono, monospace)",
            }}
          >
            Waiting for workers…
          </div>
        )}
      </div>

      {/* Encounter progress bar */}
      {total > 0 && (
        <div
          style={{
            fontFamily: "var(--font-mono, monospace)",
            fontSize: 11,
            color: "#64748b",
          }}
        >
          {total} encounter{total !== 1 ? "s" : ""} processed
        </div>
      )}

      {/* Status text */}
      {status && (
        <p
          style={{
            color: "#475569",
            fontSize: 11,
            fontFamily: "var(--font-mono, monospace)",
            textAlign: "center",
            maxWidth: 440,
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
