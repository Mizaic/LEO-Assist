"use client";

/**
 * "Results" tab body for the ProbeMonitor (Phase 6b-vi
 * decomposition).
 *
 * Shows highlighted top-level fields, a compact summary list, and
 * loading/empty states for live runs.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  formatPrimitive,
  friendlyError,
  isRecord,
  type PathSegment,
  summarizeValue,
  valueTone,
} from "./utils";

interface DataTabProps {
  isTestRunning: boolean;
  wireState: Record<string, unknown> | null;
  isEdgeNotReached: boolean;
  isNotReachedByPartialRun: boolean;
  isPending: boolean;
  isIntercepting: boolean;
  liveInputState: Record<string, unknown>;
  entries: Array<[string, unknown]>;
  highlights: Array<[string, unknown]>;
  wireError: string | null;
  openInspector: (path: PathSegment[]) => void;
}

export function ProbeMonitorData(props: DataTabProps) {
  const {
    isTestRunning,
    wireState,
    isEdgeNotReached,
    isNotReachedByPartialRun,
    isPending,
    isIntercepting,
    liveInputState,
    entries,
    highlights,
    wireError,
    openInspector,
  } = props;

  if (!isTestRunning && !wireState && !isEdgeNotReached && !isNotReachedByPartialRun) {
    return (
      <div style={{ color: "#585b70", padding: "6px 0", textAlign: "center" }}>
        No results yet — click <span style={{ color: "#cba6f7" }}>Run to here</span> to see what this step does
      </div>
    );
  }

  if (isPending) {
    return (
      <div style={{ color: "#89b4fa", padding: "4px 0" }}>
        <span style={{ animation: "probePulse 1s ease-in-out infinite", display: "inline-block" }}>◌</span>
        {" "}queued…
      </div>
    );
  }

  if (isIntercepting) {
    return (
      <div style={{ padding: "4px 0" }}>
        <div style={{ color: "#89dceb", marginBottom: 6 }}>
          <span style={{ display: "inline-block", animation: "probeSpin 0.8s linear infinite", marginRight: 6 }}>⟳</span>
          intercepting live data…
        </div>
        {Object.entries(liveInputState).slice(0, 5).map(([key, value]) => (
          <div key={key} style={{ display: "flex", gap: 8, padding: "2px 0", opacity: 0.75 }}>
            <span style={{ color: "#cba6f7", minWidth: 90, flexShrink: 0 }}>{key}</span>
            <span style={{ color: "#fab387", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {formatPrimitive(value)}
            </span>
          </div>
        ))}
      </div>
    );
  }

  if (!wireState) return null;

  if (entries.length === 0) {
    return <div style={{ color: "#585b70", padding: "4px 0" }}>No fields</div>;
  }

  return (
    <>
      <div style={{ marginBottom: 8 }}>
        <div style={{ color: "#89b4fa", fontSize: 10, fontWeight: 700, marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>
          Key results
        </div>
        <div style={{ display: "grid", gap: 6 }}>
          {highlights.map(([key, value]) => (
            <button
              key={key}
              type="button"
              onClick={() => openInspector([key])}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                width: "100%",
                textAlign: "left",
                border: "1px solid #313244",
                background: "#181825",
                borderRadius: 8,
                padding: "7px 8px",
                color: "#cdd6f4",
                cursor: "pointer",
              }}
            >
              <span style={{ color: "#89b4fa", fontWeight: 700 }}>{key}</span>
              <span style={{ color: valueTone(value), minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {summarizeValue(value)}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ color: "#89b4fa", fontSize: 10, fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase" }}>
          All fields
        </div>
        <button
          type="button"
          onClick={() => openInspector([entries[0][0]])}
          style={{
            border: "1px solid #1d4ed8",
            background: "transparent",
            color: "#89b4fa",
            borderRadius: 6,
            padding: "3px 8px",
            fontSize: 10,
            cursor: "pointer",
          }}
        >
          Open inspector
        </button>
      </div>
      <div style={{ display: "grid", gap: 4 }}>
        {entries.slice(0, 6).map(([key, value]) => (
          <button
            key={key}
            type="button"
            onClick={() => openInspector([key])}
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(96px, 120px) 1fr auto",
              gap: 8,
              alignItems: "center",
              textAlign: "left",
              border: "1px solid #313244",
              background: "transparent",
              color: "#cdd6f4",
              borderRadius: 8,
              padding: "6px 8px",
              cursor: "pointer",
            }}
          >
            <span style={{ color: "#89b4fa", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{key}</span>
            <span style={{ color: valueTone(value), overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {Array.isArray(value) || isRecord(value) ? summarizeValue(value) : formatPrimitive(value)}
            </span>
            <span style={{ color: "#6c7086", fontSize: 10 }}>Inspect</span>
          </button>
        ))}
        {entries.length > 6 && (
          <div style={{ color: "#6c7086", fontSize: 10, paddingTop: 2 }}>
            …and {entries.length - 6} more field{entries.length - 6 === 1 ? "" : "s"} in the inspector
          </div>
        )}
      </div>

      {wireError && (
        <div style={{ color: "#f38ba8", marginTop: 8, fontSize: 10, wordBreak: "break-word" }}>
          ✗ {friendlyError(wireError)}
        </div>
      )}
    </>
  );
}
