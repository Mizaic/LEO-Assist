"use client";

import { memo, useMemo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { getPortsFromDescriptor } from "../config/subgraphs";
import type { ActionNodeData, PortDefinition } from "../config/types";

const PORT_COLORS: Record<PortDefinition["dataType"], string> = {
  string: "#2196F3",
  "string[]": "#4CAF50",
  "object[]": "#FF9800",
  boolean: "#9C27B0",
  object: "#607D8B",
};

function ActionNodeComponent({ data, selected }: NodeProps) {
  const actionData = data as unknown as ActionNodeData;
  const ports = useMemo(
    () => getPortsFromDescriptor(actionData.subgraphId, actionData.fieldMappings),
    [actionData.subgraphId, actionData.fieldMappings],
  );
  const inputs = ports.filter((p) => p.direction === "input");
  const outputs = ports.filter((p) => p.direction === "output");

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
      {inputs.map((port, i) => (
        <Box key={`in-${port.key}`} sx={{ position: "absolute", left: -84, top: `${((i + 1) / (inputs.length + 1)) * 100}%`, transform: "translateY(-50%)", width: 76, textAlign: "right" }}>
          <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.62rem", color: "text.secondary" }}>{port.key}</Typography>
          <Handle id={port.key} type="target" position={Position.Left} style={{ width: 12, height: 12, background: PORT_COLORS[port.dataType], border: "2px solid #fff", left: 76 }} />
        </Box>
      ))}

      <Typography variant="body2" fontWeight={600}>{actionData.label}</Typography>
      <Chip label={actionData.subgraphId} size="small" sx={{ mt: 0.5, bgcolor: actionData.color, color: "#fff" }} />

      {outputs.map((port, i) => (
        <Box key={`out-${port.key}`} sx={{ position: "absolute", right: -84, top: `${((i + 1) / (outputs.length + 1)) * 100}%`, transform: "translateY(-50%)", width: 76 }}>
          <Handle id={port.key} type="source" position={Position.Right} style={{ width: 12, height: 12, background: PORT_COLORS[port.dataType], border: "2px solid #fff", right: 76 }} />
          <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.62rem", color: "text.secondary", ml: 1 }}>{port.key}</Typography>
        </Box>
      ))}
    </Box>
  );
}

export const ActionNode = memo(ActionNodeComponent);

