/**
 * Live-render tests for GuidelineQuotePanel -- the pinned NICE
 * wording shown in the right column while the guided highlight-to-
 * build wizard works through Step1Who. Covers the plain fallback, the
 * new tree-driven highlighting of already-captured wording, and the
 * pure `mergeHighlightRanges` helper it's built on.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import GuidelineQuotePanel, {
  mergeHighlightRanges,
} from "../GuidelineQuotePanel";
import { assignNodeIds, type LogicNodeSeed } from "../treeOps";
import type { EditableLogicNode } from "../types";
import type { HighlightSpan } from "../SentenceEditor/HighlightableRecommendationText";

const TEXT =
  "Consider non-urgent referral in people aged 55 or over with " +
  "weight loss and nausea.";

function makeAgeLeaf(): EditableLogicNode {
  return assignNodeIds({
    kind: "DEMOGRAPHIC",
    field: "age",
    operator: ">=",
    value: 55,
  } as LogicNodeSeed);
}

describe("mergeHighlightRanges", () => {
  it("passes through non-overlapping spans, sorted by start", () => {
    const spans: HighlightSpan[] = [
      { start: 10, end: 15, kind: "confirmed" },
      { start: 0, end: 5, kind: "confirmed" },
    ];
    expect(mergeHighlightRanges(spans)).toEqual([
      { start: 0, end: 5 },
      { start: 10, end: 15 },
    ]);
  });

  it("merges overlapping spans into one range", () => {
    const spans: HighlightSpan[] = [
      { start: 0, end: 10, kind: "confirmed" },
      { start: 5, end: 15, kind: "confirmed" },
    ];
    expect(mergeHighlightRanges(spans)).toEqual([{ start: 0, end: 15 }]);
  });

  it("merges adjacent (touching) spans into one range", () => {
    const spans: HighlightSpan[] = [
      { start: 0, end: 10, kind: "confirmed" },
      { start: 10, end: 20, kind: "confirmed" },
    ];
    expect(mergeHighlightRanges(spans)).toEqual([{ start: 0, end: 20 }]);
  });

  it("returns an empty array for no spans", () => {
    expect(mergeHighlightRanges([])).toEqual([]);
  });
});

describe("GuidelineQuotePanel: no highlighting", () => {
  it("renders the quote in plain text when no tree is supplied", () => {
    render(<GuidelineQuotePanel recommendationText={TEXT} />);
    expect(screen.getByText(TEXT)).toBeInTheDocument();
    expect(document.querySelector("mark")).not.toBeInTheDocument();
  });

  it("shows a fallback message when there is no guideline text", () => {
    render(<GuidelineQuotePanel recommendationText={null} />);
    expect(screen.getByText(/no guideline text to show/i)).toBeInTheDocument();
  });
});

describe("GuidelineQuotePanel: tree-driven highlighting", () => {
  it("highlights the words already captured by a tree leaf", () => {
    render(<GuidelineQuotePanel recommendationText={TEXT} tree={makeAgeLeaf()} />);

    const mark = document.querySelector("mark");
    expect(mark).toBeInTheDocument();
    expect(mark).toHaveTextContent(/aged 55 or over/i);
  });

  it("leaves unmatched wording as plain text alongside the highlight", () => {
    render(<GuidelineQuotePanel recommendationText={TEXT} tree={makeAgeLeaf()} />);
    expect(screen.getByText(/weight loss and nausea/i)).toBeInTheDocument();
  });

  it("shows the 'already captured' legend once something is highlighted", () => {
    render(<GuidelineQuotePanel recommendationText={TEXT} tree={makeAgeLeaf()} />);
    expect(screen.getByText(/already captured on the left/i)).toBeInTheDocument();
  });

  it("shows the default legend when nothing anchors yet", () => {
    render(<GuidelineQuotePanel recommendationText={TEXT} tree={null} />);
    expect(
      screen.getByText(/keep checking this against what you pick/i),
    ).toBeInTheDocument();
  });
});
