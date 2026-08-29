/** Lookup for HCCP-Agents typed I/O shown on the workflow canvas. */

import { AGENT_IO_BY_TYPE, GENERIC_AGENT_STATE } from "./agentIoCatalogue";

export type IoKind = "string" | "number" | "boolean" | "object" | "list" | "bytes";
export type IoStrictness = "typed" | "bag" | "pydantic";

export interface IoField {
  name: string;
  kind: IoKind;
  required: boolean;
  note?: string;
}

export interface AgentIoContract {
  agentType: string;
  stateName: string;
  strictness: IoStrictness;
  summary: string;
  inputs: IoField[];
  outputs: IoField[];
}

export function ioField(
  name: string,
  kind: IoKind,
  required = false,
  note?: string,
): IoField {
  if (note === undefined) {
    return { name, kind, required };
  }
  return { name, kind, required, note };
}

export function getAgentIo(agentType: string): AgentIoContract {
  const found = AGENT_IO_BY_TYPE[agentType];
  if (found) {
    return { agentType, ...found };
  }
  return { agentType, ...GENERIC_AGENT_STATE };
}

export const CANVAS_IO_PREVIEW = 5;

export function previewFields(
  fields: IoField[],
  max = CANVAS_IO_PREVIEW,
): IoField[] {
  return fields.slice(0, max);
}

export function kindLabel(kind: IoKind): string {
  if (kind === "boolean") return "bool";
  if (kind === "number") return "num";
  if (kind === "object") return "obj";
  if (kind === "bytes") return "bin";
  return kind;
}

export function strictnessLabel(strictness: IoStrictness): string {
  if (strictness === "pydantic") {
    return "Checked model from HCCP-Agents";
  }
  if (strictness === "typed") {
    return "Named fields from HCCP-Agents";
  }
  return "Loose bag -- most values are dicts";
}
