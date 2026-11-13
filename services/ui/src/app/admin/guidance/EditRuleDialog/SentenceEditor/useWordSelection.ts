/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Word-chunk text selection, shared across Step 1's full guideline quote,
 * Step 2's row-split picker (`mode="contiguous"`), Step 3's highlight-for-
 * more-codes tool, and ConceptSynonymDialog's Guideline Wording editor.
 *
 * Default `"multi"` mode lets a reviewer click individual disconnected words
 * on/off (or press Space on focused words) while still supporting drag and
 * Shift+click / Shift+Arrow for continuous spans. `"contiguous"` mode keeps
 * single-span reset behaviour for Step 2's situation split point.
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

export type WordSelectionMode = "multi" | "contiguous";

const TOKEN_RE = /\S+|\s+/g;
const MAX_SOURCE_ROW_TEXT_LENGTH = 500;

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

function addRangeToSet(
  target: Set<number>,
  a: number,
  b: number,
  disabled?: ReadonlySet<number>,
): void {
  const lo = Math.min(a, b);
  const hi = Math.max(a, b);
  for (let i = lo; i <= hi; i++) {
    if (!disabled?.has(i)) target.add(i);
  }
}

function groupContiguousRuns(sortedIndices: number[]): Array<[number, number]> {
  const runs: Array<[number, number]> = [];
  for (const idx of sortedIndices) {
    const last = runs[runs.length - 1];
    if (last && idx === last[1] + 1) {
      last[1] = idx;
    } else {
      runs.push([idx, idx]);
    }
  }
  return runs;
}

function composeSelectionResult(
  text: string,
  wordTokens: WordToken[],
  sortedIndices: number[],
): TextSelectionResult {
  const runs = groupContiguousRuns(sortedIndices);
  const joined = runs
    .map(([lo, hi]) => text.slice(wordTokens[lo].start, wordTokens[hi].end))
    .join(" ");
  const capped =
    joined.length > MAX_SOURCE_ROW_TEXT_LENGTH
      ? joined.slice(0, MAX_SOURCE_ROW_TEXT_LENGTH).trim()
      : joined;
  return {
    start: wordTokens[sortedIndices[0]].start,
    end: wordTokens[sortedIndices[sortedIndices.length - 1]].end,
    text: capped,
  };
}

interface Params {
  text: string;
  mode?: WordSelectionMode;
  disabledIndices?: ReadonlySet<number>;
  onConfirmSelection: (selection: TextSelectionResult, anchor?: HTMLElement) => void;
  onCancelSelection?: () => void;
}

interface ActiveRange {
  anchor: number;
  focus: number;
}

function deriveSelectedIndices(
  mode: WordSelectionMode,
  committed: ReadonlySet<number>,
  activeRange: ActiveRange | null,
  disabledIndices?: ReadonlySet<number>,
): Set<number> {
  const out = new Set<number>();
  if (mode === "multi") {
    for (const idx of committed) {
      if (!disabledIndices?.has(idx)) out.add(idx);
    }
  }
  if (activeRange) {
    addRangeToSet(out, activeRange.anchor, activeRange.focus, disabledIndices);
  }
  return out;
}

export function useWordSelection({
  text,
  mode = "multi",
  disabledIndices,
  onConfirmSelection,
  onCancelSelection,
}: Params) {
  const wordTokens = useMemo(() => tokenizeWords(text), [text]);
  const [committed, setCommitted] = useState<Set<number>>(() => new Set());
  const [lastAnchorIdx, setLastAnchorIdx] = useState<number | null>(null);
  const [activeRange, setActiveRange] = useState<ActiveRange | null>(null);

  const draggingRef = useRef(false);
  const dragOriginRef = useRef<number | null>(null);
  const dragMovedRef = useRef(false);
  const suppressNextFocusRef = useRef(false);
  const committedRef = useRef<Set<number>>(committed);
  committedRef.current = committed;
  const activeRangeRef = useRef<ActiveRange | null>(activeRange);
  activeRangeRef.current = activeRange;
  const lastAnchorRef = useRef<number | null>(lastAnchorIdx);
  lastAnchorRef.current = lastAnchorIdx;

  const updateCommitted = useCallback((next: Set<number>) => {
    committedRef.current = next;
    setCommitted(next);
  }, []);

  const updateActiveRange = useCallback((next: ActiveRange | null) => {
    activeRangeRef.current = next;
    setActiveRange(next);
  }, []);

  const updateLastAnchor = useCallback((next: number | null) => {
    lastAnchorRef.current = next;
    setLastAnchorIdx(next);
  }, []);

  const selectedIndices = useMemo(
    () => deriveSelectedIndices(mode, committed, activeRange, disabledIndices),
    [mode, committed, activeRange, disabledIndices],
  );

  const sortedSelected = useMemo(
    () => Array.from(selectedIndices).sort((a, b) => a - b),
    [selectedIndices],
  );

  const selectionLoHi = useMemo(() => {
    if (sortedSelected.length === 0) return null;
    return {
      lo: sortedSelected[0],
      hi: sortedSelected[sortedSelected.length - 1],
    };
  }, [sortedSelected]);

  const previewText = useMemo(() => {
    if (sortedSelected.length === 0 || wordTokens.length === 0) return "";
    return composeSelectionResult(text, wordTokens, sortedSelected).text;
  }, [sortedSelected, text, wordTokens]);

  const clearSelection = useCallback(() => {
    updateCommitted(new Set());
    updateLastAnchor(null);
    updateActiveRange(null);
    draggingRef.current = false;
    dragOriginRef.current = null;
    dragMovedRef.current = false;
  }, [updateCommitted, updateLastAnchor, updateActiveRange]);

  const handleConfirm = useCallback(
    (fallbackWordIdx?: number, anchor?: HTMLElement) => {
      const indices =
        sortedSelected.length > 0
          ? sortedSelected
          : fallbackWordIdx !== undefined && !disabledIndices?.has(fallbackWordIdx)
            ? [fallbackWordIdx]
            : [];
      if (indices.length === 0 || wordTokens.length === 0) return;
      onConfirmSelection(composeSelectionResult(text, wordTokens, indices), anchor);
      clearSelection();
    },
    [sortedSelected, disabledIndices, wordTokens, text, onConfirmSelection, clearSelection],
  );

  const handleCancel = useCallback(() => {
    clearSelection();
    onCancelSelection?.();
  }, [clearSelection, onCancelSelection]);

  const handleMouseDown = useCallback(
    (wordIdx: number, extend = false) => {
      suppressNextFocusRef.current = true;
      const curAnchor = lastAnchorRef.current;
      const curRange = activeRangeRef.current;
      const curCommitted = committedRef.current;

      if (mode === "contiguous") {
        if (extend && curAnchor !== null) {
          draggingRef.current = false;
          updateActiveRange({ anchor: curAnchor, focus: wordIdx });
          return;
        }
        draggingRef.current = true;
        updateLastAnchor(wordIdx);
        updateActiveRange({ anchor: wordIdx, focus: wordIdx });
        return;
      }

      if (extend) {
        draggingRef.current = false;
        const start = curAnchor ?? wordIdx;
        const next = new Set(curCommitted);
        if (curRange) addRangeToSet(next, curRange.anchor, curRange.focus, disabledIndices);
        addRangeToSet(next, start, wordIdx, disabledIndices);
        updateCommitted(next);
        updateActiveRange(null);
        updateLastAnchor(start);
        return;
      }

      draggingRef.current = true;
      dragOriginRef.current = wordIdx;
      dragMovedRef.current = false;
      updateLastAnchor(wordIdx);
      if (curCommitted.has(wordIdx)) {
        const next = new Set(curCommitted);
        next.delete(wordIdx);
        updateCommitted(next);
        updateActiveRange(null);
      } else {
        updateActiveRange({ anchor: wordIdx, focus: wordIdx });
      }
    },
    [mode, disabledIndices, updateCommitted, updateActiveRange, updateLastAnchor],
  );

  const handleMouseEnter = useCallback(
    (wordIdx: number) => {
      if (!draggingRef.current) return;
      const origin = dragOriginRef.current ?? wordIdx;
      if (wordIdx !== origin) dragMovedRef.current = true;
      updateActiveRange({ anchor: origin, focus: wordIdx });
    },
    [updateActiveRange],
  );

  const handleMouseUp = useCallback(() => {
    const wasDragging = draggingRef.current;
    const curRange = activeRangeRef.current;
    draggingRef.current = false;
    suppressNextFocusRef.current = false;
    if (mode === "multi" && wasDragging && curRange) {
      const next = new Set(committedRef.current);
      addRangeToSet(next, curRange.anchor, curRange.focus, disabledIndices);
      updateCommitted(next);
      updateActiveRange(null);
    }
    dragOriginRef.current = null;
    dragMovedRef.current = false;
  }, [mode, disabledIndices, updateCommitted, updateActiveRange]);

  const handleFocus = useCallback(
    (wordIdx: number) => {
      if (suppressNextFocusRef.current) {
        suppressNextFocusRef.current = false;
        return;
      }
      updateLastAnchor(wordIdx);
      if (mode === "contiguous") {
        updateActiveRange({ anchor: wordIdx, focus: wordIdx });
      } else {
        updateActiveRange(null);
      }
    },
    [mode, updateLastAnchor, updateActiveRange],
  );

  const handleKeyDown = useCallback(
    (
      wordIdx: number,
      e: {
        key: string;
        shiftKey: boolean;
        preventDefault: () => void;
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
      if (e.key === " " && mode === "multi") {
        e.preventDefault();
        const curRange = activeRangeRef.current;
        const next = new Set(committedRef.current);
        if (curRange) addRangeToSet(next, curRange.anchor, curRange.focus, disabledIndices);
        if (next.has(wordIdx)) {
          next.delete(wordIdx);
        } else if (!disabledIndices?.has(wordIdx)) {
          next.add(wordIdx);
        }
        updateCommitted(next);
        updateActiveRange(null);
        updateLastAnchor(wordIdx);
        return;
      }
      if (e.shiftKey && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        e.preventDefault();
        const delta = e.key === "ArrowRight" ? 1 : -1;
        const prev = activeRangeRef.current;
        const anchor = prev?.anchor ?? lastAnchorRef.current ?? wordIdx;
        const focus = clamp((prev?.focus ?? anchor) + delta, 0, wordTokens.length - 1);
        updateActiveRange({ anchor, focus });
      }
    },
    [
      mode,
      disabledIndices,
      handleConfirm,
      handleCancel,
      wordTokens.length,
      updateCommitted,
      updateActiveRange,
      updateLastAnchor,
    ],
  );

  return {
    wordTokens,
    selectedIndices,
    selectionLoHi,
    previewText,
    handleMouseDown,
    handleMouseEnter,
    handleMouseUp,
    handleFocus,
    handleKeyDown,
    handleConfirm,
    handleCancel,
  };
}
