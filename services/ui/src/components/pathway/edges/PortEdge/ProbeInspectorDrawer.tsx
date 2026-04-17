"use client";

/**
 * ProbeInspectorDrawer -- right-side drawer that lets users explore
 * pipeline state for a selected probe (Phase 6b-vi decomposition).
 *
 * Combines the SemanticSection, TreeNode and raw JSON view, plus a
 * search box backed by `collectSearchMatches`.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import Drawer from "@mui/material/Drawer";
import { useMemo, useState } from "react";

import { SemanticSection } from "./SemanticSection";
import { TreeNode } from "./TreeNode";
import {
  collectSearchMatches,
  expandAncestors,
  getDefaultExpandedPaths,
  getValueAtPath,
  topLevelEntries,
} from "./diff";
import {
  type PathSegment,
  pathToString,
  safeStringify,
  summarizeValue,
} from "./utils";

export interface ProbeInspectorDrawerProps {
  open: boolean;
  onClose: () => void;
  wireState: Record<string, unknown>;
  selectedPath: PathSegment[];
  onSelectPath: (path: PathSegment[]) => void;
}

export function ProbeInspectorDrawer({
  open,
  onClose,
  wireState,
  selectedPath,
  onSelectPath,
}: ProbeInspectorDrawerProps) {
  const [search, setSearch] = useState("");
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(
    getDefaultExpandedPaths(
      selectedPath[0] as string,
      getValueAtPath(wireState, selectedPath),
    ),
  );
  const topEntries = useMemo(() => topLevelEntries(wireState), [wireState]);
  const selectedValue = getValueAtPath(wireState, selectedPath);
  const selectedKey = String(selectedPath[0] ?? "");
  const selectedPathString = pathToString(selectedPath);
  const matches = useMemo(
    () => collectSearchMatches(wireState, search),
    [wireState, search],
  );

  const toggleExpand = (path: PathSegment[]) => {
    const key = pathToString(path);
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
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
