/** Save-time graph helpers. Context nodes stay display-only. */

import type { Edge, Node } from "@xyflow/react";
import type { WorkflowEdgeData, WorkflowNodeData } from "./types";

export const CONTEXT_KINDS = new Set([
  "service",
  "organisation",
  "scheduler",
]);

export function isContextNode(node: {
  id?: string;
  type?: string;
  data?: { kind?: string };
}): boolean {
  if (node.id === "__scheduler__") return true;
  if (CONTEXT_KINDS.has(node.type ?? "")) return true;
  return CONTEXT_KINDS.has(node.data?.kind ?? "");
}

type SpineIds = {
  organisation?: string;
  service?: string;
  scheduler?: string;
  start?: string;
};

function spineIdsOf(nodes: Array<{
  id: string;
  type?: string;
  data?: { kind?: string };
}>): SpineIds {
  const ids: SpineIds = {};
  for (const node of nodes) {
    if (node.id === "__start__" || node.type === "start") ids.start = node.id;
    const kind = CONTEXT_KINDS.has(node.type ?? "")
      ? node.type
      : node.data?.kind;
    if (kind === "organisation" || kind === "service" || kind === "scheduler") {
      ids[kind] = node.id;
    }
  }
  return ids;
}

function spineChainEdges(ids: SpineIds): Edge[] {
  const edges: Edge[] = [];
  if (ids.organisation && ids.service) {
    edges.push({ id: "e-context-org-service", source: ids.organisation, target: ids.service });
  }
  if (ids.service && ids.scheduler) {
    edges.push({
      id: "e-context-service-scheduler",
      source: ids.service,
      target: ids.scheduler,
    });
  } else if (ids.service && ids.start) {
    edges.push({ id: "e-context-service-start", source: ids.service, target: ids.start });
  }
  if (ids.scheduler && ids.start) {
    edges.push({
      id: "e-context-scheduler-start",
      source: ids.scheduler,
      target: ids.start,
    });
  }
  return edges;
}

export function ensureContextSpineEdges<T extends Edge>(
  nodes: Array<{ id: string; type?: string; data?: { kind?: string } }>,
  edges: T[],
): T[] {
  const ids = spineIdsOf(nodes);
  const spine = new Set(
    [ids.organisation, ids.service, ids.scheduler, ids.start].filter(
      (id): id is string => Boolean(id),
    ),
  );
  const kept = edges.filter(
    (edge) => !(spine.has(edge.source) && spine.has(edge.target)),
  );
  return [...(spineChainEdges(ids) as T[]), ...kept];
}

export function flowToSaveGraph(
  nodes: Node<WorkflowNodeData>[],
  edges: Edge<WorkflowEdgeData>[],
) {
  const saveable = nodes.filter((node) => !isContextNode(node));
  const ids = new Set(saveable.map((node) => node.id));
  return {
    nodes: saveable.map((node) => ({
      id: node.id,
      type: node.type ?? "agent",
      position: node.position,
      data: node.data,
    })),
    edges: edges
      .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
      .map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        data: edge.data,
      })),
  };
}
