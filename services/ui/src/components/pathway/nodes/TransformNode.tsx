"use client";

import { memo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Handle, Position, type NodeProps } from "@xyflow/react";

function TransformNodeComponent({ data, selected }: NodeProps) {
  const operations = (data as any).operations ?? [];
  const opSummary = operations.length === 0
    ? "No operations — click to configure"
    : `${operations.length} op${operations.length > 1 ? "s" : ""}: ${[...new Set(operations.map((o: any) => o.op))].join(", ")}`;
  return (
    <Box
      sx={{ px: 2, py: 1.5, minWidth: 200, borderRadius: 2, border: "2px solid", borderColor: selected ? "primary.main" : "#43A047", bgcolor: "background.paper", cursor: "pointer" }}
      onClick={(data as any).onConfigure}
    >
      <Handle id="input" type="target" position={Position.Left} />
      <Typography variant="body2" fontWeight={700}>Transform</Typography>
      <Chip size="small" label={opSummary} sx={{ mt: 0.5, bgcolor: "#43A047", color: "#fff", fontSize: "0.62rem", height: 18 }} />
      <Handle id="output" type="source" position={Position.Right} />
    </Box>
  );
}

export const TransformNode = memo(TransformNodeComponent);

