/** Shared TypeScript types for the Workflow Builder. */

export type StepKind = "agent" | "human" | "ambient";
export type ContextKind = "service" | "organisation" | "scheduler";
export type NodeKind = StepKind | ContextKind;

export interface ContextAttribute {
  name: string;
  value: string;
  /** Step id when the row came from an ambient agent. Never use label as the React key. */
  id?: string;
}

export interface AgentDef {
  type: string;
  label: string;
  description: string;
  kind: StepKind;
  /** Default statusOnReady emitted when this step fires. */
  statusOnReady?: string;
  /** Always triggers regardless of path conditions. */
  alwaysTrigger?: boolean;
  /** Interval in minutes (for ambient/polling agents). */
  interval?: number;
}

export interface WorkflowNodeData {
  agentType: string;
  label: string;
  kind: NodeKind;
  interval?: number;
  alwaysTrigger?: boolean;
  statusOnReady?: string;
  defaultOnHitl?: boolean;
  description?: string;
  enabled?: boolean;
  status?: string;
  enableDate?: string;
  attributes?: ContextAttribute[];
  readOnly?: boolean;
  derived?: boolean;
}

export interface WorkflowEdgeData {
  /** JSONPath condition, e.g. "$.result == true". Empty = unconditional. */
  condition?: string;
}

export interface Workflow {
  id: string;
  name: string;
  serviceId: string;
  serviceName?: string;
  orgName?: string;
  createdAt: string;
  stepCount?: number;
  humanCount?: number;
}

export interface WorkflowGraph {
  workflowId: string;
  workflowName: string;
  serviceId: string;
  nodes: WorkflowGraphNode[];
  edges: WorkflowGraphEdge[];
}

export interface WorkflowGraphNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: WorkflowNodeData;
}

export interface WorkflowGraphEdge {
  id: string;
  source: string;
  target: string;
  data?: WorkflowEdgeData;
}

export interface CreateWorkflowPayload {
  name: string;
  serviceId: string;
}
