"use client";

import { memo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Handle, Position, type NodeProps } from "@xyflow/react";

function MergeNodeComponent({ data, selected }: NodeProps) {
  const inputs = (data as any).inputs ?? ["branch_a", "branch_b"];
  return (
    <Box sx={{ px: 2, py: 1.5, minWidth: 180, borderRadius: 2, border: "2px solid", borderColor: selected ? "primary.main" : "#8E24AA", bgcolor: "background.paper", position: "relative" }}>
      {inputs.map((name: string, i: number) => (
        <Handle key={name} id={name} type="target" position={Position.Left} style={{ top: `${((i + 1) / (inputs.length + 1)) * 100}%` }} />
      ))}
      <Typography variant="body2" fontWeight={700}>Merge</Typography>
      <Chip size="small" label={`wait for ${inputs.length}`} sx={{ mt: 0.5, bgcolor: "#8E24AA", color: "#fff" }} />
      <Handle id="merged" type="source" position={Position.Right} />
    </Box>
  );
}

export const MergeNode = memo(MergeNodeComponent);

