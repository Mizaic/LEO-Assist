/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

import { useMemo } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import {
  useWordSelection,
  type TextSelectionResult,
  type WordSelectionMode,
  tokenizeWords,
} from "./useWordSelection";

/**
 * Renders a span of guideline text as individually focusable word chunks so
 * a reviewer can select contiguous or disconnected words with either the
 * mouse (click words to toggle on/off, Shift+click or drag for a continuous
 * span) or the keyboard (Tab to a chunk, Space to toggle, Shift+Arrow to
 * extend, Enter to confirm).
 */

export type HighlightKind = "confirmed" | "candidate";

export interface HighlightSpan {
  start: number;
  end: number;
  kind: HighlightKind;
  label?: string;
  /**
   * Which situation (0-based pathway index) this span belongs to, when
   * known. `null` / omitted means a prerequisite that applies to every
   * situation, or a leaf matched before any pathway split exists.
   */
  pathwayIndex?: number | null;
}

export const HIGHLIGHT_COLORS: Record<HighlightKind, { bgcolor: string; color: string }> = {
  confirmed: { bgcolor: "#DCFCE7", color: "#14532D" },
  candidate: { bgcolor: "#FEF9C3", color: "#713F12" },
};

export type { TextSelectionResult, WordSelectionMode };

interface Props {
  text: string;
  /** `"multi"` (default) toggles disconnected words; `"contiguous"` picks one span. */
  mode?: WordSelectionMode;
  /** Already-resolved (confirmed) or AI-suggested (candidate) spans. */
  highlights?: HighlightSpan[];
  /** Text outside the current pathway/scope -- greyed out and not selectable. */
  dimmedRanges?: Array<{ start: number; end: number }>;
  onConfirmSelection: (selection: TextSelectionResult, anchor?: HTMLElement) => void;
  onCancelSelection?: () => void;
}

function rangesOverlap(
  a: { start: number; end: number },
  b: { start: number; end: number },
): boolean {
  return a.start < b.end && a.end > b.start;
}

function chunkStyle(
  isPending: boolean,
  highlightKind: HighlightKind | null,
  isDimmed: boolean,
): { bgcolor: string; color: string; opacity?: number } {
  if (isPending) return { bgcolor: "#DBEAFE", color: "#1E3A8A" };
  if (highlightKind) return HIGHLIGHT_COLORS[highlightKind];
  if (isDimmed) return { bgcolor: "transparent", color: "text.secondary", opacity: 0.5 };
  return { bgcolor: "transparent", color: "text.primary" };
}

export default function HighlightableRecommendationText({
  text,
  mode = "multi",
  highlights = [],
  dimmedRanges = [],
  onConfirmSelection,
  onCancelSelection,
}: Props) {
  const disabledIndices = useMemo(() => {
    if (dimmedRanges.length === 0) return undefined;
    const tokens = tokenizeWords(text);
    const set = new Set<number>();
    tokens.forEach((token, idx) => {
      if (dimmedRanges.some((d) => rangesOverlap(token, d))) set.add(idx);
    });
    return set;
  }, [text, dimmedRanges]);

  const {
    wordTokens,
    selectedIndices,
    previewText,
    handleMouseDown,
    handleMouseEnter,
    handleMouseUp,
    handleFocus,
    handleKeyDown,
    handleConfirm,
    handleCancel,
  } = useWordSelection({
    text,
    mode,
    disabledIndices,
    onConfirmSelection,
    onCancelSelection,
  });

  const hasPending = selectedIndices.size > 0;

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
          selectedIndices,
          handleMouseDown,
          handleMouseEnter,
          handleFocus,
          handleKeyDown,
        })}
      </Box>
      {hasPending && (
        <Stack spacing={0.75} sx={{ mt: 1 }}>
          {mode === "multi" && previewText && (
            <Typography
              variant="caption"
              sx={{ color: "text.primary", fontWeight: 500 }}
              data-testid="selected-words-preview"
            >
              Selected words: &ldquo;{previewText}&rdquo;
            </Typography>
          )}
          <Stack direction="row" spacing={1}>
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
        </Stack>
      )}
    </Box>
  );
}

function renderTokens(params: {
  text: string;
  wordTokens: ReturnType<typeof useWordSelection>["wordTokens"];
  highlights: HighlightSpan[];
  dimmedRanges: Array<{ start: number; end: number }>;
  selectedIndices: ReadonlySet<number>;
  handleMouseDown: (wordIdx: number, extend?: boolean) => void;
  handleMouseEnter: (wordIdx: number) => void;
  handleFocus: (wordIdx: number) => void;
  handleKeyDown: (wordIdx: number, e: React.KeyboardEvent) => void;
}) {
  const {
    text,
    wordTokens,
    highlights,
    dimmedRanges,
    selectedIndices,
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
    const isPending = !isDimmed && selectedIndices.has(wordIdx);
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
        onMouseDown={(e) => !isDimmed && handleMouseDown(wordIdx, e.shiftKey)}
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
          userSelect: "none",
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
