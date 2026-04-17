"use client";

/**
 * "Wiring" tab body for the ProbeMonitor (Phase 6b-vi
 * decomposition).
 *
 * Compares the keys produced upstream against the keys the next step
 * expects, surfacing missing / matched / extra fields so reviewers
 * can spot wiring problems before running the full pipeline.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import { type PathSegment, summarizeValue } from "./utils";

interface ValidateTabProps {
  hasExpected: boolean;
  matched: string[];
  missing: string[];
  extra: string[];
  wireState: Record<string, unknown>;
  openInspector: (path: PathSegment[]) => void;
}

export function ProbeMonitorValidate({
  hasExpected,
  matched,
  missing,
  extra,
  wireState,
  openInspector,
}: ValidateTabProps) {
  return (
    <div style={{ paddingTop: 4 }}>
      {!hasExpected && (
        <div style={{ color: "#585b70", fontSize: 10 }}>
          The next step hasn&apos;t said what data it needs yet.
          Open its settings and set up what it reads.
        </div>
      )}

      {missing.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          <div style={{ color: "#f38ba8", fontWeight: 700, fontSize: 10, marginBottom: 3 }}>
            ✗ Missing — the next step needs these but they&apos;re not here
          </div>
          {missing.map((key) => (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: 6, padding: "1.5px 0" }}>
              <span style={{ color: "#f38ba8", fontSize: 11, width: 12 }}>✗</span>
              <span style={{ color: "#f38ba8", fontFamily: "monospace", fontSize: 11 }}>{key}</span>
            </div>
          ))}
        </div>
      )}

      {matched.length > 0 && (
        <div style={{ marginBottom: 6 }}>
          <div style={{ color: "#a6e3a1", fontWeight: 700, fontSize: 10, marginBottom: 3 }}>
            ✓ Connected — these are reaching the next step
          </div>
          {matched.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => openInspector([key])}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "3px 0",
                background: "transparent",
                border: "none",
                color: "inherit",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span style={{ color: "#a6e3a1", fontSize: 11, width: 12 }}>✓</span>
              <span style={{ color: "#a6e3a1", fontFamily: "monospace", fontSize: 11 }}>{key}</span>
              <span style={{ color: "#585b70", fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {summarizeValue(wireState[key])}
              </span>
            </button>
          ))}
        </div>
      )}

      {extra.length > 0 && (
        <div>
          <div style={{ color: "#6c7086", fontWeight: 700, fontSize: 10, marginBottom: 3 }}>
            ◌ Also here but the next step doesn&apos;t use them
          </div>
          {extra.slice(0, 8).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => openInspector([key])}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "3px 0",
                background: "transparent",
                border: "none",
                color: "inherit",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span style={{ color: "#585b70", fontSize: 11, width: 12 }}>◌</span>
              <span style={{ color: "#585b70", fontFamily: "monospace", fontSize: 11 }}>{key}</span>
              <span style={{ color: "#45475a", fontSize: 10 }}>{summarizeValue(wireState[key])}</span>
            </button>
          ))}
          {extra.length > 8 && (
            <div style={{ color: "#45475a", fontSize: 10 }}>…and {extra.length - 8} more</div>
          )}
        </div>
      )}
    </div>
  );
}
