"use client";

import { memo, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { getPortsFromDescriptor } from "../config/subgraphs";
import { SUBGRAPH_OPTIONS } from "../config/subgraphs";
import type { ActionNodeData, PortDefinition } from "../config/types";
import { usePipelineTest } from "../context/PipelineTestContext";

const PORT_COLORS: Record<PortDefinition["dataType"], string> = {
  string: "#2196F3",
  "string[]": "#4CAF50",
  "object[]": "#FF9800",
  boolean: "#9C27B0",
  object: "#607D8B",
};

function ActionNodeComponent({ id, data, selected }: NodeProps) {
  const actionData = data as unknown as ActionNodeData;
  const [outputHovered, setOutputHovered] = useState(false);
  const { testTrace, isTestRunning, runningStepId, haltedNodeId } = usePipelineTest();
  const stepResult = testTrace?.[id] ?? null;
  const isThisRunning = isTestRunning && runningStepId === id;
  const isHalted = stepResult?.status === "halted";
  // "Not reached" = a run happened (testTrace not null) but this node has no result
  // AND something upstream caused a halt
  const isNotReached = testTrace !== null && !stepResult && !isThisRunning && !!haltedNodeId;

  const subgraphLabel = useMemo(
    () => SUBGRAPH_OPTIONS.find((s) => s.id === actionData.subgraphId)?.label ?? actionData.subgraphId,
    [actionData.subgraphId],
  );

  const ports = useMemo(
    () => getPortsFromDescriptor(actionData.subgraphId, actionData.fieldMappings),
    [actionData.subgraphId, actionData.fieldMappings],
  );
  const inputs = ports.filter((p) => p.direction === "input");
  const outputs = ports.filter((p) => p.direction === "output");

  const hasOutputs = outputs.length > 0;

  return (
    <Box
      sx={{
        px: 2,
        py: 1.5,
        borderRadius: 2,
        border: "2px solid",
        borderColor: isHalted
          ? "error.main"
          : isThisRunning
            ? "primary.main"
            : selected
              ? "primary.main"
              : actionData.color,
        bgcolor: isHalted
          ? "error.50"
          : isThisRunning
            ? "primary.50"
            : isNotReached
              ? "grey.50"
              : "background.paper",
        opacity: isNotReached ? 0.45 : 1,
        minWidth: 220,
        cursor: "pointer",
        position: "relative",
        // Running: blue pulse
        ...(isThisRunning && {
          animation: "nodePulse 1s ease-in-out infinite",
          "@keyframes nodePulse": {
            "0%":   { boxShadow: "0 0 0 0 rgba(25,118,210,0.4)" },
            "70%":  { boxShadow: "0 0 0 8px rgba(25,118,210,0)" },
            "100%": { boxShadow: "0 0 0 0 rgba(25,118,210,0)" },
          },
        }),
        // Halted: red glow — persistent, not looping
        ...(isHalted && {
          animation: "nodeHalt 1.4s ease-in-out infinite",
          "@keyframes nodeHalt": {
            "0%":   { boxShadow: "0 0 0 0 rgba(211,47,47,0.55)" },
            "60%":  { boxShadow: "0 0 0 10px rgba(211,47,47,0)" },
            "100%": { boxShadow: "0 0 0 0 rgba(211,47,47,0)" },
          },
        }),
      }}
      onClick={actionData.onConfigure}
    >
      {/* Input handles (React Flow controls absolute positioning) */}
      {inputs.map((port, i) => {
        const topPct = `${((i + 1) / (inputs.length + 1)) * 100}%`;
        return (
          <Tooltip
            key={`in-${port.key}`}
            title={`Input: ${port.key} — drag a connection here from a previous step`}
            placement="left"
            arrow
          >
            <Handle
              id={port.key}
              type="target"
              position={Position.Left}
              style={{
                top: topPct,
                width: 14,
                height: 14,
                background: PORT_COLORS[port.dataType],
                border: "2px solid #fff",
                borderRadius: "50%",
              }}
            />
          </Tooltip>
        );
      })}
      {inputs.map((port, i) => {
        const topPct = `${((i + 1) / (inputs.length + 1)) * 100}%`;
        return (
          <Typography
            key={`in-label-${port.key}`}
            variant="caption"
            sx={{
              position: "absolute",
              left: -10,
              top: topPct,
              transform: "translateY(-50%) translateX(-100%)",
              fontFamily: "monospace",
              fontSize: "0.62rem",
              color: "text.secondary",
              whiteSpace: "nowrap",
              pointerEvents: "none",
              pr: 0.5,
            }}
          >
            {port.key}
          </Typography>
        );
      })}

      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <Typography variant="body2" fontWeight={600} sx={{ flex: 1 }}>{actionData.label}</Typography>

        {/* Running: spinner */}
        {isThisRunning && (
          <Tooltip title="Running…">
            <Box sx={{ display: "flex", alignItems: "center" }}>
              <svg width="12" height="12" viewBox="0 0 24 24" style={{ animation: "spin 1s linear infinite" }}>
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                <circle cx="12" cy="12" r="9" fill="none" stroke="#1976d2" strokeWidth="3" strokeDasharray="28 56" strokeLinecap="round" />
              </svg>
            </Box>
          </Tooltip>
        )}

        {/* Queued / waiting during an active run */}
        {isTestRunning && !stepResult && !isThisRunning && (
          <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: "grey.300", flexShrink: 0 }} />
        )}

        {/* Not reached — pipeline was halted upstream */}
        {isNotReached && (
          <Tooltip title="Pipeline stopped before reaching this step">
            <Typography variant="caption" sx={{ fontSize: "0.6rem", color: "text.disabled" }}>
              skipped
            </Typography>
          </Tooltip>
        )}

        {/* Passed */}
        {stepResult?.status === "completed" && (
          <Tooltip title={`Passed — ${stepResult.duration_ms < 1000 ? `${stepResult.duration_ms}ms` : `${(stepResult.duration_ms / 1000).toFixed(2)}s`}`}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.4 }}>
              <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "success.main", flexShrink: 0 }} />
              <Typography variant="caption" sx={{ fontSize: "0.6rem", color: "success.dark", fontWeight: 700 }}>
                {stepResult.duration_ms < 1000 ? `${stepResult.duration_ms}ms` : `${(stepResult.duration_ms / 1000).toFixed(1)}s`}
              </Typography>
            </Box>
          </Tooltip>
        )}

        {/* Halted — step ran but quality gate stopped the pipeline */}
        {isHalted && (
          <Tooltip title="Pipeline stopped here — check the probe for details">
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.4 }}>
              <Box component="span" sx={{ fontSize: "0.75rem", lineHeight: 1 }}>🛑</Box>
              <Typography variant="caption" sx={{ fontSize: "0.6rem", color: "error.dark", fontWeight: 700 }}>
                halted
              </Typography>
            </Box>
          </Tooltip>
        )}

        {/* Errored — step crashed */}
        {stepResult?.status === "error" && (
          <Tooltip title={stepResult.error ?? "Step failed"}>
            <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "error.main", flexShrink: 0 }} />
          </Tooltip>
        )}
      </Box>
      <Chip
        label={subgraphLabel}
        size="small"
        sx={{ mt: 0.5, bgcolor: actionData.color, color: "#fff", fontSize: "0.65rem", height: 20 }}
      />

      {/* Output handles (React Flow controls absolute positioning) */}
      {outputs.map((port, i) => {
        const topPct = `${((i + 1) / (outputs.length + 1)) * 100}%`;
        return (
          <Tooltip
            key={`out-${port.key}`}
            title={`Output: ${port.key} — drag this dot to connect to the next step`}
            placement="right"
            arrow
          >
            <Handle
              id={port.key}
              type="source"
              position={Position.Right}
              onMouseEnter={() => setOutputHovered(true)}
              onMouseLeave={() => setOutputHovered(false)}
              style={{
                top: topPct,
                width: 14,
                height: 14,
                background: PORT_COLORS[port.dataType],
                border: "2px solid #fff",
                borderRadius: "50%",
              }}
            />
          </Tooltip>
        );
      })}
      {outputs.map((port, i) => {
        const topPct = `${((i + 1) / (outputs.length + 1)) * 100}%`;
        return (
          <Typography
            key={`out-label-${port.key}`}
            variant="caption"
            sx={{
              position: "absolute",
              right: -8,
              top: topPct,
              transform: "translateY(-50%) translateX(100%)",
              fontFamily: "monospace",
              fontSize: "0.62rem",
              color: "text.secondary",
              whiteSpace: "nowrap",
              pointerEvents: "none",
              pl: 0.5,
            }}
          >
            {port.key}
          </Typography>
        );
      })}

      {/* Hint shown when step has no outputs configured yet */}
      {!hasOutputs && (
        <Typography
          variant="caption"
          sx={{
            position: "absolute",
            right: -108,
            top: "50%",
            transform: "translateY(-50%)",
            width: 100,
            color: "text.disabled",
            fontSize: "0.6rem",
            lineHeight: 1.3,
            textAlign: "left",
          }}
        >
          Configure step to add outputs
        </Typography>
      )}

      {/* "Drag to connect" hint that appears on output hover */}
      {hasOutputs && outputHovered && (
        <Typography
          variant="caption"
          sx={{
            position: "absolute",
            right: -108,
            top: "calc(50% + 18px)",
            transform: "translateY(-50%)",
            width: 100,
            color: "primary.main",
            fontSize: "0.58rem",
            lineHeight: 1.3,
            pointerEvents: "none",
          }}
        >
          Drag dot to connect →
        </Typography>
      )}
    </Box>
  );
}

export const ActionNode = memo(ActionNodeComponent);
