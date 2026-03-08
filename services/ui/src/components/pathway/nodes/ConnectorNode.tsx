"use client";

import { memo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Handle, Position, type NodeProps } from "@xyflow/react";

function ConnectorNodeComponent({ data, selected }: NodeProps) {
  const connectorType = (data as any).connectorType ?? "rest_connector";
  const label = (data as any).label || (connectorType === "queue_publish" ? "Queue Publish" : "REST API Call");
  const inputs = (data as any).inputPorts ?? ["input"];
  const outputs = connectorType === "queue_publish" ? [] : ((data as any).outputPorts ?? ["connector_response"]);
  const color = connectorType === "queue_publish" ? "#795548" : "#3F51B5";

  return (
    <Box
      sx={{
        px: 2,
        py: 1.5,
        minWidth: 200,
        borderRadius: 2,
        border: "2px dashed",
        borderColor: selected ? "primary.main" : color,
        bgcolor: "background.paper",
        position: "relative",
        cursor: "pointer",
      }}
      onClick={(data as any).onConfigure}
    >
      {inputs.map((name: string, i: number) => (
        <Handle
          key={`in-${name}`}
          id={name}
          type="target"
          position={Position.Left}
          style={{ width: 12, height: 12, top: `${((i + 1) / (inputs.length + 1)) * 100}%`, background: "#90A4AE", border: "2px solid #fff" }}
        />
      ))}
      {outputs.map((name: string, i: number) => (
        <Handle
          key={`out-${name}`}
          id={name}
          type="source"
          position={Position.Right}
          style={{ width: 12, height: 12, top: `${((i + 1) / (outputs.length + 1)) * 100}%`, background: "#26A69A", border: "2px solid #fff" }}
        />
      ))}
      <Typography variant="body2" fontWeight={700}>{label}</Typography>
      <Chip size="small" label={connectorType} sx={{ mt: 0.5, bgcolor: color, color: "#fff" }} />
    </Box>
  );
}

export const ConnectorNode = memo(ConnectorNodeComponent);

