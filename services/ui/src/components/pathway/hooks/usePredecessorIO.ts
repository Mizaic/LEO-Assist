import { useMemo } from "react";
import type { Edge, Node } from "@xyflow/react";
import { SUBGRAPH_IO } from "../config/subgraphs";
import type { ActionNodeData, ActionConfig, FieldMappingRow } from "../config/types";

export function buildProducedFields(mappings: FieldMappingRow[]): Record<string, Set<string>> {
  const result: Record<string, Set<string>> = {};
  for (const row of mappings) {
    const match = row.statePath.match(/^(\w+)\[\]\.(.+)$/);
    if (!match) continue;
    const [, key, field] = match;
    if (!result[key]) result[key] = new Set();
    result[key].add(field);
  }
  return result;
}

export function usePredecessorWrites(
  selectedNode: string | null,
  edges: Edge[],
  nodes: Node[],
): string[] | null {
  return useMemo(() => {
    if (!selectedNode) return null;
    const predecessorIds = edges.filter((e) => e.target === selectedNode).map((e) => e.source);
    if (predecessorIds.length === 0) return null;
    const allWrites = new Set<string>();
    for (const predId of predecessorIds) {
      const predNode = nodes.find((n) => n.id === predId);
      const predSubgraphId = (predNode?.data as ActionNodeData | undefined)?.subgraphId;
      if (predSubgraphId) {
        SUBGRAPH_IO[predSubgraphId]?.writes.forEach((w) => allWrites.add(w));
      }
    }
    return allWrites.size > 0 ? Array.from(allWrites) : null;
  }, [selectedNode, edges, nodes]);
}

export function usePredecessorFieldMappings(
  selectedNode: string | null,
  edges: Edge[],
  nodeConfigs: Record<string, ActionConfig>,
): FieldMappingRow[] | null {
  return useMemo(() => {
    if (!selectedNode) return null;
    const predecessorIds = edges.filter((e) => e.target === selectedNode).map((e) => e.source);
    if (predecessorIds.length === 0) return null;
    for (const predId of predecessorIds) {
      const predCfg = nodeConfigs[predId];
      const mappings = predCfg?.params?.field_mappings as FieldMappingRow[] | undefined;
      if (mappings && mappings.length > 0) return mappings;
    }
    return null;
  }, [selectedNode, edges, nodeConfigs]);
}

