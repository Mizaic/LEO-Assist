"use client";

import { memo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import BoltIcon from "@mui/icons-material/Bolt";
import { Handle, Position, type NodeProps } from "@xyflow/react";

function TriggerNodeComponent({ data, selected }: NodeProps) {
  const outputPorts = (data as any).outputPorts ?? ["patient_id", "encounter_id", "encounter_text"];
  return (
    <Box
      sx={{
        px: 2,
        py: 1.5,
        minWidth: 200,
        borderRadius: 2,
        border: "2px solid",
        borderColor: selected ? "primary.main" : "#FFC107",
        bgcolor: "#FFF8E1",
        position: "relative",
        cursor: "pointer",
      }}
      onClick={(data as any).onConfigure}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <BoltIcon fontSize="small" color="warning" />
        <Typography variant="body2" fontWeight={700}>{(data as any).label || "Trigger"}</Typography>
      </Box>
      <Chip size="small" label={(data as any).triggerEvent || "manual"} sx={{ mt: 0.5, bgcolor: "#FFB300", color: "#fff" }} />
      {outputPorts.map((name: string, i: number) => (
        <Handle
          key={name}
          id={name}
          type="source"
          position={Position.Right}
          style={{ width: 12, height: 12, top: `${((i + 1) / (outputPorts.length + 1)) * 100}%`, background: "#FFB300", border: "2px solid #fff" }}
        />
      ))}
    </Box>
  );
}

export const TriggerNode = memo(TriggerNodeComponent);

