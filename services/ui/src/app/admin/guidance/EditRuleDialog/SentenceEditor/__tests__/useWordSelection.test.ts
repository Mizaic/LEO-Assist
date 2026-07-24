/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Unit tests for useWordSelection -- the pure word-chunk selection state
 * machine extracted out of HighlightableRecommendationText.tsx so it can be
 * reused for a single Step 3 row's text (HighlightableRowText.tsx),
 * without dragging the whole rendering component along with it.
 */
import { act, renderHook } from "@testing-library/react";
import { tokenizeWords, useWordSelection } from "../useWordSelection";

const TEXT = "upper abdominal pain and a low haemoglobin level";

function keyEvent(key: string, shiftKey = false, currentTarget?: HTMLElement) {
  return {
    key,
    shiftKey,
    preventDefault: jest.fn(),
    currentTarget,
  } as unknown as React.KeyboardEvent;
}

describe("tokenizeWords", () => {
  it("splits text into word tokens with correct character offsets, skipping whitespace", () => {
    const tokens = tokenizeWords(TEXT);
    expect(tokens.map((t) => t.text)).toEqual([
      "upper",
      "abdominal",
      "pain",
      "and",
      "a",
      "low",
      "haemoglobin",
      "level",
    ]);
    expect(tokens[0]).toEqual({ start: 0, end: 5, text: "upper" });
    expect(tokens[2]).toEqual({ start: 16, end: 20, text: "pain" });
  });
});

describe("useWordSelection", () => {
  it("has no pending selection initially", () => {
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection: jest.fn() }),
    );
    expect(result.current.selectionLoHi).toBeNull();
  });

  it("mouse drag from word 0 to word 2 selects that range", () => {
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection: jest.fn() }),
    );
    act(() => result.current.handleMouseDown(0));
    act(() => result.current.handleMouseEnter(2));
    act(() => result.current.handleMouseUp());
    expect(result.current.selectionLoHi).toEqual({ lo: 0, hi: 2 });
  });

  it("ignores mouse-enter when no drag was started (mouse not down)", () => {
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection: jest.fn() }),
    );
    act(() => result.current.handleMouseEnter(2));
    expect(result.current.selectionLoHi).toBeNull();
  });

  it("confirming a drag-selected range emits the exact substring and clears selection", () => {
    const onConfirmSelection = jest.fn();
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection }),
    );
    act(() => result.current.handleMouseDown(0));
    act(() => result.current.handleMouseEnter(2));
    act(() => result.current.handleMouseUp());
    act(() => result.current.handleConfirm());

    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 0, end: 20, text: "upper abdominal pain" },
      undefined,
    );
    expect(result.current.selectionLoHi).toBeNull();
  });

  it("forwards the caller-supplied anchor element through to onConfirmSelection", () => {
    const onConfirmSelection = jest.fn();
    const anchor = document.createElement("button");
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection }),
    );
    act(() => result.current.handleMouseDown(0));
    act(() => result.current.handleMouseEnter(2));
    act(() => result.current.handleMouseUp());
    act(() => result.current.handleConfirm(undefined, anchor));

    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 0, end: 20, text: "upper abdominal pain" },
      anchor,
    );
  });

  it("Enter with no prior focus/drag falls back to confirming the single word passed in", () => {
    const onConfirmSelection = jest.fn();
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection }),
    );
    act(() => result.current.handleKeyDown(2, keyEvent("Enter")));
    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 16, end: 20, text: "pain" },
      undefined,
    );
  });

  it("Enter forwards the focused word chunk's own element as the anchor", () => {
    const onConfirmSelection = jest.fn();
    const wordChunk = document.createElement("span");
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection }),
    );
    act(() => result.current.handleKeyDown(2, keyEvent("Enter", false, wordChunk)));
    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 16, end: 20, text: "pain" },
      wordChunk,
    );
  });

  it("Tab-focus then Shift+ArrowRight extends the selection", () => {
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection: jest.fn() }),
    );
    act(() => result.current.handleFocus(0));
    act(() => result.current.handleKeyDown(0, keyEvent("ArrowRight", true)));
    act(() => result.current.handleKeyDown(0, keyEvent("ArrowRight", true)));
    expect(result.current.selectionLoHi).toEqual({ lo: 0, hi: 2 });
  });

  it("clamps Shift+ArrowRight at the last word", () => {
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection: jest.fn() }),
    );
    const lastIdx = tokenizeWords(TEXT).length - 1;
    act(() => result.current.handleFocus(lastIdx));
    act(() => result.current.handleKeyDown(lastIdx, keyEvent("ArrowRight", true)));
    expect(result.current.selectionLoHi).toEqual({ lo: lastIdx, hi: lastIdx });
  });

  it("Escape cancels the pending selection and calls onCancelSelection", () => {
    const onCancelSelection = jest.fn();
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection: jest.fn(), onCancelSelection }),
    );
    act(() => result.current.handleFocus(0));
    act(() => result.current.handleKeyDown(0, keyEvent("Escape")));
    expect(onCancelSelection).toHaveBeenCalledTimes(1);
    expect(result.current.selectionLoHi).toBeNull();
  });
});
