import type { NodeTypes } from "@xyflow/react";
import { ActionNode } from "./ActionNode";
import { ConditionNode } from "./ConditionNode";
import { ConnectorNode } from "./ConnectorNode";
import { TriggerNode } from "./TriggerNode";
import { ParallelNode } from "./ParallelNode";
import { MergeNode } from "./MergeNode";
import { TransformNode } from "./TransformNode";
import { SourceNode } from "./SourceNode";

export const nodeTypes: NodeTypes = {
  action: ActionNode,
  condition: ConditionNode,
  rest_connector: ConnectorNode,
  queue_publish: ConnectorNode,
  trigger: TriggerNode,
  parallel: ParallelNode,
  merge: MergeNode,
  transform: TransformNode,
  source: SourceNode,
};

