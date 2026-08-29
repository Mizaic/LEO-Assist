/** Map API rows and pick a readable title for the workflow list. */

import type { Workflow } from "./types";

function asString(value: unknown): string {
  return value == null ? "" : String(value).trim();
}

function asCount(value: unknown): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

export function toWorkflow(raw: Record<string, unknown>): Workflow {
  const id = asString(raw.id);
  const serviceName = asString(raw.serviceName ?? raw.service_name);
  const name = asString(raw.name);
  return {
    id,
    name: name || serviceName || id,
    serviceId: asString(raw.serviceId ?? raw.service_id),
    serviceName,
    createdAt: asString(raw.createdAt ?? raw.created_at),
    stepCount: asCount(raw.stepCount ?? raw.step_count),
    humanCount: asCount(raw.humanCount ?? raw.human_count),
  };
}

export function isTechnicalWorkflowName(name: string, id: string): boolean {
  if (!name || name === id) return true;
  return /_workflow$/i.test(name) || /^demo-wf-/i.test(name);
}

export function humanizeWorkflowId(id: string): string {
  return id
    .replace(/^demo-wf-/i, "Demo workflow ")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function workflowTitle(workflow: Workflow): string {
  const name = (workflow.name || "").trim();
  const service = (workflow.serviceName || "").trim();
  if (name && !isTechnicalWorkflowName(name, workflow.id)) return name;
  if (service) return service;
  return humanizeWorkflowId(name || workflow.id);
}
