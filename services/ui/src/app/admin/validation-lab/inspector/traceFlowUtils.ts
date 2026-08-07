/**
 * Pipeline endpoint flow helpers for Zipkin-style dependency map.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */

import { formatStageLabel } from "../labRunFormat";
import type { LabPlanEdge, LabPlanStep, LabTraceSpan } from "../inspectorTypes";
import { formatDurationLabel, spanDurationMs, statusBarColor } from "./traceWaterfallUtils";

export interface FlowEndpoint {
  id: string;
  label: string;
  subgraphId: string;
  nodeType: string;
  status: string;
  durationMs: number | null;
  workerId: string;
  borderColor: string;
}

export interface FlowLinkRow {
  stepId: string;
  label: string;
  subgraphId: string;
  status: string;
  durationLabel: string;
  relationship: string;
}

export function resolveFlowLinks(
  planSteps: LabPlanStep[],
  planEdges: LabPlanEdge[] | undefined,
): LabPlanEdge[] {
  if (planEdges && planEdges.length > 0) return planEdges;
  const ordered = [...planSteps].sort(
    (a, b) => (a.sequence ?? 0) - (b.sequence ?? 0),
  );
  const links: LabPlanEdge[] = [];
  for (let i = 1; i < ordered.length; i += 1) {
    links.push({
      source: ordered[i - 1].action_id,
      target: ordered[i].action_id,
      relationship: "after-end",
    });
  }
  return links;
}

export function buildFlowEndpoints(
  planSteps: LabPlanStep[],
  spans: LabTraceSpan[],
): FlowEndpoint[] {
  const spanById = new Map(spans.map((span) => [span.step_id, span]));
  return planSteps.map((step) => {
    const span = spanById.get(step.action_id);
    const status = span?.status || "pending";
    const durationMs = span ? spanDurationMs(span) : null;
    return {
      id: step.action_id,
      label: formatStageLabel(step.action_id),
      subgraphId: step.subgraph_id || span?.subgraph_id || "",
      nodeType: step.node_type || "action",
      status,
      durationMs,
      workerId: span?.worker_id || "",
      borderColor: statusBarColor(status),
    };
  });
}

function linkRow(
  stepId: string,
  endpoints: Map<string, FlowEndpoint>,
  relationship: string,
): FlowLinkRow | null {
  const endpoint = endpoints.get(stepId);
  if (!endpoint) return null;
  return {
    stepId,
    label: endpoint.label,
    subgraphId: endpoint.subgraphId,
    status: endpoint.status,
    durationLabel: formatDurationLabel(endpoint.durationMs),
    relationship,
  };
}

export function endpointLinkRows(
  stepId: string,
  direction: "upstream" | "downstream",
  endpoints: FlowEndpoint[],
  links: LabPlanEdge[],
): FlowLinkRow[] {
  const byId = new Map(endpoints.map((item) => [item.id, item]));
  const rows: FlowLinkRow[] = [];
  for (const link of links) {
    if (direction === "downstream" && link.source === stepId) {
      const row = linkRow(link.target, byId, link.relationship || "after-end");
      if (row) rows.push(row);
    }
    if (direction === "upstream" && link.target === stepId) {
      const row = linkRow(link.source, byId, link.relationship || "after-end");
      if (row) rows.push(row);
    }
  }
  return rows;
}
