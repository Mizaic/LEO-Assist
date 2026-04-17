"use client";

/**
 * SemanticSection -- renders a contextual summary card for the
 * currently-selected value in the ProbeInspectorDrawer
 * (Phase 6b-vi decomposition).
 *
 * Detects shape (long string, verification result, terminology row,
 * guidance rule row, generic structured rows) and picks the right
 * presentation. Returns null if no specific shape is recognised.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  formatPrimitive,
  getObjectColumns,
  isGuidanceRuleRow,
  isRecord,
  isTerminologyRow,
} from "./utils";

export interface SemanticSectionProps {
  fieldKey: string;
  value: unknown;
}

export function SemanticSection({ fieldKey, value }: SemanticSectionProps) {
  if (typeof value === "string" && value.length > 180) {
    return (
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: 12, background: "#f8fafc" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 8 }}>Long text</div>
        <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "#334155" }}>
          {value}
        </pre>
      </div>
    );
  }

  if (isRecord(value) && (fieldKey.includes("verification") || "is_verified" in value || "confidence" in value || "status" in value)) {
    const status = "is_verified" in value
      ? ((value.is_verified as boolean) ? "verified" : "not verified")
      : typeof value.status === "string"
        ? value.status
        : typeof value.result === "string"
          ? value.result
          : "unknown";
    const confidence = typeof value.confidence === "number"
      ? `${Math.round(value.confidence * 100)}%`
      : typeof value.score === "number"
        ? String(value.score)
        : null;
    const reasons = ["reason", "reasons", "errors", "issues"]
      .map((key) => value[key])
      .find((item) => Array.isArray(item) || typeof item === "string");

    return (
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: 12, background: "#f8fafc" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 8 }}>Verification summary</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
          <span style={{ background: "#dbeafe", color: "#1d4ed8", borderRadius: 999, padding: "3px 8px", fontSize: 12, fontWeight: 700 }}>
            {status}
          </span>
          {confidence && (
            <span style={{ background: "#dcfce7", color: "#166534", borderRadius: 999, padding: "3px 8px", fontSize: 12, fontWeight: 700 }}>
              confidence {confidence}
            </span>
          )}
        </div>
        {reasons && (
          <div style={{ color: "#475569", fontSize: 12 }}>
            {Array.isArray(reasons)
              ? (reasons as unknown[]).slice(0, 5).map((reason, index) => <div key={index}>• {formatPrimitive(reason)}</div>)
              : formatPrimitive(reasons)}
          </div>
        )}
      </div>
    );
  }

  if (Array.isArray(value) && value.every(isTerminologyRow)) {
    const rows = value.slice(0, 8) as Record<string, unknown>[];
    const columns = getObjectColumns(rows);
    return (
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, overflow: "hidden" }}>
        <div style={{ padding: 12, background: "#f8fafc", fontSize: 12, fontWeight: 700, color: "#0f172a" }}>
          Terminology matches
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ background: "#f8fafc" }}>
                {columns.map((column) => (
                  <th key={column} style={{ textAlign: "left", padding: "8px 10px", borderTop: "1px solid #e5e7eb", color: "#475569" }}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column} style={{ padding: "8px 10px", borderTop: "1px solid #e5e7eb", color: "#0f172a", verticalAlign: "top" }}>
                      {formatPrimitive(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (Array.isArray(value) && value.every(isGuidanceRuleRow)) {
    return (
      <div style={{ display: "grid", gap: 8 }}>
        {value.slice(0, 6).map((rule, index) => {
          const row = rule as Record<string, unknown>;
          return (
            <div key={index} style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: 12, background: "#f8fafc" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 6 }}>
                {formatPrimitive(row.title ?? row.name ?? row.rule ?? `Rule ${index + 1}`)}
              </div>
              {Boolean(row.condition) && <div style={{ fontSize: 12, color: "#334155", marginBottom: 4 }}><strong>When:</strong> {formatPrimitive(row.condition)}</div>}
              {Boolean(row.action ?? row.recommendation) && (
                <div style={{ fontSize: 12, color: "#334155" }}>
                  <strong>Then:</strong> {formatPrimitive(row.action ?? row.recommendation)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  if (Array.isArray(value) && value.every((item) => isRecord(item))) {
    const rows = value.slice(0, 8) as Record<string, unknown>[];
    const columns = getObjectColumns(rows);
    return (
      <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, overflow: "hidden" }}>
        <div style={{ padding: 12, background: "#f8fafc", fontSize: 12, fontWeight: 700, color: "#0f172a" }}>
          Structured items
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ background: "#f8fafc" }}>
                {columns.map((column) => (
                  <th key={column} style={{ textAlign: "left", padding: "8px 10px", borderTop: "1px solid #e5e7eb", color: "#475569" }}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column} style={{ padding: "8px 10px", borderTop: "1px solid #e5e7eb", color: "#0f172a", verticalAlign: "top" }}>
                      {formatPrimitive(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return null;
}
