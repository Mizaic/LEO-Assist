"use client";

import { memo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import ArticleIcon from "@mui/icons-material/Article";
import PersonIcon from "@mui/icons-material/Person";
import StorageIcon from "@mui/icons-material/Storage";
import HubIcon from "@mui/icons-material/Hub";
import { type NodeProps } from "@xyflow/react";

import { BaseNode, NodeHandle, NodeHeader } from "./_base";

export type SourceType =
  | "encounter_text"
  | "patient_graph"
  | "knowledge_graph"
  | "pubsub_subscribe";

interface SourceMeta {
  label: string;
  description: string;
  color: string;
  outputs: string[];
}

export const SOURCE_DEFINITIONS: Record<SourceType, SourceMeta> = {
  encounter_text: {
    label: "Clinical Notes",
    description: "Patient notes from the start of the pathway",
    color: "#1565C0",
    outputs: ["encounter_text", "patient_id", "encounter_id"],
  },
  patient_graph: {
    label: "Patient Records",
    description: "Live patient record database",
    color: "#6A1B9A",
    outputs: ["encounter_text"],
  },
  knowledge_graph: {
    label: "Knowledge Base",
    description: "De-identified clinical knowledge database",
    color: "#00695C",
    outputs: ["encounter_text"],
  },
  pubsub_subscribe: {
    label: "Message Queue (Subscribe)",
    description:
      "Trigger this pathway when a message arrives on a topic or queue",
    color: "#E65100",
    outputs: ["message", "payload"],
  },
};

const SOURCE_ICONS: Record<SourceType, React.ReactNode> = {
  encounter_text: <ArticleIcon sx={{ fontSize: "1rem" }} />,
  patient_graph: <PersonIcon sx={{ fontSize: "1rem" }} />,
  knowledge_graph: <StorageIcon sx={{ fontSize: "1rem" }} />,
  pubsub_subscribe: <HubIcon sx={{ fontSize: "1rem" }} />,
};

interface SourceNodeData {
  label?: string;
  sourceType?: SourceType;
  outputs?: string[];
  onConfigure?: () => void;
}

function SourceNodeComponent({ data, selected }: NodeProps) {
  const d = data as SourceNodeData;
  const sourceType: SourceType = d.sourceType ?? "encounter_text";
  const meta = SOURCE_DEFINITIONS[sourceType] ?? SOURCE_DEFINITIONS.encounter_text;
  const outputs: string[] = d.outputs ?? meta.outputs;
  const longestOutput = Math.max(0, ...outputs.map((k) => k.length));
  const rightPad = outputs.length > 0 ? `${longestOutput * 6 + 28}px` : 12;

  return (
    <BaseNode
      accentColor={meta.color}
      selected={selected}
      borderStyle="dashed"
      minWidth={190}
      ariaLabel={`${d.label || meta.label} - data source`}
      onActivate={d.onConfigure}
      sx={{ bgcolor: `${meta.color}12`, pr: rightPad }}
    >
      <NodeHeader
        icon={
          <Box sx={{ color: meta.color, display: "flex" }}>
            {SOURCE_ICONS[sourceType]}
          </Box>
        }
        title={d.label || meta.label}
      />
      <Chip
        size="small"
        label="Data source"
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
      {outputs.map((key, i) => {
        const topPct = `${((i + 1) / (outputs.length + 1)) * 100}%`;
        return (
          <NodeHandle
            key={`out-${key}`}
            id={key}
            type="source"
            color={meta.color}
            top={topPct}
            tooltip={`Drag to connect "${key}" to a step`}
          />
        );
      })}
      {outputs.map((key, i) => {
        const topPct = `${((i + 1) / (outputs.length + 1)) * 100}%`;
        return (
          <Typography
            key={`label-${key}`}
            variant="caption"
            sx={{
              position: "absolute",
              right: -8,
              top: topPct,
              transform: "translateY(-50%) translateX(100%)",
              fontFamily: "monospace",
              fontSize: "0.62rem",
              color: "text.secondary",
              whiteSpace: "nowrap",
              pointerEvents: "none",
              pl: 0.5,
            }}
          >
            {key}
          </Typography>
        );
      })}
    </BaseNode>
  );
}

export const SourceNode = memo(SourceNodeComponent);
