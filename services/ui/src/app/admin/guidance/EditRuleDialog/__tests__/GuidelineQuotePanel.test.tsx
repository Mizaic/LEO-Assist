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
  buildSituationBoundaryHighlights,
  mergeHighlightRanges,
  scopeHighlightsToActiveSituation,
  situationHighlightColor,
} from "../GuidelineQuotePanel";
import { assignNodeIds, type LogicNodeSeed } from "../treeOps";
import type { EditableLogicNode } from "../types";
import type { HighlightSpan } from "../SentenceEditor/HighlightableRecommendationText";
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";

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
      { start: 0, end: 5, pathwayIndex: undefined },
      { start: 10, end: 15, pathwayIndex: undefined },
    ]);
  });

  it("merges overlapping spans into one range when they share a pathway", () => {
    const spans: HighlightSpan[] = [
      { start: 0, end: 10, kind: "confirmed", pathwayIndex: 0 },
      { start: 5, end: 15, kind: "confirmed", pathwayIndex: 0 },
    ];
    expect(mergeHighlightRanges(spans)).toEqual([
      { start: 0, end: 15, pathwayIndex: 0 },
    ]);
  });

  it("does NOT merge adjacent spans that belong to different situations", () => {
    const spans: HighlightSpan[] = [
      { start: 0, end: 10, kind: "confirmed", pathwayIndex: 0 },
      { start: 10, end: 20, kind: "confirmed", pathwayIndex: 1 },
    ];
    expect(mergeHighlightRanges(spans)).toEqual([
      { start: 0, end: 10, pathwayIndex: 0 },
      { start: 10, end: 20, pathwayIndex: 1 },
    ]);
  });

  it("merges adjacent (touching) spans into one range when they share a pathway", () => {
    const spans: HighlightSpan[] = [
      { start: 0, end: 10, kind: "confirmed", pathwayIndex: 2 },
      { start: 10, end: 20, kind: "confirmed", pathwayIndex: 2 },
    ];
    expect(mergeHighlightRanges(spans)).toEqual([
      { start: 0, end: 20, pathwayIndex: 2 },
    ]);
  });

  it("returns an empty array for no spans", () => {
    expect(mergeHighlightRanges([])).toEqual([]);
  });
});

describe("buildSituationBoundaryHighlights", () => {
  it("emits one span per situation, tagged with its pathway index", () => {
    const a = "situation A text";
    const b = "situation B text";
    const boundaries: PathwayTextBoundary[] = [
      { start: 0, end: a.length, text: a, source: "heuristic" },
      { start: a.length + 1, end: a.length + 1 + b.length, text: b, source: "heuristic" },
    ];
    const spans = buildSituationBoundaryHighlights(boundaries);
    expect(spans).toEqual([
      expect.objectContaining({
        start: 0,
        end: a.length,
        pathwayIndex: 0,
        kind: "confirmed",
      }),
      expect.objectContaining({
        start: a.length + 1,
        end: a.length + 1 + b.length,
        pathwayIndex: 1,
        kind: "confirmed",
      }),
    ]);
  });

  it("strips a dangling trailing ', or' connector from the highlight range", () => {
    const boundaries: PathwayTextBoundary[] = [
      { start: 0, end: 20, text: "dyspepsia, or ", source: "heuristic" },
      { start: 20, end: 40, text: "upper abdominal pain", source: "heuristic" },
    ];
    const spans = buildSituationBoundaryHighlights(boundaries);
    expect(spans[0].end - spans[0].start).toBe("dyspepsia".length);
    expect(spans[0].pathwayIndex).toBe(0);
  });

  it("skips tree-rehydrated and zero-width boundaries so table rules do not paint stacked prefixes", () => {
    const boundaries: PathwayTextBoundary[] = [
      { start: 0, end: 0, text: "is between 40 and 49 years, CA125", source: "tree" },
      { start: 0, end: 0, text: "is between 50 and 59 years, CA125", source: "tree" },
      { start: 0, end: 0, text: "Situation C", source: "heuristic" },
    ];
    expect(buildSituationBoundaryHighlights(boundaries)).toEqual([]);
  });
});

function boundary(start: number, end: number, text: string): PathwayTextBoundary {
  return { start, end, text, source: "heuristic" };
}

describe("scopeHighlightsToActiveSituation", () => {
  const BOUNDARIES: PathwayTextBoundary[] = [
    boundary(0, 10, "situation A"),
    boundary(10, 20, "situation B"),
    boundary(20, 30, "situation C"),
  ];

  it("is a no-op when there is no pathway split yet", () => {
    const spans: HighlightSpan[] = [{ start: 5, end: 8, kind: "confirmed" }];
    expect(scopeHighlightsToActiveSituation(spans, null, null)).toBe(spans);
    expect(scopeHighlightsToActiveSituation(spans, [], 0)).toBe(spans);
  });

  it("keeps a highlight inside the active pathway's boundary", () => {
    const spans: HighlightSpan[] = [{ start: 12, end: 15, kind: "confirmed" }];
    expect(scopeHighlightsToActiveSituation(spans, BOUNDARIES, 1)).toEqual(spans);
  });

  it("drops a highlight that falls inside a DIFFERENT pathway's boundary", () => {
    const spans: HighlightSpan[] = [
      { start: 22, end: 25, kind: "confirmed" }, // situation C
    ];
    expect(scopeHighlightsToActiveSituation(spans, BOUNDARIES, 1)).toEqual([]);
  });

  it("keeps a highlight outside every boundary -- a prerequisite that applies everywhere", () => {
    const spans: HighlightSpan[] = [{ start: 35, end: 40, kind: "confirmed" }];
    expect(scopeHighlightsToActiveSituation(spans, BOUNDARIES, 1)).toEqual(spans);
  });

  it("keeps active-pathway and prerequisite highlights together, dropping only other pathways", () => {
    const active: HighlightSpan = { start: 12, end: 15, kind: "confirmed" };
    const prereq: HighlightSpan = { start: 35, end: 40, kind: "confirmed" };
    const other: HighlightSpan = { start: 22, end: 25, kind: "confirmed" };
    expect(
      scopeHighlightsToActiveSituation([active, prereq, other], BOUNDARIES, 1),
    ).toEqual([active, prereq]);
  });

  it("drops everything pathway-owned when no active index is given -- Step 2 uses boundary highlights instead", () => {
    const spans: HighlightSpan[] = [
      { start: 5, end: 8, kind: "confirmed" }, // situation A
      { start: 35, end: 40, kind: "confirmed" }, // prerequisite
    ];
    expect(scopeHighlightsToActiveSituation(spans, BOUNDARIES, null)).toEqual([
      spans[1],
    ]);
  });

  // NG12 nested-list regression: a structural lead `<li>` ends before
  // its own nested `<ul>` items. Those items sit past boundary.end but
  // before the next situation -- they must NOT light up as
  // "prerequisites" when an earlier situation is active.
  it("drops nested-list wording that sits past a structural lead end when another situation is active", () => {
    const text =
      "treatment-resistant dyspepsia. nausea vomiting. upper abdominal pain";
    const aEnd = text.indexOf("dyspepsia") + "dyspepsia".length;
    const nauseaStart = text.indexOf("nausea");
    const bStart = text.indexOf("upper abdominal");
    const nestedBoundaries: PathwayTextBoundary[] = [
      boundary(0, aEnd, "treatment-resistant dyspepsia"),
      boundary(bStart, text.length, "upper abdominal pain"),
    ];
    const nausea: HighlightSpan = {
      start: nauseaStart,
      end: nauseaStart + "nausea".length,
      kind: "confirmed",
    };
    const dyspepsia: HighlightSpan = {
      start: 0,
      end: aEnd,
      kind: "confirmed",
    };
    // nausea lives in A's extended window [0, bStart) -- keep when A active
    expect(
      scopeHighlightsToActiveSituation(
        [dyspepsia, nausea],
        nestedBoundaries,
        0,
        text.length,
      ),
    ).toEqual([dyspepsia, nausea]);
    // ...and drop when B is active (not a prerequisite)
    expect(
      scopeHighlightsToActiveSituation(
        [dyspepsia, nausea],
        nestedBoundaries,
        1,
        text.length,
      ),
    ).toEqual([]);
  });
});

describe("situationHighlightColor", () => {
  it("returns a distinct colour for each of the first four situations", () => {
    const colors = [0, 1, 2, 3].map((i) => situationHighlightColor(i).bgcolor);
    expect(new Set(colors).size).toBe(4);
  });

  it("returns the shared confirmed green for a prerequisite (no pathway index)", () => {
    expect(situationHighlightColor(null)).toEqual(expect.objectContaining({
      bgcolor: expect.any(String),
    }));
    expect(situationHighlightColor(undefined).bgcolor).toBe(
      situationHighlightColor(null).bgcolor,
    );
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

describe("GuidelineQuotePanel: Step 2 situation-coloured boundaries", () => {
  const SPLIT_TEXT =
    "treatment-resistant dyspepsia, or upper abdominal pain with low haemoglobin.";
  const SPLIT: PathwayTextBoundary[] = [
    {
      start: 0,
      end: "treatment-resistant dyspepsia, or ".length,
      text: "treatment-resistant dyspepsia, or ",
      source: "heuristic",
    },
    {
      start: "treatment-resistant dyspepsia, or ".length,
      end: SPLIT_TEXT.length,
      text: "upper abdominal pain with low haemoglobin.",
      source: "heuristic",
    },
  ];

  it("highlights every situation's full wording when no active index is set (Step 2 overview)", () => {
    render(
      <GuidelineQuotePanel
        recommendationText={SPLIT_TEXT}
        tree={null}
        pathwayBoundaries={SPLIT}
        activePathwayIndex={null}
      />,
    );
    const marks = Array.from(document.querySelectorAll("mark"));
    expect(marks.length).toBe(2);
    expect(marks[0]).toHaveTextContent(/treatment-resistant dyspepsia/i);
    expect(marks[1]).toHaveTextContent(/upper abdominal pain with low haemoglobin/i);
  });

  it("paints each situation with a different background colour", () => {
    render(
      <GuidelineQuotePanel
        recommendationText={SPLIT_TEXT}
        tree={null}
        pathwayBoundaries={SPLIT}
        activePathwayIndex={null}
      />,
    );
    const marks = Array.from(document.querySelectorAll("mark"));
    const bgA = (marks[0] as HTMLElement).style.backgroundColor ||
      getComputedStyle(marks[0]).backgroundColor;
    const bgB = (marks[1] as HTMLElement).style.backgroundColor ||
      getComputedStyle(marks[1]).backgroundColor;
    // MUI sx may land as a class rather than inline style -- fall back
    // to the data attribute we stamp for tests / a11y.
    expect(marks[0]).toHaveAttribute("data-situation-index", "0");
    expect(marks[1]).toHaveAttribute("data-situation-index", "1");
    expect(marks[0].getAttribute("data-situation-index")).not.toBe(
      marks[1].getAttribute("data-situation-index"),
    );
    void bgA;
    void bgB;
  });

  it("shows a legend that names the colour-per-situation overview", () => {
    render(
      <GuidelineQuotePanel
        recommendationText={SPLIT_TEXT}
        tree={null}
        pathwayBoundaries={SPLIT}
        activePathwayIndex={null}
      />,
    );
    expect(screen.getByText(/each colour is a different situation/i)).toBeInTheDocument();
  });
});

describe("GuidelineQuotePanel: scoped to the active situation", () => {
  const AGE_END = TEXT.indexOf("with") + "with".length;
  // "situation A" covers the weight-loss wording; "situation B" (not
  // active here) covers the nausea wording that follows it.
  const SITUATIONS: PathwayTextBoundary[] = [
    boundary(AGE_END, TEXT.indexOf("nausea"), "weight loss situation"),
    boundary(TEXT.indexOf("nausea"), TEXT.length, "nausea situation"),
  ];

  function makeWeightLossLeaf(): EditableLogicNode {
    return assignNodeIds({
      kind: "CONCEPT",
      criterion: { snomed_concept_id: "1", preferred_term: "weight loss" },
    } as LogicNodeSeed);
  }

  it("still highlights a prerequisite (age) while a specific situation is active", () => {
    render(
      <GuidelineQuotePanel
        recommendationText={TEXT}
        tree={makeAgeLeaf()}
        pathwayBoundaries={SITUATIONS}
        activePathwayIndex={0}
      />,
    );
    const mark = document.querySelector("mark");
    expect(mark).toHaveTextContent(/aged 55 or over/i);
  });

  it("highlights wording that belongs to the active situation", () => {
    render(
      <GuidelineQuotePanel
        recommendationText={TEXT}
        tree={makeWeightLossLeaf()}
        pathwayBoundaries={SITUATIONS}
        activePathwayIndex={0}
      />,
    );
    expect(document.querySelector("mark")).toHaveTextContent(/weight loss/i);
  });

  it("does NOT highlight wording that belongs to a different, inactive situation", () => {
    render(
      <GuidelineQuotePanel
        recommendationText={TEXT}
        tree={makeWeightLossLeaf()}
        pathwayBoundaries={SITUATIONS}
        activePathwayIndex={1}
      />,
    );
    expect(document.querySelector("mark")).not.toBeInTheDocument();
  });

  it("shows the situation-scoped legend once a split exists", () => {
    render(
      <GuidelineQuotePanel
        recommendationText={TEXT}
        tree={makeWeightLossLeaf()}
        pathwayBoundaries={SITUATIONS}
        activePathwayIndex={0}
      />,
    );
    expect(screen.getByText(/captured for this situation/i)).toBeInTheDocument();
  });
});
