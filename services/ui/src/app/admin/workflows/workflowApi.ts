/** API client for Workflow Builder CRUD operations. */

import type {
  CreateWorkflowPayload,
  Workflow,
  WorkflowGraph,
} from "./types";
import { toWorkflow } from "./workflowDisplay";

const BASE = "/api/admin/workflows";

export function parseApiBody<T>(status: number, text: string): T | undefined {
  if (status === 204 || status === 205 || !text.trim()) return undefined;
  return JSON.parse(text) as T;
}

async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await res.text().catch(() => "");
  if (!res.ok) {
    throw new Error(text || res.statusText || `HTTP ${res.status}`);
  }
  return parseApiBody<T>(res.status, text) as T;
}

export async function listWorkflows(): Promise<Workflow[]> {
  const rows = await apiFetch<Record<string, unknown>[]>(BASE);
  return rows.map(toWorkflow);
}

export async function createWorkflow(
  payload: CreateWorkflowPayload
): Promise<Workflow> {
  const raw = await apiFetch<Record<string, unknown>>(BASE, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return toWorkflow(raw);
}

export async function deleteWorkflow(id: string): Promise<void> {
  await apiFetch<void>(`${BASE}/${id}`, { method: "DELETE" });
}

export async function getWorkflowGraph(id: string): Promise<WorkflowGraph> {
  return apiFetch<WorkflowGraph>(`${BASE}/${id}/graph`);
}

export async function saveWorkflowGraph(
  id: string,
  graph: Omit<WorkflowGraph, "workflowId" | "workflowName" | "serviceId">
): Promise<void> {
  await apiFetch<void>(`${BASE}/${id}/graph`, {
    method: "PUT",
    body: JSON.stringify(graph),
  });
}

export async function listServices(): Promise<
  { id: string; name: string; orgName: string }[]
> {
  return apiFetch(`/api/admin/services`);
}
