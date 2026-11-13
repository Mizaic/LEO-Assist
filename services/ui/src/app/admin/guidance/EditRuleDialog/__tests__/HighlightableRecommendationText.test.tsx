/**
 * Live-render tests for HighlightableRecommendationText -- both the
 * mouse drag-select path and the keyboard chunk-and-extend path, per
 * the highlight-to-build wizard plan's `highlightable-text` todo.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HighlightableRecommendationText from "../SentenceEditor/HighlightableRecommendationText";

const TEXT = "upper abdominal pain and a low haemoglobin level";

function getWordChunk(word: string) {
  return screen.getByText(word, { selector: "[data-word-index]" });
}

describe("HighlightableRecommendationText: mouse drag-select", () => {
  it("selects a range by mousedown on the start word, dragging over more words, then confirming", async () => {
    const user = userEvent.setup();
    const onConfirmSelection = jest.fn();
    render(
      <HighlightableRecommendationText
        text={TEXT}
        onConfirmSelection={onConfirmSelection}
      />
    );

    const start = getWordChunk("upper");
    const middle = getWordChunk("abdominal");
    const end = getWordChunk("pain");

    await user.pointer([
      { keys: "[MouseLeft>]", target: start },
      { target: middle },
      { target: end },
      { keys: "[/MouseLeft]", target: end },
    ]);

    const confirmButton = await screen.findByRole("button", {
      name: /confirm selection/i,
    });
    await user.click(confirmButton);

    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 0, end: 20, text: "upper abdominal pain" },
      confirmButton,
    );
  });

  it("marks dragged-over chunks as pending (aria-pressed) before confirming", async () => {
    const user = userEvent.setup();
    render(
      <HighlightableRecommendationText
        text={TEXT}
        onConfirmSelection={jest.fn()}
      />
    );

    const start = getWordChunk("upper");
    const end = getWordChunk("abdominal");
    await user.pointer([
      { keys: "[MouseLeft>]", target: start },
      { target: end },
      { keys: "[/MouseLeft]", target: end },
    ]);

    expect(start).toHaveAttribute("aria-pressed", "true");
    expect(end).toHaveAttribute("aria-pressed", "true");
    expect(getWordChunk("pain")).toHaveAttribute("aria-pressed", "false");
  });

  // Regression: a continuous mouse-held drag across small inline word
  // chunks is easy to break in a real browser (the button can be
  // released mid-gesture without the user noticing). Click-then-
  // Shift-click is the forgiving alternative -- two separate clicks,
  // no held-down drag required -- and must extend the same way a
  // drag does.
  it("selects a range via click on the first word, then Shift+click on the last word", async () => {
    const user = userEvent.setup();
    const onConfirmSelection = jest.fn();
    render(
      <HighlightableRecommendationText
        text={TEXT}
        onConfirmSelection={onConfirmSelection}
      />
    );

    await user.click(getWordChunk("upper"));
    await user.keyboard("{Shift>}");
    await user.click(getWordChunk("pain"));
    await user.keyboard("{/Shift}");

    expect(getWordChunk("upper")).toHaveAttribute("aria-pressed", "true");
    expect(getWordChunk("abdominal")).toHaveAttribute("aria-pressed", "true");
    expect(getWordChunk("pain")).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /confirm selection/i }));

    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 0, end: 20, text: "upper abdominal pain" },
      expect.any(HTMLElement),
    );
  });

  it("in contiguous mode, a plain click on a second word resets to a fresh one-word selection", async () => {
    const user = userEvent.setup();
    render(
      <HighlightableRecommendationText
        text={TEXT}
        mode="contiguous"
        onConfirmSelection={jest.fn()}
      />
    );

    await user.click(getWordChunk("upper"));
    await user.click(getWordChunk("pain"));

    expect(getWordChunk("upper")).toHaveAttribute("aria-pressed", "false");
    expect(getWordChunk("pain")).toHaveAttribute("aria-pressed", "true");
  });

  it("clicks disconnected words to toggle them on/off, previews the joined phrase, and confirms them", async () => {
    const user = userEvent.setup();
    const onConfirmSelection = jest.fn();
    const ng12 = "unexplained vulval lump, ulceration or bleeding.";
    render(
      <HighlightableRecommendationText
        text={ng12}
        onConfirmSelection={onConfirmSelection}
      />
    );

    await user.click(getWordChunk("unexplained"));
    await user.click(getWordChunk("vulval"));
    await user.click(getWordChunk("lump,"));
    // Clicking an already-picked word toggles it off.
    await user.click(getWordChunk("lump,"));
    await user.click(getWordChunk("bleeding."));

    expect(getWordChunk("unexplained")).toHaveAttribute("aria-pressed", "true");
    expect(getWordChunk("vulval")).toHaveAttribute("aria-pressed", "true");
    expect(getWordChunk("lump,")).toHaveAttribute("aria-pressed", "false");
    expect(getWordChunk("ulceration")).toHaveAttribute("aria-pressed", "false");
    expect(getWordChunk("bleeding.")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/unexplained vulval bleeding\./i)).toBeInTheDocument();

    const confirmButton = screen.getByRole("button", { name: /confirm selection/i });
    await user.click(confirmButton);

    expect(onConfirmSelection).toHaveBeenCalledWith(
      {
        start: 0,
        end: ng12.length,
        text: "unexplained vulval bleeding.",
      },
      confirmButton,
    );
  });

  it("toggles disconnected words with Space via keyboard and confirms with Enter", async () => {
    const user = userEvent.setup();
    const onConfirmSelection = jest.fn();
    const ng12 = "unexplained vulval lump, ulceration or bleeding.";
    render(
      <HighlightableRecommendationText
        text={ng12}
        onConfirmSelection={onConfirmSelection}
      />
    );

    await user.tab(); // "unexplained"
    await user.keyboard(" ");
    await user.tab(); // "vulval"
    await user.keyboard(" ");
    await user.tab(); // "lump,"
    await user.tab(); // "ulceration"
    await user.tab(); // "or"
    await user.tab(); // "bleeding."
    await user.keyboard(" ");
    await user.keyboard("{Enter}");

    expect(onConfirmSelection).toHaveBeenCalledWith(
      {
        start: 0,
        end: ng12.length,
        text: "unexplained vulval bleeding.",
      },
      getWordChunk("bleeding."),
    );
  });

  it("does not select the dimmed word 'and' when dragging is not initiated on it", () => {
    render(
      <HighlightableRecommendationText
        text={TEXT}
        dimmedRanges={[{ start: 21, end: 24 }]}
        onConfirmSelection={jest.fn()}
      />
    );

    const andChunk = getWordChunk("and");
    expect(andChunk).toHaveAttribute("tabIndex", "-1");
    expect(andChunk).toHaveAttribute("data-dimmed", "true");
  });
});

describe("HighlightableRecommendationText: keyboard chunk-and-extend", () => {
  it("Tab-focuses a chunk, Shift+ArrowRight extends, Enter confirms the extended range", async () => {
    const user = userEvent.setup();
    const onConfirmSelection = jest.fn();
    render(
      <HighlightableRecommendationText
        text={TEXT}
        onConfirmSelection={onConfirmSelection}
      />
    );

    await user.tab(); // focuses "upper" -- the first tabbable chunk
    expect(getWordChunk("upper")).toHaveFocus();

    await user.keyboard("{Shift>}{ArrowRight}{ArrowRight}{/Shift}");
    expect(getWordChunk("abdominal")).toHaveAttribute("aria-pressed", "true");
    expect(getWordChunk("pain")).toHaveAttribute("aria-pressed", "true");

    await user.keyboard("{Enter}");

    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 0, end: 20, text: "upper abdominal pain" },
      getWordChunk("upper"),
    );
  });

  it("confirms a single chunk with Enter when no extension happened", async () => {
    const user = userEvent.setup();
    const onConfirmSelection = jest.fn();
    render(
      <HighlightableRecommendationText
        text={TEXT}
        onConfirmSelection={onConfirmSelection}
      />
    );

    await user.tab();
    await user.tab(); // "abdominal"
    await user.keyboard("{Enter}");

    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 6, end: 15, text: "abdominal" },
      getWordChunk("abdominal"),
    );
  });


  it("Escape cancels a pending selection and calls onCancelSelection", async () => {
    const user = userEvent.setup();
    const onConfirmSelection = jest.fn();
    const onCancelSelection = jest.fn();
    render(
      <HighlightableRecommendationText
        text={TEXT}
        onConfirmSelection={onConfirmSelection}
        onCancelSelection={onCancelSelection}
      />
    );

    await user.tab();
    await user.keyboard("{Shift>}{ArrowRight}{/Shift}");
    expect(
      screen.getByRole("button", { name: /confirm selection/i })
    ).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(onCancelSelection).toHaveBeenCalledTimes(1);
    expect(onConfirmSelection).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: /confirm selection/i })
    ).not.toBeInTheDocument();
  });

  it("Shift+ArrowLeft narrows the extension back down without going past the anchor's other side unexpectedly", async () => {
    const user = userEvent.setup();
    const onConfirmSelection = jest.fn();
    render(
      <HighlightableRecommendationText
        text={TEXT}
        onConfirmSelection={onConfirmSelection}
      />
    );

    await user.tab();
    await user.tab();
    await user.tab(); // "pain" -- fresh anchor
    await user.keyboard("{Shift>}{ArrowLeft}{/Shift}");
    // Anchor is "pain"; ArrowLeft extends selection to include "abdominal".
    expect(getWordChunk("abdominal")).toHaveAttribute("aria-pressed", "true");
    expect(getWordChunk("pain")).toHaveAttribute("aria-pressed", "true");
    expect(getWordChunk("upper")).toHaveAttribute("aria-pressed", "false");

    await user.keyboard("{Enter}");
    expect(onConfirmSelection).toHaveBeenCalledWith(
      { start: 6, end: 20, text: "abdominal pain" },
      getWordChunk("pain"),
    );
  });
});

describe("HighlightableRecommendationText: existing highlights", () => {
  it("marks a confirmed span's words with data-highlight-kind=confirmed", () => {
    render(
      <HighlightableRecommendationText
        text={TEXT}
        highlights={[{ start: 0, end: 20, kind: "confirmed", label: "Upper abdominal pain" }]}
        onConfirmSelection={jest.fn()}
      />
    );

    expect(getWordChunk("upper")).toHaveAttribute("data-highlight-kind", "confirmed");
    expect(getWordChunk("pain")).toHaveAttribute("data-highlight-kind", "confirmed");
    expect(getWordChunk("and")).not.toHaveAttribute("data-highlight-kind");
  });

  it("marks a candidate span's words with data-highlight-kind=candidate", () => {
    render(
      <HighlightableRecommendationText
        text={TEXT}
        highlights={[{ start: 27, end: 48, kind: "candidate", label: "low haemoglobin level" }]}
        onConfirmSelection={jest.fn()}
      />
    );

    expect(getWordChunk("low")).toHaveAttribute("data-highlight-kind", "candidate");
    expect(getWordChunk("level")).toHaveAttribute("data-highlight-kind", "candidate");
  });
});
