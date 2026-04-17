"use client";

import { memo } from "react";
import Chip from "@mui/material/Chip";
import { Position, type NodeProps } from "@xyflow/react";

import { BaseNode, NodeHandle, NodeHeader } from "./_base";

const MERGE_ACCENT = "#8E24AA";

interface MergeNodeData {
  inputs?: string[];
  onConfigure?: () => void;
}

function MergeNodeComponent({ data, selected }: NodeProps) {
  const d = data as MergeNodeData;
  const inputs = d.inputs ?? ["branch_a", "branch_b"];

  return (
    <BaseNode
      accentColor={MERGE_ACCENT}
      selected={selected}
      minWidth={180}
      ariaLabel={`Merge node, waits for ${inputs.length} inputs`}
      onActivate={d.onConfigure}
    >
      {inputs.map((name, i) => (
        <NodeHandle
          key={`in-${name}`}
          id={name}
          type="target"
          color={MERGE_ACCENT}
          top={`${((i + 1) / (inputs.length + 1)) * 100}%`}
          tooltip={`Wait for upstream branch ${name}`}
        />
      ))}
      <NodeHeader title="Merge" />
      <Chip
        size="small"
        label={`wait for ${inputs.length}`}
        sx={{
          mt: 0.5,
          bgcolor: MERGE_ACCENT,
          color: "#fff",
          fontSize: "0.65rem",
          height: 20,
        }}
      />
      <NodeHandle
        id="merged"
        type="source"
        position={Position.Right}
        color={MERGE_ACCENT}
        tooltip="Merged output - all branches arrived"
      />
    </BaseNode>
  );
}

export const MergeNode = memo(MergeNodeComponent);
