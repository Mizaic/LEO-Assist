/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Word-chunk text selection, extracted out of
 * HighlightableRecommendationText.tsx so the same mouse-drag /
 * Tab-and-extend keyboard model can be reused wherever a reviewer needs to
 * highlight a sub-phrase of some text -- originally the whole flattened
 * recommendation, now also a single Step 3 pathway row (see
 * HighlightableRowText.tsx).
 *
 * Free-form mouse drag-selection has no accessible default, so the
 * chunk-and-extend keyboard model here is load-bearing for WCAG 2.1 AA,
 * not a nice-to-have layered on top of a mouse-first design.
 */
import { useCallback, useMemo, useRef, useState } from "react";

export interface WordToken {
  start: number;
  end: number;
  text: string;
}

export interface TextSelectionResult {
  start: number;
  end: number;
  text: string;
}

const TOKEN_RE = /\S+|\s+/g;

/** Split `text` into word tokens (whitespace runs are dropped). */
export function tokenizeWords(text: string): WordToken[] {
  const tokens: WordToken[] = [];
  const re = new RegExp(TOKEN_RE);
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    const value = match[0];
    if (/^\s+$/.test(value)) continue;
    tokens.push({ start: match.index, end: match.index + value.length, text: value });
  }
  return tokens;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

interface Params {
  text: string;
  /**
   * `anchor` is the DOM element the reviewer actually confirmed the
   * selection from (the "Confirm selection" button, or the focused
   * word chunk when confirmed via Enter) -- always forward it so a
   * search popover opened from this selection appears next to that
   * element instead of a default position.
   */
  onConfirmSelection: (selection: TextSelectionResult, anchor?: HTMLElement) => void;
  onCancelSelection?: () => void;
}

export function useWordSelection({ text, onConfirmSelection, onCancelSelection }: Params) {
  const wordTokens = useMemo(() => tokenizeWords(text), [text]);

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
    [wordTokens, text],
  );

  const handleConfirm = useCallback(
    (fallbackWordIdx?: number, anchor?: HTMLElement) => {
      const range =
        selectionLoHi ??
        (fallbackWordIdx !== undefined
          ? { lo: fallbackWordIdx, hi: fallbackWordIdx }
          : null);
      if (!range) return;
      onConfirmSelection(buildSelectionResult(range.lo, range.hi), anchor);
      clearSelection();
    },
    [selectionLoHi, buildSelectionResult, onConfirmSelection, clearSelection],
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
    (
      wordIdx: number,
      e: {
        key: string;
        shiftKey: boolean;
        preventDefault: () => void;
        // Typed as the generic DOM event contract (not React's own
        // KeyboardEvent<T>) so this hook stays independent of which
        // element type the caller renders its word chunks as.
        currentTarget: EventTarget & Element;
      },
    ) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleConfirm(wordIdx, e.currentTarget as HTMLElement);
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
    [handleConfirm, handleCancel, wordTokens.length],
  );

  return {
    wordTokens,
    selectionLoHi,
    handleMouseDown,
    handleMouseEnter,
    handleMouseUp,
    handleFocus,
    handleKeyDown,
    handleConfirm,
    handleCancel,
  };
}
