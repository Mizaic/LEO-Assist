"use client";

import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { addEdge, applyEdgeChanges, applyNodeChanges, type Connection, type Edge, type EdgeChange, type Node, type NodeChange } from "@xyflow/react";
import { api } from "@/lib/api";
import { DEFAULT_CONFIG, type ActionConfig, type PlanData } from "../config/types";

interface PathwayState {
  planName: string;
  planDescription: string;
  planStatus: string;
  triggerEvent: string;
  nodes: Node[];
  edges: Edge[];
  nodeConfigs: Record<string, ActionConfig>;
  selectedNodeId: string | null;
  panelOpen: boolean;
  subgraphDescriptors: Array<{ id: string; label: string; description: string; reads: string[]; writes: string[] }>;

  setPlanName: (name: string) => void;
  setPlanDescription: (description: string) => void;
  setPlanStatus: (status: string) => void;
  setTriggerEvent: (event: string) => void;
  setSelectedNode: (id: string | null) => void;
  setPanelOpen: (open: boolean) => void;
  loadPlan: (data: PlanData, openConfigurator: (nodeId: string) => void) => void;
  updateNodeConfig: (nodeId: string, config: ActionConfig) => void;
  addNode: (node: Node, config: ActionConfig) => void;
  deleteNode: (nodeId: string) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  onNodesChange: (changes: NodeChange[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  onConnect: (connection: Connection) => void;
  loadSubgraphDescriptors: () => Promise<void>;
}

export const usePathwayStore = create<PathwayState>()(
  immer((set) => ({
    planName: "",
    planDescription: "",
    planStatus: "draft",
    triggerEvent: "",
    nodes: [],
    edges: [],
    nodeConfigs: {},
    selectedNodeId: null,
    panelOpen: false,
    subgraphDescriptors: [],

    setPlanName: (planName) => set((s) => { s.planName = planName; }),
    setPlanDescription: (planDescription) => set((s) => { s.planDescription = planDescription; }),
    setPlanStatus: (planStatus) => set((s) => { s.planStatus = planStatus; }),
    setTriggerEvent: (triggerEvent) => set((s) => { s.triggerEvent = triggerEvent; }),
    setSelectedNode: (selectedNodeId) => set((s) => { s.selectedNodeId = selectedNodeId; }),
    setPanelOpen: (panelOpen) => set((s) => { s.panelOpen = panelOpen; }),
    setNodes: (nodes) => set((s) => { s.nodes = nodes; }),
    setEdges: (edges) => set((s) => { s.edges = edges; }),
    onNodesChange: (changes) => set((s) => { s.nodes = applyNodeChanges(changes, s.nodes); }),
    onEdgesChange: (changes) => set((s) => { s.edges = applyEdgeChanges(changes, s.edges); }),
    onConnect: (connection) => set((s) => {
      const edgeId = `${connection.source}:${connection.sourceHandle ?? "_"}->${connection.target}:${connection.targetHandle ?? "_"}`;
      s.edges = addEdge({ ...connection, id: edgeId, type: "portEdge", data: { label: connection.sourceHandle || connection.targetHandle || "" } }, s.edges);
    }),

    loadPlan: (data, openConfigurator) => set((s) => {
      s.planName = data.name || "";
      s.planDescription = data.description || "";
      s.planStatus = data.status || "draft";
      s.triggerEvent = data.trigger?.event || "";
      const configs: Record<string, ActionConfig> = {};
      s.nodes = (data.actions || []).map((a, i) => {
        const cfg: ActionConfig = { ...DEFAULT_CONFIG, subgraphId: a.subgraphId, label: a.label || a.subgraphId, ...a.config, params: (a.config as ActionConfig)?.params ?? {} };
        configs[a.id] = cfg;
        return {
          id: a.id,
          type: (a.nodeType as string) || "action",
          position: a.position || { x: 250, y: 100 + i * 150 },
          data: {
            label: a.label || a.subgraphId,
            subgraphId: a.subgraphId,
            nodeType: a.nodeType || "action",
            onConfigure: () => openConfigurator(a.id),
          },
        } as Node;
      });
      s.nodeConfigs = configs;
      s.edges = (data.edges || []).map((e, i) => ({
        id: `e${i}`,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle,
        targetHandle: e.targetHandle,
        type: "portEdge",
        data: { label: e.sourceHandle || e.targetHandle || "" },
      }));
    }),

    updateNodeConfig: (nodeId, config) => set((s) => {
      s.nodeConfigs[nodeId] = config;
      s.nodes = s.nodes.map((n) => (n.id === nodeId ? { ...n, type: config.nodeType || "action", data: { ...n.data, label: config.label, subgraphId: config.subgraphId, nodeType: config.nodeType || "action" } } : n));
    }),
    addNode: (node, config) => set((s) => {
      s.nodes.push(node);
      s.nodeConfigs[node.id] = config;
    }),
    deleteNode: (nodeId) => set((s) => {
      s.nodes = s.nodes.filter((n) => n.id !== nodeId);
      s.edges = s.edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
      delete s.nodeConfigs[nodeId];
    }),

    loadSubgraphDescriptors: async () => {
      try {
        const payload = await api.get<{ subgraphs?: Array<{ id: string; label: string; description: string; reads: string[]; writes: string[] }> }>("/pipeline/subgraphs");
        set((s) => { s.subgraphDescriptors = payload.subgraphs ?? []; });
      } catch {
        set((s) => { s.subgraphDescriptors = []; });
      }
    },
  })),
);

