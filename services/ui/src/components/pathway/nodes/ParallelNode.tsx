"use client";

import { memo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Handle, Position, type NodeProps } from "@xyflow/react";

function ParallelNodeComponent({ data, selected }: NodeProps) {
  const branches = (data as any).branches ?? ["branch_a", "branch_b"];
  return (
    <Box sx={{ px: 2, py: 1.5, minWidth: 180, borderRadius: 2, border: "2px solid", borderColor: selected ? "primary.main" : "#00ACC1", bgcolor: "background.paper", position: "relative" }}>
      <Handle id="input" type="target" position={Position.Left} />
      <Typography variant="body2" fontWeight={700}>Parallel</Typography>
      <Chip size="small" label={`${branches.length} branches`} sx={{ mt: 0.5, bgcolor: "#00ACC1", color: "#fff" }} />
      {branches.map((name: string, i: number) => (
        <Handle key={name} id={name} type="source" position={Position.Right} style={{ top: `${((i + 1) / (branches.length + 1)) * 100}%` }} />
      ))}
    </Box>
  );
}

export const ParallelNode = memo(ParallelNodeComponent);

