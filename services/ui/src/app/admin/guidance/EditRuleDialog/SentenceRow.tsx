/**
 * One editable sentence row inside a SentenceCanvas card.
 *
 * Phase 3 of the edit-rule wizard redesign moves the primary editing
 * surface from a visible operator tree to a stack of plain-English
 * "sentence cards". Each row reads as one short sentence:
 *
 *   "has cough"                           (concept)
 *   "is 40 years or older"                (demographic)
 *   "has any 2 or more of these: ..."     (at-least cluster)
 *   "must NOT have asthma"                (single-concept NOT)
 *
 * All editing is contextual: clicking a chip opens the existing
 * ChipSearchPopover via the parent (so the search popover is
 * unchanged), demographic rows render their existing inline editor,
 * and AT_LEAST rows render a stepper next to their chips.
 *
 * No "kind" dropdown is rendered. The Advanced view (LogicTreeEditor)
 * still provides the operator-tree controls for power users; the
 * canvas hides them so first-time reviewers are not asked to choose
 * between AND, OR, NOT, AT_LEAST.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-C46DDFA3
 *   DO: DO-D4D4CAA8
 *   Risk: R-5F11517C
 *   VT: VT-123BDE46
 */
"use client";

import { useMemo } from "react";
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
import LightbulbIcon from "@mui/icons-material/Lightbulb";

import {
  ADD_BAR_LABELS,
  DEMOGRAPHIC_FIELD_LABELS,
  OBSERVATION_MODE_LABELS,
  OPERATOR_LABELS,
  RECENCY_LABELS,
  atLeastClusterLabel,
  friendlyTerm,
  recencyLabel,
} from "./copy";
import { detectVaguePhrase } from "./vaguePhrases";
import SynonymChipEditor from "./SynonymChipEditor";
import {
  DEMOGRAPHIC_FIELDS,
  DEMOGRAPHIC_OPERATORS,
  type EditableLogicNode,
  type EditableObservationPayload,
  type NodeUpdate,
  type ObservationOperator,
} from "./types";
import type { SentenceRowModel } from "./treeToCanvas";

interface RowCallbacks {
  /**
   * Called with the row's chip element when the reviewer clicks it.
   * The parent dialog opens the ChipSearchPopover anchored here.
   * Concept-only -- demographic rows ignore.
   */
  onSelectConcept: (nodeId: string, anchor?: HTMLElement | null) => void;
  /**
   * Called with the parent group's node_id when the reviewer asks to
   * add a new symptom. Used by AT_LEAST clusters and the "+ add" CTA
   * on cards.
   */
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  /** Open the concept-expansion coach for a vague phrase. */
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  onUpdate: (update: NodeUpdate) => void;
  selectedNodeId?: string | null;
}

interface Props extends RowCallbacks {
  row: SentenceRowModel;
}

/**
 * Single sentence row. Dispatches on ``row.variant`` and renders the
 * matching control set. Unknown variants render a visible "advanced"
 * fallback so the canvas never silently drops information.
 */
export default function SentenceRow(props: Props) {
  const { row } = props;
  switch (row.variant) {
    case "concept":
      return <ConceptRow {...props} />;
    case "demographic":
      return <DemographicRow {...props} />;
    case "at_least":
      return <AtLeastRow {...props} />;
    case "not_concept":
      return <NotConceptRow {...props} />;
    case "observation":
      return <ObservationRow {...props} />;
    case "unsupported":
    default:
      return <UnsupportedRow row={row} />;
  }
}

function ConceptRow({
  row,
  selectedNodeId,
  onSelectConcept,
  onRequestCoach,
  onUpdate,
}: Props) {
  const node = row.node;
  const isSelected = selectedNodeId === node.node_id;
  const friendly = friendlyTerm(node.criterion?.preferred_term);
  const label = friendly || "Click to pick a symptom";
  const vague = detectVaguePhrase(node.criterion?.preferred_term);
  const tooltip = node.criterion?.snomed_concept_id
    ? `${friendly} (clinical code ${node.criterion.snomed_concept_id}). Click to swap. X to remove.`
    : "No clinical code yet. Click to search and pick one.";
  return (
    <RowFrame ariaLabel={`Patient must have ${label}`}>
      <Typography
        variant="body2"
        sx={{ color: "text.secondary", flexShrink: 0 }}
      >
        has
      </Typography>
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
          onClick={(e) => onSelectConcept(node.node_id, e.currentTarget)}
          onDelete={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
          deleteIcon={<CloseIcon sx={{ fontSize: 14 }} />}
          sx={{
            height: 26,
            fontSize: "0.82rem",
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
        <VagueBadge
          term={label}
          onClick={(anchor) => onRequestCoach(node.node_id, anchor)}
        />
      )}
      {node.criterion?.snomed_concept_id && (
        <SynonymChipEditor node={node} onUpdate={onUpdate} />
      )}
    </RowFrame>
  );
}

function DemographicRow({ row, onUpdate }: Props) {
  const node = row.node;
  const fields = useMemo(() => DEMOGRAPHIC_FIELDS, []);
  const operators = useMemo(() => DEMOGRAPHIC_OPERATORS, []);
  const friendlyField =
    DEMOGRAPHIC_FIELD_LABELS[node.field ?? "age"] ?? "Patient detail";
  const ariaLabel = `Patient detail: ${friendlyField}`;
  return (
    <RowFrame ariaLabel={ariaLabel}>
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
        sx={{ minWidth: 150, fontSize: "0.82rem" }}
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
        sx={{ minWidth: 130, fontSize: "0.82rem" }}
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
    </RowFrame>
  );
}

/**
 * Observation-leaf row (Phase 6a).
 *
 * Renders a short sentence for a clinical measurement:
 *
 *   has Platelet count >= 400 x10^9/L in the last year
 *
 * Three responsibilities:
 *
 * 1. In the default "absolute" mode (no temporal / reference_range /
 *    trend / aggregation) the row is fully editable: clicking the
 *    observable chip opens the concept picker, the operator select
 *    swaps comparison symbols, the value field takes a number (or two
 *    for "between"), and the unit field is a free-text input so
 *    reviewers can correct a UCUM alias the ingest mis-typed. The
 *    recency window is a drop-down with six common presets.
 *
 * 2. In any advanced mode (temporal / reference_range / trend /
 *    aggregation) the row becomes read-only with a plain-English
 *    summary and a "Edit in Advanced view" hint. Structural edits to
 *    those modes live in the advanced LogicTreeEditor because the
 *    canvas's one-line-sentence shape cannot express them without
 *    pretending they are simple thresholds.
 *
 * 3. If the node is missing its ``observation`` payload entirely
 *    (legacy data or ingest bug) the row shows an empty placeholder
 *    with a "Needs attention" chip instead of crashing.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-7790EEA5 (extended for Phase 6a)
 *   DO: DO-710270EF (extended for Phase 6a)
 */
const OBSERVATION_OPERATORS: ObservationOperator[] = [
  ">=",
  "<=",
  ">",
  "<",
  "=",
  "between",
];

function observationMode(
  obs: EditableObservationPayload | undefined,
): "absolute" | "temporal" | "reference_range" | "trend" | "aggregate" {
  if (!obs) return "absolute";
  if (obs.temporal) return "temporal";
  if (obs.reference_range) return "reference_range";
  if (obs.trend) return "trend";
  if (obs.aggregation) return "aggregate";
  return "absolute";
}

function observationAriaLabel(
  obs: EditableObservationPayload | undefined,
): string {
  if (!obs) return "Incomplete lab value row -- needs attention";
  const term = friendlyTerm(obs.observable_term) || "lab value";
  const op = obs.operator ?? ">=";
  const value = Array.isArray(obs.value)
    ? `${obs.value[0]} to ${obs.value[1]}`
    : String(obs.value ?? "");
  const unit = obs.unit ?? "";
  return `Patient's ${term} is ${op} ${value} ${unit} ${recencyLabel(obs.within_days)}`.trim();
}

function ObservationRow({
  row,
  selectedNodeId,
  onSelectConcept,
  onUpdate,
}: Props) {
  const node = row.node;
  const obs = node.observation;
  const mode = observationMode(obs);

  if (!obs) {
    return (
      <RowFrame ariaLabel="Lab value row without data -- needs attention">
        <Chip
          label="Lab value needs attention"
          size="small"
          color="warning"
          variant="outlined"
          sx={{ height: 24, fontSize: "0.78rem" }}
        />
        <Tooltip title="Remove this lab value row">
          <IconButton
            size="small"
            aria-label="Remove this lab value row"
            onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </RowFrame>
    );
  }

  if (mode !== "absolute") {
    return <ObservationAdvancedRow node={node} obs={obs} onUpdate={onUpdate} />;
  }

  return (
    <ObservationAbsoluteRow
      node={node}
      obs={obs}
      isSelected={selectedNodeId === node.node_id}
      onSelectConcept={onSelectConcept}
      onUpdate={onUpdate}
    />
  );
}

function ObservationAbsoluteRow({
  node,
  obs,
  isSelected,
  onSelectConcept,
  onUpdate,
}: {
  node: EditableLogicNode;
  obs: EditableObservationPayload;
  isSelected: boolean;
  onSelectConcept: (id: string, anchor?: HTMLElement | null) => void;
  onUpdate: (u: NodeUpdate) => void;
}) {
  const term = friendlyTerm(obs.observable_term) || "Click to pick a lab value";
  const hasObservableId = Boolean(obs.observable_id);
  const chipTooltip = hasObservableId
    ? `${term} (clinical code ${obs.observable_id}). Click to swap.`
    : "No clinical code yet. Click to search and pick a lab value.";

  const isBetween = obs.operator === "between";
  const lo = Array.isArray(obs.value) ? obs.value[0] : obs.value;
  const hi = Array.isArray(obs.value) ? obs.value[1] : "";

  const setObservation = (patch: Partial<EditableObservationPayload>) =>
    onUpdate({
      kind: "set_observation",
      nodeId: node.node_id,
      observation: { ...obs, ...patch },
    });

  return (
    <RowFrame ariaLabel={observationAriaLabel(obs)}>
      <Typography
        variant="body2"
        sx={{ color: "text.secondary", fontWeight: 600, flexShrink: 0 }}
      >
        has
      </Typography>
      <Tooltip title={chipTooltip} arrow>
        <Chip
          label={term}
          color={
            isSelected ? "primary" : hasObservableId ? "success" : "warning"
          }
          variant={isSelected ? "filled" : "outlined"}
          size="small"
          onClick={(e) => onSelectConcept(node.node_id, e.currentTarget)}
          sx={{
            height: 26,
            fontSize: "0.82rem",
            fontWeight: 500,
            borderRadius: 1.5,
            bgcolor: !isSelected && hasObservableId ? "background.paper" : undefined,
          }}
          aria-label={`${term}. Click to swap.`}
        />
      </Tooltip>
      <Select
        size="small"
        value={obs.operator ?? ">="}
        onChange={(e) => {
          const newOp = String(e.target.value) as ObservationOperator;
          // Switching to "between" seeds a pair; switching away picks
          // the first element so the field stays populated.
          if (newOp === "between" && !Array.isArray(obs.value)) {
            setObservation({
              operator: newOp,
              value: [Number(obs.value ?? 0), Number(obs.value ?? 0)],
            });
          } else if (newOp !== "between" && Array.isArray(obs.value)) {
            setObservation({ operator: newOp, value: Number(obs.value[0]) });
          } else {
            setObservation({ operator: newOp });
          }
        }}
        inputProps={{ "aria-label": "How to compare the lab value" }}
        sx={{ minWidth: 110, fontSize: "0.82rem" }}
      >
        {OBSERVATION_OPERATORS.map((o) => (
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
          "aria-label": isBetween ? "Lower bound value" : "Value to compare with",
        }}
        sx={{ width: 90 }}
      />
      {isBetween && (
        <>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
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
        inputProps={{ "aria-label": "Unit (for example 10*9/L or mmol/L)" }}
        sx={{ width: 110 }}
      />
      <Select
        size="small"
        value={obs.within_days ?? 365}
        onChange={(e) =>
          setObservation({ within_days: Number(e.target.value) || 365 })
        }
        inputProps={{ "aria-label": "How recent the reading must be" }}
        sx={{ minWidth: 170, fontSize: "0.82rem" }}
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
    </RowFrame>
  );
}

function ObservationAdvancedRow({
  node,
  obs,
  onUpdate,
}: {
  node: EditableLogicNode;
  obs: EditableObservationPayload;
  onUpdate: (u: NodeUpdate) => void;
}) {
  const mode = observationMode(obs);
  const term = friendlyTerm(obs.observable_term) || "lab value";
  const modeLabel = OBSERVATION_MODE_LABELS[mode] ?? mode;
  return (
    <Box
      role="group"
      aria-label={`Advanced lab value row: ${term} -- ${modeLabel}`}
      sx={{
        px: 1.25,
        py: 1,
        bgcolor: "info.50",
        border: "1px dashed",
        borderColor: "info.200",
        borderRadius: 1.5,
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <Typography
          variant="body2"
          sx={{ fontWeight: 600, color: "info.dark" }}
        >
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
          Open the Advanced view to edit this rule's timing.
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Remove this lab value row">
          <IconButton
            size="small"
            aria-label="Remove this lab value row"
            onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Box>
  );
}

function AtLeastRow({
  row,
  selectedNodeId,
  onSelectConcept,
  onRequestAdd,
  onRequestCoach,
  onUpdate,
}: Props) {
  const node = row.node;
  const min = node.min ?? 1;
  const children = node.children ?? [];
  const childCount = children.length;
  return (
    <Box
      role="group"
      aria-label={atLeastClusterLabel(min)}
      sx={{
        px: 1.25,
        py: 1,
        bgcolor: "primary.50",
        border: "1px solid",
        borderColor: "primary.100",
        borderRadius: 1.5,
      }}
    >
      <Stack
        direction="row"
        spacing={0.75}
        alignItems="center"
        useFlexGap
        sx={{ flexWrap: "wrap", rowGap: 0.5 }}
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
            variant="body2"
            sx={{ fontWeight: 600, color: "primary.dark" }}
          >
            Any
          </Typography>
          <TextField
            size="small"
            type="number"
            value={min}
            onChange={(e) =>
              onUpdate({
                kind: "set_min",
                nodeId: node.node_id,
                min: Number(e.target.value) || 1,
              })
            }
            inputProps={{
              min: 1,
              max: Math.max(childCount, 1),
              "aria-label": "How many of these the patient must have",
            }}
            sx={{ width: 60 }}
          />
          <Typography
            variant="body2"
            sx={{ fontWeight: 600, color: "text.secondary" }}
          >
            or more of these
          </Typography>
        </Stack>
        {children.map((child) => (
          <AtLeastChip
            key={child.node_id}
            node={child}
            isSelected={selectedNodeId === child.node_id}
            onSelectConcept={onSelectConcept}
            onUpdate={onUpdate}
            onRequestCoach={onRequestCoach}
          />
        ))}
        <Chip
          icon={<AddIcon sx={{ fontSize: 14 }} />}
          label={ADD_BAR_LABELS.symptom}
          size="small"
          variant="outlined"
          color="primary"
          onClick={(e) => onRequestAdd(node.node_id, e.currentTarget)}
          aria-label="Add a symptom or sign to this group"
          sx={{
            height: 26,
            fontSize: "0.72rem",
            fontWeight: 600,
            borderRadius: 1.5,
            bgcolor: "background.paper",
          }}
        />
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Remove this group">
          <IconButton
            size="small"
            aria-label="Remove this group"
            onClick={() =>
              onUpdate({ kind: "remove", nodeId: node.node_id })
            }
            sx={{
              color: "text.secondary",
              "&:hover": { color: "error.main" },
            }}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Box>
  );
}

function AtLeastChip({
  node,
  isSelected,
  onSelectConcept,
  onUpdate,
  onRequestCoach,
}: {
  node: EditableLogicNode;
  isSelected: boolean;
  onSelectConcept: (id: string, anchor?: HTMLElement | null) => void;
  onUpdate: (u: NodeUpdate) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}) {
  const friendly = friendlyTerm(node.criterion?.preferred_term);
  const label = friendly || "Click to pick";
  const vague = detectVaguePhrase(node.criterion?.preferred_term);
  return (
    <Stack direction="row" spacing={0} alignItems="center" component="span">
      <Tooltip
        title={
          node.criterion?.snomed_concept_id
            ? `${friendly} (clinical code ${node.criterion.snomed_concept_id}). Click to swap. X to remove.`
            : "No clinical code yet. Click to search and pick one."
        }
        arrow
      >
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
          onClick={(e) => onSelectConcept(node.node_id, e.currentTarget)}
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
        <VagueBadge
          term={label}
          onClick={(anchor) => onRequestCoach(node.node_id, anchor)}
        />
      )}
    </Stack>
  );
}

function NotConceptRow({
  row,
  selectedNodeId,
  onSelectConcept,
  onRequestCoach,
  onUpdate,
}: Props) {
  const inner = row.node.children?.[0];
  if (!inner) {
    return (
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ fontStyle: "italic" }}
      >
        Empty &quot;must NOT have&quot; row.
      </Typography>
    );
  }
  const isSelected = selectedNodeId === inner.node_id;
  const friendly = friendlyTerm(inner.criterion?.preferred_term);
  const label = friendly || "Click to pick a symptom";
  const vague = detectVaguePhrase(inner.criterion?.preferred_term);
  return (
    <RowFrame ariaLabel={`Patient must NOT have ${label}`}>
      <Typography
        variant="body2"
        sx={{ color: "error.dark", fontWeight: 600, flexShrink: 0 }}
      >
        must NOT have
      </Typography>
      <Tooltip
        title={
          inner.criterion?.snomed_concept_id
            ? `${friendly} (clinical code ${inner.criterion.snomed_concept_id}). Click to swap.`
            : "No clinical code yet. Click to search and pick one."
        }
        arrow
      >
        <Chip
          label={label}
          color={
            isSelected
              ? "primary"
              : vague.isVague
                ? "warning"
                : inner.criterion?.snomed_concept_id
                  ? "error"
                  : "warning"
          }
          variant={isSelected ? "filled" : "outlined"}
          size="small"
          onClick={(e) => onSelectConcept(inner.node_id, e.currentTarget)}
          onDelete={() =>
            onUpdate({ kind: "remove", nodeId: row.node.node_id })
          }
          deleteIcon={<CloseIcon sx={{ fontSize: 14 }} />}
          sx={{
            height: 26,
            fontSize: "0.82rem",
            fontWeight: 500,
            borderRadius: 1.5,
            bgcolor:
              !isSelected && inner.criterion?.snomed_concept_id
                ? "background.paper"
                : undefined,
          }}
          aria-label={`${label}. Click to swap, X to remove.`}
        />
      </Tooltip>
      {vague.isVague && onRequestCoach && (
        <VagueBadge
          term={label}
          onClick={(anchor) => onRequestCoach(inner.node_id, anchor)}
        />
      )}
    </RowFrame>
  );
}

function UnsupportedRow({ row }: { row: SentenceRowModel }) {
  return (
    <Box
      role="status"
      sx={{
        px: 1.25,
        py: 1,
        bgcolor: "warning.50",
        border: "1px dashed",
        borderColor: "warning.200",
        borderRadius: 1.5,
      }}
    >
      <Typography
        variant="body2"
        color="warning.dark"
        sx={{ fontWeight: 600 }}
      >
        Complex condition (kind: {row.node.kind})
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Open the Advanced view to edit this part of the rule.
      </Typography>
    </Box>
  );
}

function RowFrame({
  ariaLabel,
  children,
}: {
  ariaLabel: string;
  children: React.ReactNode;
}) {
  return (
    <Stack
      role="group"
      aria-label={ariaLabel}
      direction="row"
      spacing={0.75}
      alignItems="center"
      useFlexGap
      sx={{
        flexWrap: "wrap",
        rowGap: 0.5,
        py: 0.5,
      }}
    >
      {children}
    </Stack>
  );
}

function VagueBadge({
  term,
  onClick,
}: {
  term: string;
  onClick: (anchor: HTMLElement) => void;
}) {
  return (
    <Tooltip
      title={`"${term}" is vague. Click for specific suggestions.`}
      arrow
    >
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
