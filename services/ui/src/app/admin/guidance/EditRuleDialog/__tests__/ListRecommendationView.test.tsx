/**
 * Live-render tests for ListRecommendationView -- row click -> pre-filled
 * search, nested-<ul> child rows, checkmark state, confidence banding.
 * Per the highlight-to-build wizard plan's `list-recommendation-view` todo.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ListRecommendationView, {
  ListRowResolution,
} from "../SentenceEditor/ListRecommendationView";
import type { RecommendationStructureItem } from "../SentenceEditor/pathwayTextSplit";
import type { LogicCriterion } from "../types";

// NG12 1.2.9-shaped fixture: 2 top-level pathways, one (B) with a nested
// "any of the following" list -- the same shape used throughout this
// codebase's other NG12 1.2.9 fixtures.
const PATHWAY_A: RecommendationStructureItem = {
  text: "upper abdominal pain",
  start: 0,
  end: 21,
};

const PATHWAY_B: RecommendationStructureItem = {
  text: "indigestion with any of the following:",
  start: 25,
  end: 64,
  children: [
    { text: "upper abdominal pain", start: 65, end: 86 },
    { text: "nausea", start: 88, end: 94 },
    { text: "vomiting", start: 96, end: 104 },
  ],
};

function makeCriterion(overrides: Partial<LogicCriterion> = {}): LogicCriterion {
  return {
    snomed_concept_id: "123",
    preferred_term: "Indigestion (finding)",
    ...overrides,
  };
}

describe("ListRecommendationView: rendering the structure tree", () => {
  it("renders lead text and one row per top-level item", () => {
    render(
      <ListRecommendationView
        leadText="In people aged 55 or over with:"
        items={[PATHWAY_A, PATHWAY_B]}
        onRowClick={jest.fn()}
      />
    );

    expect(screen.getByText(/in people aged 55 or over with/i)).toBeInTheDocument();
    expect(screen.getAllByText(/upper abdominal pain/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/indigestion with any of the following/i)).toBeInTheDocument();
  });

  it("renders pathway letter labels aligned to top-level items", () => {
    render(
      <ListRecommendationView
        items={[PATHWAY_A, PATHWAY_B]}
        pathwayLabels={["A", "B"]}
        onRowClick={jest.fn()}
      />
    );

    expect(screen.getByText("(A)")).toBeInTheDocument();
    expect(screen.getByText("(B)")).toBeInTheDocument();
  });

  it("renders nested <ul> children as indented child rows automatically", () => {
    render(
      <ListRecommendationView items={[PATHWAY_B]} onRowClick={jest.fn()} />
    );

    expect(screen.getByText(/nausea/i)).toBeInTheDocument();
    expect(screen.getByText(/vomiting/i)).toBeInTheDocument();
    const nauseaRow = screen.getByTestId(
      `list-row-${PATHWAY_B.children![1].start}-${PATHWAY_B.children![1].end}`
    );
    const parentRow = screen.getByTestId(`list-row-${PATHWAY_B.start}-${PATHWAY_B.end}`);
    // Child row should be indented further (larger left padding) than parent.
    const childPl = parseFloat(getComputedStyle(nauseaRow).paddingLeft);
    const parentPl = parseFloat(getComputedStyle(parentRow).paddingLeft);
    expect(childPl).toBeGreaterThan(parentPl);
  });
});

describe("ListRecommendationView: row click opens pre-filled search", () => {
  it("calls onRowClick with the clicked item's own text", async () => {
    const user = userEvent.setup();
    const onRowClick = jest.fn();
    render(
      <ListRecommendationView items={[PATHWAY_A, PATHWAY_B]} onRowClick={onRowClick} />
    );

    await user.click(
      screen.getByTestId(`list-row-${PATHWAY_A.start}-${PATHWAY_A.end}`)
    );

    expect(onRowClick).toHaveBeenCalledWith(PATHWAY_A, expect.any(HTMLElement));
  });

  it("clicking a nested child row passes that child's own item, not the parent's", async () => {
    const user = userEvent.setup();
    const onRowClick = jest.fn();
    render(<ListRecommendationView items={[PATHWAY_B]} onRowClick={onRowClick} />);

    await user.click(screen.getByText(/^nausea$/i));

    expect(onRowClick).toHaveBeenCalledWith(PATHWAY_B.children![1], expect.any(HTMLElement));
  });

  it("passes the actual clicked row element as the anchor, so a search popover opened from it appears in the right place", async () => {
    const user = userEvent.setup();
    const onRowClick = jest.fn();
    render(<ListRecommendationView items={[PATHWAY_A]} onRowClick={onRowClick} />);

    const row = screen.getByTestId(`list-row-${PATHWAY_A.start}-${PATHWAY_A.end}`);
    await user.click(row);

    const anchor = onRowClick.mock.calls[0][1];
    expect(anchor).toBeInstanceOf(HTMLElement);
    expect(row.contains(anchor) || row === anchor).toBe(true);
  });
});

describe("ListRecommendationView: checkmark state", () => {
  it("shows an unchecked row when no resolution is provided", () => {
    render(<ListRecommendationView items={[PATHWAY_A]} onRowClick={jest.fn()} />);

    const row = screen.getByTestId(`list-row-${PATHWAY_A.start}-${PATHWAY_A.end}`);
    expect(row).toHaveAttribute("data-resolved", "false");
  });

  it("shows a checkmark and the matched term when the row resolves", () => {
    const getRowResolution = (item: RecommendationStructureItem): ListRowResolution | undefined =>
      item === PATHWAY_A
        ? { criterion: makeCriterion(), preferredTerm: "Indigestion (finding)" }
        : undefined;
    render(
      <ListRecommendationView
        items={[PATHWAY_A]}
        getRowResolution={getRowResolution}
        onRowClick={jest.fn()}
      />
    );

    const row = screen.getByTestId(`list-row-${PATHWAY_A.start}-${PATHWAY_A.end}`);
    expect(row).toHaveAttribute("data-resolved", "true");
    expect(screen.getByText(/matched to: indigestion \(finding\)/i)).toBeInTheDocument();
  });

  it("resolves rows independently -- a resolved parent does not mark unresolved children", () => {
    const getRowResolution = (item: RecommendationStructureItem): ListRowResolution | undefined =>
      item === PATHWAY_B ? { criterion: makeCriterion(), preferredTerm: "Indigestion (finding)" } : undefined;
    render(
      <ListRecommendationView
        items={[PATHWAY_B]}
        getRowResolution={getRowResolution}
        onRowClick={jest.fn()}
      />
    );

    const parentRow = screen.getByTestId(`list-row-${PATHWAY_B.start}-${PATHWAY_B.end}`);
    const nauseaRow = screen.getByTestId(
      `list-row-${PATHWAY_B.children![1].start}-${PATHWAY_B.children![1].end}`
    );
    expect(parentRow).toHaveAttribute("data-resolved", "true");
    expect(nauseaRow).toHaveAttribute("data-resolved", "false");
  });
});

describe("ListRecommendationView: renderRowExtra slot", () => {
  it("renders the caller-supplied extra content for every row, keyed by that row's own item", () => {
    render(
      <ListRecommendationView
        items={[PATHWAY_A, PATHWAY_B]}
        onRowClick={jest.fn()}
        renderRowExtra={(item) => <span>extra:{item.text}</span>}
      />
    );

    expect(screen.getAllByText("extra:upper abdominal pain").length).toBeGreaterThan(0);
    expect(
      screen.getByText("extra:indigestion with any of the following:")
    ).toBeInTheDocument();
    // Nested children get the slot too, not just top-level rows.
    expect(screen.getByText("extra:nausea")).toBeInTheDocument();
  });

  it("renders nothing extra when renderRowExtra is not supplied (default, unaffected callers)", () => {
    render(<ListRecommendationView items={[PATHWAY_A]} onRowClick={jest.fn()} />);
    expect(screen.queryByText(/^extra:/)).not.toBeInTheDocument();
  });
});

describe("ListRecommendationView: confidence banding", () => {
  it("shows no confidence badge for a high-confidence resolved row", () => {
    const getRowResolution = (): ListRowResolution => ({
      criterion: makeCriterion({ confidence: 0.97 }),
      preferredTerm: "Indigestion (finding)",
    });
    render(
      <ListRecommendationView
        items={[PATHWAY_A]}
        getRowResolution={getRowResolution}
        onRowClick={jest.fn()}
      />
    );

    expect(screen.queryByText(/please check/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/check this/i)).not.toBeInTheDocument();
  });

  it("shows a low-confidence badge for a low-confidence resolved row", () => {
    const getRowResolution = (): ListRowResolution => ({
      criterion: makeCriterion({ confidence: 0.2 }),
      preferredTerm: "Indigestion (finding)",
    });
    render(
      <ListRecommendationView
        items={[PATHWAY_A]}
        getRowResolution={getRowResolution}
        onRowClick={jest.fn()}
      />
    );

    expect(screen.getByText(/please check/i)).toBeInTheDocument();
  });

  it("shows no badge at all for an unresolved row (nothing to band yet)", () => {
    render(<ListRecommendationView items={[PATHWAY_A]} onRowClick={jest.fn()} />);

    expect(screen.queryByText(/please check/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/check this/i)).not.toBeInTheDocument();
  });
});
