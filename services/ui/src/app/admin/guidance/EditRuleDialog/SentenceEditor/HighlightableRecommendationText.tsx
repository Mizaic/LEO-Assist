/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";

/**
 * Renders a span of guideline text as individually focusable word/phrase
 * chunks so a reviewer can select a range of text with either the mouse
 * (click-drag) or the keyboard (Tab to a chunk, Shift+Arrow to extend,
 * Enter to confirm) -- the fallback path used when no
 * `recommendation_structure` exists at all, or for a single compound
 * list-item's text that still bundles more than one criterion. See the
 * "Fallback" sections of the wizard wireframes for the exact interaction.
 *
 * Free-form mouse drag-selection has no accessible default, so the
 * chunk-and-extend keyboard model here is load-bearing for WCAG 2.1 AA,
 * not a nice-to-have layered on top of a mouse-first design.
 */

export type HighlightKind = "confirmed" | "candidate";

export interface HighlightSpan {
  start: number;
  end: number;
  kind: HighlightKind;
  label?: string;
}

export interface TextSelectionResult {
  start: number;
  end: number;
  text: string;
}

interface Props {
  text: string;
  /** Already-resolved (confirmed) or AI-suggested (candidate) spans,
   * rendered distinctly from plain and pending-selection text. */
  highlights?: HighlightSpan[];
  /** Text outside the current pathway/scope -- rendered greyed out and
   * not selectable (see the wireframes' "dimmed" notation). */
  dimmedRanges?: Array<{ start: number; end: number }>;
  onConfirmSelection: (selection: TextSelectionResult) => void;
  onCancelSelection?: () => void;
}

interface Token {
  isWord: boolean;
  start: number;
  end: number;
  text: string;
}

const TOKEN_RE = /\S+|\s+/g;

function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  const re = new RegExp(TOKEN_RE);
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    const value = match[0];
    tokens.push({
      isWord: !/^\s+$/.test(value),
      start: match.index,
      end: match.index + value.length,
      text: value,
    });
  }
  return tokens;
}

function rangesOverlap(
  a: { start: number; end: number },
  b: { start: number; end: number }
): boolean {
  return a.start < b.end && a.end > b.start;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/** Background/text colour for one word chunk, in priority order:
 * pending selection > confirmed > candidate > dimmed > plain. */
function chunkStyle(
  isPending: boolean,
  highlightKind: HighlightKind | null,
  isDimmed: boolean
): { bgcolor: string; color: string; opacity?: number } {
  if (isPending) return { bgcolor: "#DBEAFE", color: "#1E3A8A" };
  if (highlightKind === "confirmed") return { bgcolor: "#DCFCE7", color: "#14532D" };
  if (highlightKind === "candidate") return { bgcolor: "#FEF9C3", color: "#713F12" };
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
  const tokens = useMemo(() => tokenize(text), [text]);
  const wordTokens = useMemo(() => tokens.filter((t) => t.isWord), [tokens]);

  const [anchorIdx, setAnchorIdx] = useState<number | null>(null);
  const [focusIdx, setFocusIdx] = useState<number | null>(null);
  const draggingRef = useRef(false);

  const selectionLoHi = useMemo(() => {
    if (anchorIdx === null || focusIdx === null) return null;
    return { lo: Math.min(anchorIdx, focusIdx), hi: Math.max(anchorIdx, focusIdx) };
  }, [anchorIdx, focusIdx]);

  const clearSelection = useCallback(() => {
    setAnchorIdx(null);
    setFocusIdx(null);
  }, []);

  const buildSelectionResult = useCallback(
    (lo: number, hi: number): TextSelectionResult => {
      const start = wordTokens[lo].start;
      const end = wordTokens[hi].end;
      return { start, end, text: text.slice(start, end) };
    },
    [wordTokens, text]
  );

  const handleConfirm = useCallback(
    (fallbackWordIdx?: number) => {
      const range = selectionLoHi ?? (
        fallbackWordIdx !== undefined
          ? { lo: fallbackWordIdx, hi: fallbackWordIdx }
          : null
      );
      if (!range) return;
      onConfirmSelection(buildSelectionResult(range.lo, range.hi));
      clearSelection();
    },
    [selectionLoHi, buildSelectionResult, onConfirmSelection, clearSelection]
  );

  const handleCancel = useCallback(() => {
    clearSelection();
    onCancelSelection?.();
  }, [clearSelection, onCancelSelection]);

  const handleMouseDown = useCallback((wordIdx: number) => {
    draggingRef.current = true;
    setAnchorIdx(wordIdx);
    setFocusIdx(wordIdx);
  }, []);

  const handleMouseEnter = useCallback((wordIdx: number) => {
    if (draggingRef.current) setFocusIdx(wordIdx);
  }, []);

  const handleMouseUp = useCallback(() => {
    draggingRef.current = false;
  }, []);

  const handleFocus = useCallback((wordIdx: number) => {
    if (draggingRef.current) return;
    setAnchorIdx(wordIdx);
    setFocusIdx(wordIdx);
  }, []);

  const handleKeyDown = useCallback(
    (wordIdx: number, e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleConfirm(wordIdx);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        handleCancel();
        return;
      }
      if (e.shiftKey && e.key === "ArrowRight") {
        e.preventDefault();
        setFocusIdx((f) => clamp((f ?? wordIdx) + 1, 0, wordTokens.length - 1));
        return;
      }
      if (e.shiftKey && e.key === "ArrowLeft") {
        e.preventDefault();
        setFocusIdx((f) => clamp((f ?? wordIdx) - 1, 0, wordTokens.length - 1));
      }
    },
    [handleConfirm, handleCancel, wordTokens.length]
  );

  let wordCounter = -1;

  return (
    <Box>
      <Box
        component="span"
        onMouseUp={handleMouseUp}
        sx={{ lineHeight: 2, wordSpacing: 2 }}
      >
        {tokens.map((token, tokenIdx) => {
          if (!token.isWord) {
            return <span key={tokenIdx}>{token.text}</span>;
          }
          wordCounter += 1;
          const wordIdx = wordCounter;
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
          return (
            <Box
              key={tokenIdx}
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
            </Box>
          );
        })}
      </Box>
      {selectionLoHi && (
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Button size="small" variant="contained" onClick={() => handleConfirm()}>
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
