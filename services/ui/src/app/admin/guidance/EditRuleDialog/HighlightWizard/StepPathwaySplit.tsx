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
 * Highlight-to-build wizard, Step 2: "Does this split into different
 * situations?"
 *
 * With a structured `recommendation_structure` (2+ top-level `<li>`
 * items), this is a statement to confirm, not a question to ask --
 * those items ARE the pathways, found from the guideline's own list
 * formatting. Without structure, boundaries fall back to the
 * `", or "`-splitting text heuristic and are shown with visibly lower
 * confidence (a dashed border, "we think we found N", never styled
 * identically to a structure-derived boundary). Either way the
 * result is a *suggestion* the reviewer can merge or split before
 * confirming -- never a silent auto-decision.
 *
 * See the plan's Step 2 wireframe (highlight-to-build_rule_wizard_
 * wireframes.md) for the exact layout this implements.
 */
import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ConfirmDialog from "@/components/ConfirmDialog";
import type { TextSelectionResult } from "../SentenceEditor/HighlightableRecommendationText";
import {
  splitPathways,
  type PathwayTextBoundary,
  type RecommendationStructure,
} from "../SentenceEditor/pathwayTextSplit";
import { STEP_PATHWAY_SPLIT } from "./copy";
import PathwayBoundaryRow from "./PathwayBoundaryRow";
import { MergedToOneState, NoSplitState } from "./PathwaySplitEmptyStates";
import { mergeBoundaries, pathwayLetter, splitBoundaryAt } from "./pathwayBoundaryEdits";

type SelectMode = "idle" | "merging" | "splitting";

export interface StepPathwaySplitProps {
  recommendationText?: string | null;
  recommendationStructure?: RecommendationStructure | null;
  /**
   * Lets the wizard re-open this step with the reviewer's own prior
   * merge/split edits still applied, instead of re-deriving fresh
   * boundaries from `splitPathways()` on every mount.
   */
  initialBoundaries?: PathwayTextBoundary[] | null;
  onConfirm: (boundaries: PathwayTextBoundary[]) => void;
  /** "No, it applies the same way to everyone" -- skips straight to a
   *  single Step 3 pass with no lettered pathways. */
  onNoSplit: () => void;
  /**
   * Fires whenever the proposed situation list changes (initial
   * detect, merge, split) so the host can paint each situation a
   * different colour in GuidelineQuotePanel -- Step 2 has no
   * "active" index yet, so the quote panel needs the live proposal
   * rather than waiting for Confirm.
   */
  onProposedBoundariesChange?: (boundaries: PathwayTextBoundary[] | null) => void;
}

export default function StepPathwaySplit({
  recommendationText,
  recommendationStructure,
  initialBoundaries,
  onConfirm,
  onNoSplit,
  onProposedBoundariesChange,
}: StepPathwaySplitProps) {
  const derivedBoundaries = useMemo(
    () => splitPathways(recommendationText, recommendationStructure),
    [recommendationText, recommendationStructure],
  );
  const [boundaries, setBoundaries] = useState<PathwayTextBoundary[] | null>(
    initialBoundaries ?? derivedBoundaries,
  );
  const [mode, setMode] = useState<SelectMode>("idle");
  const [selected, setSelected] = useState<number[]>([]);
  /**
   * Set only when the REVIEWER's own merge collapsed exactly two rows
   * down to one -- lets the empty-state branch tell "you merged
   * everything together" (undoable) apart from "the tool never found
   * more than one situation here" (nothing to undo). See
   * `mergedToOneTitle` in copy.ts.
   */
  const [preMergeSnapshot, setPreMergeSnapshot] = useState<
    PathwayTextBoundary[] | null
  >(null);
  /** Gates a merge of two NON-adjacent rows behind an extra confirm
   *  -- see `nonAdjacentMergeBody` in copy.ts for why that combination
   *  is destructive to the row in between, not just a reordering. */
  const [confirmNonAdjacentMerge, setConfirmNonAdjacentMerge] = useState(false);

  useEffect(() => {
    onProposedBoundariesChange?.(boundaries);
  }, [boundaries, onProposedBoundariesChange]);

  const source = boundaries?.[0]?.source ?? null;

  function resetSelection() {
    setMode("idle");
    setSelected([]);
  }

  function handleRowClick(index: number) {
    if (mode === "merging") {
      setSelected((prev) => {
        if (prev.includes(index)) return prev.filter((i) => i !== index);
        if (prev.length >= 2) return prev;
        return [...prev, index];
      });
      return;
    }
    if (mode === "splitting") {
      setSelected([index]);
    }
  }

  function performMerge(a: number, b: number) {
    if (!boundaries) return;
    const merged = mergeBoundaries(boundaries[a], boundaries[b]);
    const next = boundaries.filter((_, i) => i !== a && i !== b);
    next.splice(a, 0, merged);
    setPreMergeSnapshot(next.length === 1 ? boundaries : null);
    setBoundaries(next);
    resetSelection();
  }

  function handleConfirmMerge() {
    if (!boundaries || selected.length !== 2) return;
    const [a, b] = [...selected].sort((x, y) => x - y);
    if (b - a > 1) {
      // Not next-door rows -- merging them would also swallow
      // whichever row sits at index a+1..b-1, silently dropping its
      // wording. Make the reviewer say yes to that explicitly.
      setConfirmNonAdjacentMerge(true);
      return;
    }
    performMerge(a, b);
  }

  function handleConfirmNonAdjacentMerge() {
    setConfirmNonAdjacentMerge(false);
    if (selected.length !== 2) return;
    const [a, b] = [...selected].sort((x, y) => x - y);
    performMerge(a, b);
  }

  function handleUndoMerge() {
    if (!preMergeSnapshot) return;
    setBoundaries(preMergeSnapshot);
    setPreMergeSnapshot(null);
  }

  function handleConfirmSplit(selection: TextSelectionResult) {
    if (!boundaries || selected.length !== 1) return;
    const index = selected[0];
    const target = boundaries[index];
    if (selection.end <= 0 || selection.end >= target.text.length) return;
    const [before, after] = splitBoundaryAt(target, selection.end);
    const next = [...boundaries];
    next.splice(index, 1, before, after);
    setBoundaries(next);
    resetSelection();
  }

  const canConfirmMerge = mode === "merging" && selected.length === 2;

  if (!boundaries || boundaries.length < 2) {
    // Deliberately does NOT render StepHeader here -- its "we found
    // N situations" wording would flatly contradict whichever of
    // these two single-row explanations follows it.
    return (
      <Stack spacing={2}>
        {preMergeSnapshot ? (
          <MergedToOneState onUndo={handleUndoMerge} onNoSplit={onNoSplit} />
        ) : (
          <NoSplitState onNoSplit={onNoSplit} />
        )}
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      <StepHeader source={source} count={boundaries.length} />

      <Stack spacing={1}>
        {mode === "merging" && (
          <Typography variant="caption" color="text.secondary">
            {STEP_PATHWAY_SPLIT.mergeInstruction}
          </Typography>
        )}
        {boundaries.map((boundary, index) => (
          <PathwayBoundaryRow
            key={`${boundary.start}-${boundary.end}`}
            boundary={boundary}
            letter={pathwayLetter(index)}
            selectable={mode !== "idle"}
            selected={selected.includes(index)}
            isSplitTarget={mode === "splitting" && selected[0] === index}
            onClick={() => handleRowClick(index)}
            onConfirmSplitSelection={handleConfirmSplit}
          />
        ))}
      </Stack>

      <StepActions
        mode={mode}
        canConfirmMerge={canConfirmMerge}
        onLooksRight={() => onConfirm(boundaries)}
        onStartMerge={() => setMode("merging")}
        onStartSplit={() => setMode("splitting")}
        onConfirmMerge={handleConfirmMerge}
        onCancel={resetSelection}
      />

      {confirmNonAdjacentMerge && (
        <ConfirmDialog
          title={STEP_PATHWAY_SPLIT.nonAdjacentMergeTitle}
          body={STEP_PATHWAY_SPLIT.nonAdjacentMergeBody}
          confirmLabel={STEP_PATHWAY_SPLIT.nonAdjacentMergeConfirmLabel}
          cancelLabel={STEP_PATHWAY_SPLIT.cancelLabel}
          variant="danger"
          onConfirm={handleConfirmNonAdjacentMerge}
          onCancel={() => setConfirmNonAdjacentMerge(false)}
        />
      )}
    </Stack>
  );
}

function StepHeader({
  source,
  count,
}: {
  source: PathwayTextBoundary["source"] | null;
  count: number;
}) {
  const isStructure = source === "structure";
  return (
    <Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
        {isStructure
          ? STEP_PATHWAY_SPLIT.structureTitle(count)
          : STEP_PATHWAY_SPLIT.heuristicTitle}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {isStructure
          ? STEP_PATHWAY_SPLIT.structureTag
          : STEP_PATHWAY_SPLIT.heuristicTag(count)}
      </Typography>
    </Box>
  );
}

function StepActions({
  mode,
  canConfirmMerge,
  onLooksRight,
  onStartMerge,
  onStartSplit,
  onConfirmMerge,
  onCancel,
}: {
  mode: SelectMode;
  canConfirmMerge: boolean;
  onLooksRight: () => void;
  onStartMerge: () => void;
  onStartSplit: () => void;
  onConfirmMerge: () => void;
  onCancel: () => void;
}) {
  if (mode === "merging") {
    return (
      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ rowGap: 1 }}>
        <Button
          variant="contained"
          size="small"
          disabled={!canConfirmMerge}
          onClick={onConfirmMerge}
        >
          {STEP_PATHWAY_SPLIT.confirmMergeLabel}
        </Button>
        <Button variant="text" size="small" onClick={onCancel}>
          {STEP_PATHWAY_SPLIT.cancelLabel}
        </Button>
      </Stack>
    );
  }
  if (mode === "splitting") {
    return (
      <Stack direction="row" spacing={1}>
        <Button variant="text" size="small" onClick={onCancel}>
          {STEP_PATHWAY_SPLIT.cancelLabel}
        </Button>
      </Stack>
    );
  }
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ rowGap: 1 }}>
      <Button variant="contained" size="small" onClick={onLooksRight}>
        {STEP_PATHWAY_SPLIT.looksRightLabel}
      </Button>
      <Button variant="outlined" size="small" onClick={onStartMerge}>
        {STEP_PATHWAY_SPLIT.mergeLabel}
      </Button>
      <Button variant="outlined" size="small" onClick={onStartSplit}>
        {STEP_PATHWAY_SPLIT.splitLabel}
      </Button>
    </Stack>
  );
}

