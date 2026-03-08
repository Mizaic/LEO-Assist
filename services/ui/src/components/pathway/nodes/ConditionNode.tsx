"use client";

import { memo, useMemo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Handle, Position, type NodeProps } from "@xyflow/react";

function ConditionNodeComponent({ data, selected }: NodeProps) {
  const rules = (data as any).rules ?? [];
  const defaultPort = (data as any).defaultPort ?? "else";
  const ports = useMemo(() => {
    const unique = new Set<string>();
    for (const rule of rules) {
      if (rule?.outputPort) unique.add(String(rule.outputPort));
    }
    unique.add(defaultPort);
    return Array.from(unique);
  }, [rules, defaultPort]);

  return (
    <Box
      sx={{
        px: 2,
        py: 1.5,
        minWidth: 180,
        bgcolor: "background.paper",
        borderRadius: 2,
        border: "2px solid",
        borderColor: selected ? "primary.main" : "#E91E63",
        cursor: "pointer",
        position: "relative",
      }}
      onClick={(data as any).onConfigure}
    >
      <Handle type="target" id="input" position={Position.Left} style={{ width: 12, height: 12, background: "#E91E63", border: "2px solid #fff" }} />
      <Typography variant="body2" fontWeight={700}>{(data as any).label || "Condition"}</Typography>
      <Chip size="small" label={`${rules.length} rule${rules.length === 1 ? "" : "s"}`} sx={{ mt: 0.5, height: 18, fontSize: "0.62rem" }} />

      {ports.map((port, i) => (
        <Box key={port} sx={{ position: "absolute", right: -80, top: `${((i + 1) / (ports.length + 1)) * 100}%`, transform: "translateY(-50%)", width: 72 }}>
          <Handle type="source" id={port} position={Position.Right} style={{ width: 12, height: 12, background: "#4CAF50", border: "2px solid #fff", right: 72 }} />
          <Typography variant="caption" sx={{ ml: 1, fontFamily: "monospace", fontSize: "0.62rem" }}>{port}</Typography>
        </Box>
      ))}
    </Box>
  );
}

export const ConditionNode = memo(ConditionNodeComponent);

