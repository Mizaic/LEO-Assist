export const PIPELINE_GENERATED_SENTINEL = "__pipeline_passthrough__";

export interface FieldMappingRow {
  id: string;
  llmField: string;
  type: string;
  description: string;
  required: boolean;
  statePath: string;
  custom: boolean;
}

export interface ActionConfig {
  subgraphId: string;
  label: string;
  description: string;
  inputSource: string;
  outputTarget: string;
  enableVerification: boolean;
  maxRetries: number;
  timeout: number;
  modelPresetId: string;
  modelPresetName: string;
  temperature: number;
  promptConfigId: string;
  promptConfigName: string;
  params: Record<string, unknown>;
  nodeType?: "action" | "condition" | "rest_connector" | "queue_publish" | "trigger" | "parallel" | "merge" | "transform";
}

export const DEFAULT_CONFIG: ActionConfig = {
  subgraphId: "",
  label: "",
  description: "",
  inputSource: "previous_step",
  outputTarget: "patient_graph",
  enableVerification: false,
  maxRetries: 2,
  timeout: 120,
  modelPresetId: "",
  modelPresetName: "",
  temperature: 0.0,
  promptConfigId: "",
  promptConfigName: "",
  params: {},
  nodeType: "action",
};

export interface ActionNodeData {
  label: string;
  subgraphId: string;
  color: string;
  config?: Partial<ActionConfig>;
  nodeType?: string;
  /** Field mappings saved from the wizard — used to derive live output port handles on the canvas. */
  fieldMappings?: FieldMappingRow[];
  onConfigure: () => void;
}

export interface PlanData {
  id: string;
  name: string;
  status: string;
  description: string;
  trigger?: { event?: string; type?: string };
  actions: Array<{
    id: string;
    subgraphId: string;
    label: string;
    nodeType?: string;
    position?: { x: number; y: number };
    config?: Partial<ActionConfig>;
  }>;
  edges: Array<{
    source: string;
    target: string;
    sourceHandle?: string;
    targetHandle?: string;
  }>;
}

export interface ModelPreset {
  preset_id: string;
  name: string;
  description: string;
  color: string;
  extractor: string;
  primary_model: string;
  consensus_mode: boolean;
  is_default: boolean;
  is_system: boolean;
  prompt_config_id: string;
}

export interface PortDefinition {
  key: string;
  direction: "input" | "output";
  dataType: "string" | "string[]" | "object[]" | "boolean" | "object";
  required: boolean;
  fields?: string[];
}

export interface ConditionRule {
  id: string;
  field: string;
  operator: "==" | "!=" | ">" | "<" | "contains" | "exists";
  value: string;
  outputPort: string;
}

export interface ConditionNodeData {
  label: string;
  rules: ConditionRule[];
  defaultPort: string;
  onConfigure: () => void;
}

export interface ConnectorConfig {
  mode: "registered" | "custom";
  registeredApiId?: string;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  url?: string;
  responseMapping: FieldMappingRow[];
  timeout?: number;
  retries?: number;
}

export interface QueuePublishConfig {
  queue: string;
  messageTemplate: Record<string, string>;
  delaySeconds?: number;
}

export interface NodeDescriptor {
  id: string;
  type: string;
  label: string;
  ports: PortDefinition[];
  config: ActionConfig | ConnectorConfig | QueuePublishConfig;
}

