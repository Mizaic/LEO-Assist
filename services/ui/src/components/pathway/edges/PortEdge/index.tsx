"use client";

/**
 * PortEdge -- the React Flow edge that renders our pipeline wires and
 * the clamp-on probe affordance. The body of the probe (banners,
 * tabs, drawer) lives in sibling modules so this file stays small.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  BaseEdge,
  EdgeLabelRenderer,
  type EdgeProps,
  getSmoothStepPath,
} from "@xyflow/react";

import { usePipelineTest } from "../../context/PipelineTestContext";
import { ProbeMonitor } from "./ProbeMonitor";
import { probeKey } from "./utils";

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
