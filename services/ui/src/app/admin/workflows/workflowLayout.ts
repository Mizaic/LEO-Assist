/** Spread stacked workflow nodes when Neo4j has no canvas coordinates. */

import type { Edge, Node } from "@xyflow/react";
import { CANVAS_IO_PREVIEW, getAgentIo } from "./agentIo";
import { isContextNode } from "./workflowGraph";

const COL = 300;
const ORIGIN_X = 200;
const ORIGIN_Y = 40;
const RANK_GAP = 48;
const NODE_WIDTH = 260;
const START_HEIGHT = 52;
const HEADER_HEIGHT = 58;
const SECTION_HEIGHT = 20;
const ROW_HEIGHT = 20;

type Positioned = {
  id: string;
  type?: string;
  position: { x: number; y: number };
  data?: unknown;
};

function agentTypeOf(node: Positioned): string {
  const data = node.data as { agentType?: string } | undefined;
  return data?.agentType ?? "";
}

function attributeCount(node: Positioned): number {
  const data = node.data as { attributes?: { name: string }[] } | undefined;
  return data?.attributes?.length ?? 1;
}

export function estimateNodeHeight(node: Positioned): number {
  if (node.id === "__start__" || node.type === "start") {
    return START_HEIGHT;
  }
  if (isContextNode(node)) {
    return HEADER_HEIGHT + SECTION_HEIGHT + attributeCount(node) * ROW_HEIGHT;
  }
  const io = getAgentIo(agentTypeOf(node));
  const inRows = Math.min(CANVAS_IO_PREVIEW, io.inputs.length);
  const outRows = Math.min(CANVAS_IO_PREVIEW, io.outputs.length);
  const extra =
    (io.inputs.length > CANVAS_IO_PREVIEW ? 1 : 0) +
    (io.outputs.length > CANVAS_IO_PREVIEW ? 1 : 0);
  return HEADER_HEIGHT + SECTION_HEIGHT * 2 + (inRows + outRows + extra) * ROW_HEIGHT;
}

function samePointStack(nodes: Positioned[]): boolean {
  const counts = new Map<string, number>();
  for (const node of nodes) {
    if (node.id === "__start__") continue;
    const key = `${Math.round(node.position.x)}:${Math.round(node.position.y)}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.values()].some((count) => count > 1);
}

function boxesOverlap(a: Positioned, b: Positioned): boolean {
  const aRight = a.position.x + NODE_WIDTH;
  const aBottom = a.position.y + estimateNodeHeight(a);
  const bRight = b.position.x + NODE_WIDTH;
  const bBottom = b.position.y + estimateNodeHeight(b);
  return (
    a.position.x < bRight &&
    aRight > b.position.x &&
    a.position.y < bBottom &&
    aBottom > b.position.y
  );
}

export function needsAutoLayout(nodes: Positioned[]): boolean {
  if (samePointStack(nodes)) return true;
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      if (boxesOverlap(nodes[i]!, nodes[j]!)) return true;
    }
  }
  return false;
}

const CONTEXT_ORDER = ["organisation", "service", "scheduler"];

function contextKindOf(node: Positioned): string {
  if (node.type && CONTEXT_ORDER.includes(node.type)) return node.type;
  const data = node.data as { kind?: string } | undefined;
  return data?.kind ?? "";
}

function childMap(edges: Edge[]): Map<string, string[]> {
  const children = new Map<string, string[]>();
  for (const edge of edges) {
    if (!edge.source || !edge.target) continue;
    const list = children.get(edge.source) ?? [];
    list.push(edge.target);
    children.set(edge.source, list);
  }
  return children;
}

function seedSpineRanks(nodes: Node[], rank: Map<string, number>): void {
  for (const node of nodes) {
    if (node.id === "__start__" || node.type === "start") {
      rank.set(node.id, 3);
      continue;
    }
    const idx = CONTEXT_ORDER.indexOf(contextKindOf(node));
    if (idx >= 0) rank.set(node.id, idx);
  }
}

function ranksFor(nodes: Node[], edges: Edge[]): Map<string, number> {
  const children = childMap(edges);
  const rank = new Map<string, number>();
  seedSpineRanks(nodes, rank);
  const start = nodes.find((n) => n.id === "__start__")?.id ?? nodes[0]?.id;
  if (!start) return rank;
  if (!rank.has(start)) rank.set(start, 0);
  const queue = [start];
  while (queue.length) {
    const current = queue.shift()!;
    for (const next of children.get(current) ?? []) {
      if (rank.has(next)) continue;
      rank.set(next, (rank.get(current) ?? 0) + 1);
      queue.push(next);
    }
  }
  let extra = Math.max(0, ...rank.values()) + 1;
  for (const node of nodes) {
    if (rank.has(node.id)) continue;
    rank.set(node.id, extra);
    extra += 1;
  }
  return rank;
}

function bandY(
  nodes: Node[],
  bands: Map<number, string[]>,
): Map<number, number> {
  const yForRank = new Map<number, number>();
  const byId = new Map(nodes.map((node) => [node.id, node]));
  let y = ORIGIN_Y;
  const ranks = [...bands.keys()].sort((a, b) => a - b);
  for (const r of ranks) {
    yForRank.set(r, y);
    const ids = bands.get(r) ?? [];
    const tallest = Math.max(
      START_HEIGHT,
      ...ids.map((id) => estimateNodeHeight(byId.get(id) ?? { id, position: { x: 0, y: 0 } })),
    );
    y += tallest + RANK_GAP;
  }
  return yForRank;
}

function layoutRanks<T extends Node>(nodes: T[], edges: Edge[]): T[] {
  const rank = ranksFor(nodes, edges);
  const bands = new Map<number, string[]>();
  for (const [id, r] of rank) {
    const band = bands.get(r) ?? [];
    band.push(id);
    bands.set(r, band);
  }
  const yForRank = bandY(nodes, bands);
  return nodes.map((node) => {
    const r = rank.get(node.id) ?? 0;
    const band = bands.get(r) ?? [node.id];
    const index = band.indexOf(node.id);
    return {
      ...node,
      position: {
        x: ORIGIN_X + (index - (band.length - 1) / 2) * COL,
        y: yForRank.get(r) ?? ORIGIN_Y,
      },
    };
  });
}

export function applyWorkflowLayout<T extends Node>(
  nodes: T[],
  edges: Edge[],
): T[] {
  return layoutRanks(nodes, edges);
}
