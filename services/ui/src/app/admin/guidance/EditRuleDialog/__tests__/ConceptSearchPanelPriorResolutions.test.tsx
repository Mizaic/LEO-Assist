/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Live-render tests for ConceptSearchPanel's concept-mapping nudge: a
 * soft suggestion of the SNOMED code(s) already used elsewhere in the
 * rule library for the phrase the reviewer is coding, surfaced from
 * GET /api/terminology/prior-resolutions. Per the highlight-to-build
 * wizard plan's rubber-stamping-risk discussion, this must never call
 * onPick on its own -- only the reviewer's own click on "Use this" can.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ConceptSearchPanel from "../ConceptSearchPanel";

function mockFetch(priorResolutions: unknown[] = [], searchHits: unknown[] = []) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    const href = String(url);
    if (href.includes("/api/terminology/prior-resolutions")) {
      return Promise.resolve({
        ok: true,
        json: async () => priorResolutions,
      } as Response);
    }
    if (href.includes("/api/terminology/search")) {
      return Promise.resolve({
        ok: true,
        json: async () => searchHits,
      } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => [] } as Response);
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("ConceptSearchPanel: prior-resolution nudge", () => {
  it("shows a singular nudge banner with the prior code when one match exists", async () => {
    mockFetch([
      {
        snomed_concept_id: "422587007",
        preferred_term: "Vomiting (finding)",
        semantic_tag: "finding",
        count: 3,
      },
    ]);
    render(
      <ConceptSearchPanel
        mode="add"
        focusLabel={null}
        initialQuery="vomiting"
        onPick={jest.fn()}
      />,
    );

    expect(
      await screen.findByRole("group", { name: /other rules use this code for "vomiting"/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Vomiting")).toBeInTheDocument();
    expect(screen.getByText("Used 3 times")).toBeInTheDocument();
  });

  it("pluralises the heading when multiple prior codes exist", async () => {
    mockFetch([
      {
        snomed_concept_id: "422587007",
        preferred_term: "Vomiting (finding)",
        semantic_tag: "finding",
        count: 3,
      },
      {
        snomed_concept_id: "999999999",
        preferred_term: "A different vomiting code (finding)",
        semantic_tag: "finding",
        count: 1,
      },
    ]);
    render(
      <ConceptSearchPanel
        mode="add"
        focusLabel={null}
        initialQuery="vomiting"
        onPick={jest.fn()}
      />,
    );

    expect(
      await screen.findByRole("group", { name: /other rules use these codes for "vomiting"/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Used once")).toBeInTheDocument();
  });

  it("calls onPick with the prior criterion only when the reviewer clicks Use this", async () => {
    const user = userEvent.setup();
    mockFetch([
      {
        snomed_concept_id: "422587007",
        preferred_term: "Vomiting (finding)",
        semantic_tag: "finding",
        count: 3,
      },
    ]);
    const onPick = jest.fn();
    render(
      <ConceptSearchPanel
        mode="add"
        focusLabel={null}
        initialQuery="vomiting"
        onPick={onPick}
      />,
    );

    await screen.findByRole("group", { name: /other rules use this code/i });
    expect(onPick).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", { name: /use vomiting \(previously used for "vomiting"\)/i }),
    );
    expect(onPick).toHaveBeenCalledWith({
      snomed_concept_id: "422587007",
      preferred_term: "Vomiting (finding)",
      semantic_tag: "finding",
      term: "vomiting",
    });
  });

  it("renders no nudge banner when there are no prior resolutions", async () => {
    mockFetch([]);
    render(
      <ConceptSearchPanel
        mode="add"
        focusLabel={null}
        initialQuery="a totally novel phrase"
        onPick={jest.fn()}
      />,
    );

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(screen.queryByRole("group", { name: /other rules use/i })).not.toBeInTheDocument();
  });

  it("does not fetch prior resolutions in idle mode", () => {
    mockFetch([]);
    render(
      <ConceptSearchPanel mode="idle" focusLabel={null} initialQuery="vomiting" onPick={jest.fn()} />,
    );

    expect(global.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/terminology/prior-resolutions"),
    );
  });
});
