"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Core replacement for LogicTreeEditor/GroupBody.tsx: renders a group
 * as flowing prose instead of a bordered, indented box.
 *
 * A clickable lead-in phrase names the group's kind (reusing the exact
 * copy.ts wording the Advanced view's kind Select already shows, so
 * switching views never changes the vocabulary a reviewer sees), then
 * every child flows inline after it, joined with the same and/or/and-not
 * grammar as treeToSentence.ts's read-only preview.
 *
 * A child that is itself a group (AND/OR/NOT/AT_LEAST) renders
 * recursively as another GroupSentence, wrapped in a soft-tinted
 * rounded "chunk" (color from KIND_TINTS) instead of the boxed view's
 * border+indent, so nesting stays visually contained without breaking
 * the reading flow. Chunks at depth >= 2 start collapsed to a one-line
 * summary, mirroring GroupBody's auto-collapse behaviour exactly.
 */
import { useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { GROUP_KIND_LABELS, atLeastClusterLabel } from "../copy";
import { GROUP_KINDS, type LogicNodeKind, type NodeUpdate } from "../types";
import { KIND_CONNECTOR, type NodeProps } from "../LogicTreeEditor/shared";
import { describeChildren } from "../LogicTreeEditor/GroupBody";
import AddInlineLinks from "./AddInlineLinks";
import { KIND_TINT_BORDERS, KIND_TINTS, joinNodes } from "./shared";
import SentenceNodeDispatcher from "./SentenceNodeDispatcher";

type Props = NodeProps & { isTopLevel?: boolean };

/**
 * Matches GroupBody's isPureAtLeast fast path: an AT_LEAST group whose
 * children are all plain CONCEPT leaves is rendered as a distinct blue
 * "cluster" pill (not the generic AND/OR/NOT chunk tint), and that pill
 * shows up even when the cluster is the literal root of the tree -- the
 * same precedence InlineAtLeast has over isTopLevel in GroupBody.tsx.
 */
function isPureConceptAtLeast(node: Props["node"]): boolean {
  const children = node.children ?? [];
  return node.kind === "AT_LEAST" && children.length >= 1 && children.every((c) => c.kind === "CONCEPT");
}

export default function GroupSentence(props: Props) {
  const { node, isTopLevel } = props;
  const pureCluster = isPureConceptAtLeast(node);
  // Pure-CONCEPT AT_LEAST clusters never auto-collapse, matching
  // InlineAtLeast in GroupBody.tsx -- it has no collapsed state at all.
  const [collapsed, setCollapsed] = useState(
    !isTopLevel && !pureCluster && props.depth >= 2,
  );
  const leadInLabel =
    node.kind === "AT_LEAST" ? atLeastClusterLabel(node.min ?? 1) : GROUP_KIND_LABELS[node.kind];
  const hasOuterWrapper = !isTopLevel || pureCluster;
  const body = (
    <GroupSentenceBody
      {...props}
      leadInLabel={leadInLabel}
      collapsed={collapsed}
      onToggleCollapse={() => setCollapsed((v) => !v)}
      showControls={hasOuterWrapper}
      restrictAddToConcepts={pureCluster}
      hasOuterWrapper={hasOuterWrapper}
      showChevron={!isTopLevel && !pureCluster}
    />
  );

  if (!hasOuterWrapper) return body;

  return (
    <Box
      component="span"
      role="group"
      aria-label={leadInLabel}
      aria-expanded={!collapsed}
      sx={{
        display: "inline-flex",
        bgcolor: pureCluster ? "primary.50" : KIND_TINTS[node.kind] ?? "action.hover",
        border: "1px solid",
        borderColor: pureCluster ? "primary.100" : KIND_TINT_BORDERS[node.kind] ?? "divider",
        borderRadius: 2,
        px: 1,
        py: 0.5,
      }}
    >
      {body}
    </Box>
  );
}

interface BodyProps extends Props {
  leadInLabel: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
  /** Show the remove-group button (and, for nested chunks, the collapse
   *  chevron). True for every non-top-level group, and also true for a
   *  top-level pure-CONCEPT AT_LEAST cluster (see isPureConceptAtLeast). */
  showControls: boolean;
  /** Pure-CONCEPT AT_LEAST clusters only ever accept more concepts, so
   *  the multi-type AddInlineLinks menu collapses to a single "Add" link,
   *  matching InlineAtLeast's single Chip in GroupBody.tsx. */
  restrictAddToConcepts: boolean;
  /** True whenever GroupSentence renders the tinted/pill outer <Box>
   *  (every non-top-level chunk, plus a top-level pure-CONCEPT cluster).
   *  That Box already carries role="group" + the lead-in label, so this
   *  Stack must not duplicate it. */
  hasOuterWrapper: boolean;
  /** Show the collapse/expand chevron. False for top-level groups and
   *  for pure-CONCEPT AT_LEAST clusters (InlineAtLeast has no collapsed
   *  state at any depth). */
  showChevron: boolean;
}

function GroupSentenceBody({
  node,
  root,
  depth,
  isTopLevel,
  leadInLabel,
  collapsed,
  onToggleCollapse,
  showControls,
  restrictAddToConcepts,
  hasOuterWrapper,
  showChevron,
  selectedNodeId,
  onSelect,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
  guidelineId,
  currentRuleId,
}: BodyProps) {
  const children = node.children ?? [];
  const connector = KIND_CONNECTOR[node.kind] ?? "and";

  const childNodes = children.map((child) => (
    <SentenceNodeDispatcher
      key={child.node_id}
      node={child}
      root={root}
      depth={depth + 1}
      selectedNodeId={selectedNodeId}
      onSelect={onSelect}
      onUpdate={onUpdate}
      onRequestAdd={onRequestAdd}
      onRequestCoach={onRequestCoach}
      guidelineId={guidelineId}
      currentRuleId={currentRuleId}
    />
  ));

  return (
    <Stack
      component="span"
      direction="row"
      flexWrap="wrap"
      alignItems="center"
      useFlexGap
      role={!hasOuterWrapper ? "group" : undefined}
      aria-label={!hasOuterWrapper ? leadInLabel : undefined}
      sx={{ rowGap: 0.75, columnGap: 0.75, display: "inline-flex" }}
    >
      {showChevron && (
        <CollapseToggle collapsed={collapsed} onToggle={onToggleCollapse} />
      )}

      <KindLeadIn node={node} onUpdate={onUpdate} label={leadInLabel} />

      {collapsed ? (
        <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic" }}>
          ({describeChildren(node)})
        </Typography>
      ) : children.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
          nothing yet
        </Typography>
      ) : (
        joinNodes(childNodes, connector)
      )}

      {!collapsed && restrictAddToConcepts && (
        <AddInlineLinks
          onlyConcept
          onAddConcept={(anchor) => {
            onSelect(node.node_id);
            onRequestAdd(node.node_id, anchor);
          }}
        />
      )}
      {!collapsed && !restrictAddToConcepts && (
        <AddInlineLinks
          onAddConcept={(anchor) => {
            onSelect(node.node_id);
            onRequestAdd(node.node_id, anchor);
          }}
          onAddDemographic={() =>
            onUpdate({ kind: "add_demographic", parentNodeId: node.node_id })
          }
          onAddObservation={() =>
            onUpdate({ kind: "add_observation", parentNodeId: node.node_id })
          }
          onAddRuleFired={() =>
            onUpdate({ kind: "add_rule_fired", parentNodeId: node.node_id })
          }
          onAddGroup={() =>
            onUpdate({ kind: "add_group", parentNodeId: node.node_id, groupKind: "OR" })
          }
          onAddShouldNotHave={() =>
            onUpdate({ kind: "add_group", parentNodeId: node.node_id, groupKind: "NOT" })
          }
        />
      )}

      {showControls && (
        <Tooltip title="Remove this group">
          <IconButton
            size="small"
            aria-label="Remove this group"
            onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Stack>
  );
}

/** Chevron toggle for a nested chunk, matching GroupBody's collapse UX. */
function CollapseToggle({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <Tooltip title={collapsed ? "Show what's inside" : "Hide what's inside"}>
      <IconButton
        size="small"
        onClick={onToggle}
        aria-label={collapsed ? "Expand group" : "Collapse group"}
        sx={{ p: 0.25 }}
      >
        {collapsed ? <ChevronRightIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
      </IconButton>
    </Tooltip>
  );
}

/**
 * Clickable, underlined lead-in phrase for a group's kind. Functions
 * exactly like the Advanced view's kind Select (same change_kind /
 * set_min updates) but is styled as inline prose instead of a boxed
 * form control so it reads as part of the sentence.
 */
function KindLeadIn({
  node,
  onUpdate,
  label,
}: {
  node: NodeProps["node"];
  onUpdate: (update: NodeUpdate) => void;
  label: string;
}) {
  return (
    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
      <Select
        variant="standard"
        disableUnderline
        value={node.kind}
        onChange={(e) =>
          onUpdate({
            kind: "change_kind",
            nodeId: node.node_id,
            newKind: e.target.value as LogicNodeKind,
          })
        }
        renderValue={() => (
          <Box
            component="span"
            sx={{
              fontWeight: 600,
              color: "primary.main",
              textDecoration: "underline",
              textDecorationStyle: "dashed",
              textUnderlineOffset: "3px",
            }}
          >
            {label}
          </Box>
        )}
        inputProps={{ "aria-label": "How to match conditions in this group" }}
        sx={{
          "& .MuiSelect-select": { p: "0 !important", pr: "20px !important" },
          fontSize: "0.9rem",
        }}
      >
        {GROUP_KINDS.map((k) => (
          <MenuItem key={k} value={k} sx={{ fontSize: "0.85rem" }}>
            {GROUP_KIND_LABELS[k]}
          </MenuItem>
        ))}
      </Select>
      {node.kind === "AT_LEAST" && (
        <TextField
          size="small"
          type="number"
          variant="standard"
          value={node.min ?? 1}
          onChange={(e) =>
            onUpdate({
              kind: "set_min",
              nodeId: node.node_id,
              min: Number(e.target.value) || 1,
            })
          }
          inputProps={{
            min: 1,
            max: Math.max(node.children?.length ?? 1, 1),
            "aria-label": "How many conditions must match",
            style: { width: 28, textAlign: "center" },
          }}
        />
      )}
      {node.kind === "AT_LEAST" && (
        <Typography variant="caption" color="text.secondary">
          of {node.children?.length ?? 0}
        </Typography>
      )}
      <Typography component="span" sx={{ color: "text.secondary" }}>
        :
      </Typography>
    </Box>
  );
}
