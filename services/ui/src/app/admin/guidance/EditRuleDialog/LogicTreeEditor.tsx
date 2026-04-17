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

import { useMemo, useState } from "react";
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
  OPERATOR_LABELS,
  friendlyTerm,
} from "./copy";
import { detectVaguePhrase } from "./vaguePhrases";
import {
  DEMOGRAPHIC_FIELDS,
  DEMOGRAPHIC_OPERATORS,
  type EditableLogicNode,
  type LogicNodeKind,
  type NodeUpdate,
} from "./types";

interface Props {
  root: EditableLogicNode;
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string) => void;
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
            onAddConcept={() => {
              onSelect(node.node_id);
              onRequestAdd(node.node_id);
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
  onSelect: (nodeId: string) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  root: EditableLogicNode;
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
        spacing={0.75}
        sx={{ mb: 1, pl: 0.5 }}
      >
        <Typography
          variant="body2"
          sx={{ fontWeight: 600, color: "text.primary" }}
        >
          The rule fires if the patient matches any one of these pathways:
        </Typography>
        <Tooltip title="Add another pathway">
          <Chip
            icon={<AddIcon sx={{ fontSize: 14 }} />}
            label="Add pathway"
            size="small"
            variant="outlined"
            onClick={() =>
              onUpdate({
                kind: "add_group",
                parentNodeId: node.node_id,
                groupKind: "AND",
              })
            }
            sx={{ height: 24, fontSize: "0.72rem" }}
          />
        </Tooltip>
      </Stack>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={1.5}
        useFlexGap
        sx={{ alignItems: "stretch", flexWrap: "wrap" }}
      >
        {children.map((child, i) => (
          <Box
            key={child.node_id}
            sx={{
              flex: 1,
              minWidth: { xs: "100%", md: 280 },
              p: 1.25,
              borderRadius: 1.5,
              border: "1px solid",
              borderColor: "primary.100",
              bgcolor: "background.paper",
              boxShadow: 1,
              position: "relative",
            }}
          >
            <Stack
              direction="row"
              alignItems="center"
              spacing={0.5}
              sx={{ mb: 0.5 }}
            >
              <Typography
                variant="subtitle2"
                sx={{ fontWeight: 700, color: "primary.dark" }}
              >
                Pathway {String.fromCharCode(65 + i)}
              </Typography>
              <Box sx={{ flex: 1 }} />
              <Tooltip title="Remove this pathway">
                <IconButton
                  size="small"
                  aria-label={`Remove pathway ${String.fromCharCode(65 + i)}`}
                  onClick={() =>
                    onUpdate({ kind: "remove", nodeId: child.node_id })
                  }
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
            {i < children.length - 1 && (
              <Box
                sx={{
                  display: { xs: "none", md: "flex" },
                  position: "absolute",
                  right: -22,
                  top: "50%",
                  transform: "translateY(-50%)",
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  bgcolor: "primary.main",
                  color: "primary.contrastText",
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  alignItems: "center",
                  justifyContent: "center",
                  zIndex: 1,
                }}
                aria-hidden
              >
                OR
              </Box>
            )}
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

/**
 * Body of a single pathway card.
 *
 * The card itself already implies "patient must have ALL of these" -- so
 * when the immediate child is a plain AND group with at least one child,
 * we render its children directly with no extra kind selector and no
 * collapse chevron. This avoids the cryptic "(1 symptom, 1 sub-group)"
 * collapsed line that previously made pathways B and C look empty.
 *
 * Anything that isn't a plain AND (an OR, NOT, AT-LEAST, or a bare
 * leaf) is rendered through the standard NodeView so the user still
 * sees the structure they built.
 */
interface PathwayCardBodyProps {
  root: EditableLogicNode;
  node: EditableLogicNode;
  depth: number;
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}

function PathwayCardBody(p: PathwayCardBodyProps) {
  const { node, depth, root, selectedNodeId } = p;

  if (node.kind === "AND") {
    const children = node.children ?? [];
    if (children.length === 0) {
      return (
        <Box>
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
            onAddConcept={() => {
              p.onSelect(node.node_id);
              p.onRequestAdd(node.node_id);
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
          onAddConcept={() => {
            p.onSelect(node.node_id);
            p.onRequestAdd(node.node_id);
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
  onSelect: (nodeId: string) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string) => void;
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
        mt: 0.75,
        pl: 1.25,
        py: 0.5,
        borderLeft: "2px solid",
        borderColor: depth <= 1 ? "primary.light" : "divider",
        bgcolor: "grey.50",
        borderRadius: "0 4px 4px 0",
      }}
    >
      <Stack
        direction="row"
        spacing={0.75}
        alignItems="center"
        useFlexGap
        sx={{ flexWrap: "wrap", rowGap: 0.5 }}
      >
        <Typography variant="body2" sx={{ fontWeight: 600, mr: 0.25 }}>
          At least
        </Typography>
        <AtLeastCounter
          min={node.min ?? 1}
          childCount={childCount}
          onChange={(n) => onUpdate({ kind: "set_min", nodeId: node.node_id, min: n })}
        />
        <Typography variant="body2" sx={{ mr: 0.25 }}>
          of these:
        </Typography>
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
          onClick={() => {
            onSelect(node.node_id);
            onRequestAdd(node.node_id);
          }}
          aria-label="Add a symptom or sign to this group"
          sx={{ height: 26, fontSize: "0.72rem" }}
        />
        <Box sx={{ flex: 1 }} />
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
  onSelect: (id: string) => void;
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
    <Stack direction="row" spacing={0.25} alignItems="center" component="span">
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
          onClick={() => onSelect(node.node_id)}
          onDelete={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
          deleteIcon={<CloseIcon sx={{ fontSize: 14 }} />}
          sx={{ height: 26, fontSize: "0.78rem" }}
          aria-label={`${label}. Click to swap, X to remove.`}
        />
      </Tooltip>
      {vague.isVague && onRequestCoach && (
        <VaguePhraseBadge
          term={label}
          onClick={(anchor) => onRequestCoach(node.node_id, anchor)}
        />
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
  onAddConcept: () => void;
  onAddGroup: (k: "AND" | "OR" | "NOT" | "AT_LEAST") => void;
  onAddDemographic: () => void;
}) {
  const nextGroupKind = parentKind === "AND" ? "OR" : "AND";
  const groupLabel =
    nextGroupKind === "OR"
      ? "Add a choice (any of these)"
      : "Add a sub-group (all of these)";
  return (
    <Stack
      direction="row"
      spacing={0.5}
      alignItems="center"
      sx={{ mt: 0.5, pl: 0.25, color: "text.secondary", flexWrap: "wrap" }}
    >
      <Chip
        icon={<AddIcon sx={{ fontSize: 14 }} />}
        label={ADD_BAR_LABELS.symptom}
        size="small"
        variant="outlined"
        onClick={onAddConcept}
        sx={{ height: 24, fontSize: "0.72rem" }}
      />
      <Chip
        icon={<AddIcon sx={{ fontSize: 14 }} />}
        label={groupLabel}
        size="small"
        variant="outlined"
        onClick={() => onAddGroup(nextGroupKind)}
        sx={{ height: 24, fontSize: "0.72rem" }}
      />
      <Chip
        icon={<AddIcon sx={{ fontSize: 14 }} />}
        label={ADD_BAR_LABELS.detail}
        size="small"
        variant="outlined"
        onClick={onAddDemographic}
        sx={{ height: 24, fontSize: "0.72rem" }}
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
      spacing={0.25}
      alignItems="center"
      sx={{ display: "inline-flex", mr: 0.5, mb: 0.5 }}
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
          onClick={() => onSelect(node.node_id)}
          onDelete={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
          deleteIcon={<CloseIcon sx={{ fontSize: 14 }} />}
          sx={{ height: 26, fontSize: "0.78rem" }}
          aria-label={`${label}. Click to swap, X to remove.`}
        />
      </Tooltip>
      {vague.isVague && onRequestCoach && (
        <VaguePhraseBadge
          term={label}
          onClick={(anchor) => onRequestCoach(node.node_id, anchor)}
        />
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
