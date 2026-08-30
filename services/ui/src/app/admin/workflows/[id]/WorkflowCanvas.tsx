"use client";

/**
 * WorkflowCanvas -- the full 3-panel editor.
 *
 * Layout: [AgentPalette] | [ReactFlow canvas] | [PropertiesPanel]
 * The canvas fills the remaining vertical space (100vh minus the app shell).
 */

import { useCallback, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
  type NodeMouseHandler,
  type EdgeMouseHandler,
  type OnSelectionChangeFunc,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import { useRouter } from "next/navigation";

import { AgentPalette } from "./AgentPalette";
import { PropertiesPanel } from "./PropertiesPanel";
import { AgentNode } from "./nodes/AgentNode";
import { ContextNode } from "./nodes/ContextNode";
import { HumanNode } from "./nodes/HumanNode";
import { StartNode } from "./nodes/StartNode";
import { useWorkflowEditor } from "./useWorkflowEditor";
import type { WorkflowNodeData, WorkflowEdgeData } from "../types";
import type { Node, Edge } from "@xyflow/react";

const NODE_TYPES = {
  agent: AgentNode,
  human: HumanNode,
  start: StartNode,
  service: ContextNode,
  organisation: ContextNode,
  scheduler: ContextNode,
};

// -- Inner canvas (needs ReactFlow context) --------------------------------

function CanvasInner({ workflowId }: { workflowId: string }) {
  const router = useRouter();
  const rf = useReactFlow();
  const canvasRef = useRef<HTMLDivElement>(null);

  const ed = useWorkflowEditor(workflowId);

  const onNodeClick: NodeMouseHandler<Node<WorkflowNodeData>> = useCallback(
    (_, node) => {
      ed.setSelectedNodeId(node.id);
      ed.setSelectedEdgeId(null);
    },
    [ed]
  );

  const onEdgeClick: EdgeMouseHandler<Edge<WorkflowEdgeData>> = useCallback(
    (_, edge) => {
      ed.setSelectedEdgeId(edge.id);
      ed.setSelectedNodeId(null);
    },
    [ed]
  );

  const onSelectionChange: OnSelectionChangeFunc = useCallback(
    ({ nodes: n, edges: e }) => {
      const node = n[0];
      if (node) {
        ed.setSelectedNodeId(node.id);
        ed.setSelectedEdgeId(null);
        return;
      }
      const edge = e[0];
      if (edge) {
        ed.setSelectedEdgeId(edge.id);
        ed.setSelectedNodeId(null);
        return;
      }
      ed.setSelectedNodeId(null);
      ed.setSelectedEdgeId(null);
    },
    [ed.setSelectedNodeId, ed.setSelectedEdgeId]
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      if (!canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      ed.onDrop(e, rect, rf.screenToFlowPosition);
    },
    [ed, rf]
  );

  if (ed.loading) {
    return (
      <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <CircularProgress size={32} />
      </Box>
    );
  }

  if (ed.error) {
    return (
      <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", p: 4 }}>
        <Alert severity="error" sx={{ maxWidth: 480 }}>
          {ed.error}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, minWidth: 0 }}>
      {/* Top toolbar */}
      <Box
        sx={{
          px: 2,
          py: 1,
          borderBottom: "1px solid #e2e8f0",
          bgcolor: "#fff",
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          flexShrink: 0,
        }}
      >
        <Button
          size="small"
          startIcon={<ArrowBackIcon fontSize="small" />}
          onClick={() => router.push("/admin/workflows")}
          sx={{ textTransform: "none", color: "text.secondary" }}
        >
          Workflows
        </Button>
        <Typography
          variant="subtitle2"
          sx={{ fontWeight: 700, flex: 1, fontSize: "0.9rem", color: "text.primary" }}
        >
          {ed.workflowName}
        </Typography>
        {ed.isDirty && (
          <Typography variant="caption" sx={{ color: "text.disabled" }}>
            Unsaved changes
          </Typography>
        )}
        <Button
          size="small"
          variant="contained"
          startIcon={
            ed.saving
              ? <CircularProgress size={12} sx={{ color: "#fff" }} />
              : <SaveOutlinedIcon fontSize="small" />
          }
          disabled={ed.saving || !ed.isDirty}
          onClick={() => void ed.save()}
          sx={{ textTransform: "none" }}
        >
          {ed.saving ? "Saving..." : "Save"}
        </Button>
      </Box>

      {/* 3-panel body */}
      <Box sx={{ display: "flex", flex: 1, minHeight: 0 }}>
        <AgentPalette />

        {/* React Flow canvas */}
        <Box
          ref={canvasRef}
          sx={{ flex: 1, minWidth: 0, height: "100%", bgcolor: "#f0f4f8" }}
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
          <ReactFlow
            nodes={ed.nodes}
            edges={ed.edges}
            nodeTypes={NODE_TYPES}
            onNodesChange={ed.onNodesChange}
            onEdgesChange={ed.onEdgesChange}
            onConnect={ed.onConnect}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onSelectionChange={onSelectionChange}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            deleteKeyCode={["Backspace", "Delete"]}
            proOptions={{ hideAttribution: true }}
            style={{ width: "100%", height: "100%" }}
          >
            <Background gap={20} size={1} color="#cbd5e1" />
            <Controls />
            <MiniMap
              nodeColor={(n) => {
                if (n.type === "human") return "#9338ff";
                if (n.type === "start") return "#002178";
                return "#0d46d6";
              }}
              maskColor="rgba(0,0,0,0.04)"
            />
          </ReactFlow>
        </Box>

        <PropertiesPanel
          selectedNode={ed.selectedNode}
          selectedEdge={ed.selectedEdge}
          onUpdateNode={ed.updateNode}
          onUpdateEdge={ed.updateEdge}
          onDeleteNode={ed.deleteNode}
          onDeleteEdge={ed.deleteEdge}
        />
      </Box>

      <Snackbar
        open={!!ed.saveError}
        autoHideDuration={6000}
        onClose={() => ed.setSaveError(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="error" onClose={() => ed.setSaveError(null)}>
          {ed.saveError}
        </Alert>
      </Snackbar>
    </Box>
  );
}

// -- Public export (wraps with provider) -----------------------------------

export function WorkflowCanvas({ workflowId }: { workflowId: string }) {
  return (
    <ReactFlowProvider>
      <CanvasInner workflowId={workflowId} />
    </ReactFlowProvider>
  );
}
