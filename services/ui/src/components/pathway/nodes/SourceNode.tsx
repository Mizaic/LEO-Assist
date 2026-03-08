"use client";

import { memo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import ArticleIcon from "@mui/icons-material/Article";
import PersonIcon from "@mui/icons-material/Person";
import StorageIcon from "@mui/icons-material/Storage";
import { Handle, Position, type NodeProps } from "@xyflow/react";

export type SourceType = "encounter_text" | "patient_graph" | "knowledge_graph";

export const SOURCE_DEFINITIONS: Record<
  SourceType,
  { label: string; description: string; color: string; outputs: string[] }
> = {
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
};

const SOURCE_ICONS: Record<SourceType, React.ReactNode> = {
  encounter_text: <ArticleIcon sx={{ fontSize: "1rem" }} />,
  patient_graph:  <PersonIcon  sx={{ fontSize: "1rem" }} />,
  knowledge_graph: <StorageIcon sx={{ fontSize: "1rem" }} />,
};

function SourceNodeComponent({ data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    sourceType?: SourceType;
    outputs?: string[];
    onConfigure?: () => void;
  };

  const sourceType: SourceType = d.sourceType ?? "encounter_text";
  const meta = SOURCE_DEFINITIONS[sourceType] ?? SOURCE_DEFINITIONS.encounter_text;
  const outputs: string[] = d.outputs ?? meta.outputs;

  return (
    <Box
      onDoubleClick={d.onConfigure}
      sx={{
        px: 2,
        py: 1.5,
        minWidth: 190,
        borderRadius: 2,
        border: "2px dashed",
        borderColor: selected ? "primary.main" : meta.color,
        bgcolor: `${meta.color}12`,
        cursor: "grab",
        position: "relative",
        // Extra right padding to make room for the handle labels
        pr: outputs.length > 0 ? `${Math.max(...outputs.map((k) => k.length)) * 6 + 28}px` : 2,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}>
        <Box sx={{ color: meta.color, display: "flex" }}>{SOURCE_ICONS[sourceType]}</Box>
        <Typography variant="body2" fontWeight={700}>{d.label || meta.label}</Typography>
      </Box>
      <Chip
        size="small"
        label="Data source"
        sx={{ bgcolor: meta.color, color: "#fff", fontSize: "0.65rem", height: 20 }}
      />
      <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 0.5, fontSize: "0.6rem" }}>
        Double-click to configure
      </Typography>

      {/* Output handles — React Flow manages absolute positioning; labels sit alongside */}
      {outputs.map((key, i) => {
        const topPct = `${((i + 1) / (outputs.length + 1)) * 100}%`;
        return (
          <Tooltip key={key} title={`Drag to connect "${key}" to a step`} placement="right" arrow>
            {/* Handle must not have position/top/right/transform overridden — React Flow needs those */}
            <Handle
              id={key}
              type="source"
              position={Position.Right}
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

      {/* Labels float to the right of the handles, positioned independently */}
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
    </Box>
  );
}

export const SourceNode = memo(SourceNodeComponent);
