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

function mockSearch(
  hits: unknown[] = [],
  descendants: unknown[] = [],
) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    const href = String(url);
    if (href.includes("/api/terminology/search")) {
      return Promise.resolve({
        ok: true,
        json: async () => hits,
      } as Response);
    }
    if (href.includes("/descendants")) {
      return Promise.resolve({
        ok: true,
        json: async () => descendants,
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

const LESION_SIZE = {
  snomed_concept_id: "396361002",
  term: "Lesion size, largest dimension",
  semantic_tag: "observable_entity",
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

  it("hovering Depth at 0 explains exact-match only, without fetching descendants", async () => {
    const user = userEvent.setup();
    mockSearch([NAUSEA], [{ snomed_concept_id: "x", term: "Should not load" }]);
    render(<MultiConceptPicker initialQuery="nausea" onConfirm={jest.fn()} />);

    await user.click(await screen.findByRole("checkbox", { name: /select nausea/i }));
    const depth = screen.getByLabelText(/depth.*nausea.*exact match/i);
    await user.hover(depth);

    const tip = await screen.findByRole("tooltip");
    expect(tip).toHaveTextContent(/only "nausea" will match/i);
    const descendantCalls = (global.fetch as jest.Mock).mock.calls.filter((c) =>
      String(c[0]).includes("/descendants"),
    );
    expect(descendantCalls).toHaveLength(0);
  });

  it("hovering Depth above 0 lists every more specific code in a scrollable tooltip", async () => {
    const user = userEvent.setup();
    const descendants = Array.from({ length: 12 }, (_, i) => ({
      snomed_concept_id: String(i + 1),
      term: `Nausea variant ${i + 1}`,
    }));
    mockSearch([NAUSEA], descendants);
    render(<MultiConceptPicker initialQuery="nausea" onConfirm={jest.fn()} />);

    await user.click(await screen.findByRole("checkbox", { name: /select nausea/i }));
    const depth = screen.getByLabelText(/depth.*nausea.*exact match/i);
    await user.clear(depth);
    await user.type(depth, "1");
    await user.hover(depth);

    const tip = await screen.findByRole("tooltip");
    expect(tip).toHaveTextContent(/also includes 12 more specific codes/i);
    expect(tip).toHaveTextContent(/nausea variant 1/i);
    expect(tip).toHaveTextContent(/nausea variant 12/i);
    expect(tip).not.toHaveTextContent(/and \d+ more/i);
  });

  it("shows operator, value, and unit for a ticked observable, prefilled from the phrase", async () => {
    const user = userEvent.setup();
    mockSearch([LESION_SIZE]);
    render(
      <MultiConceptPicker
        initialQuery="largest diameter 7 mm or more"
        onConfirm={jest.fn()}
        onConfirmObservation={jest.fn()}
      />,
    );

    await user.click(
      await screen.findByRole("checkbox", {
        name: /select lesion size, largest dimension/i,
      }),
    );

    expect(
      screen.getByLabelText(/comparison for lesion size/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/value for lesion size/i)).toHaveValue(7);
    expect(screen.getByLabelText(/unit for lesion size/i)).toHaveValue("mm");
    expect(
      screen.getByRole("button", { name: /add this reading/i }),
    ).toBeEnabled();
  });

  it("confirms an OBSERVATION seed when value is filled on one observable", async () => {
    const user = userEvent.setup();
    mockSearch([LESION_SIZE]);
    const onConfirm = jest.fn();
    const onConfirmObservation = jest.fn();
    render(
      <MultiConceptPicker
        initialQuery="largest diameter 7 mm or more"
        onConfirm={onConfirm}
        onConfirmObservation={onConfirmObservation}
      />,
    );

    await user.click(
      await screen.findByRole("checkbox", {
        name: /select lesion size, largest dimension/i,
      }),
    );
    await user.click(screen.getByRole("button", { name: /add this reading/i }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(onConfirmObservation).toHaveBeenCalledWith({
      observable_id: "396361002",
      observable_term: "Lesion size, largest dimension",
      operator: ">=",
      value: 7,
      unit: "mm",
    });
  });

  it("disables confirm when several codes are selected and a reading value is filled", async () => {
    const user = userEvent.setup();
    mockSearch([LESION_SIZE, NAUSEA]);
    render(
      <MultiConceptPicker
        initialQuery="largest diameter 7 mm or more"
        onConfirm={jest.fn()}
        onConfirmObservation={jest.fn()}
      />,
    );

    await user.click(
      await screen.findByRole("checkbox", {
        name: /select lesion size, largest dimension/i,
      }),
    );
    await user.click(screen.getByRole("checkbox", { name: /select nausea/i }));

    expect(
      screen.getByText(/reading value can only be added when one code is selected/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add 2 codes/i })).toBeDisabled();
  });

  it("stays on the CONCEPT path when an observable has a blank value", async () => {
    const user = userEvent.setup();
    mockSearch([LESION_SIZE]);
    const onConfirm = jest.fn();
    const onConfirmObservation = jest.fn();
    render(
      <MultiConceptPicker
        initialQuery="lesion size"
        onConfirm={onConfirm}
        onConfirmObservation={onConfirmObservation}
      />,
    );

    await user.click(
      await screen.findByRole("checkbox", {
        name: /select lesion size, largest dimension/i,
      }),
    );
    const value = screen.getByLabelText(/value for lesion size/i);
    await user.clear(value);
    await user.click(screen.getByRole("button", { name: "Add 1 code" }));

    expect(onConfirmObservation).not.toHaveBeenCalled();
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm.mock.calls[0][0].snomed_concept_id).toBe("396361002");
  });
});
