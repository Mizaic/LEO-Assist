"use client";

import { memo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import SendIcon from "@mui/icons-material/Send";
import HubIcon from "@mui/icons-material/Hub";
import { Handle, Position, type NodeProps } from "@xyflow/react";

/**
 * OutputNode — a terminal node on the canvas that represents an outbound
 * destination (e.g. a Pub/Sub topic to publish to after the pipeline runs).
 * It has INPUT handles only; it never forwards data further.
 */

export type OutputType = "pubsub_publish" | "webhook";

export const OUTPUT_DEFINITIONS: Record<
  OutputType,
  { label: string; description: string; color: string; inputs: string[] }
> = {
  pubsub_publish: {
    label: "Message Queue (Publish)",
    description: "Push pipeline results to a topic or queue",
    color: "#BF360C",
    inputs: ["payload"],
  },
  webhook: {
    label: "Webhook / REST endpoint",
    description: "POST pipeline results to an external HTTP endpoint",
    color: "#283593",
    inputs: ["payload"],
  },
};

const OUTPUT_ICONS: Record<OutputType, React.ReactNode> = {
  pubsub_publish: <HubIcon  sx={{ fontSize: "1rem" }} />,
  webhook:        <SendIcon sx={{ fontSize: "1rem" }} />,
};

function OutputNodeComponent({ data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    outputType?: OutputType;
    inputs?: string[];
    onConfigure?: () => void;
  };

  const outputType: OutputType = d.outputType ?? "pubsub_publish";
  const meta = OUTPUT_DEFINITIONS[outputType] ?? OUTPUT_DEFINITIONS.pubsub_publish;
  const inputs: string[] = d.inputs ?? meta.inputs;

  return (
    <Box
      onDoubleClick={d.onConfigure}
      sx={{
        px: 2,
        py: 1.5,
        minWidth: 190,
        borderRadius: 2,
        border: "2px solid",
        borderColor: selected ? "primary.main" : meta.color,
        bgcolor: `${meta.color}12`,
        cursor: "grab",
        position: "relative",
        // Extra left padding for handle labels
        pl: inputs.length > 0 ? `${Math.max(...inputs.map((k) => k.length)) * 6 + 28}px` : 2,
      }}
    >
      {/* Input handles + labels */}
      {inputs.map((key, i) => {
        const topPct = `${((i + 1) / (inputs.length + 1)) * 100}%`;
        return (
          <Tooltip key={key} title={`Wire "${key}" from an upstream step`} placement="left" arrow>
            <Handle
              id={key}
              type="target"
              position={Position.Left}
              style={{
                top: topPct,
                width: 12,
                height: 12,
                background: meta.color,
                border: "2px solid #fff",
                borderRadius: "50%",
              }}
            />
          </Tooltip>
        );
      })}

      {/* Labels sit to the left of the handles */}
      {inputs.map((key, i) => {
        const topPct = `${((i + 1) / (inputs.length + 1)) * 100}%`;
        return (
          <Typography
            key={`label-${key}`}
            variant="caption"
            sx={{
              position: "absolute",
              left: -8,
              top: topPct,
              transform: "translateY(-50%) translateX(-100%)",
              fontFamily: "monospace",
              fontSize: "0.62rem",
              color: "text.secondary",
              whiteSpace: "nowrap",
              pointerEvents: "none",
              pr: 0.5,
            }}
          >
            {key}
          </Typography>
        );
      })}

      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}>
        <Box sx={{ color: meta.color, display: "flex" }}>{OUTPUT_ICONS[outputType]}</Box>
        <Typography variant="body2" fontWeight={700}>{d.label || meta.label}</Typography>
      </Box>
      <Chip
        size="small"
        label="Output"
        sx={{ bgcolor: meta.color, color: "#fff", fontSize: "0.65rem", height: 20 }}
      />
      <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 0.5, fontSize: "0.6rem" }}>
        Double-click to configure
      </Typography>
    </Box>
  );
}

export const OutputNode = memo(OutputNodeComponent);
