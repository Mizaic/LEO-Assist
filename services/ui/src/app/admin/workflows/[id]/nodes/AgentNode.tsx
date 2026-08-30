"use client";

/**
 * React Flow node for automated and ambient agent steps.
 */

import { memo } from "react";
import type { Node, NodeProps } from "@xyflow/react";
import type { WorkflowNodeData } from "../../types";
import { WorkflowEntityCard } from "./WorkflowEntityCard";

export const AgentNode = memo(function AgentNode({
  data,
  selected,
}: NodeProps<Node<WorkflowNodeData>>) {
  return (
    <WorkflowEntityCard
      data={data}
      selected={selected}
      kind={data.kind === "ambient" ? "ambient" : "agent"}
    />
  );
});
