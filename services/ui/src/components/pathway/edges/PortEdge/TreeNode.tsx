"use client";

/**
 * TreeNode -- recursive expandable tree row used inside the
 * ProbeInspectorDrawer (Phase 6b-vi decomposition).
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  type PathSegment,
  formatPrimitive,
  isRecord,
  pathToString,
  summarizeValue,
} from "./utils";

export interface TreeNodeProps {
  label: string;
  value: unknown;
  path: PathSegment[];
  depth: number;
  expandedPaths: Set<string>;
  selectedPath: string;
  onToggleExpand: (path: PathSegment[]) => void;
  onSelect: (path: PathSegment[]) => void;
}

export function TreeNode({
  label,
  value,
  path,
  depth,
  expandedPaths,
  selectedPath,
  onToggleExpand,
  onSelect,
}: TreeNodeProps) {
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
