"use client";

/**
 * Right-side properties panel.
 * Shows editable fields for the selected node or edge.
 */

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Divider from "@mui/material/Divider";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import TuneIcon from "@mui/icons-material/Tune";
import type { Node, Edge } from "@xyflow/react";
import { attributeRowKey } from "../contextAttributes";
import type { WorkflowNodeData, WorkflowEdgeData } from "../types";
import { isContextNode } from "../workflowGraph";
import { AgentIoPanel } from "./AgentIoPanel";
import { JOB_CONDITION_KEYS } from "../agentIoCatalogue";

interface PropertiesPanelProps {
  selectedNode: Node<WorkflowNodeData> | null;
  selectedEdge: Edge<WorkflowEdgeData> | null;
  onUpdateNode: (id: string, patch: Partial<WorkflowNodeData>) => void;
  onUpdateEdge: (id: string, patch: Partial<WorkflowEdgeData>) => void;
  onDeleteNode: (id: string) => void;
  onDeleteEdge: (id: string) => void;
}

export function PropertiesPanel({
  selectedNode,
  selectedEdge,
  onUpdateNode,
  onUpdateEdge,
  onDeleteNode,
  onDeleteEdge,
}: PropertiesPanelProps) {
  return (
    <Box
      sx={{
        width: 288,
        flexShrink: 0,
        height: "100%",
        overflowY: "auto",
        borderLeft: "1px solid #e2e8f0",
        bgcolor: "#f8fafc",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Box sx={{ px: 1.5, pt: 1.5, pb: 1 }}>
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <TuneIcon sx={{ fontSize: 15, color: "#6b7280" }} />
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              fontSize: "0.68rem",
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: 0.6,
            }}
          >
            Properties
          </Typography>
        </Stack>
      </Box>

      <Divider />

      <Box sx={{ px: 1.5, py: 1.5, flex: 1 }}>
        {selectedNode && isContextNode(selectedNode) && (
          <ContextProperties node={selectedNode} />
        )}
        {selectedNode &&
          selectedNode.type !== "start" &&
          !isContextNode(selectedNode) && (
          <NodeProperties
            node={selectedNode}
            onUpdate={(patch) => onUpdateNode(selectedNode.id, patch)}
            onDelete={() => onDeleteNode(selectedNode.id)}
          />
        )}
        {selectedEdge && (
          <EdgeProperties
            edge={selectedEdge}
            onUpdate={(patch) => onUpdateEdge(selectedEdge.id, patch)}
            onDelete={() => onDeleteEdge(selectedEdge.id)}
          />
        )}
        {!selectedNode && !selectedEdge && (
          <Typography variant="body2" sx={{ color: "#94a3b8", fontSize: "0.8rem" }}>
            Click a node or edge to see its settings here.
          </Typography>
        )}
        {selectedNode?.type === "start" && (
          <Typography variant="body2" sx={{ color: "#94a3b8", fontSize: "0.8rem" }}>
            The Start node marks where the workflow begins. It cannot be changed.
          </Typography>
        )}
      </Box>
    </Box>
  );
}

function ContextProperties({ node }: { node: Node<WorkflowNodeData> }) {
  const d = node.data;
  return (
    <Stack spacing={1.5}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.82rem" }}>
        {d.label}
      </Typography>
      <Typography variant="body2" sx={{ color: "text.secondary", fontSize: "0.8rem" }}>
        This is read-only context. It is not saved with the workflow.
        {d.derived ? " The scheduler is derived from intervals, not a Neo4j node." : ""}
      </Typography>
      {(d.attributes ?? []).map((row, index) => (
        <Stack key={attributeRowKey(row, index)} spacing={0.25}>
          <Typography sx={{ fontSize: "0.62rem", color: "text.secondary" }}>
            {row.name}
          </Typography>
          <Typography sx={{ fontSize: "0.78rem", fontFamily: "monospace", wordBreak: "break-word" }}>
            {row.value}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}

function NodeProperties({
  node,
  onUpdate,
  onDelete,
}: {
  node: Node<WorkflowNodeData>;
  onUpdate: (patch: Partial<WorkflowNodeData>) => void;
  onDelete: () => void;
}) {
  const d = node.data;

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.82rem" }}>
          {d.kind === "human" ? "Human gate" : "Agent step"}
        </Typography>
        <Tooltip title="Remove this step">
          <IconButton size="small" onClick={onDelete} aria-label="Delete step">
            <DeleteOutlineIcon sx={{ fontSize: 17, color: "#ef4444" }} />
          </IconButton>
        </Tooltip>
      </Stack>

      <TextField
        label="Label"
        size="small"
        fullWidth
        value={d.label}
        onChange={(e) => onUpdate({ label: e.target.value })}
        inputProps={{ maxLength: 80 }}
      />

      <TextField
        label="Agent type"
        size="small"
        fullWidth
        value={d.agentType}
        disabled
        helperText="Drag a new agent to replace"
      />

      <TextField
        label="Description"
        size="small"
        fullWidth
        multiline
        rows={2}
        value={d.description ?? ""}
        onChange={(e) => onUpdate({ description: e.target.value })}
        inputProps={{ maxLength: 300 }}
      />

      {d.kind !== "human" && (
        <TextField
          label="Interval (minutes)"
          size="small"
          fullWidth
          type="number"
          value={d.interval ?? ""}
          onChange={(e) =>
            onUpdate({ interval: parseInt(e.target.value, 10) || undefined })
          }
          inputProps={{ min: 1 }}
        />
      )}

      <TextField
        label="Status on ready"
        size="small"
        fullWidth
        value={d.statusOnReady ?? ""}
        onChange={(e) => onUpdate({ statusOnReady: e.target.value })}
        helperText="e.g. AWAITING_CLINICIAN_REVIEW"
        inputProps={{ maxLength: 80 }}
      />

      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={d.enabled !== false}
            onChange={(e) => onUpdate({ enabled: e.target.checked })}
          />
        }
        label={<Typography sx={{ fontSize: "0.78rem" }}>Enabled</Typography>}
      />

      {d.kind !== "human" && (
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={!!d.alwaysTrigger}
              onChange={(e) => onUpdate({ alwaysTrigger: e.target.checked })}
            />
          }
          label={
            <Typography sx={{ fontSize: "0.78rem" }}>Always triggers</Typography>
          }
        />
      )}

      {d.kind === "human" && (
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={!!d.defaultOnHitl}
              onChange={(e) => onUpdate({ defaultOnHitl: e.target.checked })}
            />
          }
          label={
            <Typography sx={{ fontSize: "0.78rem" }}>Default HITL gate</Typography>
          }
        />
      )}

      <Divider />
      <AgentIoPanel agentType={d.agentType} />
    </Stack>
  );
}

function EdgeProperties({
  edge,
  onUpdate,
  onDelete,
}: {
  edge: Edge<WorkflowEdgeData>;
  onUpdate: (patch: Partial<WorkflowEdgeData>) => void;
  onDelete: () => void;
}) {
  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.82rem" }}>
          Connection
        </Typography>
        <Tooltip title="Remove this connection">
          <IconButton size="small" onClick={onDelete} aria-label="Delete connection">
            <DeleteOutlineIcon sx={{ fontSize: 17, color: "#ef4444" }} />
          </IconButton>
        </Tooltip>
      </Stack>

      <TextField
        label="Condition (optional)"
        size="small"
        fullWidth
        multiline
        rows={3}
        value={edge.data?.condition ?? ""}
        onChange={(e) => onUpdate({ condition: e.target.value })}
        helperText='JSONPath condition, e.g. $.result == "approved". Leave blank for unconditional.'
        inputProps={{ maxLength: 500, style: { fontFamily: "monospace", fontSize: "0.76rem" } }}
      />

      <Typography sx={{ fontSize: "0.66rem", fontWeight: 700, color: "text.secondary" }}>
        Common job keys
      </Typography>
      {JOB_CONDITION_KEYS.map((key) => (
        <Typography
          key={key}
          sx={{
            fontSize: "0.62rem",
            fontFamily: "monospace",
            color: "text.secondary",
            wordBreak: "break-all",
            cursor: "pointer",
          }}
          onClick={() => onUpdate({ condition: key })}
        >
          {key}
        </Typography>
      ))}
    </Stack>
  );
}
