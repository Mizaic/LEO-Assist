/**
 * Zipkin-style pipeline endpoint flow graph (React Flow + dagre).
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */
"use client";

import { useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import {
  Background,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";

import { statusColor } from "../RunSheetTasks";
import type { LabPlanEdge, LabPlanStep, LabTraceSpan } from "../inspectorTypes";
import {
  buildFlowEndpoints,
  resolveFlowLinks,
  type FlowEndpoint,
} from "./traceFlowUtils";
import { formatDurationLabel } from "./traceWaterfallUtils";

const NODE_WIDTH = 148;
const NODE_HEIGHT = 56;

type EndpointNodeData = FlowEndpoint & { selected: boolean };

function EndpointNode({ data }: NodeProps) {
  const item = data as EndpointNodeData;
  return (
    <Box
      sx={{
        width: NODE_WIDTH,
        px: 1,
        py: 0.75,
        borderRadius: 1,
        border: "2px solid",
        borderColor: item.selected ? "primary.main" : item.borderColor,
        bgcolor: "background.paper",
        boxShadow: item.selected ? 2 : 0,
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0.35 }} />
      <Typography variant="caption" fontWeight={700} noWrap>
        {item.label}
      </Typography>
      <Typography variant="caption" color="text.secondary" noWrap display="block">
        {item.subgraphId || item.nodeType}
      </Typography>
      <Typography variant="caption" color={statusColor(item.status)} display="block">
        {item.status} · {formatDurationLabel(item.durationMs)}
      </Typography>
      <Handle type="source" position={Position.Right} style={{ opacity: 0.35 }} />
    </Box>
  );
}

const nodeTypes = { endpoint: EndpointNode };

function layoutFlow(
  nodes: Node[],
  edges: Edge[],
): Node[] {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "LR", nodesep: 28, ranksep: 72 });
  graph.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((node) => {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });
  edges.forEach((edge) => {
    if (edge.source && edge.target) graph.setEdge(edge.source, edge.target);
  });
  dagre.layout(graph);
  return nodes.map((node) => {
    const pos = graph.node(node.id);
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    };
  });
}

function buildGraph(
  planSteps: LabPlanStep[],
  planEdges: LabPlanEdge[] | undefined,
  spans: LabTraceSpan[],
  selectedStepId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  const links = resolveFlowLinks(planSteps, planEdges);
  const endpoints = buildFlowEndpoints(planSteps, spans);
  const nodes: Node[] = endpoints.map((endpoint) => ({
    id: endpoint.id,
    type: "endpoint",
    position: { x: 0, y: 0 },
    data: { ...endpoint, selected: selectedStepId === endpoint.id },
    selectable: true,
  }));
  const edges: Edge[] = links.map((link) => {
    const target = endpoints.find((item) => item.id === link.target);
    const active = target?.status === "running";
    return {
      id: `${link.source}->${link.target}`,
      source: link.source,
      target: link.target,
      animated: active,
      style: {
        stroke: target ? target.borderColor : "#94a3b8",
        strokeWidth: 2,
      },
      label: link.relationship === "after-end" ? undefined : link.relationship,
    };
  });
  return { nodes: layoutFlow(nodes, edges), edges };
}

interface Props {
  planSteps: LabPlanStep[];
  planEdges?: LabPlanEdge[];
  spans: LabTraceSpan[];
  selectedStepId: string | null;
  onSelectStep: (id: string | null) => void;
}

export function TraceFlowGraph({
  planSteps,
  planEdges,
  spans,
  selectedStepId,
  onSelectStep,
}: Props) {
  const graph = useMemo(
    () => buildGraph(planSteps, planEdges, spans, selectedStepId),
    [planSteps, planEdges, spans, selectedStepId],
  );

  if (!planSteps.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        Plan steps not loaded yet.
      </Typography>
    );
  }

  return (
    <Box
      sx={{ width: "100%", height: 280, minHeight: 220 }}
      data-testid="validation-lab-inspector-flow-graph"
    >
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        zoomOnScroll
        onNodeClick={(_, node) => onSelectStep(node.id)}
        onPaneClick={() => onSelectStep(null)}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} color="#e2e8f0" />
      </ReactFlow>
    </Box>
  );
}
