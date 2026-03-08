"use client";

import { useState } from "react";
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from "@xyflow/react";
import { usePipelineTest } from "../context/PipelineTestContext";

export function PortEdge({
  id,
  source,
  target,
  sourceX,
  sourceY,
  sourcePosition,
  targetX,
  targetY,
  targetPosition,
  data,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const { testTrace, onPeekEdge } = usePipelineTest();
  const [hovered, setHovered] = useState(false);

  const sourceTrace = testTrace?.[source] ?? null;
  const hasPassed = sourceTrace?.status === "completed";
  const hasError  = sourceTrace?.status === "error";
  const edgeColor = hasPassed ? "#22c55e" : hasError ? "#ef4444" : undefined;

  const label = typeof data?.label === "string" ? data.label : "";

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={edgeColor ? { stroke: edgeColor, strokeWidth: hasPassed ? 2 : 1.5 } : undefined}
      />
      <EdgeLabelRenderer>
        {/* Original port-name label */}
        {label && (
          <div
            className="nodrag nopan"
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
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

        {/* Peek button — shown when trace data exists for this edge */}
        {sourceTrace && (
          <div
            className="nodrag nopan"
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            onClick={() => onPeekEdge(source, target)}
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${(label ? labelY + 22 : labelY)}px)`,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 7px",
              borderRadius: 10,
              fontSize: 10,
              fontWeight: 600,
              border: `1.5px solid ${edgeColor ?? "#94a3b8"}`,
              background: hovered ? (edgeColor ?? "#64748b") : "#fff",
              color: hovered ? "#fff" : (edgeColor ?? "#64748b"),
              transition: "all 0.15s ease",
              whiteSpace: "nowrap",
              userSelect: "none",
            }}
          >
            <svg width="10" height="10" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="9" cy="9" r="6" />
              <line x1="14" y1="14" x2="18" y2="18" />
            </svg>
            {hovered ? "Peek data" : (hasPassed ? "✓" : "✗")}
          </div>
        )}
      </EdgeLabelRenderer>
    </>
  );
}
