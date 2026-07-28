/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Highlight-to-build wizard, Step 1: "What must ALWAYS be true?"
 *
 * Fuzzy-matches every existing DEMOGRAPHIC / OBSERVATION / CONCEPT
 * prerequisite leaf (the wrapping AND's siblings alongside the
 * pathway-split OR -- see `findPathwaySplit` -- or the whole tree
 * when there is no split yet) onto the guideline's own verbatim
 * text, so an age check like "aged 55 or over" lights up with no
 * user action needed. The reviewer can then drag-select (or
 * tab/shift-arrow) any remaining text to add another always-true
 * fact, or say "No, nothing else" to move on.
 *
 * See the plan's Step 1 wireframe (highlight-to-build_rule_wizard_
 * wireframes.md) for the exact layout this implements.
 */
import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";

import DemographicRow from "../LogicTreeEditor/DemographicRow";
import HighlightableRecommendationText, {
  type HighlightSpan,
  type TextSelectionResult,
} from "../SentenceEditor/HighlightableRecommendationText";
import type { TextMatchRange } from "../SentenceEditor/recommendationTextMatch";
import { findAllValidationErrors } from "../treeOps";
import {
  conceptSeedLabels,
  conceptText,
  demographicToText,
  observationToText,
} from "../treeToSentence";
import type { EditableLogicNode, NodeUpdate } from "../types";
import CapturedConceptChips from "./CapturedConceptChips";
import { STEP_PREREQUISITES, WIZARD_TOOLTIPS } from "./copy";
import { leafTextMatches } from "./leafTextMatch";
import type { PathwayDemographicField } from "./PathwayDemographicsPanel";
import ProblemNodeRow from "./ProblemNodeRow";

const PREREQUISITE_LEAF_KINDS = new Set([
  "CONCEPT",
  "DEMOGRAPHIC",
  "OBSERVATION",
  "MEDICATION",
  "ALLERGY",
  "TREATMENT_HISTORY",
  "RULE_FIRED",
]);

/**
 * Walk each top-level prerequisite node and collect its leaf
 * descendants. A prerequisite is almost always a single DEMOGRAPHIC
 * leaf (NG12 1.2.9's age check), but a hand-authored rule may wrap
 * several always-true leaves in a group -- recursing keeps both
 * shapes working without the caller needing to know which one it has.
 */
export function collectPrerequisiteLeaves(
  nodes: EditableLogicNode[],
): EditableLogicNode[] {
  const leaves: EditableLogicNode[] = [];
  const walk = (n: EditableLogicNode): void => {
    if (PREREQUISITE_LEAF_KINDS.has(n.kind)) {
      leaves.push(n);
      return;
    }
    for (const child of n.children ?? []) walk(child);
  };
  for (const node of nodes) walk(node);
  return leaves;
}

function capitalize(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/**
 * Plain-English label for the "Captured so far" list. Reuses the
 * same phrase-building already unit-tested in `treeToSentence.ts`
 * rather than inventing a second set of copy rules.
 */
export function prerequisiteLabel(node: EditableLogicNode): string {
  if (node.kind === "DEMOGRAPHIC") {
    return capitalize(`Patient ${demographicToText(node)}`);
  }
  if (node.kind === "OBSERVATION" && node.observation) {
    return capitalize(`Patient ${observationToText(node.observation)}`);
  }
  if (node.kind === "CONCEPT") {
    return capitalize(`Patient has ${conceptText(node)}`);
  }
  return "An unfilled patient detail";
}

interface PrerequisiteRowData {
  node: EditableLogicNode;
  label: string;
  matches: TextMatchRange[];
}

export interface StepPrerequisitesProps {
  recommendationText?: string | null;
  /**
   * Existing "always true" leaves/groups -- typically
   * `findPathwaySplit(tree)?.prerequisites`, or the whole tree's
   * children when there is no pathway split yet.
   */
  prerequisites: EditableLogicNode[];
  onEdit: (nodeId: string, anchor?: HTMLElement | null) => void;
  /**
   * Opens the add/remove/depth synonym editor for an already-matched
   * CONCEPT prerequisite -- see `PathwayConditionsStage`'s doc
   * comment on the same prop. An OBSERVATION prerequisite has no
   * synonym set of its own, so it still uses `onEdit`'s single-pick
   * swap. A DEMOGRAPHIC prerequisite (age/sex) is neither a search
   * swap nor a synonym set -- it expands the same inline
   * `DemographicRow` editor Step 3 uses, driven by `onUpdate` below.
   */
  onEditConcept: (nodeId: string) => void;
  /** Applies a `set_demographic` (or any other) update to the tree --
   *  used by the inline age/sex editor a DEMOGRAPHIC row expands to. */
  onUpdate: (update: NodeUpdate) => void;
  onRemove: (nodeId: string) => void;
  /**
   * Fires when the reviewer confirms a NEW highlighted span that
   * isn't already one of `prerequisites`. The wizard orchestrator
   * decides which existing add-flow (demographic / observation /
   * concept search) to open, pre-filled with `selection.text` --
   * this component only detects and reports the selection.
   */
  onAddFromSelection: (selection: TextSelectionResult, anchor?: HTMLElement) => void;
  /**
   * Adds a blank, global (every-pathway) age or sex prerequisite --
   * the reviewer then fills in the operator/value/unit via the same
   * inline editor an existing DEMOGRAPHIC row expands to. Undefined
   * hides the "Add age" / "Add sex" buttons entirely (e.g. in tests
   * that don't care about this affordance).
   */
  onAddDemographic?: (field: PathwayDemographicField) => void;
  /** "No, nothing else always applies" -- lets the wizard move on
   *  without opening any add flow. */
  onConfirmNoMore?: () => void;
}

export default function StepPrerequisites({
  recommendationText,
  prerequisites,
  onEdit,
  onEditConcept,
  onUpdate,
  onRemove,
  onAddFromSelection,
  onAddDemographic,
  onConfirmNoMore,
}: StepPrerequisitesProps) {
  const [questionDismissed, setQuestionDismissed] = useState(false);

  const rows: PrerequisiteRowData[] = useMemo(() => {
    const leaves = collectPrerequisiteLeaves(prerequisites);
    return leaves.map((node) => ({
      node,
      label: prerequisiteLabel(node),
      matches: leafTextMatches(recommendationText, node),
    }));
  }, [prerequisites, recommendationText]);

  // Empty/invalid GROUP nodes (e.g. an "any of" group the reviewer
  // started but never filled in) have no leaf of their own, so
  // `collectPrerequisiteLeaves` never surfaces them -- they would
  // otherwise be invisible even though `findValidationError` blocks
  // Save on them. Filtering out nodeIds already covered by a leaf row
  // avoids double-reporting the same problem twice.
  const rowNodeIds = useMemo(() => new Set(rows.map((r) => r.node.node_id)), [rows]);
  const problemIssues = useMemo(
    () =>
      prerequisites
        .flatMap((node) => findAllValidationErrors(node))
        .filter((issue) => issue.nodeId && !rowNodeIds.has(issue.nodeId)),
    [prerequisites, rowNodeIds],
  );

  const hasAge = rows.some((r) => r.node.kind === "DEMOGRAPHIC" && r.node.field === "age");
  const hasSex = rows.some((r) => r.node.kind === "DEMOGRAPHIC" && r.node.field === "sex");

  const highlights: HighlightSpan[] = useMemo(
    () =>
      rows.flatMap((r) =>
        r.matches.map((m) => ({
          start: m.start,
          end: m.end,
          kind: "confirmed" as const,
          label: r.label,
        })),
      ),
    [rows],
  );

  // "Highlight more text" only hides the question WHILE the reviewer is
  // actively picking a new fact -- it must never strand them. Once the
  // captured set changes (a new prerequisite lands, or one is removed),
  // ask again rather than leaving them with no way to proceed.
  const rowCount = rows.length;
  useEffect(() => {
    setQuestionDismissed(false);
  }, [rowCount]);

  return (
    <Stack spacing={2} data-tour="er-03-always">
      <Box>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {STEP_PREREQUISITES.title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {STEP_PREREQUISITES.helper}
        </Typography>
      </Box>

      {recommendationText ? (
        <Box
          sx={{
            p: 1.5,
            borderRadius: 1.5,
            bgcolor: "grey.50",
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <HighlightableRecommendationText
            text={recommendationText}
            highlights={highlights}
            onConfirmSelection={onAddFromSelection}
          />
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
            {STEP_PREREQUISITES.selectionHint}
          </Typography>
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary" role="status">
          {STEP_PREREQUISITES.noTextFallback}
        </Typography>
      )}

      {(rows.length > 0 || problemIssues.length > 0) && (
        <Box>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.04em",
              color: "text.secondary",
            }}
          >
            {STEP_PREREQUISITES.capturedHeading}
          </Typography>
          <Stack spacing={0.75} sx={{ mt: 0.75 }}>
            {rows.map((row) => (
              <PrerequisiteRow
                key={row.node.node_id}
                row={row}
                onEdit={onEdit}
                onEditConcept={onEditConcept}
                onUpdate={onUpdate}
                onRemove={onRemove}
              />
            ))}
            {problemIssues.map((issue) => (
              <ProblemNodeRow key={issue.nodeId} issue={issue} onRemove={onRemove} />
            ))}
          </Stack>
        </Box>
      )}

      {!questionDismissed && (
        <Box
          role="group"
          aria-label={STEP_PREREQUISITES.questionAriaLabel}
          sx={{ p: 1.5, borderRadius: 1.5, bgcolor: "primary.50" }}
        >
          <Typography variant="body2" sx={{ mb: 1 }}>
            {STEP_PREREQUISITES.question}
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ rowGap: 1 }}>
            <Tooltip title={WIZARD_TOOLTIPS.noMore}>
              <Button variant="outlined" size="small" onClick={onConfirmNoMore}>
                {STEP_PREREQUISITES.noMoreLabel}
              </Button>
            </Tooltip>
            {onAddDemographic && !hasAge && (
              <Tooltip title={WIZARD_TOOLTIPS.addAgeAlways}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<AddRoundedIcon fontSize="small" />}
                  onClick={() => onAddDemographic("age")}
                  aria-label={STEP_PREREQUISITES.addAgeAriaLabel}
                >
                  {STEP_PREREQUISITES.addAgeLabel}
                </Button>
              </Tooltip>
            )}
            {onAddDemographic && !hasSex && (
              <Tooltip title={WIZARD_TOOLTIPS.addSexAlways}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<AddRoundedIcon fontSize="small" />}
                  onClick={() => onAddDemographic("sex")}
                  aria-label={STEP_PREREQUISITES.addSexAriaLabel}
                >
                  {STEP_PREREQUISITES.addSexLabel}
                </Button>
              </Tooltip>
            )}
            {recommendationText && (
              <Tooltip title={WIZARD_TOOLTIPS.highlightMore}>
                <Button
                  variant="text"
                  size="small"
                  onClick={() => setQuestionDismissed(true)}
                >
                  {STEP_PREREQUISITES.highlightMoreLabel}
                </Button>
              </Tooltip>
            )}
          </Stack>
        </Box>
      )}
    </Stack>
  );
}

function PrerequisiteRow({
  row,
  onEdit,
  onEditConcept,
  onUpdate,
  onRemove,
}: {
  row: PrerequisiteRowData;
  onEdit: (nodeId: string, anchor?: HTMLElement | null) => void;
  onEditConcept: (nodeId: string) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRemove: (nodeId: string) => void;
}) {
  const isDemographic = row.node.kind === "DEMOGRAPHIC";
  // A DEMOGRAPHIC row has no search-swap or synonym flow to hand off
  // to -- "Edit" expands the same inline age/sex controls Step 3
  // uses, in place, rather than opening a popover elsewhere on the
  // page (see the `onEditConcept`/`onUpdate` doc comments above).
  const [expanded, setExpanded] = useState(false);
  const hasAnchor = row.matches.length > 0;
  const seedLabels = row.node.kind === "CONCEPT" ? conceptSeedLabels(row.node) : [];

  function handleEdit(anchor: HTMLElement) {
    if (row.node.kind === "CONCEPT") {
      onEditConcept(row.node.node_id);
      return;
    }
    if (isDemographic) {
      setExpanded((prev) => !prev);
      return;
    }
    onEdit(row.node.node_id, anchor);
  }

  const editLabel = isDemographic
    ? expanded
      ? STEP_PREREQUISITES.doneEditingLabel
      : STEP_PREREQUISITES.editLabel
    : hasAnchor
      ? STEP_PREREQUISITES.editLabel
      : STEP_PREREQUISITES.placeManuallyLabel;
  const editTip = isDemographic
    ? expanded
      ? WIZARD_TOOLTIPS.doneEditing
      : WIZARD_TOOLTIPS.editCaptured
    : hasAnchor
      ? WIZARD_TOOLTIPS.editCaptured
      : WIZARD_TOOLTIPS.placeManually;

  return (
    <Box
      data-testid={`prerequisite-row-${row.node.node_id}`}
      data-has-anchor={hasAnchor}
      data-node-id={row.node.node_id}
      data-wizard-jump-target="true"
      sx={{
        p: 1,
        borderRadius: 1,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1}>
        {hasAnchor ? (
          <CheckCircleIcon fontSize="small" color="success" />
        ) : (
          <WarningAmberRoundedIcon fontSize="small" color="warning" />
        )}
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          {seedLabels.length > 1 ? (
            <CapturedConceptChips terms={seedLabels} />
          ) : (
            <Typography variant="body2">{row.label}</Typography>
          )}
          {!hasAnchor && (
            <Typography variant="caption" color="text.secondary" display="block">
              {STEP_PREREQUISITES.noAnchorHint}
            </Typography>
          )}
        </Box>
        <Tooltip title={editTip}>
          <Button size="small" onClick={(e) => handleEdit(e.currentTarget)}>
            {editLabel}
          </Button>
        </Tooltip>
        <Tooltip title={WIZARD_TOOLTIPS.removePrerequisite}>
          <Button
            size="small"
            color="error"
            startIcon={<DeleteOutlineIcon fontSize="small" />}
            onClick={() => onRemove(row.node.node_id)}
          >
            {STEP_PREREQUISITES.removeLabel}
          </Button>
        </Tooltip>
      </Stack>
      {isDemographic && (
        <Collapse in={expanded} unmountOnExit>
          <Box sx={{ mt: 1, pl: 4 }}>
            <DemographicRow node={row.node} onUpdate={onUpdate} />
          </Box>
        </Collapse>
      )}
    </Box>
  );
}
