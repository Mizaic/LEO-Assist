/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";

import { useWordSelection, type TextSelectionResult } from "./useWordSelection";

/**
 * Renders a span of guideline text as individually focusable word/phrase
 * chunks so a reviewer can select a range of text with either the mouse
 * (click-drag) or the keyboard (Tab to a chunk, Shift+Arrow to extend,
 * Enter to confirm) -- the fallback path used when no
 * `recommendation_structure` exists at all, or for a single compound
 * list-item's text that still bundles more than one criterion. See the
 * "Fallback" sections of the wizard wireframes for the exact interaction.
 *
 * The selection state machine itself lives in useWordSelection.ts, shared
 * with HighlightableRowText.tsx (Step 3's per-row highlight-and-code pick).
 */

export type HighlightKind = "confirmed" | "candidate";

export interface HighlightSpan {
  start: number;
  end: number;
  kind: HighlightKind;
  label?: string;
}

/** Background/text colour for each highlight kind -- exported so other
 * read-only renderers (e.g. GuidelineQuotePanel) use the exact same
 * palette as this interactive one, instead of a second copy that can
 * drift out of sync. */
export const HIGHLIGHT_COLORS: Record<HighlightKind, { bgcolor: string; color: string }> = {
  confirmed: { bgcolor: "#DCFCE7", color: "#14532D" },
  candidate: { bgcolor: "#FEF9C3", color: "#713F12" },
};

export type { TextSelectionResult };

interface Props {
  text: string;
  /** Already-resolved (confirmed) or AI-suggested (candidate) spans,
   * rendered distinctly from plain and pending-selection text. */
  highlights?: HighlightSpan[];
  /** Text outside the current pathway/scope -- rendered greyed out and
   * not selectable (see the wireframes' "dimmed" notation). */
  dimmedRanges?: Array<{ start: number; end: number }>;
  onConfirmSelection: (selection: TextSelectionResult, anchor?: HTMLElement) => void;
  onCancelSelection?: () => void;
}

function rangesOverlap(
  a: { start: number; end: number },
  b: { start: number; end: number }
): boolean {
  return a.start < b.end && a.end > b.start;
}

/** Background/text colour for one word chunk, in priority order:
 * pending selection > confirmed > candidate > dimmed > plain. */
function chunkStyle(
  isPending: boolean,
  highlightKind: HighlightKind | null,
  isDimmed: boolean
): { bgcolor: string; color: string; opacity?: number } {
  if (isPending) return { bgcolor: "#DBEAFE", color: "#1E3A8A" };
  if (highlightKind) return HIGHLIGHT_COLORS[highlightKind];
  if (isDimmed) return { bgcolor: "transparent", color: "text.secondary", opacity: 0.5 };
  return { bgcolor: "transparent", color: "text.primary" };
}

export default function HighlightableRecommendationText({
  text,
  highlights = [],
  dimmedRanges = [],
  onConfirmSelection,
  onCancelSelection,
}: Props) {
  const {
    wordTokens,
    selectionLoHi,
    handleMouseDown,
    handleMouseEnter,
    handleMouseUp,
    handleFocus,
    handleKeyDown,
    handleConfirm,
    handleCancel,
  } = useWordSelection({ text, onConfirmSelection, onCancelSelection });

  return (
    <Box>
      <Box
        component="span"
        onMouseUp={handleMouseUp}
        sx={{ lineHeight: 2, wordSpacing: 2 }}
      >
        {renderTokens({
          text,
          wordTokens,
          highlights,
          dimmedRanges,
          selectionLoHi,
          handleMouseDown,
          handleMouseEnter,
          handleFocus,
          handleKeyDown,
        })}
      </Box>
      {selectionLoHi && (
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Button
            size="small"
            variant="contained"
            onClick={(e) => handleConfirm(undefined, e.currentTarget)}
          >
            Confirm selection
          </Button>
          <Button size="small" variant="text" onClick={handleCancel}>
            Cancel
          </Button>
        </Stack>
      )}
    </Box>
  );
}

/**
 * Re-walks the ORIGINAL (non-tokenized-word-only) text so inter-word
 * whitespace is preserved verbatim, interleaving plain whitespace spans
 * with the interactive word chunks from useWordSelection's wordTokens.
 */
function renderTokens(params: {
  text: string;
  wordTokens: ReturnType<typeof useWordSelection>["wordTokens"];
  highlights: HighlightSpan[];
  dimmedRanges: Array<{ start: number; end: number }>;
  selectionLoHi: { lo: number; hi: number } | null;
  handleMouseDown: (wordIdx: number) => void;
  handleMouseEnter: (wordIdx: number) => void;
  handleFocus: (wordIdx: number) => void;
  handleKeyDown: (wordIdx: number, e: React.KeyboardEvent) => void;
}) {
  const {
    text,
    wordTokens,
    highlights,
    dimmedRanges,
    selectionLoHi,
    handleMouseDown,
    handleMouseEnter,
    handleFocus,
    handleKeyDown,
  } = params;

  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  wordTokens.forEach((token, wordIdx) => {
    if (token.start > cursor) {
      nodes.push(<span key={`gap-${cursor}`}>{text.slice(cursor, token.start)}</span>);
    }
    const isDimmed = dimmedRanges.some((d) => rangesOverlap(token, d));
    const isPending =
      !isDimmed &&
      !!selectionLoHi &&
      wordIdx >= selectionLoHi.lo &&
      wordIdx <= selectionLoHi.hi;
    const highlightKind = isDimmed
      ? null
      : highlights.find((h) => rangesOverlap(token, h))?.kind ?? null;
    const style = chunkStyle(isPending, highlightKind, isDimmed);
    nodes.push(
      <Box
        key={`word-${wordIdx}`}
        component="span"
        role="button"
        tabIndex={isDimmed ? -1 : 0}
        aria-pressed={isPending}
        data-word-index={wordIdx}
        data-highlight-kind={highlightKind ?? undefined}
        data-dimmed={isDimmed || undefined}
        onMouseDown={() => !isDimmed && handleMouseDown(wordIdx)}
        onMouseEnter={() => !isDimmed && handleMouseEnter(wordIdx)}
        onFocus={() => !isDimmed && handleFocus(wordIdx)}
        onKeyDown={(e) => !isDimmed && handleKeyDown(wordIdx, e)}
        sx={{
          bgcolor: style.bgcolor,
          color: style.color,
          opacity: style.opacity ?? 1,
          borderRadius: 0.5,
          cursor: isDimmed ? "default" : "pointer",
          outlineOffset: 1,
          "&:focus-visible": { outline: "2px solid #2563EB" },
        }}
      >
        {token.text}
      </Box>,
    );
    cursor = token.end;
  });
  if (cursor < text.length) {
    nodes.push(<span key={`gap-${cursor}`}>{text.slice(cursor)}</span>);
  }
  return nodes;
}
