"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import type { PipelineRunResponse } from "@/lib/types";
import type { WorkerState } from "@/hooks/usePipelineStream";
import ProgressViz from "./games/ProgressViz";

const SnakeGame = dynamic(() => import("./games/SnakeGame"), { ssr: false });
const SpaceInvaders = dynamic(() => import("./games/SpaceInvaders"), { ssr: false });
const BreakoutGame = dynamic(() => import("./games/BreakoutGame"), { ssr: false });

type GameTab = "snake" | "invaders" | "breakout" | "progress";

interface Props {
  running: boolean;
  status: string | null;
  live: PipelineRunResponse | null;
  result: PipelineRunResponse | null;
  error: string | null;
  workerStates: Record<number, WorkerState>;
  onClose: () => void;
  onMinimize: () => void;
}

const TAB_META: { id: GameTab; label: string; icon: string }[] = [
  { id: "snake", label: "Snake", icon: "🐍" },
  { id: "invaders", label: "Space Invaders", icon: "👾" },
  { id: "breakout", label: "Breakout", icon: "🧱" },
  { id: "progress", label: "Progress", icon: "📊" },
];

function StatChip({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "6px 14px",
        background: "rgba(255,255,255,0.06)",
        borderRadius: 8,
        minWidth: 80,
      }}
    >
      <span style={{ fontSize: 22, fontWeight: 700, color, fontFamily: "var(--font-mono)" }}>
        {value}
      </span>
      <span style={{ fontSize: 11, color: "#94a3b8" }}>{label}</span>
    </div>
  );
}

export default function PipelineModal({
  running,
  status,
  live,
  result,
  error,
  workerStates,
  onClose,
  onMinimize,
}: Props) {
  const [tab, setTab] = useState<GameTab>("progress");

  const done = !!result || !!error;
  const stats = result ?? live;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(15,23,42,0.92)",
        backdropFilter: "blur(8px)",
      }}
    >
      {/* Top bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 24px",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: running ? "#22c55e" : done ? "#6366f1" : "#64748b",
              boxShadow: running ? "0 0 8px #22c55e" : "none",
              animation: running ? "pulse 1.5s infinite" : "none",
            }}
          />
          <span style={{ color: "#e2e8f0", fontSize: 14, fontFamily: "var(--font-mono)" }}>
            {status ?? "Pipeline"}
          </span>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={onMinimize} style={topBtn} title="Minimize">
            &#x2015;
          </button>
          {done && (
            <button onClick={onClose} style={topBtn} title="Close">
              &#x2715;
            </button>
          )}
        </div>
      </div>

      {/* Stats bar */}
      {stats && (
        <div
          style={{
            position: "absolute",
            top: 52,
            display: "flex",
            gap: 12,
            padding: "8px 0",
          }}
        >
          <StatChip label="Processed" value={stats.processed_encounters} color="#e2e8f0" />
          <StatChip label="Queued" value={stats.queued_for_review} color="#22c55e" />
          <StatChip label="Rejected" value={stats.rejected_hard_fail} color="#ef4444" />
          <StatChip label="Warnings" value={stats.warnings_only} color="#f59e0b" />
        </div>
      )}

      {/* Game area */}
      <div style={{ marginTop: 80 }}>
        {tab === "snake" && <SnakeGame />}
        {tab === "invaders" && <SpaceInvaders />}
        {tab === "breakout" && <BreakoutGame />}
        {tab === "progress" && (
          <ProgressViz status={status} live={live} workerStates={workerStates} />
        )}
      </div>

      {/* Completion overlay */}
      {done && !error && (
        <div
          style={{
            position: "absolute",
            bottom: 80,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12,
          }}
        >
          <span style={{ fontSize: 28, color: "#22c55e", fontWeight: 700 }}>
            Pipeline Complete
          </span>
          <button
            onClick={onClose}
            style={{
              background: "#4f46e5",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "10px 28px",
              fontSize: 15,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            View Results
          </button>
        </div>
      )}

      {error && (
        <div
          style={{
            position: "absolute",
            bottom: 80,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span style={{ color: "#ef4444", fontSize: 16, fontWeight: 600 }}>
            Pipeline Error
          </span>
          <span style={{ color: "#f87171", fontSize: 13, maxWidth: 400, textAlign: "center" }}>
            {error}
          </span>
          <button
            onClick={onClose}
            style={{
              background: "#334155",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "8px 20px",
              fontSize: 14,
              cursor: "pointer",
              marginTop: 4,
            }}
          >
            Close
          </button>
        </div>
      )}

      {/* Tab bar */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
          gap: 4,
          padding: "10px 24px",
          borderTop: "1px solid rgba(255,255,255,0.08)",
          background: "rgba(15,23,42,0.6)",
        }}
      >
        {TAB_META.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              background: tab === t.id ? "rgba(99,102,241,0.25)" : "transparent",
              border: tab === t.id ? "1px solid #6366f1" : "1px solid transparent",
              borderRadius: 8,
              padding: "8px 18px",
              color: tab === t.id ? "#e2e8f0" : "#94a3b8",
              fontSize: 13,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}

const topBtn: React.CSSProperties = {
  background: "rgba(255,255,255,0.08)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 6,
  color: "#94a3b8",
  width: 28,
  height: 28,
  fontSize: 14,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};
