/**
 * Block-based condition editor for the "Who is this rule about?" step.
 *
 * Replaces SentenceCanvas as the primary editing surface. Instead of
 * a fixed who-card + pathway-cards layout, the editor shows the rule
 * as a vertical stack of independently-typed condition blocks:
 *
 *   Block 1  [ALL OF THESE]   -- Patient's age >= 18
 *   --- AND ---
 *   Block 2  [ANY OF THESE]   -- Mycoplasma  /  Occult blood
 *   --- AND ---
 *   [+ Add a condition block]
 *
 * Each block maps to one child of the AND root (or the root itself
 * when the root is not AND). Within a block the user can:
 *   - Change the block type (ALL / ANY / NONE / AT LEAST N)
 *   - Add symptoms, patient details, or lab values
 *   - Remove individual items or the whole block
 *
 * Atlas trace:  DO: DO-D6CE2AA5  DI: DI-A3107424
 */
"use client";

import * as React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import SentenceRow from "./SentenceRow";
import { assignNodeIds, canHaveChildren } from "./treeOps";
import type { SentenceRowModel } from "./treeToCanvas";
import type { EditableLogicNode, LogicNodeKind, NodeUpdate } from "./types";

export interface BlockEditorProps {
  tree: EditableLogicNode;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}

export default function BlockEditor(props: BlockEditorProps) {
  const { tree } = props;
  const isAndRoot = tree.kind === "AND";
  const blocks: EditableLogicNode[] = isAndRoot
    ? (tree.children ?? [])
    : [tree];

  return (
    <Stack spacing={0}>
      {blocks.map((block, i) => (
        <React.Fragment key={block.node_id}>
          {i > 0 && <AndConnector />}
          <ConditionBlock
            block={block}
            isDeletable={blocks.length > 1}
            onRemoveBlock={() =>
              props.onUpdate({ kind: "remove", nodeId: block.node_id })
            }
            {...props}
          />
        </React.Fragment>
      ))}
      <AndConnector faint />
      <AddBlockBar root={tree} onUpdate={props.onUpdate} />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// AndConnector
// ---------------------------------------------------------------------------

function AndConnector({ faint = false }: { faint?: boolean }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", my: 0.75, gap: 1 }}>
      <Divider
        sx={{ flex: 1, borderColor: faint ? "divider" : "text.secondary" }}
      />
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          letterSpacing: 0.8,
          color: faint ? "text.disabled" : "text.secondary",
          px: 0.5,
        }}
      >
        AND
      </Typography>
      <Divider
        sx={{ flex: 1, borderColor: faint ? "divider" : "text.secondary" }}
      />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// ConditionBlock
// ---------------------------------------------------------------------------

interface ConditionBlockProps extends BlockEditorProps {
  block: EditableLogicNode;
  isDeletable: boolean;
  onRemoveBlock: () => void;
}

function ConditionBlock({
  block,
  isDeletable,
  onRemoveBlock,
  selectedNodeId,
  onSelectNode,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
}: ConditionBlockProps) {
  const isGroup = canHaveChildren(block.kind);
  const rows = blockRows(block);

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        bgcolor: "background.paper",
        boxShadow:
          "0 1px 2px rgba(15,23,42,0.04), 0 4px 12px rgba(15,23,42,0.04)",
        overflow: "hidden",
      }}
    >
      {isGroup && (
        <BlockHeader
          nodeId={block.node_id}
          kind={block.kind}
          min={block.min}
          isDeletable={isDeletable}
          onRemove={onRemoveBlock}
          onUpdate={onUpdate}
        />
      )}

      <Box sx={{ p: 1.5 }}>
        {rows.length === 0 ? (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ fontStyle: "italic", mb: 0.75 }}
          >
            This block is empty. Add a condition below.
          </Typography>
        ) : (
          <Stack spacing={0.75} sx={{ mb: 1 }}>
            {rows.map((row) => (
              <SentenceRow
                key={row.nodeId}
                row={row}
                selectedNodeId={selectedNodeId}
                onSelectConcept={onSelectNode}
                onRequestAdd={onRequestAdd}
                onRequestCoach={onRequestCoach}
                onUpdate={onUpdate}
              />
            ))}
          </Stack>
        )}

        {isGroup && (
          <BlockAddBar
            parentNodeId={block.node_id}
            blockKind={block.kind}
            onUpdate={onUpdate}
            onRequestAdd={onRequestAdd}
          />
        )}

        {!isGroup && isDeletable && (
          <Tooltip title="Remove this condition">
            <IconButton
              size="small"
              aria-label="Remove condition"
              onClick={onRemoveBlock}
              sx={{ mt: 0.25, color: "text.secondary", "&:hover": { color: "error.main" } }}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// BlockHeader
// ---------------------------------------------------------------------------

const KIND_LABELS: Partial<Record<LogicNodeKind, string>> = {
  OR: "ANY of these",
  AND: "ALL of these",
  NOT: "NONE of these",
  AT_LEAST: "AT LEAST",
};

interface BlockHeaderProps {
  nodeId: string;
  kind: LogicNodeKind;
  min?: number;
  isDeletable: boolean;
  onRemove: () => void;
  onUpdate: (update: NodeUpdate) => void;
}

function BlockHeader({
  nodeId,
  kind,
  isDeletable,
  onRemove,
  onUpdate,
}: BlockHeaderProps) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1,
        px: 1.5,
        py: 0.75,
        borderBottom: "1px solid",
        borderColor: "divider",
        bgcolor: "grey.50",
      }}
    >
      <Select
        size="small"
        value={kind}
        onChange={(e) =>
          onUpdate({
            kind: "change_kind",
            nodeId,
            newKind: e.target.value as LogicNodeKind,
          })
        }
        sx={{
          fontSize: "0.78rem",
          fontWeight: 700,
          height: 28,
          "& .MuiOutlinedInput-notchedOutline": { borderColor: "divider" },
          bgcolor: "background.paper",
        }}
        inputProps={{ "aria-label": "Block type" }}
      >
        <MenuItem value="AND">ALL of these must match</MenuItem>
        <MenuItem value="OR">ANY of these can match</MenuItem>
        <MenuItem value="NOT">NONE of these must match</MenuItem>
        <MenuItem value="AT_LEAST">AT LEAST N must match</MenuItem>
      </Select>
      <Box sx={{ flex: 1 }} />
      {isDeletable && (
        <Tooltip title="Remove this block">
          <IconButton
            size="small"
            aria-label="Remove block"
            onClick={onRemove}
            sx={{ color: "text.secondary", "&:hover": { color: "error.main" } }}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// BlockAddBar  (add items inside a block)
// ---------------------------------------------------------------------------

interface BlockAddBarProps {
  parentNodeId: string;
  blockKind: LogicNodeKind;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
}

function BlockAddBar({ parentNodeId, onUpdate, onRequestAdd }: BlockAddBarProps) {
  return (
    <Stack direction="row" spacing={0.75} flexWrap="wrap" sx={{ rowGap: 0.5 }}>
      <AddChip
        label="Add a symptom or sign"
        onClick={(anchor) => onRequestAdd(parentNodeId, anchor)}
      />
      <AddChip
        label="Add a patient detail"
        onClick={() =>
          onUpdate({ kind: "add_demographic", parentNodeId })
        }
      />
      <AddChip
        label="Add a lab value or reading"
        onClick={(anchor) => onRequestAdd(parentNodeId, anchor)}
      />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// AddBlockBar  (add a new top-level block)
// ---------------------------------------------------------------------------

interface AddBlockBarProps {
  root: EditableLogicNode;
  onUpdate: (update: NodeUpdate) => void;
}

function AddBlockBar({ root, onUpdate }: AddBlockBarProps) {
  function addBlock(groupKind: "AND" | "OR" | "NOT") {
    if (root.kind !== "AND") {
      const wrapped = assignNodeIds({
        kind: "AND",
        children: [root, { kind: groupKind, children: [] }],
      });
      onUpdate({ kind: "replace_root", node: wrapped });
      return;
    }
    onUpdate({ kind: "add_group", parentNodeId: root.node_id, groupKind });
  }

  return (
    <Box sx={{ mt: 0.5 }}>
      <Stack direction="row" spacing={0.75} flexWrap="wrap" sx={{ rowGap: 0.5 }}>
        <AddChip
          label="Add condition block (ALL)"
          icon
          onClick={() => addBlock("AND")}
        />
        <AddChip
          label="Add condition block (ANY)"
          icon
          onClick={() => addBlock("OR")}
        />
        <AddChip
          label="Add condition block (NONE)"
          icon
          onClick={() => addBlock("NOT")}
        />
      </Stack>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// AddChip
// ---------------------------------------------------------------------------

interface AddChipProps {
  label: string;
  icon?: boolean;
  onClick: (anchor: HTMLElement) => void;
}

function AddChip({ label, icon = false, onClick }: AddChipProps) {
  return (
    <Chip
      icon={icon ? <AddIcon sx={{ fontSize: 13 }} /> : undefined}
      label={label}
      size="small"
      variant="outlined"
      onClick={(e) => onClick(e.currentTarget)}
      sx={{
        height: 26,
        fontSize: "0.72rem",
        fontWeight: 500,
        borderRadius: 1.5,
        cursor: "pointer",
        borderStyle: icon ? "dashed" : "solid",
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function nodeToRowVariant(kind: LogicNodeKind): SentenceRowModel["variant"] {
  if (kind === "CONCEPT") return "concept";
  if (kind === "DEMOGRAPHIC") return "demographic";
  if (kind === "OBSERVATION") return "observation";
  if (kind === "AT_LEAST") return "at_least";
  return "unsupported";
}

function blockRows(block: EditableLogicNode): SentenceRowModel[] {
  if (!canHaveChildren(block.kind)) {
    return [
      {
        nodeId: block.node_id,
        variant: nodeToRowVariant(block.kind),
        node: block,
      },
    ];
  }
  return (block.children ?? []).map((child) => ({
    nodeId: child.node_id,
    variant: nodeToRowVariant(child.kind),
    node: child,
  }));
}
