"use client";

import { memo } from "react";
import Chip from "@mui/material/Chip";
import BoltIcon from "@mui/icons-material/Bolt";
import { type NodeProps } from "@xyflow/react";

import { BaseNode, NodeHandle, NodeHeader } from "./_base";

const TRIGGER_ACCENT = "#FFC107";
const TRIGGER_PORT_COLOR = "#FFB300";

interface TriggerNodeData {
  label?: string;
  triggerEvent?: string;
  outputPorts?: string[];
  onConfigure?: () => void;
}

function TriggerNodeComponent({ data, selected }: NodeProps) {
  const d = data as TriggerNodeData;
  const outputPorts = d.outputPorts ?? [
    "patient_id",
    "encounter_id",
    "encounter_text",
  ];
  const triggerLabel = d.triggerEvent || "manual";

  return (
    <BaseNode
      accentColor={TRIGGER_ACCENT}
      selected={selected}
      minWidth={200}
      ariaLabel={`Trigger node, fires on ${triggerLabel}`}
      onActivate={d.onConfigure}
      sx={{ bgcolor: "#FFF8E1" }}
    >
      <NodeHeader
        icon={<BoltIcon fontSize="small" color="warning" />}
        title={d.label || "Trigger"}
      />
      <Chip
        size="small"
        label={triggerLabel}
        sx={{
          mt: 0.5,
          bgcolor: TRIGGER_PORT_COLOR,
          color: "#fff",
          fontSize: "0.65rem",
          height: 20,
        }}
      />
      {outputPorts.map((name, i) => (
        <NodeHandle
          key={`out-${name}`}
          id={name}
          type="source"
          color={TRIGGER_PORT_COLOR}
          top={`${((i + 1) / (outputPorts.length + 1)) * 100}%`}
          tooltip={`Trigger output ${name}`}
        />
      ))}
    </BaseNode>
  );
}

export const TriggerNode = memo(TriggerNodeComponent);
