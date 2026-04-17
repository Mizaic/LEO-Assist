"use client";

import { memo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import SendIcon from "@mui/icons-material/Send";
import HubIcon from "@mui/icons-material/Hub";
import StorageIcon from "@mui/icons-material/Storage";
import PersonIcon from "@mui/icons-material/Person";
import { type NodeProps } from "@xyflow/react";

import { BaseNode, NodeHandle, NodeHeader } from "./_base";

/**
 * OutputNode - terminal node on the canvas. Has INPUT handles only; never
 * forwards data further.
 */
export type OutputType =
  | "knowledge_graph"
  | "patient_graph"
  | "pubsub_publish"
  | "webhook";

interface OutputMeta {
  label: string;
  description: string;
  color: string;
  inputs: string[];
}

export const OUTPUT_DEFINITIONS: Record<OutputType, OutputMeta> = {
  knowledge_graph: {
    label: "Knowledge Base",
    description:
      "Write processed clinical facts back to the de-identified knowledge database",
    color: "#00695C",
    inputs: ["entities", "documents_written"],
  },
  patient_graph: {
    label: "Patient Records",
    description: "Write results to the live patient record database",
    color: "#6A1B9A",
    inputs: ["entities", "documents_written"],
  },
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
  knowledge_graph: <StorageIcon sx={{ fontSize: "1rem" }} />,
  patient_graph: <PersonIcon sx={{ fontSize: "1rem" }} />,
  pubsub_publish: <HubIcon sx={{ fontSize: "1rem" }} />,
  webhook: <SendIcon sx={{ fontSize: "1rem" }} />,
};

interface OutputNodeData {
  label?: string;
  outputType?: OutputType;
  inputs?: string[];
  onConfigure?: () => void;
}

function OutputNodeComponent({ data, selected }: NodeProps) {
  const d = data as OutputNodeData;
  const outputType: OutputType = d.outputType ?? "knowledge_graph";
  const meta = OUTPUT_DEFINITIONS[outputType] ?? OUTPUT_DEFINITIONS.knowledge_graph;
  const inputs: string[] = d.inputs ?? meta.inputs;
  const longestInput = Math.max(0, ...inputs.map((k) => k.length));
  const leftPad = inputs.length > 0 ? `${longestInput * 6 + 28}px` : 12;
  const chipLabel =
    outputType === "knowledge_graph" || outputType === "patient_graph"
      ? "Write destination"
      : "Output";

  return (
    <BaseNode
      accentColor={meta.color}
      selected={selected}
      minWidth={190}
      ariaLabel={`${d.label || meta.label} - output destination`}
      onActivate={d.onConfigure}
      sx={{ bgcolor: `${meta.color}12`, pl: leftPad }}
    >
      {inputs.map((key, i) => {
        const topPct = `${((i + 1) / (inputs.length + 1)) * 100}%`;
        return (
          <NodeHandle
            key={`in-${key}`}
            id={key}
            type="target"
            color={meta.color}
            top={topPct}
            tooltip={`Wire "${key}" from an upstream step`}
          />
        );
      })}
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
      <NodeHeader
        icon={
          <Box sx={{ color: meta.color, display: "flex" }}>
            {OUTPUT_ICONS[outputType]}
          </Box>
        }
        title={d.label || meta.label}
      />
      <Chip
        size="small"
        label={chipLabel}
        sx={{
          mt: 0.5,
          bgcolor: meta.color,
          color: "#fff",
          fontSize: "0.65rem",
          height: 20,
        }}
      />
      <Typography
        variant="caption"
        color="text.disabled"
        sx={{ display: "block", mt: 0.5, fontSize: "0.6rem" }}
      >
        Click to configure
      </Typography>
    </BaseNode>
  );
}

export const OutputNode = memo(OutputNodeComponent);
