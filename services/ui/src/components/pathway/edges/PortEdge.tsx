"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Drawer from "@mui/material/Drawer";
import { getSmoothStepPath, EdgeLabelRenderer, BaseEdge, type EdgeProps, useReactFlow } from "@xyflow/react";
import { usePipelineTest } from "../context/PipelineTestContext";
import { PROBE_STRATEGIES, TargetHint, getSubgraphLabel } from "./probeStrategies";

type PathSegment = string | number;
type SearchMatch = { path: PathSegment[]; preview: string };
type ProbeTab = "changes" | "data" | "validate";
type StateChangeKind = "added" | "removed" | "changed";
type PostProcessingLayerTrace = {
  layer_id: string;
  name: string;
  status: string;
  before_count: number;
  after_count: number;
  added_count: number;
  removed_count: number;
  updated_count: number;
  duration_ms: number;
  error?: string;
};
type StateChange = {
  kind: StateChangeKind;
  path: PathSegment[];
  beforeValue: unknown;
  afterValue: unknown;
};

const PRIORITY_KEYS = [
  "verification_result",
  "guidance_rules",
  "rules",
  "matches",
  "codes",
  "entities",
  "sentences",
  "errors",
  "is_verified",
  "status",
];
const MAX_DIFF_DEPTH = 4;
const MAX_DIFF_ENTRIES = 24;
const MAX_DIFF_CHILDREN = 18;

function probeKey(s: string, t: string) { return `${s}|${t}`; }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asPostProcessingTrace(value: unknown): PostProcessingLayerTrace[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is PostProcessingLayerTrace => {
    if (!isRecord(item)) return false;
    return typeof item.name === "string"
      && typeof item.status === "string"
      && typeof item.before_count === "number"
      && typeof item.after_count === "number";
  });
}

function safeStringify(value: unknown, spacing = 2): string {
  try {
    return JSON.stringify(value, null, spacing) ?? "null";
  } catch {
    return "[unserializable]";
  }
}

function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function formatPrimitive(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return truncate(value.replace(/\s+/g, " "), 120);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return truncate(safeStringify(value, 0), 120);
}

function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function friendlyError(raw: string): string {
  if (/invalid JSON/i.test(raw) || /JSONDecodeError/i.test(raw) || /json\.loads/i.test(raw))
    return "The AI replied with plain text instead of the expected format. The step carried on without it.";
  if (/timeout/i.test(raw))
    return "This step took too long and was stopped.";
  if (/connection|ECONNREFUSED|network/i.test(raw))
    return "Could not reach the service — it may be offline.";
  if (/ImportError|ModuleNotFound/i.test(raw))
    return "A required library is missing on the server.";
  if (raw.length > 120) return `${raw.slice(0, 100)}…`;
  return raw;
}

function summarizeValue(value: unknown): string {
  if (value === null || value === undefined) return "empty";
  if (typeof value === "string") return value.length > 140 ? `${value.length} chars` : truncate(value.replace(/\s+/g, " "), 90);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
  if (isRecord(value)) return `${Object.keys(value).length} field${Object.keys(value).length === 1 ? "" : "s"}`;
  return truncate(String(value), 90);
}

const PREVIEW_KEYS = ["text", "display", "name", "mention", "type", "label", "assertion", "code", "title", "semantic_tag", "lookup_term"];

/** Produce a short, human-readable preview for entity-like objects in diffs. */
function previewForChange(value: unknown, path: PathSegment[], maxParts = 2): string {
  if (value === null || value === undefined) return value === undefined ? "—" : "null";
  if (typeof value === "string") return truncate(value.replace(/\s+/g, " "), 60);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `${value.length} item${value.length === 1 ? "" : "s"}`;
  if (isRecord(value)) {
    const parts: string[] = [];
    for (const k of PREVIEW_KEYS) {
      if (k in value && value[k] != null) {
        const v = value[k];
        parts.push(typeof v === "string" ? truncate(v, 50) : String(v));
        if (parts.length >= maxParts) break;
      }
    }
    if (parts.length > 0) return parts.join(" · ");
    return `${Object.keys(value).length} field${Object.keys(value).length === 1 ? "" : "s"}`;
  }
  return truncate(String(value), 60);
}

/** Richer preview for added items — show more fields. */
function previewForAdded(value: unknown, path: PathSegment[]): string {
  return previewForChange(value, path, 4);
}

function valueTone(value: unknown): string {
  if (Array.isArray(value)) return "#fab387";
  if (typeof value === "boolean") return "#cba6f7";
  if (typeof value === "number") return "#a6e3a1";
  if (isRecord(value)) return "#89dceb";
  return "#cdd6f4";
}

function pathToString(path: PathSegment[]): string {
  return path.reduce<string>((acc, part, index) => {
    if (typeof part === "number") return `${acc}[${part}]`;
    if (index === 0) return String(part);
    return `${acc}.${String(part)}`;
  }, "");
}

function describePath(path: PathSegment[]): string {
  return pathToString(path) || "pipeline_state";
}

function getValueAtPath(root: unknown, path: PathSegment[]): unknown {
  let current: unknown = root;
  for (const part of path) {
    if (typeof part === "number") {
      if (!Array.isArray(current)) return undefined;
      current = current[part];
      continue;
    }
    if (!isRecord(current)) return undefined;
    current = current[part];
  }
  return current;
}

function valuesEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (typeof left !== typeof right) return false;
  if ((Array.isArray(left) && Array.isArray(right)) || (isRecord(left) && isRecord(right))) {
    return safeStringify(left, 0) === safeStringify(right, 0);
  }
  return false;
}

function collectStateChanges(
  beforeValue: unknown,
  afterValue: unknown,
  path: PathSegment[] = [],
  depth = 0,
  changes: StateChange[] = [],
): StateChange[] {
  if (changes.length >= MAX_DIFF_ENTRIES || valuesEqual(beforeValue, afterValue)) return changes;

  if (depth >= MAX_DIFF_DEPTH) {
    changes.push({ kind: "changed", path, beforeValue, afterValue });
    return changes;
  }

  if (Array.isArray(beforeValue) && Array.isArray(afterValue)) {
    const limit = Math.min(Math.max(beforeValue.length, afterValue.length), MAX_DIFF_CHILDREN);
    for (let index = 0; index < limit && changes.length < MAX_DIFF_ENTRIES; index += 1) {
      if (index >= beforeValue.length) {
        changes.push({ kind: "added", path: [...path, index], beforeValue: undefined, afterValue: afterValue[index] });
        continue;
      }
      if (index >= afterValue.length) {
        changes.push({ kind: "removed", path: [...path, index], beforeValue: beforeValue[index], afterValue: undefined });
        continue;
      }
      collectStateChanges(beforeValue[index], afterValue[index], [...path, index], depth + 1, changes);
    }
    if (changes.length === 0) {
      changes.push({ kind: "changed", path, beforeValue, afterValue });
    }
    return changes;
  }

  if (isRecord(beforeValue) && isRecord(afterValue)) {
    const keys = Array.from(new Set([...Object.keys(beforeValue), ...Object.keys(afterValue)])).sort();
    for (const key of keys.slice(0, MAX_DIFF_CHILDREN)) {
      if (changes.length >= MAX_DIFF_ENTRIES) break;
      if (!(key in beforeValue)) {
        changes.push({ kind: "added", path: [...path, key], beforeValue: undefined, afterValue: afterValue[key] });
        continue;
      }
      if (!(key in afterValue)) {
        changes.push({ kind: "removed", path: [...path, key], beforeValue: beforeValue[key], afterValue: undefined });
        continue;
      }
      collectStateChanges(beforeValue[key], afterValue[key], [...path, key], depth + 1, changes);
    }
    if (changes.length === 0) {
      changes.push({ kind: "changed", path, beforeValue, afterValue });
    }
    return changes;
  }

  if (beforeValue === undefined) {
    changes.push({ kind: "added", path, beforeValue, afterValue });
    return changes;
  }
  if (afterValue === undefined) {
    changes.push({ kind: "removed", path, beforeValue, afterValue });
    return changes;
  }

  changes.push({ kind: "changed", path, beforeValue, afterValue });
  return changes;
}

function resolveInspectablePath(root: unknown, path: PathSegment[]): PathSegment[] {
  for (let index = path.length; index > 0; index -= 1) {
    const candidate = path.slice(0, index);
    if (getValueAtPath(root, candidate) !== undefined) return candidate;
  }
  return [];
}

function toneForChange(kind: StateChangeKind): string {
  if (kind === "added") return "#a6e3a1";
  if (kind === "removed") return "#f38ba8";
  return "#89b4fa";
}

function labelForChange(kind: StateChangeKind): string {
  if (kind === "added") return "Added";
  if (kind === "removed") return "Removed";
  return "Updated";
}

function collectSearchMatches(value: unknown, query: string, path: PathSegment[] = [], matches: SearchMatch[] = []): SearchMatch[] {
  if (matches.length >= 40) return matches;
  const normalized = query.trim().toLowerCase();
  if (!normalized) return matches;

  const label = pathToString(path).toLowerCase();
  const preview = formatPrimitive(value).toLowerCase();
  if (path.length > 0 && (label.includes(normalized) || preview.includes(normalized))) {
    matches.push({ path, preview: formatPrimitive(value) });
  }

  if (Array.isArray(value)) {
    value.slice(0, 50).forEach((item, index) => collectSearchMatches(item, query, [...path, index], matches));
    return matches;
  }

  if (isRecord(value)) {
    Object.entries(value).slice(0, 100).forEach(([key, child]) => {
      if (matches.length >= 40) return;
      collectSearchMatches(child, query, [...path, key], matches);
    });
  }

  return matches;
}

function topLevelEntries(state: Record<string, unknown> | null): Array<[string, unknown]> {
  if (!state) return [];
  return Object.entries(state)
    .filter(([, value]) => value !== null && value !== undefined)
    .sort(([a], [b]) => {
      const ai = PRIORITY_KEYS.indexOf(a);
      const bi = PRIORITY_KEYS.indexOf(b);
      if (ai !== -1 && bi !== -1) return ai - bi;
      if (ai !== -1) return -1;
      if (bi !== -1) return 1;
      return a.localeCompare(b);
    });
}

function getMeaningfulHighlights(entries: Array<[string, unknown]>): Array<[string, unknown]> {
  const scored = entries.map(([key, value]) => {
    const preferred = PRIORITY_KEYS.includes(key) ? 100 : 0;
    const primitive = typeof value === "boolean" || typeof value === "number" ? 40 : 0;
    const shortString = typeof value === "string" && value.length <= 80 ? 30 : 0;
    const complex = Array.isArray(value) || isRecord(value) ? 20 : 0;
    return { key, value, score: preferred + primitive + shortString + complex };
  });

  return scored
    .sort((a, b) => b.score - a.score || a.key.localeCompare(b.key))
    .slice(0, 4)
    .map(({ key, value }) => [key, value]);
}

function getDefaultExpandedPaths(rootLabel: string, value: unknown): Set<string> {
  const expanded = new Set<string>([rootLabel]);
  if (Array.isArray(value)) {
    value.slice(0, 3).forEach((_, index) => expanded.add(pathToString([rootLabel, index])));
  } else if (isRecord(value)) {
    Object.keys(value).slice(0, 4).forEach((key) => expanded.add(pathToString([rootLabel, key])));
  }
  return expanded;
}

function expandAncestors(path: PathSegment[]): Set<string> {
  const expanded = new Set<string>();
  for (let i = 1; i <= path.length; i += 1) expanded.add(pathToString(path.slice(0, i)));
  return expanded;
}

function isTerminologyRow(value: unknown): boolean {
  return isRecord(value) && ("code" in value || "display" in value || "system" in value);
}

function isGuidanceRuleRow(value: unknown): boolean {
  return isRecord(value) && (
    "condition" in value
    || "action" in value
    || "recommendation" in value
    || "rule" in value
    || "title" in value
  );
}

function getObjectColumns(rows: Record<string, unknown>[]): string[] {
  const priority = ["code", "display", "system", "title", "name", "condition", "action", "recommendation", "status", "confidence"];
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return keys
    .sort((a, b) => {
      const ai = priority.indexOf(a);
      const bi = priority.indexOf(b);
      if (ai !== -1 && bi !== -1) return ai - bi;
      if (ai !== -1) return -1;
      if (bi !== -1) return 1;
      return a.localeCompare(b);
    })
    .slice(0, 5);
}

function TreeNode({
  label,
  value,
  path,
  depth,
  expandedPaths,
  selectedPath,
  onToggleExpand,
  onSelect,
}: {
  label: string;
  value: unknown;
  path: PathSegment[];
  depth: number;
  expandedPaths: Set<string>;
  selectedPath: string;
  onToggleExpand: (path: PathSegment[]) => void;
  onSelect: (path: PathSegment[]) => void;
}) {
  const nodePath = pathToString(path);
  const expandable = Array.isArray(value) || isRecord(value);
  const isExpanded = expandedPaths.has(nodePath);
  const isSelected = selectedPath === nodePath;
  const children = Array.isArray(value)
    ? value.map((child, index) => [String(index), child] as const)
    : isRecord(value)
      ? Object.entries(value)
      : [];

  return (
    <div style={{ marginLeft: depth * 14 }}>
      <div
        onClick={() => onSelect(path)}
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 6,
          padding: "4px 6px",
          borderRadius: 6,
          cursor: "pointer",
          background: isSelected ? "#1d4ed820" : "transparent",
          border: isSelected ? "1px solid #1d4ed8" : "1px solid transparent",
        }}
      >
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            if (expandable) onToggleExpand(path);
          }}
          style={{
            width: 18,
            border: "none",
            background: "transparent",
            color: "#6b7280",
            cursor: expandable ? "pointer" : "default",
            padding: 0,
            textAlign: "center",
          }}
        >
          {expandable ? (isExpanded ? "▾" : "▸") : ""}
        </button>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            <span style={{ color: "#1d4ed8", fontWeight: 700, fontFamily: "monospace", fontSize: 12 }}>
              {Array.isArray(value) && /^\d+$/.test(label) ? `[${label}]` : label}
            </span>
            <span style={{ color: "#6b7280", fontSize: 12, minWidth: 0 }}>
              {expandable ? summarizeValue(value) : formatPrimitive(value)}
            </span>
          </div>
        </div>
      </div>
      {expandable && isExpanded && (
        <div>
          {children.slice(0, 25).map(([childLabel, childValue]) => (
            <TreeNode
              key={`${nodePath}:${childLabel}`}
              label={childLabel}
              value={childValue}
              path={[...path, Array.isArray(value) ? Number(childLabel) : childLabel]}
              depth={depth + 1}
              expandedPaths={expandedPaths}
              selectedPath={selectedPath}
              onToggleExpand={onToggleExpand}
              onSelect={onSelect}
            />
          ))}
          {children.length > 25 && (
            <div style={{ marginLeft: (depth + 1) * 14, color: "#6b7280", fontSize: 12, padding: "4px 6px" }}>
              …{children.length - 25} more item{children.length - 25 === 1 ? "" : "s"}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SemanticSection({ fieldKey, value }: { fieldKey: string; value: unknown }) {
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

function ProbeInspectorDrawer({
  open,
  onClose,
  wireState,
  selectedPath,
  onSelectPath,
}: {
  open: boolean;
  onClose: () => void;
  wireState: Record<string, unknown>;
  selectedPath: PathSegment[];
  onSelectPath: (path: PathSegment[]) => void;
}) {
  const [search, setSearch] = useState("");
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(getDefaultExpandedPaths(selectedPath[0] as string, getValueAtPath(wireState, selectedPath)));
  const topEntries = useMemo(() => topLevelEntries(wireState), [wireState]);
  const selectedValue = getValueAtPath(wireState, selectedPath);
  const selectedKey = String(selectedPath[0] ?? "");
  const selectedPathString = pathToString(selectedPath);
  const matches = useMemo(() => collectSearchMatches(wireState, search), [wireState, search]);

  const toggleExpand = (path: PathSegment[]) => {
    const key = pathToString(path);
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const selectAndExpand = (path: PathSegment[]) => {
    onSelectPath(path);
    setExpandedPaths((prev) => new Set([...prev, ...expandAncestors(path)]));
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: 620, maxWidth: "92vw" } }}
    >
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <div style={{ padding: 16, borderBottom: "1px solid #e5e7eb", background: "#f8fafc" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a" }}>Probe inspector</div>
              <div style={{ fontSize: 12, color: "#64748b", fontFamily: "monospace" }}>{selectedPathString}</div>
            </div>
            <button
              type="button"
              onClick={onClose}
              style={{ border: "none", background: "transparent", fontSize: 18, cursor: "pointer", color: "#ef4444" }}
            >
              ✕
            </button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
            {topEntries.map(([key, value]) => {
              const active = selectedKey === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    onSelectPath([key]);
                    setExpandedPaths(getDefaultExpandedPaths(key, value));
                  }}
                  style={{
                    borderRadius: 999,
                    border: active ? "1px solid #2563eb" : "1px solid #cbd5e1",
                    background: active ? "#dbeafe" : "#fff",
                    color: active ? "#1d4ed8" : "#334155",
                    padding: "5px 10px",
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {key} · {summarizeValue(value)}
                </button>
              );
            })}
          </div>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search nested keys or values"
            style={{
              width: "100%",
              marginTop: 12,
              borderRadius: 8,
              border: "1px solid #cbd5e1",
              padding: "8px 10px",
              fontSize: 13,
            }}
          />
          {search.trim() && matches.length > 0 && (
            <div style={{ marginTop: 10, display: "grid", gap: 6, maxHeight: 140, overflowY: "auto" }}>
              {matches.slice(0, 8).map((match) => (
                <button
                  key={pathToString(match.path)}
                  type="button"
                  onClick={() => selectAndExpand(match.path)}
                  style={{
                    textAlign: "left",
                    border: "1px solid #e5e7eb",
                    background: "#fff",
                    borderRadius: 8,
                    padding: "7px 9px",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ fontFamily: "monospace", fontSize: 12, color: "#1d4ed8" }}>{pathToString(match.path)}</div>
                  <div style={{ fontSize: 12, color: "#64748b" }}>{match.preview}</div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "grid", gap: 14 }}>
          {selectedValue === undefined ? (
            <div style={{ color: "#64748b", fontSize: 13 }}>Nothing selected.</div>
          ) : (
            <>
              <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: 12 }}>
                <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>Selected value</div>
                <div style={{ fontSize: 14, color: "#0f172a", fontWeight: 700, marginBottom: 4 }}>{selectedPathString}</div>
                <div style={{ fontSize: 12, color: "#475569" }}>{summarizeValue(selectedValue)}</div>
              </div>

              <SemanticSection fieldKey={selectedKey} value={selectedValue} />

              <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#0f172a", marginBottom: 10 }}>Tree view</div>
                <TreeNode
                  label={selectedKey}
                  value={selectedValue}
                  path={[selectedKey]}
                  depth={0}
                  expandedPaths={expandedPaths}
                  selectedPath={selectedPathString}
                  onToggleExpand={toggleExpand}
                  onSelect={selectAndExpand}
                />
              </div>

              <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: 12, background: "#0f172a" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#cbd5e1", marginBottom: 10 }}>Raw JSON</div>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "#e2e8f0" }}>
                  {safeStringify(selectedValue, 2)}
                </pre>
              </div>
            </>
          )}
        </div>
      </div>
    </Drawer>
  );
}

interface MonitorProps {
  sourceId: string;
  targetId: string;
  x: number;
  y: number;
  onClose: () => void;
}

function ProbeMonitor({ sourceId, targetId, x, y, onClose }: MonitorProps) {
  const { testTrace, isTestRunning, runningStepId, haltedNodeId, partialRunEndNodeId, runToStep, getNodeExpectedInputs } = usePipelineTest();
  const [tab, setTab] = useState<ProbeTab>("changes");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedPath, setSelectedPath] = useState<PathSegment[]>([]);
  const [showAllChanges, setShowAllChanges] = useState(false);

  // Drag-to-reposition state — lets users move overlapping probes apart
  const [dragOffset, setDragOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isRaised, setIsRaised] = useState(false);
  const dragStart = useRef<{ mx: number; my: number; ox: number; oy: number } | null>(null);

  const handleDragMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    dragStart.current = { mx: e.clientX, my: e.clientY, ox: dragOffset.x, oy: dragOffset.y };
    setIsRaised(true);
    const onMove = (ev: MouseEvent) => {
      if (!dragStart.current) return;
      setDragOffset({
        x: dragStart.current.ox + ev.clientX - dragStart.current.mx,
        y: dragStart.current.oy + ev.clientY - dragStart.current.my,
      });
    };
    const onUp = () => {
      dragStart.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  const sourceTrace = testTrace?.[sourceId] ?? null;
  const targetTrace = testTrace?.[targetId] ?? null;
  const isInjectedEdge = !sourceTrace && Boolean(targetTrace);
  const wireState: Record<string, unknown> | null = sourceTrace
    ? sourceTrace.output_state
    : (targetTrace ? targetTrace.input_state : null);
  const postProcessingTrace = asPostProcessingTrace(wireState?.post_processing_trace);
  const { getNode } = useReactFlow();
  const sourceSubgraphId = sourceTrace?.subgraph_id
    ?? ((getNode(sourceId)?.data as Record<string, unknown>)?.subgraphId as string)
    ?? "";
  const targetSubgraphId = targetTrace?.subgraph_id
    ?? ((getNode(targetId)?.data as Record<string, unknown>)?.subgraphId as string)
    ?? "";
  const strategy = PROBE_STRATEGIES[sourceSubgraphId] ?? null;
  const sourceLabel = sourceTrace?.label ?? getSubgraphLabel(sourceSubgraphId);
  const targetLabel = targetTrace?.label ?? getSubgraphLabel(targetSubgraphId);
  const wireStatus = sourceTrace?.status ?? (targetTrace ? "injected" : null);
  const wireDuration = sourceTrace?.duration_ms ?? null;
  const wireLabel = sourceTrace?.label ?? (isInjectedEdge ? `Injected into ${targetTrace?.label ?? targetId}` : null);
  const wireError = sourceTrace?.error ?? null;

  const isIntercepting = isTestRunning && (runningStepId === sourceId || runningStepId === targetId);
  const isPending = isTestRunning && !wireState && !isIntercepting;
  const entries = topLevelEntries(wireState);
  const highlights = getMeaningfulHighlights(entries);
  const stepChanges = useMemo(
    () => (
      sourceTrace
        ? collectStateChanges(sourceTrace.input_state, sourceTrace.output_state)
            .filter((change) => String(change.path[0] ?? "") !== "post_processing_trace")
        : []
    ),
    [sourceTrace],
  );
  const hadRetries = useMemo(() => {
    const attempts = sourceTrace?.output_state?.extraction_attempts;
    return Array.isArray(attempts) && (attempts as unknown[]).length > 1;
  }, [sourceTrace]);
  const hasSoftErrors = wireStatus === "completed" && stepChanges.some(
    (c) => String(c.path[0] ?? "").toLowerCase().includes("error") && c.kind === "added",
  );
  const sourceOutputEntries = useMemo(
    () => (sourceTrace ? topLevelEntries(sourceTrace.output_state) : []),
    [sourceTrace],
  );
  const changeCounts = useMemo(
    () => stepChanges.reduce(
      (summary, change) => {
        summary[change.kind] += 1;
        return summary;
      },
      { added: 0, changed: 0, removed: 0 },
    ),
    [stepChanges],
  );
  const changedRoots = useMemo(
    () => Array.from(new Set(stepChanges.map((change) => String(change.path[0] ?? "pipeline_state")))),
    [stepChanges],
  );
  const arrayCountDeltas = useMemo(() => {
    if (!sourceTrace) return [];
    const deltas: Array<{ key: string; before: number; after: number }> = [];
    const inp = sourceTrace.input_state;
    const out = sourceTrace.output_state;
    const keys = new Set([...Object.keys(inp ?? {}), ...Object.keys(out ?? {})]);
    for (const key of keys) {
      const b = inp?.[key];
      const a = out?.[key];
      if (Array.isArray(b) && Array.isArray(a) && b.length !== a.length) {
        deltas.push({ key, before: b.length, after: a.length });
      }
    }
    return deltas;
  }, [sourceTrace]);

  const produced = wireState ? Object.keys(wireState) : [];
  const expected = getNodeExpectedInputs(targetId);
  const matched = expected.filter((key) => produced.includes(key));
  const missing = expected.filter((key) => !produced.includes(key));
  const extra = produced.filter((key) => !expected.includes(key));
  const hasExpected = expected.length > 0;

  // "halted" = the source step ran but its quality gate stopped the pipeline
  const isSourceHalted = sourceTrace?.status === "halted";
  // "not reached (quality gate)" = a run finished but upstream halted before this edge
  const isEdgeNotReached = !isTestRunning && testTrace !== null && !sourceTrace && !!haltedNodeId;
  // "partial run end" = this edge's source was the last step in a "Run to here" partial run
  const isPartialRunEnd = !isTestRunning && sourceId === partialRunEndNodeId && !!sourceTrace;
  // "not reached (partial run)" = this edge's source was beyond the partial run boundary
  const isNotReachedByPartialRun = !isTestRunning && testTrace !== null && !sourceTrace && !!partialRunEndNodeId && !haltedNodeId;

  const statusColor = isSourceHalted
    ? "#f38ba8"
    : (wireStatus === "completed" || wireStatus === "injected")
      ? "#a6e3a1"
      : wireStatus === "error"
        ? "#f38ba8"
        : "#89b4fa";

  const openInspector = (path: PathSegment[]) => {
    setSelectedPath(path);
    setDrawerOpen(true);
  };

  const hadSourceTraceRef = useRef(false);
  useEffect(() => {
    if (!sourceTrace && tab === "changes") setTab("data");
    if (sourceTrace && !hadSourceTraceRef.current) {
      hadSourceTraceRef.current = true;
      setTab("changes"); // "What changed" is the default when data first arrives
    }
  }, [sourceTrace, tab]);

  const availableTabs: ProbeTab[] = sourceTrace ? ["changes", "data", "validate"] : ["data", "validate"];
  const changeSummaryBits = [
    changeCounts.added > 0 ? `added ${pluralize(changeCounts.added, "thing")}` : null,
    changeCounts.changed > 0 ? `changed ${pluralize(changeCounts.changed, "thing")}` : null,
    changeCounts.removed > 0 ? `removed ${pluralize(changeCounts.removed, "thing")}` : null,
  ].filter(Boolean);

  return (
    <>
      <div
        className="nodrag nopan"
        style={{
          position: "absolute",
          transform: `translate(-50%, 0) translate(${x + dragOffset.x}px, ${y + 18 + dragOffset.y}px)`,
          pointerEvents: "all",
          background: "#1e1e2e",
          color: "#cdd6f4",
          borderRadius: 10,
          border: `2px solid ${statusColor}`,
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
          fontSize: 11,
          minWidth: 520,
          maxWidth: 680,
          boxShadow: isRaised ? "0 16px 48px rgba(0,0,0,0.85)" : "0 8px 32px rgba(0,0,0,0.6)",
          zIndex: isRaised ? 1100 : 1000,
          overflow: "hidden",
          userSelect: dragStart.current ? "none" : "auto",
        }}
      >
        <div
          onMouseDown={handleDragMouseDown}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "5px 10px",
            background: "#313244",
            borderBottom: `1px solid ${statusColor}40`,
            cursor: dragStart.current ? "grabbing" : "grab",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ color: "#45475a", fontSize: 12, letterSpacing: 1 }}>⠿</span>
            <span style={{ fontSize: 13 }}>{strategy?.icon ?? "⊕"}</span>
            <span style={{ color: "#89b4fa", fontWeight: 700, fontSize: 10, letterSpacing: "0.05em" }}>PROBE</span>
            <span style={{ color: "#6c7086", fontSize: 10 }}>{sourceLabel || sourceId} → {targetLabel || targetId}</span>
          </span>
          <span onMouseDown={(e) => e.stopPropagation()} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <button
              onClick={() => runToStep(sourceId)}
              disabled={isTestRunning}
              title="Run the pipeline only up to this step"
              style={{
                background: isTestRunning ? "#45475a" : "#1d4ed8",
                border: "none",
                borderRadius: 4,
                color: isTestRunning ? "#6c7086" : "#fff",
                cursor: isTestRunning ? "default" : "pointer",
                fontSize: 10,
                fontWeight: 700,
                padding: "2px 7px",
                letterSpacing: "0.03em",
              }}
            >
              {isTestRunning ? "running…" : "▶ Run to here"}
            </button>
            <button
              onClick={onClose}
              style={{
                background: "none",
                border: "none",
                color: "#f38ba8",
                cursor: "pointer",
                fontSize: 13,
                lineHeight: 1,
                padding: 0,
              }}
            >
              ✕
            </button>
          </span>
        </div>

        {/* ── Pipeline halted at source node ─────────────────────────── */}
        {isSourceHalted && (
          <div style={{
            padding: "10px 12px",
            background: "#2d1b1b",
            borderBottom: "1px solid #f38ba840",
          }}>
            <div style={{ color: "#f38ba8", fontWeight: 700, fontSize: 11, marginBottom: 6 }}>
              🛑 Pipeline stopped here
            </div>
            <div style={{ color: "#cdd6f4", fontSize: 10, lineHeight: 1.5 }}>
              This step ran but the quality gate decided the results weren't good enough
              to continue. Check the probe details above to see what failed, then fix the
              issue and run again.
            </div>
            {((sourceTrace as unknown as { halt_reason?: string } | null)?.halt_reason === "verification_failed") && (
              <div style={{ color: "#fab387", fontSize: 10, marginTop: 6 }}>
                Verification found issues with the extracted entities. Downstream steps
                (terminology coding, saving, etc.) were not run.
              </div>
            )}
          </div>
        )}

        {/* ── Partial run ended at this step ───────────────────────── */}
        {isPartialRunEnd && (
          <div style={{
            padding: "10px 12px",
            background: "#1a2a1a",
            borderBottom: "1px solid #a6e3a140",
          }}>
            <div style={{ color: "#a6e3a1", fontWeight: 700, fontSize: 11, marginBottom: 4 }}>
              ▶ Partial run stopped here
            </div>
            <div style={{ color: "#a6adc8", fontSize: 10, lineHeight: 1.5 }}>
              This is as far as the last "Run to here" went. Steps to the right
              were not run. Click <span style={{ color: "#89b4fa" }}>Run all steps</span> to
              execute the full pipeline.
            </div>
          </div>
        )}

        {/* ── Edge was never reached (upstream halt) ──────────────── */}
        {isEdgeNotReached && (
          <div style={{
            padding: "14px 12px",
            background: "#1a1a2e",
            borderBottom: "1px solid #313244",
          }}>
            <div style={{ color: "#6c7086", fontWeight: 700, fontSize: 11, marginBottom: 6 }}>
              ⏹ Pipeline stopped before reaching this step
            </div>
            <div style={{ color: "#45475a", fontSize: 10, lineHeight: 1.5 }}>
              A quality gate earlier in the pipeline halted the run. This step never
              executed. Fix the problem on the node marked 🛑 red and run again.
            </div>
          </div>
        )}

        {/* ── Step not included in partial run ─────────────────────── */}
        {isNotReachedByPartialRun && (
          <div style={{
            padding: "14px 12px",
            background: "#1a1a2e",
            borderBottom: "1px solid #313244",
          }}>
            <div style={{ color: "#6c7086", fontWeight: 700, fontSize: 11, marginBottom: 6 }}>
              ⏹ Not run — beyond the partial run boundary
            </div>
            <div style={{ color: "#45475a", fontSize: 10, lineHeight: 1.5 }}>
              The last run used "Run to here" and stopped before this step.
              Click <span style={{ color: "#89b4fa" }}>Run all steps</span> to include it.
            </div>
          </div>
        )}

        {!isEdgeNotReached && wireState && (
          <div style={{
            display: "flex",
            gap: 0,
            background: "#181825",
            borderBottom: "1px solid #313244",
          }}>
            {availableTabs.map((section) => (
              <button
                key={section}
                onClick={() => setTab(section)}
                style={{
                  background: "none",
                  border: "none",
                  borderBottom: tab === section ? `2px solid ${statusColor}` : "2px solid transparent",
                  color: tab === section ? statusColor : "#6c7086",
                  cursor: "pointer",
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "3px 10px",
                  letterSpacing: "0.04em",
                  textTransform: "uppercase",
                }}
              >
                {section === "changes"
                  ? `What's different${stepChanges.length > 0 ? ` (${stepChanges.length})` : ""}`
                  : section === "data"
                    ? (isInjectedEdge ? "Data going in" : "Results")
                    : `Wiring ${missing.length > 0 ? "⚠" : matched.length > 0 ? "✓" : ""}`}
              </button>
            ))}
          </div>
        )}

        {!isEdgeNotReached && wireState && (
          <div style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 10,
            padding: "4px 10px",
            background: "#181825",
            fontSize: 10,
            borderBottom: "1px solid #313244",
          }}>
            <span style={{ color: statusColor, fontWeight: 700 }}>
              {isSourceHalted ? "🛑 Halted" : wireStatus === "injected" ? "⬇ Data fed in" : wireStatus === "completed" ? "✓ Worked" : "✗ Problem"}
            </span>
            {wireDuration !== null && (
              <span style={{ color: "#6c7086" }}>
                took {wireDuration < 1000 ? `${wireDuration}ms` : `${(wireDuration / 1000).toFixed(1)}s`}
              </span>
            )}
            {sourceTrace && changeSummaryBits.length > 0 && (
              <span style={{ color: "#6c7086" }}>
                {changeSummaryBits.join(", ")}
              </span>
            )}
            <span style={{ color: "#6c7086" }}>{entries.length} field{entries.length === 1 ? "" : "s"} total</span>
            {wireLabel && <span style={{ color: "#6c7086" }}>{wireLabel}</span>}
          </div>
        )}

        <div style={{ padding: "8px 10px", maxHeight: "60vh", overflowY: "auto" }}>
          {tab === "changes" && sourceTrace && (
            <div style={{ display: "grid", gap: 8 }}>
              <div style={{ border: "1px solid #313244", borderRadius: 8, padding: "8px 9px", background: "#181825" }}>
                <div style={{ color: "#89b4fa", fontSize: 10, fontWeight: 700, marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                  {strategy ? `${strategy.icon} What happened` : "What happened"}
                </div>
                <div style={{ color: "#cdd6f4", fontSize: strategy ? 12 : 11, lineHeight: 1.45 }}>
                  {strategy
                    ? strategy.headline(sourceTrace.output_state ?? {}, sourceTrace.input_state ?? {})
                    : stepChanges.length === 0
                      ? "Nothing changed — data passed straight through."
                      : `This step ${changeSummaryBits.join(", ")} in ${pluralize(changedRoots.length, "area")}.`}
                </div>
                {arrayCountDeltas.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6, fontSize: 10 }}>
                    {arrayCountDeltas.map(({ key, before, after }) => (
                      <span key={key} style={{ color: "#fab387", fontFamily: "monospace" }}>
                        {key}: {before} → {after}
                      </span>
                    ))}
                  </div>
                )}
                {!strategy && changedRoots.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                    {changedRoots.slice(0, 6).map((root) => (
                      <button
                        key={root}
                        type="button"
                        onClick={() => openInspector([root])}
                        style={{
                          borderRadius: 999,
                          border: "1px solid #313244",
                          background: "#11111b",
                          color: "#89b4fa",
                          padding: "3px 8px",
                          fontSize: 10,
                          cursor: "pointer",
                        }}
                      >
                        {root}
                      </button>
                    ))}
                    {changedRoots.length > 6 && (
                      <span style={{ color: "#6c7086", fontSize: 10, alignSelf: "center" }}>
                        +{changedRoots.length - 6} more
                      </span>
                    )}
                  </div>
                )}
              </div>

              {strategy && sourceTrace && (
                <div style={{ border: "1px solid #313244", borderRadius: 8, padding: "8px 9px", background: "#181825" }}>
                  {strategy.Detail({ output: sourceTrace.output_state ?? {}, input: sourceTrace.input_state ?? {}, openInspector })}
                </div>
              )}

              {!strategy && sourceOutputEntries.length > 0 && (
                <div style={{ border: "1px solid #313244", borderRadius: 8, padding: "8px 9px", background: "#181825" }}>
                  <div style={{ color: "#89b4fa", fontSize: 10, fontWeight: 700, marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                    What this step produced
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                    {sourceOutputEntries.slice(0, 12).map(([key, value]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => openInspector([key])}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 6,
                          width: "100%",
                          textAlign: "left",
                          border: key === "verification_result" ? "1px solid #a6adc8" : "1px solid #313244",
                          background: "#11111b",
                          borderRadius: 6,
                          padding: "4px 7px",
                          color: "#cdd6f4",
                          cursor: "pointer",
                        }}
                      >
                        <span style={{ color: key === "verification_result" ? "#f9e2af" : "#89b4fa", fontFamily: "monospace", fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {key}
                        </span>
                        <span style={{ color: valueTone(value), fontSize: 10, flexShrink: 0 }}>
                          {summarizeValue(value)}
                        </span>
                      </button>
                    ))}
                  </div>
                  {sourceOutputEntries.length > 12 && (
                    <div style={{ color: "#6c7086", fontSize: 10, marginTop: 4 }}>
                      …and {sourceOutputEntries.length - 12} more
                    </div>
                  )}
                </div>
              )}

              {!strategy && postProcessingTrace.length > 0 && (
                <div style={{ border: "1px solid #313244", borderRadius: 8, overflow: "hidden", background: "#181825" }}>
                  <div style={{ color: "#89b4fa", fontSize: 10, fontWeight: 700, padding: "7px 9px", letterSpacing: "0.04em", textTransform: "uppercase", borderBottom: "1px solid #313244" }}>
                    Did each clean-up step run?
                  </div>
                  {postProcessingTrace.map((layer, i) => {
                    const isSkipped = layer.status === "skipped";
                    const isError = layer.status === "error";
                    const statusColor = isError ? "#f38ba8" : isSkipped ? "#6c7086" : "#a6e3a1";
                    const statusIcon = isError ? "✗" : isSkipped ? "○" : "✓";
                    const statusLabel = isError ? "Error" : isSkipped ? "Skipped" : "Ran OK";
                    const delta = layer.after_count - layer.before_count;
                    const hasChanges = layer.added_count > 0 || layer.removed_count > 0 || layer.updated_count > 0;
                    const changeParts: string[] = [];
                    if (layer.added_count > 0) changeParts.push(`+${layer.added_count} added`);
                    if (layer.removed_count > 0) changeParts.push(`−${layer.removed_count} removed`);
                    if (layer.updated_count > 0) changeParts.push(`${layer.updated_count} updated`);
                    const changeText = isSkipped ? "—" : hasChanges ? changeParts.join(", ") : "no change";
                    const changeColor = delta < 0 ? "#f38ba8" : delta > 0 ? "#a6e3a1" : "#6c7086";
                    return (
                      <div
                        key={layer.layer_id}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "1fr auto auto",
                          alignItems: "center",
                          gap: 10,
                          padding: "5px 9px",
                          borderBottom: i < postProcessingTrace.length - 1 ? "1px solid #31324440" : "none",
                          opacity: isSkipped ? 0.6 : 1,
                        }}
                      >
                        <span style={{ color: "#cdd6f4", fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {layer.name}
                        </span>
                        <span style={{ color: changeColor, fontSize: 10, whiteSpace: "nowrap" }}>
                          {changeText}
                        </span>
                        <span style={{ color: statusColor, fontSize: 10, fontWeight: 700, whiteSpace: "nowrap", minWidth: 60, textAlign: "right" }}>
                          {statusIcon} {statusLabel}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {targetSubgraphId && <TargetHint targetSubgraphId={targetSubgraphId} producedKeys={produced} />}

              {strategy && stepChanges.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowAllChanges(prev => !prev)}
                  style={{
                    background: "none", border: "none", color: "#6c7086",
                    cursor: "pointer", fontSize: 10, textAlign: "left", padding: "4px 0",
                  }}
                >
                  {showAllChanges ? "▾ Hide" : "▸ Show"} {stepChanges.length} individual changes
                </button>
              )}

              {(!strategy || showAllChanges) && (stepChanges.length === 0 ? (
                <div style={{ color: "#6c7086", fontSize: 11 }}>
                  Everything stayed the same — no differences found.
                </div>
              ) : (
                <div style={{ display: "grid", gap: 3 }}>
                  {hasSoftErrors && (
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "5px 7px",
                      borderRadius: 6,
                      background: "#fab38712",
                      border: "1px solid #fab38740",
                      fontSize: 10,
                      color: "#fab387",
                    }}>
                      <span>{hadRetries ? "↺" : "⚠"}</span>
                      <span>
                        {hadRetries
                          ? "A retry succeeded — the ⚠ error rows below are from earlier failed attempts."
                          : "These errors are non-fatal — the step logged them and carried on."}
                      </span>
                    </div>
                  )}
                  {stepChanges.map((change, index) => {
                    const inspectPath = resolveInspectablePath(sourceTrace.output_state, change.path);
                    const canInspect = inspectPath.length > 0;
                    const isErrorField = String(change.path[0] ?? "").toLowerCase().includes("error");
                    const isSoftError = isErrorField && change.kind === "added" && wireStatus === "completed";
                    const rawBefore = change.kind === "added" ? "—" : previewForChange(change.beforeValue, change.path, 2);
                    const rawAfter = change.kind === "removed" ? "—" : previewForAdded(change.afterValue, change.path);
                    const beforePreview = isErrorField ? friendlyError(rawBefore) : rawBefore;
                    const afterPreview = isErrorField ? friendlyError(rawAfter) : rawAfter;
                    const rowLabel = isSoftError ? "⚠" : labelForChange(change.kind);
                    const rowLabelColor = isSoftError ? "#fab387" : toneForChange(change.kind);
                    return (
                      <button
                        key={`${describePath(change.path)}:${index}`}
                        type="button"
                        onClick={() => { if (canInspect) openInspector(inspectPath); }}
                        disabled={!canInspect}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "54px 1fr auto",
                          gap: 6,
                          alignItems: "baseline",
                          width: "100%",
                          textAlign: "left",
                          border: "none",
                          borderBottom: "1px solid #31324440",
                          background: "transparent",
                          padding: "4px 4px",
                          color: "#cdd6f4",
                          cursor: canInspect ? "pointer" : "default",
                          opacity: canInspect ? 1 : 0.7,
                        }}
                      >
                        <span style={{ fontSize: 9, fontWeight: 700, color: rowLabelColor }}>
                          {rowLabel}
                        </span>
                        <span style={{ minWidth: 0 }}>
                          <span style={{ color: "#89b4fa", fontFamily: "monospace", fontSize: 10 }}>
                            {describePath(change.path)}
                          </span>
                          {" "}
                          <span style={{ color: isSoftError ? "#fab38799" : "#6c7086", fontSize: 10 }}>
                            {change.kind === "removed"
                              ? beforePreview
                              : change.kind === "added"
                                ? afterPreview
                                : `${beforePreview} → ${afterPreview}`}
                          </span>
                        </span>
                        {canInspect && <span style={{ color: "#45475a", fontSize: 9 }}>→</span>}
                      </button>
                    );
                  })}
                </div>
              ))}

              {wireState && hasExpected && (
                <div style={{ borderTop: "1px solid #313244", padding: "6px 4px 2px", marginTop: 6, fontSize: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
                  <span style={{ color: "#89b4fa", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" }}>Wiring</span>
                  {matched.length > 0 && <span style={{ color: "#a6e3a1" }}>✓ {matched.join(", ")} reaching next step</span>}
                  {missing.length > 0 && <span style={{ color: "#f38ba8" }}>✗ Missing: {missing.join(", ")}</span>}
                  {extra.length > 0 && <span style={{ color: "#6c7086" }}>also has: {extra.slice(0, 4).join(", ")}{extra.length > 4 ? ` +${extra.length - 4}` : ""}</span>}
                </div>
              )}
            </div>
          )}

          {tab === "data" && !isTestRunning && !wireState && !isEdgeNotReached && !isNotReachedByPartialRun && (
            <div style={{ color: "#585b70", padding: "6px 0", textAlign: "center" }}>
              No results yet — click <span style={{ color: "#cba6f7" }}>Run to here</span> to see what this step does
            </div>
          )}

          {tab === "data" && isPending && (
            <div style={{ color: "#89b4fa", padding: "4px 0" }}>
              <span style={{ animation: "probePulse 1s ease-in-out infinite", display: "inline-block" }}>◌</span>
              {" "}queued…
            </div>
          )}

          {tab === "data" && isIntercepting && (
            <div style={{ padding: "4px 0" }}>
              <div style={{ color: "#89dceb", marginBottom: 6 }}>
                <span style={{ display: "inline-block", animation: "probeSpin 0.8s linear infinite", marginRight: 6 }}>⟳</span>
                intercepting live data…
              </div>
              {Object.entries(testTrace?.[runningStepId ?? ""]?.input_state ?? {}).slice(0, 5).map(([key, value]) => (
                <div key={key} style={{ display: "flex", gap: 8, padding: "2px 0", opacity: 0.75 }}>
                  <span style={{ color: "#cba6f7", minWidth: 90, flexShrink: 0 }}>{key}</span>
                  <span style={{ color: "#fab387", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {formatPrimitive(value)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {tab === "data" && wireState && entries.length === 0 && (
            <div style={{ color: "#585b70", padding: "4px 0" }}>No fields</div>
          )}

          {tab === "data" && wireState && entries.length > 0 && (
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
            </>
          )}

          {tab === "data" && wireError && (
            <div style={{ color: "#f38ba8", marginTop: 8, fontSize: 10, wordBreak: "break-word" }}>
              ✗ {friendlyError(wireError)}
            </div>
          )}

          {tab === "validate" && wireState && (
            <div style={{ paddingTop: 4 }}>
              {!hasExpected && (
                <div style={{ color: "#585b70", fontSize: 10 }}>
                  The next step hasn't said what data it needs yet.
                  Open its settings and set up what it reads.
                </div>
              )}

              {missing.length > 0 && (
                <div style={{ marginBottom: 6 }}>
                  <div style={{ color: "#f38ba8", fontWeight: 700, fontSize: 10, marginBottom: 3 }}>
                    ✗ Missing — the next step needs these but they're not here
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
                    ◌ Also here but the next step doesn't use them
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
          )}
        </div>

        <style>{`
          @keyframes probeSpin  { to { transform: rotate(360deg); } }
          @keyframes probePulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
        `}</style>
      </div>

      {wireState && selectedPath.length > 0 && (
        <ProbeInspectorDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          wireState={wireState}
          selectedPath={selectedPath}
          onSelectPath={setSelectedPath}
        />
      )}
    </>
  );
}

export function PortEdge({
  id,
  source,
  target,
  sourceX, sourceY, sourcePosition,
  targetX, targetY, targetPosition,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
  });

  const { testTrace, runningStepId, isTestRunning, probedEdges, toggleProbe } = usePipelineTest();

  const key = probeKey(source, target);
  const isProbed = probedEdges.has(key);
  const trace = testTrace?.[source] ?? testTrace?.[target] ?? null;
  const hasPassed = trace?.status === "completed";
  const hasError = trace?.status === "error";
  const isActive = isTestRunning && (runningStepId === source || runningStepId === target);

  const edgeColor = hasPassed ? "#22c55e" : hasError ? "#ef4444" : isActive ? "#1976d2" : undefined;
  const label = typeof data?.label === "string" ? data.label : "";

  return (
    <>
      {isActive && (
        <>
          <style>{`@keyframes flowDash { to { stroke-dashoffset: -20; } }`}</style>
          <path
            d={edgePath}
            fill="none"
            stroke="#1976d2"
            strokeWidth={3}
            strokeDasharray="8 12"
            strokeLinecap="round"
            style={{ animation: "flowDash 0.7s linear infinite" }}
          />
        </>
      )}

      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: edgeColor,
          strokeWidth: (hasPassed || isActive || isProbed) ? 2 : 1.5,
          strokeDasharray: isProbed && !isActive ? "4 3" : undefined,
        }}
      />

      <EdgeLabelRenderer>
        {label && (
          <div
            className="nodrag nopan"
            style={{
              position: "absolute",
              transform: `translate(-50%,-50%) translate(${labelX}px,${labelY}px)`,
              fontSize: 10,
              padding: "2px 6px",
              borderRadius: 8,
              border: "1px solid #ddd",
              background: "#fff",
            }}
          >
            {label}
          </div>
        )}

        <div
          className="nodrag nopan"
          onClick={() => toggleProbe(source, target)}
          title={isProbed ? "Remove probe" : "Clamp probe here to inspect data"}
          style={{
            position: "absolute",
            transform: `translate(-50%,-50%) translate(${labelX}px,${label ? labelY + 20 : labelY}px)`,
            cursor: "pointer",
            pointerEvents: "all",
            width: 20,
            height: 20,
            borderRadius: "50%",
            background: isProbed ? "#1e1e2e" : "#fff",
            border: `2px solid ${isProbed ? (edgeColor ?? "#cba6f7") : "#94a3b8"}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 13,
            fontWeight: 900,
            color: isProbed ? (edgeColor ?? "#cba6f7") : "#94a3b8",
            transition: "all 0.15s ease",
            boxShadow: isProbed ? `0 0 8px ${edgeColor ?? "#cba6f7"}60` : "none",
            zIndex: 10,
          }}
        >
          ⊕
        </div>

        {isProbed && (
          <ProbeMonitor
            sourceId={source}
            targetId={target}
            x={labelX}
            y={label ? labelY + 20 : labelY}
            onClose={() => toggleProbe(source, target)}
          />
        )}
      </EdgeLabelRenderer>
    </>
  );
}
