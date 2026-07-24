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
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";

import HighlightableRecommendationText, {
  type HighlightSpan,
  type TextSelectionResult,
} from "../SentenceEditor/HighlightableRecommendationText";
import {
  conceptText,
  demographicToText,
  observationToText,
} from "../treeToSentence";
import type { EditableLogicNode } from "../types";
import { STEP_PREREQUISITES } from "./copy";
import { leafTextMatch } from "./leafTextMatch";

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
  match: ReturnType<typeof leafTextMatch>;
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
   * comment on the same prop. A DEMOGRAPHIC / OBSERVATION
   * prerequisite has no synonym set of its own, so those still use
   * `onEdit`'s single-pick swap.
   */
  onEditConcept: (nodeId: string) => void;
  onRemove: (nodeId: string) => void;
  /**
   * Fires when the reviewer confirms a NEW highlighted span that
   * isn't already one of `prerequisites`. The wizard orchestrator
   * decides which existing add-flow (demographic / observation /
   * concept search) to open, pre-filled with `selection.text` --
   * this component only detects and reports the selection.
   */
  onAddFromSelection: (selection: TextSelectionResult, anchor?: HTMLElement) => void;
  /** "No, nothing else always applies" -- lets the wizard move on
   *  without opening any add flow. */
  onConfirmNoMore?: () => void;
}

export default function StepPrerequisites({
  recommendationText,
  prerequisites,
  onEdit,
  onEditConcept,
  onRemove,
  onAddFromSelection,
  onConfirmNoMore,
}: StepPrerequisitesProps) {
  const [questionDismissed, setQuestionDismissed] = useState(false);

  const rows: PrerequisiteRowData[] = useMemo(() => {
    const leaves = collectPrerequisiteLeaves(prerequisites);
    return leaves.map((node) => ({
      node,
      label: prerequisiteLabel(node),
      match: leafTextMatch(recommendationText, node),
    }));
  }, [prerequisites, recommendationText]);

  const highlights: HighlightSpan[] = useMemo(
    () =>
      rows
        .filter((r) => r.match)
        .map((r) => ({
          start: r.match!.start,
          end: r.match!.end,
          kind: "confirmed" as const,
          label: r.label,
        })),
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
    <Stack spacing={2}>
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
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary" role="status">
          {STEP_PREREQUISITES.noTextFallback}
        </Typography>
      )}

      {rows.length > 0 && (
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
                onRemove={onRemove}
              />
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
            <Button variant="outlined" size="small" onClick={onConfirmNoMore}>
              {STEP_PREREQUISITES.noMoreLabel}
            </Button>
            {recommendationText && (
              <Button
                variant="text"
                size="small"
                onClick={() => setQuestionDismissed(true)}
              >
                {STEP_PREREQUISITES.highlightMoreLabel}
              </Button>
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
  onRemove,
}: {
  row: PrerequisiteRowData;
  onEdit: (nodeId: string, anchor?: HTMLElement | null) => void;
  onEditConcept: (nodeId: string) => void;
  onRemove: (nodeId: string) => void;
}) {
  const hasAnchor = !!row.match;
  function handleEdit(anchor: HTMLElement) {
    if (row.node.kind === "CONCEPT") {
      onEditConcept(row.node.node_id);
    } else {
      onEdit(row.node.node_id, anchor);
    }
  }
  return (
    <Stack
      direction="row"
      alignItems="center"
      spacing={1}
      data-testid={`prerequisite-row-${row.node.node_id}`}
      data-has-anchor={hasAnchor}
      sx={{
        p: 1,
        borderRadius: 1,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      {hasAnchor ? (
        <CheckCircleIcon fontSize="small" color="success" />
      ) : (
        <WarningAmberRoundedIcon fontSize="small" color="warning" />
      )}
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Typography variant="body2">{row.label}</Typography>
        {!hasAnchor && (
          <Typography variant="caption" color="text.secondary" display="block">
            {STEP_PREREQUISITES.noAnchorHint}
          </Typography>
        )}
      </Box>
      <Button
        size="small"
        onClick={(e) => handleEdit(e.currentTarget)}
      >
        {hasAnchor
          ? STEP_PREREQUISITES.editLabel
          : STEP_PREREQUISITES.placeManuallyLabel}
      </Button>
      <Button
        size="small"
        color="error"
        startIcon={<DeleteOutlineIcon fontSize="small" />}
        onClick={() => onRemove(row.node.node_id)}
      >
        {STEP_PREREQUISITES.removeLabel}
      </Button>
    </Stack>
  );
}
