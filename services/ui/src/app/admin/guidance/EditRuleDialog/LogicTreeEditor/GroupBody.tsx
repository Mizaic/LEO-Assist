"use client";
/**
 * Recursive group renderer.
 * Left border colored by kind. Section label above children.
 * Thin HR separator between label and rows.
 * Connector labels (or / and / not) between condition rows.
 * Nested GroupBody for sub-groups.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { useState } from "react";
import { AnimatePresence, motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { useMotion } from "@leo/design-system";

import { GROUP_KIND_LABELS, atLeastClusterLabel } from "../copy";
import { GROUP_KINDS, type EditableLogicNode, type LogicNodeKind, type NodeUpdate } from "../types";
import ConceptPill from "./ConceptPill";
import DemographicRow from "./DemographicRow";
import NodeDispatcher from "./NodeDispatcher";
import AddBar from "./AddBar";
import { KIND_COLORS, KIND_CONNECTOR, KIND_SECTION_LABELS } from "./shared";
import { popVariants } from "../../motionPresets";

interface Props {
  node: EditableLogicNode;
  root: EditableLogicNode;
  depth: number;
  isTopLevel?: boolean;
  /** When true and isTopLevel, render an operator Select above the conditions.
   *  Set false when a parent component (PathwayCard) owns the Select. */
  showKindSelect?: boolean;
  selectedNodeId: string | null;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  guidelineId?: string;
  currentRuleId?: string;
}

export default function GroupBody({
  node, root, depth, isTopLevel, showKindSelect = true,
  selectedNodeId, onSelect, onUpdate, onRequestAdd, onRequestCoach,
  guidelineId, currentRuleId,
}: Props) {
  const [collapsed, setCollapsed] = useState(!isTopLevel && depth >= 2);
  const { reducedMotion } = useMotion();
  const children = node.children ?? [];
  const borderColor = KIND_COLORS[node.kind] ?? "grey.300";
  const connector = KIND_CONNECTOR[node.kind] ?? "and";
  const sectionLabel = node.kind === "AT_LEAST"
    ? `ANY ${node.min ?? 1} OR MORE OF THESE`
    : KIND_SECTION_LABELS[node.kind] ?? node.kind;

  const isPureAtLeast =
    node.kind === "AT_LEAST" &&
    children.length >= 1 &&
    children.every((c) => c.kind === "CONCEPT");

  if (isPureAtLeast) {
    return (
      <InlineAtLeast
        node={node}
        selectedNodeId={selectedNodeId}
        onSelect={onSelect}
        onUpdate={onUpdate}
        onRequestAdd={onRequestAdd}
        onRequestCoach={onRequestCoach}
        depth={depth}
      />
    );
  }

  return (
    <Box
      role="group"
      aria-label={sectionLabel}
      aria-expanded={!isTopLevel ? !collapsed : undefined}
      sx={{
        pl: isTopLevel ? 0 : 1.25,
        ml: isTopLevel ? 0 : 0.5,
        borderLeft: isTopLevel ? "none" : `3px solid ${borderColor}`,
        mt: isTopLevel ? 0 : 1,
      }}
    >
      {!isTopLevel && (
        <CollapsibleGroupHeader
          node={node}
          collapsed={collapsed}
          onToggle={() => setCollapsed((v) => !v)}
          onUpdate={onUpdate}
        />
      )}

      {isTopLevel && showKindSelect && (
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
          <Select
            size="small"
            value={node.kind}
            onChange={(e) =>
              onUpdate({ kind: "change_kind", nodeId: node.node_id, newKind: e.target.value as LogicNodeKind })
            }
            inputProps={{ "aria-label": "How to match conditions in this group" }}
            sx={{
              fontSize: "0.72rem",
              "& .MuiSelect-select": { py: 0.3, pr: "26px !important", color: "text.secondary", fontWeight: 700, letterSpacing: 0.4 },
              "& .MuiOutlinedInput-notchedOutline": { borderColor: "divider" },
              "& .MuiSvgIcon-root": { fontSize: "1rem" },
            }}
          >
            {GROUP_KINDS.map((k) => (
              <MenuItem key={k} value={k} sx={{ fontSize: "0.78rem" }}>
                {GROUP_KIND_LABELS[k]}
              </MenuItem>
            ))}
          </Select>
          {node.kind === "AT_LEAST" && (
            <Stack direction="row" spacing={0.5} alignItems="center">
              <TextField
                size="small"
                type="number"
                value={node.min ?? 1}
                onChange={(e) =>
                  onUpdate({ kind: "set_min", nodeId: node.node_id, min: Number(e.target.value) || 1 })
                }
                inputProps={{ min: 1, max: Math.max(node.children?.length ?? 1, 1), "aria-label": "How many conditions must match" }}
                sx={{ width: 60 }}
              />
              <Typography variant="caption" color="text.secondary">
                of {node.children?.length ?? 0}
              </Typography>
            </Stack>
          )}
        </Stack>
      )}
      {isTopLevel && showKindSelect && <Divider sx={{ mb: 1 }} />}

      {!collapsed && (
        <fm.div
          initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -6, scaleY: 0.96 }}
          animate={{ opacity: 1, y: 0, scaleY: 1 }}
          transition={
            reducedMotion
              ? { duration: 0 }
              : { type: "spring", stiffness: 340, damping: 30 }
          }
          style={{ transformOrigin: "top" }}
        >
          <AnimatePresence initial={false}>
            {children.map((child, idx) => (
              <fm.div
                key={child.node_id}
                layout
                variants={popVariants(reducedMotion)}
                initial="initial"
                animate="animate"
                exit="exit"
              >
                <NodeDispatcher
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
                {idx < children.length - 1 && (
                  <Typography
                    variant="caption"
                    sx={{
                      display: "block",
                      color: "text.disabled",
                      fontStyle: "italic",
                      fontSize: "0.72rem",
                      my: 0.25,
                      pl: 0.5,
                    }}
                  >
                    {connector}
                  </Typography>
                )}
              </fm.div>
            ))}
          </AnimatePresence>

          <AddBar
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
          />
        </fm.div>
      )}
    </Box>
  );
}

// -- Collapsible group header for nested sub-groups -------------------------

function describeChildren(node: EditableLogicNode): string {
  const children = node.children ?? [];
  const concepts = children.filter((c) => c.kind === "CONCEPT").length;
  const demographics = children.filter((c) => c.kind === "DEMOGRAPHIC").length;
  const groups = children.filter((c) =>
    c.kind === "AND" || c.kind === "OR" || c.kind === "NOT" || c.kind === "AT_LEAST",
  ).length;
  const parts: string[] = [];
  if (concepts) parts.push(`${concepts} condition${concepts === 1 ? "" : "s"}`);
  if (demographics) parts.push(`${demographics} patient detail${demographics === 1 ? "" : "s"}`);
  if (groups) parts.push(`${groups} sub-group${groups === 1 ? "" : "s"}`);
  return parts.length ? parts.join(", ") : "empty";
}

function CollapsibleGroupHeader({
  node,
  collapsed,
  onToggle,
  onUpdate,
}: {
  node: EditableLogicNode;
  collapsed: boolean;
  onToggle: () => void;
  onUpdate: (u: NodeUpdate) => void;
}) {
  const childCount = node.children?.length ?? 0;
  const { reducedMotion } = useMotion();

  return (
    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: collapsed ? 0 : 0.75, flexWrap: "wrap" }}>
      <Tooltip title={collapsed ? "Show what's inside" : "Hide what's inside"}>
        <IconButton size="small" onClick={onToggle}
          aria-label={collapsed ? "Expand group" : "Collapse group"}
          sx={{ p: 0.25 }}>
          <fm.div
            animate={{ rotate: collapsed ? 0 : 90 }}
            transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 30 }}
            style={{ display: "flex" }}
          >
            {collapsed ? <ChevronRightIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
          </fm.div>
        </IconButton>
      </Tooltip>
      <Select
        size="small"
        value={node.kind}
        onChange={(e) =>
          onUpdate({ kind: "change_kind", nodeId: node.node_id, newKind: e.target.value as LogicNodeKind })
        }
        inputProps={{ "aria-label": "What this group means" }}
        sx={{ minWidth: 240, fontSize: "0.78rem", "& .MuiSelect-select": { py: 0.4 } }}
      >
        {GROUP_KINDS.map((k) => (
          <MenuItem key={k} value={k}>{GROUP_KIND_LABELS[k]}</MenuItem>
        ))}
      </Select>
      {node.kind === "AT_LEAST" && (
        <Stack direction="row" spacing={0.5} alignItems="center">
          <TextField
            size="small" type="number" value={node.min ?? 1}
            onChange={(e) =>
              onUpdate({ kind: "set_min", nodeId: node.node_id, min: Number(e.target.value) || 1 })
            }
            inputProps={{ min: 1, max: Math.max(childCount, 1), "aria-label": atLeastClusterLabel(node.min ?? 1) }}
            sx={{ width: 60 }}
          />
          <Typography variant="caption" color="text.secondary">of {childCount}</Typography>
        </Stack>
      )}
      {collapsed && (
        <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic" }}>
          ({describeChildren(node)})
        </Typography>
      )}
      <Tooltip title="Remove this sub-group">
        <IconButton size="small" aria-label="Remove this sub-group"
          onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}>
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}

// -- Inline AT_LEAST cluster with all CONCEPT children ----------------------

function InlineAtLeast({
  node, selectedNodeId, onSelect, onUpdate, onRequestAdd, onRequestCoach, depth,
}: Omit<Props, "isTopLevel" | "root">) {
  const children = node.children ?? [];
  return (
    <Box
      role="group"
      aria-label={atLeastClusterLabel(node.min ?? 1)}
      sx={{
        mt: 1, px: 1.25, py: 1,
        position: "relative",
        bgcolor: "primary.50",
        border: "1px solid", borderColor: "primary.100",
        borderRadius: 1.5,
        "&::before": {
          content: '""',
          position: "absolute",
          left: 0, top: 8, bottom: 8, width: 3,
          borderRadius: 2,
          bgcolor: depth <= 1 ? "primary.main" : "primary.light",
        },
      }}
    >
      <Stack direction="row" spacing={0.75} alignItems="center" useFlexGap
        sx={{ flexWrap: "wrap", rowGap: 0.75, pl: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={0.5}
          sx={{ mr: 0.5, px: 0.85, py: 0.35, borderRadius: 1,
            bgcolor: "background.paper", border: "1px solid", borderColor: "primary.100" }}>
          <Typography variant="caption" sx={{ fontWeight: 600, color: "primary.dark" }}>Any</Typography>
          <TextField
            size="small" type="number" value={node.min ?? 1}
            onChange={(e) =>
              onUpdate({ kind: "set_min", nodeId: node.node_id, min: Number(e.target.value) || 1 })
            }
            inputProps={{ min: 1, max: children.length, "aria-label": "How many of these the patient must have" }}
            sx={{ width: 55 }}
          />
          <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
            or more of these
          </Typography>
          <Typography variant="caption" color="text.secondary">
            of {children.length}
          </Typography>
        </Stack>
        {children.map((child) => (
          <ConceptPill
            key={child.node_id}
            node={child}
            selectedNodeId={selectedNodeId}
            onSelect={onSelect}
            onUpdate={onUpdate}
            onRequestCoach={onRequestCoach}
          />
        ))}
        <Chip
          icon={<AddIcon sx={{ fontSize: 13 }} />}
          label="Add"
          size="small"
          variant="outlined"
          color="primary"
          onClick={(e) => {
            onSelect(node.node_id);
            onRequestAdd(node.node_id, e.currentTarget);
          }}
          aria-label="Add a symptom, sign, procedure, or situation to this group"
          sx={{ height: 26, fontSize: "0.72rem", fontWeight: 600, bgcolor: "background.paper", borderRadius: 1.5 }}
        />
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Remove this group">
          <IconButton size="small" aria-label="Remove this group"
            onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}>
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Box>
  );
}
