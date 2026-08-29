"use client";

/**
 * React Flow node for human-in-the-loop gates.
 */

import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import type { WorkflowNodeData } from "../../types";
import { WorkflowEntityCard } from "./WorkflowEntityCard";

export const HumanNode = memo(function HumanNode({
  data,
  selected,
}: NodeProps<WorkflowNodeData>) {
  return <WorkflowEntityCard data={data} selected={selected} kind="human" />;
});
