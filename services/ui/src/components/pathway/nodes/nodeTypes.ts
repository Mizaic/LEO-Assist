/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
import type { NodeTypes } from "@xyflow/react";
import { ActionNode } from "./ActionNode";
import { ConditionNode } from "./ConditionNode";
import { ConnectorNode } from "./ConnectorNode";
import { TriggerNode } from "./TriggerNode";
import { ParallelNode } from "./ParallelNode";
import { MergeNode } from "./MergeNode";
import { TransformNode } from "./TransformNode";
import { SourceNode } from "./SourceNode";
import { OutputNode } from "./OutputNode";
import { MiniHitlNode } from "./MiniHitlNode";

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
  output: OutputNode,
  viewer: MiniHitlNode,
};

