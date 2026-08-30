"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Node,
  type Edge,
} from "@xyflow/react";
import type { WorkflowNodeData, WorkflowEdgeData, WorkflowGraph } from "../types";
import { getWorkflowGraph, saveWorkflowGraph } from "../workflowApi";
import { applyWorkflowLayout, needsAutoLayout } from "../workflowLayout";
import { ensureContextSpineEdges, flowToSaveGraph, isContextNode } from "../workflowGraph";
import { CATALOGUE_BY_TYPE } from "../agentCatalogue";

const START_NODE_ID = "__start__";

function makeStartNode(): Node<WorkflowNodeData> {
  return {
    id: START_NODE_ID,
    type: "start",
    position: { x: 200, y: 40 },
    data: {
      agentType: "__start__",
      label: "Start",
      kind: "agent",
    },
    deletable: false,
  };
}

function graphToFlow(graph: WorkflowGraph): {
  nodes: Node<WorkflowNodeData>[];
  edges: Edge<WorkflowEdgeData>[];
} {
  if (!graph.nodes.length) {
    return { nodes: [makeStartNode()], edges: [] };
  }
  const seenNodes = new Set<string>();
  const nodes = (graph.nodes as Node<WorkflowNodeData>[]).filter((node) => {
    if (seenNodes.has(node.id)) return false;
    seenNodes.add(node.id);
    return true;
  });
  const seen = new Set<string>();
  const edges = (graph.edges as Edge<WorkflowEdgeData>[]).map((edge, index) => {
    let id = edge.id || `e-${edge.source}-${edge.target}-${index}`;
    if (seen.has(id)) id = `${id}-${index}`;
    seen.add(id);
    return { ...edge, id };
  });
  const spineEdges = ensureContextSpineEdges(nodes, edges);
  const laid = needsAutoLayout(nodes)
    ? applyWorkflowLayout(nodes, spineEdges)
    : nodes;
  return { nodes: laid, edges: spineEdges };
}


export function useWorkflowEditor(workflowId: string) {
  const [workflowName, setWorkflowName] = useState("Workflow");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<WorkflowNodeData>>([makeStartNode()]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<WorkflowEdgeData>>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const idCounterRef = useRef(1);

  // -- Load ---------------------------------------------------------------
  useEffect(() => {
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const graph = await getWorkflowGraph(workflowId);
        setWorkflowName(graph.workflowName);
        const { nodes: n, edges: e } = graphToFlow(graph);
        setNodes(n);
        setEdges(e);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Could not load this workflow."
        );
      } finally {
        setLoading(false);
      }
    })();
  }, [workflowId, setNodes, setEdges]);

  // -- Connect ------------------------------------------------------------
  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge({ ...connection, data: {} }, eds));
      setIsDirty(true);
    },
    [setEdges]
  );

  // -- Drop agent from palette --------------------------------------------
  const onDrop = useCallback(
    (e: React.DragEvent, canvasRect: DOMRect, screenToFlowCoords: (p: { x: number; y: number }) => { x: number; y: number }) => {
      e.preventDefault();
      const raw = e.dataTransfer.getData("application/leo-agent");
      if (!raw) return;

      let payload: { agentType: string; label: string; kind: string };
      try { payload = JSON.parse(raw); } catch { return; }

      const def = CATALOGUE_BY_TYPE[payload.agentType];
      const position = screenToFlowCoords({
        x: e.clientX - canvasRect.left,
        y: e.clientY - canvasRect.top,
      });

      const newId = `node-${Date.now()}-${idCounterRef.current++}`;
      const newNode: Node<WorkflowNodeData> = {
        id: newId,
        type: payload.kind === "human" ? "human" : "agent",
        position,
        data: {
          agentType: payload.agentType,
          label: payload.label,
          kind: payload.kind as WorkflowNodeData["kind"],
          interval: def?.interval,
          alwaysTrigger: def?.alwaysTrigger,
          statusOnReady: def?.statusOnReady,
          description: def?.description,
        },
      };
      setNodes((nds) => [...nds, newNode]);
      setIsDirty(true);
    },
    [setNodes]
  );

  // -- Update node data ---------------------------------------------------
  const updateNode = useCallback(
    (id: string, patch: Partial<WorkflowNodeData>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === id ? { ...n, data: { ...n.data, ...patch } } : n
        )
      );
      setIsDirty(true);
    },
    [setNodes]
  );

  // -- Update edge data ---------------------------------------------------
  const updateEdge = useCallback(
    (id: string, patch: Partial<WorkflowEdgeData>) => {
      setEdges((eds) =>
        eds.map((e) =>
          e.id === id ? { ...e, data: { ...e.data, ...patch } } : e
        )
      );
      setIsDirty(true);
    },
    [setEdges]
  );

  // -- Delete node --------------------------------------------------------
  const deleteNode = useCallback(
    (id: string) => {
      const target = nodes.find((n) => n.id === id);
      if (id === START_NODE_ID || (target && isContextNode(target))) return;
      setNodes((nds) => nds.filter((n) => n.id !== id));
      setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
      setSelectedNodeId(null);
      setIsDirty(true);
    },
    [nodes, setNodes, setEdges]
  );

  // -- Delete edge --------------------------------------------------------
  const deleteEdge = useCallback(
    (id: string) => {
      setEdges((eds) => eds.filter((e) => e.id !== id));
      setSelectedEdgeId(null);
      setIsDirty(true);
    },
    [setEdges]
  );

  // -- Save ---------------------------------------------------------------
  const save = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await saveWorkflowGraph(workflowId, flowToSaveGraph(nodes, edges));
      setIsDirty(false);
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "Could not save. Please try again."
      );
    } finally {
      setSaving(false);
    }
  }, [workflowId, nodes, edges]);

  const selectedNode =
    selectedNodeId ? (nodes.find((n) => n.id === selectedNodeId) ?? null) : null;
  const selectedEdge =
    selectedEdgeId ? (edges.find((e) => e.id === selectedEdgeId) ?? null) : null;

  return {
    workflowName,
    nodes,
    edges,
    loading,
    saving,
    error,
    saveError,
    setSaveError,
    isDirty,
    selectedNode,
    selectedEdge,
    setSelectedNodeId,
    setSelectedEdgeId,
    onNodesChange: (changes: Parameters<typeof onNodesChange>[0]) => {
      onNodesChange(changes);
      // Mark dirty only for user-driven changes, not React Flow's own
      // internal position/dimension recalculations.
      const isDriven = changes.some(
        (c) => c.type === "remove" || (c.type === "position" && c.dragging)
      );
      if (isDriven) setIsDirty(true);
    },
    onEdgesChange: (changes: Parameters<typeof onEdgesChange>[0]) => {
      onEdgesChange(changes);
      const isDriven = changes.some((c) => c.type === "remove");
      if (isDriven) setIsDirty(true);
    },
    onConnect,
    onDrop,
    updateNode,
    updateEdge,
    deleteNode,
    deleteEdge,
    save,
  };
}
