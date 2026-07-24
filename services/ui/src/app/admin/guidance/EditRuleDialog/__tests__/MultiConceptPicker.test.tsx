/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Live-render tests for MultiConceptPicker: the "highlight a word, assign
 * one or more SNOMED codes" picker. Unlike ConceptSearchPanel (one pick per
 * "Use this"), this lets a reviewer tick several results and confirm once,
 * with each pick's descendant-matching depth asked explicitly and
 * defaulting to 0 (exact match only) -- see multiConceptSeed.ts.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import MultiConceptPicker from "../MultiConceptPicker";
import type { LogicCriterion } from "../types";

function mockSearch(hits: unknown[] = []) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).includes("/api/terminology/search")) {
      return Promise.resolve({
        ok: true,
        json: async () => hits,
      } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => [] } as Response);
  });
}

const NAUSEA = {
  snomed_concept_id: "422587007",
  term: "Nausea",
  semantic_tag: "finding",
};
const VOMITING = {
  snomed_concept_id: "422400008",
  term: "Vomiting",
  semantic_tag: "finding",
};

afterEach(() => {
  jest.restoreAllMocks();
});

describe("MultiConceptPicker", () => {
  it("pre-fills the search box with the initial query and lists hits, unchecked by default", async () => {
    mockSearch([NAUSEA, VOMITING]);
    render(<MultiConceptPicker initialQuery="nausea" onConfirm={jest.fn()} />);

    expect(screen.getByLabelText(/search clinical terms/i)).toHaveValue("nausea");
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: /select nausea/i })).not.toBeChecked(),
    );
    expect(screen.getByRole("checkbox", { name: /select vomiting/i })).not.toBeChecked();
  });

  it("disables confirm with nothing selected, and labels it 'Add 1 code' after one pick", async () => {
    const user = userEvent.setup();
    mockSearch([NAUSEA]);
    render(<MultiConceptPicker initialQuery="nausea" onConfirm={jest.fn()} />);

    expect(
      screen.getByRole("button", { name: /add.*code/i }),
    ).toBeDisabled();

    await user.click(await screen.findByRole("checkbox", { name: /select nausea/i }));

    expect(screen.getByRole("button", { name: "Add 1 code" })).toBeEnabled();
  });

  it("pluralises the confirm button and shows a depth field defaulting to 0 once checked", async () => {
    const user = userEvent.setup();
    mockSearch([NAUSEA, VOMITING]);
    render(<MultiConceptPicker initialQuery="nausea" onConfirm={jest.fn()} />);

    await user.click(await screen.findByRole("checkbox", { name: /select nausea/i }));
    await user.click(screen.getByRole("checkbox", { name: /select vomiting/i }));

    expect(screen.getByRole("button", { name: "Add 2 codes" })).toBeEnabled();
    expect(screen.getByLabelText(/depth.*nausea.*exact match/i)).toHaveValue(0);
    expect(screen.getByLabelText(/depth.*vomiting.*exact match/i)).toHaveValue(0);
  });

  it("confirms a single exact-match seed when depth is left at the default 0", async () => {
    const user = userEvent.setup();
    mockSearch([NAUSEA]);
    const onConfirm = jest.fn();
    render(<MultiConceptPicker initialQuery="nausea" onConfirm={onConfirm} />);

    await user.click(await screen.findByRole("checkbox", { name: /select nausea/i }));
    await user.click(screen.getByRole("button", { name: "Add 1 code" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const criterion: LogicCriterion = onConfirm.mock.calls[0][0];
    expect(criterion.snomed_concept_id).toBe("422587007");
    expect(criterion.seeds).toEqual([
      {
        snomed_concept_id: "422587007",
        preferred_term: "Nausea",
        semantic_tag: "finding",
        include_descendants: false,
        distance_child: null,
      },
    ]);
  });

  it("confirms multiple seeds in pick order, each keeping its own depth", async () => {
    const user = userEvent.setup();
    mockSearch([NAUSEA, VOMITING]);
    const onConfirm = jest.fn();
    render(<MultiConceptPicker initialQuery="nausea" onConfirm={onConfirm} />);

    await user.click(await screen.findByRole("checkbox", { name: /select nausea/i }));
    await user.click(screen.getByRole("checkbox", { name: /select vomiting/i }));

    const vomitingDepth = screen.getByLabelText(/depth.*vomiting.*exact match/i);
    await user.clear(vomitingDepth);
    await user.type(vomitingDepth, "2");

    await user.click(screen.getByRole("button", { name: "Add 2 codes" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const criterion: LogicCriterion = onConfirm.mock.calls[0][0];
    expect(criterion.primary_concept_id).toBe("422587007");
    expect(criterion.seeds).toEqual([
      expect.objectContaining({
        snomed_concept_id: "422587007",
        include_descendants: false,
        distance_child: null,
      }),
      expect.objectContaining({
        snomed_concept_id: "422400008",
        include_descendants: true,
        distance_child: 2,
      }),
    ]);
  });

  it("unchecking a hit removes it from the pick set and hides its depth field", async () => {
    const user = userEvent.setup();
    mockSearch([NAUSEA]);
    render(<MultiConceptPicker initialQuery="nausea" onConfirm={jest.fn()} />);

    const checkbox = await screen.findByRole("checkbox", { name: /select nausea/i });
    await user.click(checkbox);
    expect(screen.getByLabelText(/depth.*nausea.*exact match/i)).toBeInTheDocument();

    await user.click(checkbox);
    expect(screen.queryByLabelText(/depth.*nausea.*exact match/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add.*code/i })).toBeDisabled();
  });
});
