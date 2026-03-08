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
  const { testTrace, isTestRunning } = usePipelineTest();
  const stepResult = testTrace?.[id] ?? null;

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
        borderColor: selected ? "primary.main" : actionData.color,
        bgcolor: "background.paper",
        minWidth: 220,
        cursor: "pointer",
        position: "relative",
      }}
      onClick={actionData.onConfigure}
    >
      {/* Input port handles */}
      {inputs.map((port, i) => (
        <Tooltip
          key={`in-${port.key}`}
          title={`Input: ${port.key} — drag a connection here from a previous step`}
          placement="left"
          arrow
        >
          <Box sx={{
            position: "absolute",
            left: -88,
            top: `${((i + 1) / (inputs.length + 1)) * 100}%`,
            transform: "translateY(-50%)",
            width: 80,
            textAlign: "right",
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: "4px",
          }}>
            <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.62rem", color: "text.secondary" }}>
              {port.key}
            </Typography>
            <Handle
              id={port.key}
              type="target"
              position={Position.Left}
              style={{ width: 14, height: 14, background: PORT_COLORS[port.dataType], border: "2px solid #fff", position: "relative", left: "auto", top: "auto", transform: "none" }}
            />
          </Box>
        </Tooltip>
      ))}

      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <Typography variant="body2" fontWeight={600} sx={{ flex: 1 }}>{actionData.label}</Typography>
        {/* Test-run status badge */}
        {isTestRunning && !stepResult && (
          <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "grey.400", flexShrink: 0, opacity: 0.6 }} />
        )}
        {stepResult?.status === "completed" && (
          <Tooltip title={`Passed in ${(stepResult.duration_ms / 1000).toFixed(2)}s`}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.4 }}>
              <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "success.main", flexShrink: 0 }} />
              <Typography variant="caption" sx={{ fontSize: "0.6rem", color: "success.dark", fontWeight: 700 }}>
                {stepResult.duration_ms < 1000 ? `${stepResult.duration_ms}ms` : `${(stepResult.duration_ms / 1000).toFixed(1)}s`}
              </Typography>
            </Box>
          </Tooltip>
        )}
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

      {/* Output port handles */}
      {outputs.map((port, i) => (
        <Tooltip
          key={`out-${port.key}`}
          title={`Output: ${port.key} — drag this dot to connect to the next step`}
          placement="right"
          arrow
        >
          <Box
            onMouseEnter={() => setOutputHovered(true)}
            onMouseLeave={() => setOutputHovered(false)}
            sx={{
              position: "absolute",
              right: -88,
              top: `${((i + 1) / (outputs.length + 1)) * 100}%`,
              transform: "translateY(-50%)",
              width: 80,
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            <Handle
              id={port.key}
              type="source"
              position={Position.Right}
              style={{ width: 14, height: 14, background: PORT_COLORS[port.dataType], border: "2px solid #fff", position: "relative", right: "auto", top: "auto", transform: "none" }}
            />
            <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.62rem", color: "text.secondary" }}>
              {port.key}
            </Typography>
          </Box>
        </Tooltip>
      ))}

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
