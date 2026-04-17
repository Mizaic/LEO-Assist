"use client";

import { memo } from "react";
import Chip from "@mui/material/Chip";
import { type NodeProps } from "@xyflow/react";

import { BaseNode, NodeHandle, NodeHeader } from "./_base";

const TRANSFORM_ACCENT = "#43A047";

interface TransformOperation {
  op: string;
}

interface TransformNodeData {
  operations?: TransformOperation[];
  onConfigure?: () => void;
}

function summariseOperations(operations: TransformOperation[]): string {
  if (operations.length === 0) return "No operations - click to configure";
  const opNames = Array.from(new Set(operations.map((o) => o.op)));
  const noun = operations.length === 1 ? "op" : "ops";
  return `${operations.length} ${noun}: ${opNames.join(", ")}`;
}

function TransformNodeComponent({ data, selected }: NodeProps) {
  const d = data as TransformNodeData;
  const operations = d.operations ?? [];
  const opSummary = summariseOperations(operations);

  return (
    <BaseNode
      accentColor={TRANSFORM_ACCENT}
      selected={selected}
      minWidth={200}
      ariaLabel={`Transform node, ${opSummary}`}
      onActivate={d.onConfigure}
    >
      <NodeHandle
        id="input"
        type="target"
        color={TRANSFORM_ACCENT}
        tooltip="Input - data to transform"
      />
      <NodeHeader title="Transform" />
      <Chip
        size="small"
        label={opSummary}
        sx={{
          mt: 0.5,
          bgcolor: TRANSFORM_ACCENT,
          color: "#fff",
          fontSize: "0.62rem",
          height: 20,
        }}
      />
      <NodeHandle
        id="output"
        type="source"
        color={TRANSFORM_ACCENT}
        tooltip="Output - transformed data"
      />
    </BaseNode>
  );
}

export const TransformNode = memo(TransformNodeComponent);
