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

import HighlightableRecommendationText, {
  type TextSelectionResult,
} from "../SentenceEditor/HighlightableRecommendationText";
import {
  splitPathways,
  type PathwayTextBoundary,
  type RecommendationStructure,
} from "../SentenceEditor/pathwayTextSplit";
import { STEP_PATHWAY_SPLIT } from "./copy";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

function pathwayLetter(index: number): string {
  return LETTERS[index % LETTERS.length];
}

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

/** Merge two adjacent boundaries into one; a mixed structure+heuristic
 *  pair degrades to "heuristic" -- the merged text no longer reads as
 *  a single clean `<li>` the guideline's own markup vouched for. */
function mergeBoundaries(
  first: PathwayTextBoundary,
  second: PathwayTextBoundary,
): PathwayTextBoundary {
  return {
    start: Math.min(first.start, second.start),
    end: Math.max(first.end, second.end),
    text: `${first.text} ${second.text}`.trim(),
    source: first.source === second.source ? first.source : "heuristic",
  };
}

/** Split one boundary into two at a LOCAL offset (relative to the
 *  boundary's own text, as returned by a scoped selection). */
function splitBoundaryAt(
  boundary: PathwayTextBoundary,
  localSplitPoint: number,
): [PathwayTextBoundary, PathwayTextBoundary] {
  const splitAt = boundary.start + localSplitPoint;
  return [
    {
      start: boundary.start,
      end: splitAt,
      text: boundary.text.slice(0, localSplitPoint).trim(),
      source: boundary.source,
    },
    {
      start: splitAt,
      end: boundary.end,
      text: boundary.text.slice(localSplitPoint).trim(),
      source: boundary.source,
    },
  ];
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

  function handleConfirmMerge() {
    if (!boundaries || selected.length !== 2) return;
    const [a, b] = [...selected].sort((x, y) => x - y);
    const merged = mergeBoundaries(boundaries[a], boundaries[b]);
    const next = boundaries.filter((_, i) => i !== a && i !== b);
    next.splice(a, 0, merged);
    setBoundaries(next);
    resetSelection();
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

  return (
    <Stack spacing={2}>
      <StepHeader source={source} count={boundaries?.length ?? 0} />

      {!boundaries || boundaries.length < 2 ? (
        <NoSplitState onNoSplit={onNoSplit} />
      ) : (
        <>
          <Stack spacing={1}>
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
        </>
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

function PathwayBoundaryRow({
  boundary,
  letter,
  selectable,
  selected,
  isSplitTarget,
  onClick,
  onConfirmSplitSelection,
}: {
  boundary: PathwayTextBoundary;
  letter: string;
  selectable: boolean;
  selected: boolean;
  isSplitTarget: boolean;
  onClick: () => void;
  onConfirmSplitSelection: (selection: TextSelectionResult) => void;
}) {
  const nestedItems = boundary.structureChildren ?? [];
  // Once this row IS the active split target it hosts genuinely
  // interactive descendants of its own (word chunks, Confirm/Cancel)
  // -- nesting those inside a role="button" wrapper is both an ARIA
  // violation and, concretely, makes this row's own accessible name
  // swallow "Confirm selection" as a text-content substring, which
  // breaks any query for that button. Only wrap non-target rows.
  const isSelectableButton = selectable && !isSplitTarget;
  return (
    <Box
      data-testid={`pathway-boundary-row-${boundary.start}-${boundary.end}`}
      data-selected={selected || undefined}
      data-source={boundary.source}
      role={isSelectableButton ? "button" : undefined}
      tabIndex={isSelectableButton ? 0 : undefined}
      onClick={isSelectableButton ? onClick : undefined}
      onKeyDown={
        isSelectableButton
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      sx={{
        p: 1.25,
        borderRadius: 1.5,
        border: boundary.source === "structure" ? "1px solid" : "1px dashed",
        borderColor: selected ? "primary.main" : "divider",
        bgcolor: selected ? "primary.50" : "background.paper",
        cursor: isSelectableButton ? "pointer" : "default",
      }}
    >
      {isSplitTarget ? (
        <Box>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
            {STEP_PATHWAY_SPLIT.splitInstruction}
          </Typography>
          <HighlightableRecommendationText
            text={boundary.text}
            onConfirmSelection={onConfirmSplitSelection}
          />
        </Box>
      ) : (
        <Typography variant="body2">
          <strong>({letter})</strong> {boundary.text}
        </Typography>
      )}
      {!isSplitTarget && nestedItems.length > 0 && (
        <Box component="ul" sx={{ mt: 0.5, mb: 0, pl: 3 }}>
          {nestedItems.map((child) => (
            <Box component="li" key={`${child.start}-${child.end}`}>
              <Typography variant="caption" color="text.secondary">
                {child.text}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

function NoSplitState({ onNoSplit }: { onNoSplit: () => void }) {
  return (
    <Box
      sx={{
        p: 2,
        borderRadius: 1.5,
        border: "1px dashed",
        borderColor: "divider",
        textAlign: "center",
      }}
    >
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        {STEP_PATHWAY_SPLIT.noSplitBody}
      </Typography>
      <Button variant="outlined" size="small" onClick={onNoSplit}>
        {STEP_PATHWAY_SPLIT.noSplitConfirmLabel}
      </Button>
    </Box>
  );
}
