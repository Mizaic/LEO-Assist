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

  it("in contiguous mode, a second plain mousedown (no Shift) resets to a fresh one-word selection", () => {
    const { result } = renderHook(() =>
      useWordSelection({
        text: TEXT,
        mode: "contiguous",
        onConfirmSelection: jest.fn(),
      }),
    );
    act(() => result.current.handleMouseDown(0));
    act(() => result.current.handleMouseUp());
    act(() => result.current.handleMouseDown(2));
    act(() => result.current.handleMouseUp());
    expect(result.current.selectionLoHi).toEqual({ lo: 2, hi: 2 });
  });

  it("in default multi mode, plain clicks toggle disconnected words and confirm joins them in sentence order", () => {
    const onConfirmSelection = jest.fn();
    const ng12 = "unexplained vulval lump, ulceration or bleeding.";
    const { result } = renderHook(() =>
      useWordSelection({ text: ng12, onConfirmSelection }),
    );
    act(() => {
      result.current.handleMouseDown(0);
      result.current.handleMouseUp();
    });
    act(() => {
      result.current.handleMouseDown(1);
      result.current.handleMouseUp();
    });
    act(() => {
      result.current.handleMouseDown(5);
      result.current.handleMouseUp();
    });
    expect(Array.from(result.current.selectedIndices)).toEqual([0, 1, 5]);
    expect(result.current.previewText).toBe("unexplained vulval bleeding.");

    act(() => result.current.handleConfirm());
    expect(onConfirmSelection).toHaveBeenCalledWith(
      {
        start: 0,
        end: ng12.length,
        text: "unexplained vulval bleeding.",
      },
      undefined,
    );
  });

  it("clicking an already-selected word toggles it off", () => {
    const ng12 = "unexplained vulval lump, ulceration or bleeding.";
    const { result } = renderHook(() =>
      useWordSelection({ text: ng12, onConfirmSelection: jest.fn() }),
    );
    act(() => {
      result.current.handleMouseDown(0);
      result.current.handleMouseUp();
    });
    act(() => {
      result.current.handleMouseDown(2);
      result.current.handleMouseUp();
    });
    act(() => {
      result.current.handleMouseDown(2);
      result.current.handleMouseUp();
    });
    expect(Array.from(result.current.selectedIndices)).toEqual([0]);
  });

  it("combines a Shift+click range with a later disconnected plain click", () => {
    const onConfirmSelection = jest.fn();
    const ng12 = "unexplained vulval lump, ulceration or bleeding.";
    const { result } = renderHook(() =>
      useWordSelection({ text: ng12, onConfirmSelection }),
    );
    act(() => {
      result.current.handleMouseDown(0);
      result.current.handleMouseUp();
    });
    act(() => {
      result.current.handleMouseDown(1, true);
      result.current.handleMouseUp();
    });
    act(() => {
      result.current.handleMouseDown(5);
      result.current.handleMouseUp();
    });
    act(() => result.current.handleConfirm());
    expect(onConfirmSelection).toHaveBeenCalledWith(
      {
        start: 0,
        end: ng12.length,
        text: "unexplained vulval bleeding.",
      },
      undefined,
    );
  });

  it("Space toggles focused words across Tab focus changes and Enter confirms them", () => {
    const onConfirmSelection = jest.fn();
    const ng12 = "unexplained vulval lump, ulceration or bleeding.";
    const { result } = renderHook(() =>
      useWordSelection({ text: ng12, onConfirmSelection }),
    );
    act(() => result.current.handleFocus(0));
    act(() => result.current.handleKeyDown(0, keyEvent(" ")));
    act(() => result.current.handleFocus(1));
    act(() => result.current.handleKeyDown(1, keyEvent(" ")));
    act(() => result.current.handleFocus(3)); // focus "ulceration" without pressing Space
    act(() => result.current.handleFocus(5));
    act(() => result.current.handleKeyDown(5, keyEvent(" ")));
    act(() => result.current.handleKeyDown(5, keyEvent("Enter")));

    expect(onConfirmSelection).toHaveBeenCalledWith(
      {
        start: 0,
        end: ng12.length,
        text: "unexplained vulval bleeding.",
      },
      undefined,
    );
  });

  // Click-drag across small inline word chunks is fragile in a real
  // browser -- Shift+click extending the current selection to a new
  // word (without requiring the mouse to stay held down the whole
  // time) is the same forgiving gesture already supported via the
  // keyboard's Shift+Arrow, and is the fix for "can't select more
  // than one word" when a continuous drag doesn't land cleanly.
  it("Shift+click extends the existing selection to the newly clicked word", () => {
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection: jest.fn() }),
    );
    act(() => result.current.handleMouseDown(0));
    act(() => result.current.handleMouseUp());
    act(() => result.current.handleMouseDown(2, true));
    expect(result.current.selectionLoHi).toEqual({ lo: 0, hi: 2 });
  });

  it("Shift+click with no prior anchor starts a fresh one-word selection instead of throwing", () => {
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection: jest.fn() }),
    );
    act(() => result.current.handleMouseDown(1, true));
    expect(result.current.selectionLoHi).toEqual({ lo: 1, hi: 1 });
  });

  it("confirming a Shift+click-extended selection emits the exact multi-word substring", () => {
    const onConfirmSelection = jest.fn();
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection }),
    );
    act(() => result.current.handleMouseDown(0));
    act(() => result.current.handleMouseUp());
    act(() => result.current.handleMouseDown(2, true));
    act(() => result.current.handleConfirm());

    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 0, end: 20, text: "upper abdominal pain" },
      undefined,
    );
  });

  it("Shift+click does not re-arm dragging -- a later mouse-enter without a fresh mousedown does not extend further", () => {
    const { result } = renderHook(() =>
      useWordSelection({ text: TEXT, onConfirmSelection: jest.fn() }),
    );
    act(() => result.current.handleMouseDown(0));
    act(() => result.current.handleMouseUp());
    act(() => result.current.handleMouseDown(2, true));
    act(() => result.current.handleMouseEnter(5));
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
