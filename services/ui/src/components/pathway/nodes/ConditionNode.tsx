/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
"use client";

import { memo, useMemo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Position, type NodeProps } from "@xyflow/react";

import { BaseNode, NodeHandle, NodeHeader } from "./_base";

const CONDITION_ACCENT = "#E91E63";
const CONDITION_PORT_COLOR = "#4CAF50";

interface ConditionRule {
  outputPort?: string;
}

interface ConditionNodeData {
  label?: string;
  rules?: ConditionRule[];
  defaultPort?: string;
  onConfigure?: () => void;
}

function ConditionNodeComponent({ data, selected }: NodeProps) {
  const d = data as ConditionNodeData;
  const rules = d.rules ?? [];
  const defaultPort = d.defaultPort ?? "else";

  const ports = useMemo(() => {
    const unique = new Set<string>();
    for (const rule of rules) {
      if (rule?.outputPort) unique.add(String(rule.outputPort));
    }
    unique.add(defaultPort);
    return Array.from(unique);
  }, [rules, defaultPort]);

  return (
    <BaseNode
      accentColor={CONDITION_ACCENT}
      selected={selected}
      minWidth={180}
      ariaLabel={`Condition node with ${rules.length} rule${rules.length === 1 ? "" : "s"}`}
      onActivate={d.onConfigure}
    >
      <NodeHandle
        id="input"
        type="target"
        color={CONDITION_ACCENT}
        tooltip="Input - value to evaluate"
      />
      <NodeHeader title={d.label || "Condition"} />
      <Chip
        size="small"
        label={`${rules.length} rule${rules.length === 1 ? "" : "s"}`}
        sx={{
          mt: 0.5,
          height: 20,
          fontSize: "0.62rem",
          bgcolor: CONDITION_ACCENT,
          color: "#fff",
        }}
      />
      {ports.map((port, i) => (
        <Box
          key={`port-${port}`}
          sx={{
            position: "absolute",
            right: -80,
            top: `${((i + 1) / (ports.length + 1)) * 100}%`,
            transform: "translateY(-50%)",
            width: 72,
          }}
        >
          <NodeHandle
            id={port}
            type="source"
            position={Position.Right}
            color={CONDITION_PORT_COLOR}
            style={{ right: 72 }}
            tooltip={`Branch '${port}' - taken when matching rule fires`}
          />
          <Typography
            variant="caption"
            sx={{ ml: 1, fontFamily: "monospace", fontSize: "0.62rem" }}
          >
            {port}
          </Typography>
        </Box>
      ))}
    </BaseNode>
  );
}

export const ConditionNode = memo(ConditionNodeComponent);
