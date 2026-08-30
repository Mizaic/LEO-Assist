"use client";

/**
 * Sentinel START node. Royal Blue; cannot be deleted.
 * Every workflow begins here -- the STARTS_AT edge leaves this node.
 */

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

const ROYAL_BLUE = "#002178";

export const StartNode = memo(function StartNode(_: NodeProps) {
  return (
    <Box
      sx={{
        background: ROYAL_BLUE,
        border: "2px solid #001255",
        borderRadius: "10px",
        padding: "8px 16px",
        minWidth: 120,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 0.8,
        boxShadow: "0 2px 8px rgba(0,9,59,0.25)",
        cursor: "default",
        userSelect: "none",
      }}
    >
      <PlayArrowIcon sx={{ color: "#fff", fontSize: 16 }} />
      <Typography
        sx={{
          color: "#fff",
          fontWeight: 700,
          fontSize: "0.82rem",
          letterSpacing: 0.5,
          textTransform: "uppercase",
        }}
      >
        Start
      </Typography>

      <Handle
        type="target"
        position={Position.Top}
        style={{
          background: "#fff",
          border: `2px solid ${ROYAL_BLUE}`,
          width: 10,
          height: 10,
        }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        style={{
          background: "#fff",
          border: `2px solid ${ROYAL_BLUE}`,
          width: 10,
          height: 10,
        }}
      />
    </Box>
  );
});
