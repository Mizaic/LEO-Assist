"use client";

/**
 * React Flow node for read-only Service / Organisation / Scheduler cards.
 */

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import type { ContextKind, WorkflowNodeData } from "../../types";
import { ContextEntityCard } from "./ContextEntityCard";

function asContextKind(kind: string | undefined): ContextKind {
  if (kind === "organisation" || kind === "scheduler") return kind;
  return "service";
}

export const ContextNode = memo(function ContextNode({
  data,
  selected,
}: NodeProps<WorkflowNodeData>) {
  return (
    <ContextEntityCard
      data={data}
      selected={selected}
      kind={asContextKind(data.kind)}
    />
  );
});
