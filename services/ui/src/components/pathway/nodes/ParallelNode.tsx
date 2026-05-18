/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
"use client";

import { memo } from "react";
import Chip from "@mui/material/Chip";
import { type NodeProps } from "@xyflow/react";

import { BaseNode, NodeHandle, NodeHeader } from "./_base";

const PARALLEL_ACCENT = "#00ACC1";

interface ParallelNodeData {
  branches?: string[];
  onConfigure?: () => void;
}

function ParallelNodeComponent({ data, selected }: NodeProps) {
  const d = data as ParallelNodeData;
  const branches = d.branches ?? ["branch_a", "branch_b"];

  return (
    <BaseNode
      accentColor={PARALLEL_ACCENT}
      selected={selected}
      minWidth={180}
      ariaLabel={`Parallel fan-out with ${branches.length} branches`}
      onActivate={d.onConfigure}
    >
      <NodeHandle
        id="input"
        type="target"
        color={PARALLEL_ACCENT}
        tooltip="Input - data is forwarded to every branch"
      />
      <NodeHeader title="Parallel" />
      <Chip
        size="small"
        label={`${branches.length} branches`}
        sx={{
          mt: 0.5,
          bgcolor: PARALLEL_ACCENT,
          color: "#fff",
          fontSize: "0.65rem",
          height: 20,
        }}
      />
      {branches.map((name, i) => (
        <NodeHandle
          key={`out-${name}`}
          id={name}
          type="source"
          color={PARALLEL_ACCENT}
          top={`${((i + 1) / (branches.length + 1)) * 100}%`}
          tooltip={`Branch output ${name}`}
        />
      ))}
    </BaseNode>
  );
}

export const ParallelNode = memo(ParallelNodeComponent);
