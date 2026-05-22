/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-D6CE2AA5
 *   DI: DI-A3107424
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-D6CE2AA5")
 */
"use client";

/**
 * Left-column editable view of a rule logic tree.
 *
 * Each group node (AND / OR / NOT / AT_LEAST) is rendered as a labelled
 * indent block with controls for: change kind, delete branch, add a child
 * concept, add a nested group, add a demographic check.
 *
 * Phase 1 layout work:
 *   - Collapsible groups (chevron + summary line when collapsed) so
 *     reviewers can fold parts of the tree they have already audited.
 *   - Inline AT-LEAST clusters: when all children of an AT-LEAST node are
 *     plain CONCEPT chips, render the selector, count and chips on one
 *     wrapping row instead of separate stacked lines (saves about half the
 *     vertical space per cluster).
 *
 * Each leaf node:
 *   - CONCEPT  -> chip; click selects it as the search-panel target.
 *                 A small X removes the chip from its parent.
 *   - DEMOGRAPHIC -> inline field/operator/value/unit inputs.
 *
 * Mutations bubble up via ``onUpdate``; this component is otherwise pure.
 */

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import LightbulbIcon from "@mui/icons-material/Lightbulb";

import {
  ADD_BAR_LABELS,
  DEMOGRAPHIC_FIELD_LABELS,
  GROUP_KIND_LABELS,
  OBSERVATION_MODE_LABELS,
  OPERATOR_LABELS,
  PATHWAY_NAME,
  RECENCY_LABELS,
  atLeastClusterLabel,
  friendlyTerm,
} from "./copy";
import { detectVaguePhrase } from "./vaguePhrases";
import SynonymChipEditor from "./SynonymChipEditor";
import {
  DEMOGRAPHIC_FIELDS,
  DEMOGRAPHIC_OPERATORS,
  type EditableLogicNode,
  type EditableObservationPayload,
  type LogicNodeKind,
  type NodeUpdate,
  type ObservationOperator,
} from "./types";

interface Props {
  root: EditableLogicNode;
  selectedNodeId: string | null;
  /**
   * Called when the reviewer focuses a chip. The optional `anchor`
   * argument is the chip's DOM element so the parent can position
   * a chip-anchored popover at the click point. Anchor is omitted
   * when selection is triggered programmatically (e.g. before
   * `onRequestAdd` fires from the same handler).
   */
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  /**
   * Called when the reviewer clicks an "+ Add" chip / button inside a
   * group. The optional `anchor` argument is the trigger element so
   * the parent can position the search popover where the click
   * happened.
   */
  onRequestAdd: (
    parentNodeId: string,
    anchor?: HTMLElement | null,
  ) => void;
  /**
   * Open the concept-expansion coach for a chip whose term matches a
   * vague pattern (e.g. "symptoms of lung cancer"). The anchor element
   * is the warning icon next to the chip.
   */
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}

export default function LogicTreeEditor(props: Props) {
  return (
    <Box
      role="tree"
      aria-label="Editable rule logic"
      sx={{
        p: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        bgcolor: "background.paper",
        maxHeight: { xs: 480, md: "70vh" },
        overflowY: "auto",
      }}
    >
      <NodeView {...props} node={props.root} depth={0} isRoot />
    </Box>
  );
}

interface NodeViewProps extends Props {
  node: EditableLogicNode;
  depth: number;
  isRoot?: boolean;
}

function NodeView(p: NodeViewProps) {
  const { node } = p;
  if (node.kind === "CONCEPT") return <ConceptNodeView {...p} />;
  if (node.kind === "DEMOGRAPHIC") return <DemographicNodeView {...p} />;
  if (node.kind === "OBSERVATION") return <ObservationNodeView {...p} />;
  return <GroupNodeView {...p} />;
}

// ---- Group nodes (AND / OR / NOT / AT_LEAST) -----------------------------

function isPureConceptGroup(node: EditableLogicNode): boolean {
  const children = node.children ?? [];
  return (
    node.kind === "AT_LEAST" &&
    children.length >= 1 &&
    children.every((c) => c.kind === "CONCEPT")
  );
}

/**
 * An OR group near the top of the tree maps cleanly onto the
 * "patient must match one of these pathways" pattern that NICE
 * recommendations use. Render those as side-by-side cards so each
 * pathway is its own visual unit instead of one long indented block.
 */
function isPathwaySplit(node: EditableLogicNode, depth: number): boolean {
  if (node.kind !== "OR") return false;
  if (depth > 1) return false;
  return (node.children?.length ?? 0) >= 2;
}

function describeGroup(node: EditableLogicNode): string {
  const children = node.children ?? [];
  const concepts = children.filter((c) => c.kind === "CONCEPT").length;
  const demographics = children.filter((c) => c.kind === "DEMOGRAPHIC").length;
  const groups = children.filter(
    (c) => c.kind === "AND" || c.kind === "OR" || c.kind === "NOT" || c.kind === "AT_LEAST",
  ).length;
  const parts: string[] = [];
  if (concepts) parts.push(`${concepts} symptom${concepts === 1 ? "" : "s"}`);
  if (demographics) parts.push(`${demographics} patient detail${demographics === 1 ? "" : "s"}`);
  if (groups) parts.push(`${groups} sub-group${groups === 1 ? "" : "s"}`);
  return parts.length ? parts.join(", ") : "empty";
}

function GroupNodeView(props: NodeViewProps) {
  const {
    node,
    depth,
    isRoot,
    selectedNodeId,
    onSelect,
    onUpdate,
    onRequestAdd,
    onRequestCoach,
    root,
  } = props;
  const [collapsed, setCollapsed] = useState<boolean>(!isRoot && depth >= 2);
  const childCount = node.children?.length ?? 0;
  const inline = isPureConceptGroup(node);
  const asPathwayCards = isPathwaySplit(node, depth);

  if (inline) {
    return (
      <InlineAtLeastView
        node={node}
        depth={depth}
        isRoot={Boolean(isRoot)}
        selectedNodeId={selectedNodeId}
        onSelect={onSelect}
        onUpdate={onUpdate}
        onRequestAdd={onRequestAdd}
        onRequestCoach={onRequestCoach}
      />
    );
  }

  if (asPathwayCards) {
    return (
      <PathwayCardsView
        node={node}
        depth={depth}
        selectedNodeId={selectedNodeId}
        onSelect={onSelect}
        onUpdate={onUpdate}
        onRequestAdd={onRequestAdd}
        onRequestCoach={onRequestCoach}
        root={root}
      />
    );
  }

  return (
    <Box
      role="treeitem"
      aria-expanded={!collapsed}
      sx={{
        ml: isRoot ? 0 : 1.5,
        mt: 0.75,
        pl: 1.25,
        borderLeft: "2px solid",
        borderColor: depth === 0 ? "transparent" : depth === 1 ? "primary.light" : "divider",
      }}
    >
      <Stack
        direction="row"
        spacing={0.75}
        alignItems="center"
        sx={{ mb: 0.5, flexWrap: "wrap" }}
      >
        {!isRoot && (
          <Tooltip title={collapsed ? "Show what's inside" : "Hide what's inside"}>
            <IconButton
              size="small"
              aria-label={collapsed ? "Expand group" : "Collapse group"}
              onClick={() => setCollapsed((v) => !v)}
              sx={{ p: 0.25 }}
            >
              {collapsed ? (
                <ChevronRightIcon fontSize="small" />
              ) : (
                <ExpandMoreIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
        )}
        <KindSelect
          value={node.kind}
          onChange={(newKind) =>
            onUpdate({ kind: "change_kind", nodeId: node.node_id, newKind })
          }
        />
        {node.kind === "AT_LEAST" && (
          <AtLeastCounter
            min={node.min ?? 1}
            childCount={childCount}
            onChange={(n) => onUpdate({ kind: "set_min", nodeId: node.node_id, min: n })}
          />
        )}
        {collapsed && (
          <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic" }}>
            ({describeGroup(node)})
          </Typography>
        )}
        {!isRoot && (
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
      {!collapsed && (
        <>
          {(node.children ?? []).map((child) => (
            <NodeView
              key={child.node_id}
              root={root}
              node={child}
              depth={depth + 1}
              selectedNodeId={selectedNodeId}
              onSelect={onSelect}
              onUpdate={onUpdate}
              onRequestAdd={onRequestAdd}
              onRequestCoach={onRequestCoach}
            />
          ))}
          <AddChildBar
            parentKind={node.kind}
            onAddConcept={(anchor) => {
              onSelect(node.node_id);
              onRequestAdd(node.node_id, anchor);
            }}
            onAddGroup={(g) =>
              onUpdate({ kind: "add_group", parentNodeId: node.node_id, groupKind: g })
            }
            onAddDemographic={() =>
              onUpdate({ kind: "add_demographic", parentNodeId: node.node_id })
            }
          />
        </>
      )}
    </Box>
  );
}

// ---- Pathway cards layout ------------------------------------------------

interface PathwayCardsProps {
  node: EditableLogicNode;
  depth: number;
  selectedNodeId: string | null;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  root: EditableLogicNode;
}

const PATHWAY_ACCENTS = [
  { stripe: "primary.main", chipBg: "primary.50", chipFg: "primary.dark" },
  { stripe: "info.main", chipBg: "info.50", chipFg: "info.dark" },
  { stripe: "secondary.main", chipBg: "secondary.50", chipFg: "secondary.dark" },
  { stripe: "success.main", chipBg: "success.50", chipFg: "success.dark" },
] as const;

function pathwayAccent(index: number) {
  return PATHWAY_ACCENTS[index % PATHWAY_ACCENTS.length];
}

function PathwayCardsView(props: PathwayCardsProps) {
  const {
    node,
    depth,
    selectedNodeId,
    onSelect,
    onUpdate,
    onRequestAdd,
    onRequestCoach,
    root,
  } = props;
  const children = node.children ?? [];
  return (
    <Box
      role="treeitem"
      aria-label="Patient pathways"
      sx={{
        ml: depth === 0 ? 0 : 1.5,
        mt: 0.75,
        pl: 0,
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{ mb: 1.25, pl: 0.5, flexWrap: "wrap", rowGap: 0.5 }}
      >
        <Typography
          variant="body2"
          sx={{
            fontWeight: 600,
            color: "text.primary",
            lineHeight: 1.4,
          }}
        >
          The rule fires if the patient matches any one of these
          pathways:
        </Typography>
        <Tooltip title={ADD_BAR_LABELS.pathway}>
          <Chip
            icon={<AddIcon sx={{ fontSize: 14 }} />}
            label="Add pathway"
            size="small"
            variant="outlined"
            color="primary"
            onClick={() =>
              onUpdate({
                kind: "add_group",
                parentNodeId: node.node_id,
                groupKind: "AND",
              })
            }
            sx={{
              height: 24,
              fontSize: "0.72rem",
              fontWeight: 600,
              borderRadius: 1.5,
              bgcolor: "background.paper",
            }}
          />
        </Tooltip>
      </Stack>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={2}
        useFlexGap
        sx={{ alignItems: "stretch", flexWrap: "wrap" }}
      >
        {children.map((child, i) => {
          const accent = pathwayAccent(i);
          const letter = String.fromCharCode(65 + i);
          const positional = `Pathway ${letter}`;
          return (
            <Box
              key={child.node_id}
              sx={{
                flex: 1,
                minWidth: { xs: "100%", md: 280 },
                position: "relative",
                borderRadius: 2,
                border: "1px solid",
                borderColor: "divider",
                bgcolor: "background.paper",
                boxShadow:
                  "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.04)",
                overflow: "hidden",
                transition:
                  "box-shadow 150ms ease, border-color 150ms ease",
                "&:hover": {
                  boxShadow:
                    "0 1px 2px rgba(15, 23, 42, 0.06), 0 6px 18px rgba(15, 23, 42, 0.08)",
                },
              }}
            >
              <Box
                aria-hidden
                sx={{
                  height: 4,
                  width: "100%",
                  bgcolor: accent.stripe,
                }}
              />
              <Box sx={{ p: 1.5 }}>
                <Stack
                  direction="row"
                  alignItems="flex-start"
                  spacing={0.75}
                  sx={{ mb: 1 }}
                >
                  <Box
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 0.5,
                      px: 0.85,
                      py: 0.25,
                      borderRadius: 1,
                      bgcolor: accent.chipBg,
                      color: accent.chipFg,
                      fontSize: "0.7rem",
                      fontWeight: 700,
                      letterSpacing: 0.4,
                      textTransform: "uppercase",
                      flexShrink: 0,
                      mt: 0.4,
                    }}
                  >
                    {letter}
                  </Box>
                  <PathwayNameInput
                    node={child}
                    positional={positional}
                    onUpdate={onUpdate}
                  />
                  <Tooltip title="Remove this pathway">
                    <IconButton
                      size="small"
                      aria-label={`Remove ${positional}`}
                      onClick={() =>
                        onUpdate({ kind: "remove", nodeId: child.node_id })
                      }
                      sx={{
                        color: "text.secondary",
                        mt: 0.2,
                        "&:hover": { color: "error.main" },
                      }}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
                <PathwayCardBody
                  root={root}
                  node={child}
                  depth={depth + 1}
                  selectedNodeId={selectedNodeId}
                  onSelect={onSelect}
                  onUpdate={onUpdate}
                  onRequestAdd={onRequestAdd}
                  onRequestCoach={onRequestCoach}
                />
              </Box>
              {i < children.length - 1 && (
                <Box
                  sx={{
                    display: { xs: "none", md: "flex" },
                    position: "absolute",
                    right: -18,
                    top: "50%",
                    transform: "translateY(-50%)",
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    bgcolor: "background.paper",
                    color: "primary.dark",
                    border: "1px solid",
                    borderColor: "primary.light",
                    fontSize: "0.65rem",
                    fontWeight: 800,
                    letterSpacing: 0.5,
                    alignItems: "center",
                    justifyContent: "center",
                    zIndex: 1,
                    boxShadow:
                      "0 1px 2px rgba(15, 23, 42, 0.06), 0 4px 10px rgba(15, 23, 42, 0.08)",
                  }}
                  aria-hidden
                >
                  OR
                </Box>
              )}
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
}

/**
 * Optional plain-English name for a pathway card (Phase 2 of the
 * wizard redesign).
 *
 * Renders as an unobtrusive in-card text field that sits next to the
 * positional letter chip. Empty values clear the name and let the
 * read-only review view fall back to "Pathway A/B/C".
 *
 * Local state mirrors ``node.name`` so typing stays smooth without
 * re-deriving the whole tree on every keystroke; commits happen on
 * blur and on Enter so the editor's debounce / validation pipeline
 * sees one update per intentional change.
 */
function PathwayNameInput({
  node,
  positional,
  onUpdate,
}: {
  node: EditableLogicNode;
  positional: string;
  onUpdate: (u: NodeUpdate) => void;
}) {
  const initial = typeof node.name === "string" ? node.name : "";
  const [draft, setDraft] = useState<string>(initial);
  const inputId = `pathway-name-${node.node_id}`;

  // Re-sync when the upstream tree replaces the node's name (undo,
  // sibling reordering, programmatic clear). Skip the sync while the
  // field is focused so we never clobber the user's in-progress
  // typing in a debounced parent.
  useEffect(() => {
    if (typeof document !== "undefined" && document.activeElement?.id === inputId) {
      return;
    }
    setDraft(initial);
  }, [initial, inputId]);

  const commit = (next: string) => {
    const trimmed = next.trim();
    const current = (node.name ?? "").trim();
    if (trimmed === current) return;
    onUpdate({ kind: "set_name", nodeId: node.node_id, name: trimmed });
  };

  return (
    <TextField
      id={`pathway-name-${node.node_id}`}
      size="small"
      variant="standard"
      value={draft}
      onChange={(e) => setDraft(e.target.value.slice(0, PATHWAY_NAME.helperMaxChars))}
      onBlur={(e) => commit(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
        }
      }}
      placeholder={PATHWAY_NAME.inputPlaceholder}
      inputProps={{
        "aria-label": PATHWAY_NAME.inputAriaTemplate(positional),
        maxLength: PATHWAY_NAME.helperMaxChars,
      }}
      sx={{
        flex: 1,
        "& .MuiInput-input": {
          fontSize: "0.82rem",
          fontWeight: 600,
          py: 0.25,
        },
        "& .MuiInput-underline:before": {
          borderBottomStyle: "dashed",
          borderBottomColor: "divider",
        },
      }}
    />
  );
}

/**
 * Body of a single pathway card.
 *
 * Each pathway is an AND/OR group. Show the match-mode selector at the
 * top of every pathway so reviewers can see and change ALL vs ANY even
 * when the pathway is a plain AND list (pathway B style).
 */
interface PathwayCardBodyProps {
  root: EditableLogicNode;
  node: EditableLogicNode;
  depth: number;
  selectedNodeId: string | null;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}

function PathwayCardBody(p: PathwayCardBodyProps) {
  const { node, depth, root, selectedNodeId } = p;

  if (node.kind === "AND") {
    const children = node.children ?? [];
    const matchMode = (
      <Box sx={{ mb: children.length ? 1 : 0.75 }}>
        <KindSelect
          value={node.kind}
          onChange={(newKind) =>
            p.onUpdate({
              kind: "change_kind",
              nodeId: node.node_id,
              newKind,
            })
          }
        />
      </Box>
    );
    if (children.length === 0) {
      return (
        <Box>
          {matchMode}
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ fontStyle: "italic", mb: 0.75 }}
          >
            This pathway is empty. Add a symptom, a sub-group, or a
            patient detail below.
          </Typography>
          <AddChildBar
            parentKind="AND"
            onAddConcept={(anchor) => {
              p.onSelect(node.node_id);
              p.onRequestAdd(node.node_id, anchor);
            }}
            onAddGroup={(g) =>
              p.onUpdate({
                kind: "add_group",
                parentNodeId: node.node_id,
                groupKind: g,
              })
            }
            onAddDemographic={() =>
              p.onUpdate({ kind: "add_demographic", parentNodeId: node.node_id })
            }
          />
        </Box>
      );
    }
    return (
      <Box>
        {matchMode}
        {children.map((child) => (
          <NodeView
            key={child.node_id}
            root={root}
            node={child}
            depth={depth + 1}
            isRoot={false}
            selectedNodeId={selectedNodeId}
            onSelect={p.onSelect}
            onUpdate={p.onUpdate}
            onRequestAdd={p.onRequestAdd}
            onRequestCoach={p.onRequestCoach}
          />
        ))}
        <AddChildBar
          parentKind="AND"
          onAddConcept={(anchor) => {
            p.onSelect(node.node_id);
            p.onRequestAdd(node.node_id, anchor);
          }}
          onAddGroup={(g) =>
            p.onUpdate({
              kind: "add_group",
              parentNodeId: node.node_id,
              groupKind: g,
            })
          }
          onAddDemographic={() =>
            p.onUpdate({ kind: "add_demographic", parentNodeId: node.node_id })
          }
        />
      </Box>
    );
  }

  return (
    <NodeView
      root={root}
      node={node}
      depth={depth}
      isRoot={false}
      selectedNodeId={selectedNodeId}
      onSelect={p.onSelect}
      onUpdate={p.onUpdate}
      onRequestAdd={p.onRequestAdd}
      onRequestCoach={p.onRequestCoach}
    />
  );
}

// ---- Inline AT-LEAST cluster ---------------------------------------------

interface InlineAtLeastProps {
  node: EditableLogicNode;
  depth: number;
  isRoot: boolean;
  selectedNodeId: string | null;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}

function InlineAtLeastView({
  node,
  depth,
  isRoot,
  selectedNodeId,
  onSelect,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
}: InlineAtLeastProps) {
  const childCount = node.children?.length ?? 0;
  return (
    <Box
      role="treeitem"
      sx={{
        ml: isRoot ? 0 : 1.5,
        mt: 1,
        px: 1.25,
        py: 1,
        position: "relative",
        bgcolor: "primary.50",
        border: "1px solid",
        borderColor: "primary.100",
        borderRadius: 1.5,
        "&::before": {
          content: '""',
          position: "absolute",
          left: 0,
          top: 8,
          bottom: 8,
          width: 3,
          borderRadius: 2,
          bgcolor: depth <= 1 ? "primary.main" : "primary.light",
        },
      }}
    >
      <Stack
        direction="row"
        spacing={0.75}
        alignItems="center"
        useFlexGap
        sx={{ flexWrap: "wrap", rowGap: 0.75, pl: 0.5 }}
      >
        <Stack
          direction="row"
          alignItems="center"
          spacing={0.5}
          sx={{
            mr: 0.5,
            px: 0.85,
            py: 0.35,
            borderRadius: 1,
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "primary.100",
          }}
        >
          <Typography
            variant="caption"
            sx={{
              fontWeight: 600,
              color: "primary.dark",
            }}
            aria-label={atLeastClusterLabel(node.min ?? 1)}
          >
            Any
          </Typography>
          <AtLeastCounter
            min={node.min ?? 1}
            childCount={childCount}
            onChange={(n) =>
              onUpdate({ kind: "set_min", nodeId: node.node_id, min: n })
            }
          />
          <Typography
            variant="caption"
            sx={{
              fontWeight: 600,
              color: "text.secondary",
            }}
          >
            or more of these
          </Typography>
        </Stack>
        {(node.children ?? []).map((child) => (
          <ConceptChipInline
            key={child.node_id}
            node={child}
            isSelected={selectedNodeId === child.node_id}
            onSelect={onSelect}
            onUpdate={onUpdate}
            onRequestCoach={onRequestCoach}
          />
        ))}
        <Chip
          icon={<AddIcon sx={{ fontSize: 14 }} />}
          label="Add"
          size="small"
          variant="outlined"
          color="primary"
          onClick={(e) => {
            onSelect(node.node_id);
            onRequestAdd(node.node_id, e.currentTarget);
          }}
          aria-label="Add a symptom or sign to this group"
          sx={{
            height: 26,
            fontSize: "0.72rem",
            fontWeight: 600,
            bgcolor: "background.paper",
            borderRadius: 1.5,
          }}
        />
        <Box sx={{ flex: 1 }} />
        {!isRoot && (
          <Tooltip title="Remove this group">
            <IconButton
              size="small"
              aria-label="Remove this group"
              onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
              sx={{
                color: "text.secondary",
                "&:hover": { color: "error.main" },
              }}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Stack>
    </Box>
  );
}

function ConceptChipInline({
  node,
  isSelected,
  onSelect,
  onUpdate,
  onRequestCoach,
}: {
  node: EditableLogicNode;
  isSelected: boolean;
  onSelect: (id: string, anchor?: HTMLElement | null) => void;
  onUpdate: (u: NodeUpdate) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}) {
  const friendly = friendlyTerm(node.criterion?.preferred_term);
  const label = friendly || "Click to pick";
  const vague = detectVaguePhrase(node.criterion?.preferred_term);
  const tooltip = node.criterion?.snomed_concept_id
    ? `${friendly} (clinical code ${node.criterion.snomed_concept_id}). Click to swap. X to remove.`
    : "No clinical code yet. Click to search and pick one.";
  return (
    <Stack
      direction="row"
      spacing={0}
      alignItems="center"
      component="span"
      sx={{
        borderRadius: 1.5,
        bgcolor: isSelected ? "primary.50" : "transparent",
        border: "1px solid",
        borderColor: isSelected ? "primary.light" : "transparent",
        px: isSelected ? 0.25 : 0,
        py: isSelected ? 0.25 : 0,
        transition:
          "background-color 120ms ease, border-color 120ms ease",
      }}
    >
      <Tooltip title={tooltip} arrow>
        <Chip
          label={label}
          color={
            isSelected
              ? "primary"
              : vague.isVague
                ? "warning"
                : node.criterion?.snomed_concept_id
                  ? "success"
                  : "warning"
          }
          variant={isSelected ? "filled" : "outlined"}
          size="small"
          onClick={(e) => onSelect(node.node_id, e.currentTarget)}
          onDelete={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
          deleteIcon={<CloseIcon sx={{ fontSize: 14 }} />}
          sx={{
            height: 26,
            fontSize: "0.78rem",
            fontWeight: 500,
            borderRadius: 1.5,
            bgcolor:
              !isSelected && node.criterion?.snomed_concept_id
                ? "background.paper"
                : undefined,
          }}
          aria-label={`${label}. Click to swap, X to remove.`}
        />
      </Tooltip>
      {vague.isVague && onRequestCoach && (
        <VaguePhraseBadge
          term={label}
          onClick={(anchor) => onRequestCoach(node.node_id, anchor)}
        />
      )}
      {node.criterion?.snomed_concept_id && (
        <SynonymChipEditor node={node} onUpdate={onUpdate} />
      )}
    </Stack>
  );
}

function VaguePhraseBadge({
  term,
  onClick,
}: {
  term: string;
  onClick: (anchor: HTMLElement) => void;
}) {
  return (
    <Tooltip title={`"${term}" is vague. Click for specific suggestions.`} arrow>
      <IconButton
        size="small"
        aria-label={`Get specific suggestions for "${term}"`}
        onClick={(e) => onClick(e.currentTarget)}
        sx={{
          p: 0.25,
          color: "warning.dark",
          bgcolor: "warning.50",
          "&:hover": { bgcolor: "warning.100" },
        }}
      >
        <LightbulbIcon sx={{ fontSize: 14 }} />
      </IconButton>
    </Tooltip>
  );
}

function AtLeastCounter({
  min,
  childCount,
  onChange,
}: {
  min: number;
  childCount: number;
  onChange: (n: number) => void;
}) {
  return (
    <Stack direction="row" spacing={0.5} alignItems="center">
      <TextField
        size="small"
        type="number"
        value={min}
        onChange={(e) => onChange(Number(e.target.value) || 1)}
        inputProps={{
          min: 1,
          max: Math.max(childCount, 1),
          "aria-label": "How many of these the patient must have",
        }}
        sx={{ width: 64 }}
      />
      <Typography variant="caption" color="text.secondary">
        of {childCount}
      </Typography>
    </Stack>
  );
}

function KindSelect({
  value,
  onChange,
}: {
  value: LogicNodeKind;
  onChange: (k: LogicNodeKind) => void;
}) {
  return (
    <Select
      size="small"
      value={value}
      onChange={(e) => onChange(e.target.value as LogicNodeKind)}
      inputProps={{ "aria-label": "What this group means" }}
      sx={{ minWidth: 280, fontSize: "0.82rem", "& .MuiSelect-select": { py: 0.4 } }}
    >
      <MenuItem value="AND">{GROUP_KIND_LABELS.AND}</MenuItem>
      <MenuItem value="OR">{GROUP_KIND_LABELS.OR}</MenuItem>
      <MenuItem value="NOT">{GROUP_KIND_LABELS.NOT}</MenuItem>
      <MenuItem value="AT_LEAST">{GROUP_KIND_LABELS.AT_LEAST}</MenuItem>
    </Select>
  );
}

function AddChildBar({
  parentKind,
  onAddConcept,
  onAddGroup,
  onAddDemographic,
}: {
  parentKind: LogicNodeKind;
  onAddConcept: (anchor?: HTMLElement | null) => void;
  onAddGroup: (k: "AND" | "OR" | "NOT" | "AT_LEAST") => void;
  onAddDemographic: () => void;
}) {
  const nextGroupKind = parentKind === "AND" ? "OR" : "AND";
  const groupLabel =
    nextGroupKind === "OR" ? ADD_BAR_LABELS.choice : ADD_BAR_LABELS.subgroup;
  const addChipSx = {
    height: 26,
    fontSize: "0.72rem",
    fontWeight: 600,
    borderRadius: 1.5,
    color: "text.secondary",
    borderColor: "divider",
    bgcolor: "background.paper",
    transition:
      "background-color 120ms ease, border-color 120ms ease, color 120ms ease",
    "&:hover": {
      bgcolor: "primary.50",
      borderColor: "primary.light",
      color: "primary.dark",
    },
    "& .MuiChip-icon": { color: "inherit" },
  } as const;
  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="center"
      sx={{
        mt: 1,
        pl: 0.25,
        color: "text.secondary",
        flexWrap: "wrap",
        rowGap: 0.5,
      }}
    >
      <Chip
        icon={<AddIcon sx={{ fontSize: 14 }} />}
        label={ADD_BAR_LABELS.symptom}
        size="small"
        variant="outlined"
        onClick={(e) => onAddConcept(e.currentTarget)}
        sx={addChipSx}
      />
      <Chip
        icon={<AddIcon sx={{ fontSize: 14 }} />}
        label={groupLabel}
        size="small"
        variant="outlined"
        onClick={() => onAddGroup(nextGroupKind)}
        sx={addChipSx}
      />
      <Chip
        icon={<AddIcon sx={{ fontSize: 14 }} />}
        label={ADD_BAR_LABELS.detail}
        size="small"
        variant="outlined"
        onClick={onAddDemographic}
        sx={addChipSx}
      />
    </Stack>
  );
}

// ---- Concept leaf --------------------------------------------------------

function ConceptNodeView({
  node,
  selectedNodeId,
  onSelect,
  onUpdate,
  onRequestCoach,
}: NodeViewProps) {
  const isSelected = selectedNodeId === node.node_id;
  const rawLabel =
    node.criterion?.preferred_term ||
    node.criterion?.snomed_concept_id ||
    "";
  const friendly = friendlyTerm(rawLabel);
  const label = friendly || "Click to pick a symptom";
  const vague = detectVaguePhrase(node.criterion?.preferred_term);
  const tooltip = node.criterion?.snomed_concept_id
    ? `${friendly} (clinical code ${node.criterion.snomed_concept_id}). Click to swap. X to remove.`
    : "No clinical code yet. Click to search and pick one.";
  return (
    <Stack
      direction="row"
      spacing={0}
      alignItems="center"
      sx={{
        display: "inline-flex",
        mr: 0.5,
        mb: 0.5,
        borderRadius: 1.5,
        bgcolor: isSelected ? "primary.50" : "transparent",
        border: "1px solid",
        borderColor: isSelected ? "primary.light" : "transparent",
        px: isSelected ? 0.25 : 0,
        py: isSelected ? 0.25 : 0,
        transition:
          "background-color 120ms ease, border-color 120ms ease",
      }}
    >
      <Tooltip title={tooltip} arrow>
        <Chip
          label={label}
          color={
            isSelected
              ? "primary"
              : vague.isVague
                ? "warning"
                : node.criterion?.snomed_concept_id
                  ? "success"
                  : "warning"
          }
          variant={isSelected ? "filled" : "outlined"}
          size="small"
          onClick={(e) => onSelect(node.node_id, e.currentTarget)}
          onDelete={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
          deleteIcon={<CloseIcon sx={{ fontSize: 14 }} />}
          sx={{
            height: 26,
            fontSize: "0.78rem",
            fontWeight: 500,
            borderRadius: 1.5,
            bgcolor:
              !isSelected && node.criterion?.snomed_concept_id
                ? "background.paper"
                : undefined,
          }}
          aria-label={`${label}. Click to swap, X to remove.`}
        />
      </Tooltip>
      {vague.isVague && onRequestCoach && (
        <VaguePhraseBadge
          term={label}
          onClick={(anchor) => onRequestCoach(node.node_id, anchor)}
        />
      )}
      {node.criterion?.snomed_concept_id && (
        <SynonymChipEditor node={node} onUpdate={onUpdate} />
      )}
    </Stack>
  );
}

// ---- Demographic leaf ---------------------------------------------------

function DemographicNodeView({ node, onUpdate }: NodeViewProps) {
  const fields = useMemo(() => DEMOGRAPHIC_FIELDS, []);
  const operators = useMemo(() => DEMOGRAPHIC_OPERATORS, []);
  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="center"
      sx={{ ml: 0.5, my: 0.5, flexWrap: "wrap" }}
    >
      <Select
        size="small"
        value={node.field ?? "age"}
        onChange={(e) =>
          onUpdate({
            kind: "set_demographic",
            nodeId: node.node_id,
            field: String(e.target.value),
            operator: node.operator ?? ">=",
            value: String(node.value ?? ""),
            unit: node.unit ?? "years",
          })
        }
        inputProps={{ "aria-label": "What patient detail to check" }}
        sx={{ minWidth: 150, fontSize: "0.78rem" }}
      >
        {fields.map((f) => (
          <MenuItem key={f} value={f}>
            {DEMOGRAPHIC_FIELD_LABELS[f] ?? f}
          </MenuItem>
        ))}
      </Select>
      <Select
        size="small"
        value={node.operator ?? ">="}
        onChange={(e) =>
          onUpdate({
            kind: "set_demographic",
            nodeId: node.node_id,
            field: node.field ?? "age",
            operator: String(e.target.value),
            value: String(node.value ?? ""),
            unit: node.unit ?? "years",
          })
        }
        inputProps={{ "aria-label": "How to compare" }}
        sx={{ minWidth: 130, fontSize: "0.78rem" }}
      >
        {operators.map((o) => (
          <MenuItem key={o} value={o}>
            {OPERATOR_LABELS[o] ?? o}
          </MenuItem>
        ))}
      </Select>
      <TextField
        size="small"
        value={node.value ?? ""}
        onChange={(e) =>
          onUpdate({
            kind: "set_demographic",
            nodeId: node.node_id,
            field: node.field ?? "age",
            operator: node.operator ?? ">=",
            value: e.target.value,
            unit: node.unit ?? "years",
          })
        }
        placeholder="40"
        inputProps={{ "aria-label": "Value to compare with" }}
        sx={{ width: 80 }}
      />
      <TextField
        size="small"
        value={node.unit ?? ""}
        onChange={(e) =>
          onUpdate({
            kind: "set_demographic",
            nodeId: node.node_id,
            field: node.field ?? "age",
            operator: node.operator ?? ">=",
            value: String(node.value ?? ""),
            unit: e.target.value || null,
          })
        }
        placeholder="years"
        inputProps={{ "aria-label": "Unit (for example: years)" }}
        sx={{ width: 90 }}
      />
      <Tooltip title="Remove this patient detail">
        <IconButton
          size="small"
          aria-label="Remove this patient detail"
          onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
        >
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}

// ---- OBSERVATION leaf (Phase 6a) -----------------------------------------

/**
 * Editor row for an OBSERVATION leaf in the Advanced view.
 *
 * The advanced view mirrors the canvas ObservationRow for the default
 * "absolute" mode (observable chip, operator, value(s), unit, recency
 * window) and shows a read-only summary + "open timing settings"
 * hint for the four advanced modes (temporal / reference_range /
 * trend / aggregation). Full mode-editing lives behind a separate
 * modal to keep the tree view compact; those screens land in a
 * subsequent phase. Remove-this-row is always available.
 *
 * Atlas trace: UN-26E57FA1 / DI-7790EEA5 / DO-710270EF (extended in
 * Phase 6a for the OBSERVATION leaf UI).
 */
function ObservationNodeView({ node, onUpdate, onSelect }: NodeViewProps) {
  const obs = node.observation;
  if (!obs) {
    return (
      <Stack
        direction="row"
        spacing={0.75}
        alignItems="center"
        sx={{ ml: 0.5, my: 0.5, flexWrap: "wrap" }}
        aria-label="Lab value row without data -- needs attention"
      >
        <Chip
          label="Lab value needs attention"
          size="small"
          color="warning"
          variant="outlined"
          sx={{ fontSize: "0.78rem" }}
        />
        <Tooltip title="Remove this lab value">
          <IconButton
            size="small"
            aria-label="Remove this lab value"
            onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    );
  }

  const mode = pickObservationMode(obs);
  const term = friendlyTerm(obs.observable_term) || "Lab value";
  if (mode !== "absolute") {
    const modeLabel = OBSERVATION_MODE_LABELS[mode] ?? mode;
    return (
      <Box
        role="group"
        aria-label={`Advanced lab value row: ${term} -- ${modeLabel}`}
        sx={{
          ml: 0.5,
          my: 0.5,
          px: 1.25,
          py: 1,
          bgcolor: "info.50",
          border: "1px dashed",
          borderColor: "info.200",
          borderRadius: 1.5,
        }}
      >
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="body2" sx={{ fontWeight: 600, color: "info.dark" }}>
            {term}
          </Typography>
          <Chip
            label={modeLabel}
            size="small"
            color="info"
            variant="outlined"
            sx={{ height: 22, fontSize: "0.72rem" }}
          />
          <Typography variant="caption" color="text.secondary">
            Open the timing settings modal to edit this rule's timing.
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Tooltip title="Remove this lab value">
            <IconButton
              size="small"
              aria-label="Remove this lab value"
              onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </Box>
    );
  }

  const setObservation = (patch: Partial<EditableObservationPayload>) =>
    onUpdate({
      kind: "set_observation",
      nodeId: node.node_id,
      observation: { ...obs, ...patch },
    });

  const isBetween = obs.operator === "between";
  const lo = Array.isArray(obs.value) ? obs.value[0] : obs.value;
  const hi = Array.isArray(obs.value) ? obs.value[1] : "";
  const hasObservableId = Boolean(obs.observable_id);

  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="center"
      sx={{ ml: 0.5, my: 0.5, flexWrap: "wrap" }}
    >
      <Chip
        label={term}
        size="small"
        color={hasObservableId ? "success" : "warning"}
        variant={hasObservableId ? "filled" : "outlined"}
        onClick={(e) => onSelect(node.node_id, e.currentTarget)}
        sx={{ fontSize: "0.78rem" }}
        aria-label={`${term}. Click to swap the lab value.`}
      />
      <Select
        size="small"
        value={obs.operator ?? ">="}
        onChange={(e) => {
          const next = String(e.target.value) as ObservationOperator;
          if (next === "between" && !Array.isArray(obs.value)) {
            setObservation({
              operator: next,
              value: [Number(obs.value ?? 0), Number(obs.value ?? 0)],
            });
          } else if (next !== "between" && Array.isArray(obs.value)) {
            setObservation({ operator: next, value: Number(obs.value[0]) });
          } else {
            setObservation({ operator: next });
          }
        }}
        inputProps={{ "aria-label": "How to compare the lab value" }}
        sx={{ minWidth: 130, fontSize: "0.78rem" }}
      >
        {(
          [">=", "<=", ">", "<", "=", "between"] as ObservationOperator[]
        ).map((o) => (
          <MenuItem key={o} value={o}>
            {OPERATOR_LABELS[o] ?? o}
          </MenuItem>
        ))}
      </Select>
      <TextField
        size="small"
        type="number"
        value={String(lo ?? "")}
        onChange={(e) => {
          const next = Number(e.target.value);
          if (isBetween) {
            setObservation({ value: [next, Number(hi ?? next)] });
          } else {
            setObservation({ value: Number.isFinite(next) ? next : 0 });
          }
        }}
        placeholder="400"
        inputProps={{
          "aria-label": isBetween
            ? "Lower bound value"
            : "Value to compare with",
        }}
        sx={{ width: 90 }}
      />
      {isBetween && (
        <>
          <Typography variant="body2" color="text.secondary">
            and
          </Typography>
          <TextField
            size="small"
            type="number"
            value={String(hi ?? "")}
            onChange={(e) => {
              const next = Number(e.target.value);
              setObservation({
                value: [Number(lo ?? 0), Number.isFinite(next) ? next : 0],
              });
            }}
            placeholder="500"
            inputProps={{ "aria-label": "Upper bound value" }}
            sx={{ width: 90 }}
          />
        </>
      )}
      <TextField
        size="small"
        value={obs.unit ?? ""}
        onChange={(e) => setObservation({ unit: e.target.value })}
        placeholder="10*9/L"
        inputProps={{
          "aria-label": "Unit (for example 10*9/L or mmol/L)",
        }}
        sx={{ width: 110 }}
      />
      <Select
        size="small"
        value={obs.within_days ?? 365}
        onChange={(e) =>
          setObservation({ within_days: Number(e.target.value) || 365 })
        }
        inputProps={{ "aria-label": "How recent the reading must be" }}
        sx={{ minWidth: 170, fontSize: "0.78rem" }}
      >
        {RECENCY_LABELS.map((r) => (
          <MenuItem key={r.days} value={r.days}>
            {r.label}
          </MenuItem>
        ))}
      </Select>
      <Tooltip title="Remove this lab value">
        <IconButton
          size="small"
          aria-label="Remove this lab value"
          onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
        >
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}

function pickObservationMode(
  obs: EditableObservationPayload,
): "absolute" | "temporal" | "reference_range" | "trend" | "aggregate" {
  if (obs.temporal) return "temporal";
  if (obs.reference_range) return "reference_range";
  if (obs.trend) return "trend";
  if (obs.aggregation) return "aggregate";
  return "absolute";
}
