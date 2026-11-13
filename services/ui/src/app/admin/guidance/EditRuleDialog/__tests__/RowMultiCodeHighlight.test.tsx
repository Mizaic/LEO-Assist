/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Live-render tests for RowMultiCodeHighlight -- the Step 3 row affordance
 * that lets a reviewer highlight a specific sub-phrase of a row (rather
 * than the whole row) and assign one or more SNOMED codes to just that
 * sub-phrase, each with its own explicit depth. Ties useWordSelection
 * (via HighlightableRecommendationText) to MultiConceptPicker.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import RowMultiCodeHighlight from "../HighlightWizard/RowMultiCodeHighlight";
import type { RecommendationStructureItem } from "../SentenceEditor/pathwayTextSplit";

const ROW: RecommendationStructureItem = {
  text: "upper abdominal pain and a low haemoglobin level",
  start: 100,
  end: 150,
};

const NAUSEA = {
  snomed_concept_id: "422587007",
  term: "Nausea",
  semantic_tag: "finding",
};

function mockSearch(hits: unknown[] = []) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).includes("/api/terminology/search")) {
      return Promise.resolve({ ok: true, json: async () => hits } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => [] } as Response);
  });
}

function getWordChunk(word: string) {
  return screen.getByText(word, { selector: "[data-word-index]" });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("RowMultiCodeHighlight", () => {
  it("starts collapsed, showing only the toggle button", () => {
    render(<RowMultiCodeHighlight item={ROW} onAddCriterion={jest.fn()} />);
    expect(
      screen.getByRole("button", { name: /highlight text for more codes/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText("upper", { selector: "[data-word-index]" })).not.toBeInTheDocument();
  });

  it("expands into highlightable word chunks of the row's own text when toggled", async () => {
    const user = userEvent.setup();
    render(<RowMultiCodeHighlight item={ROW} onAddCriterion={jest.fn()} />);

    await user.click(screen.getByRole("button", { name: /highlight text for more codes/i }));

    expect(getWordChunk("upper")).toBeInTheDocument();
    expect(getWordChunk("haemoglobin")).toBeInTheDocument();
  });

  it("collapses back to the toggle when cancelled before making a selection", async () => {
    const user = userEvent.setup();
    render(<RowMultiCodeHighlight item={ROW} onAddCriterion={jest.fn()} />);

    await user.click(screen.getByRole("button", { name: /highlight text for more codes/i }));
    // MUI Tooltip sets the button's accessible name from its `title`
    // (v7 default `describeChild=false`), replacing the visible "Close"
    // text -- see WIZARD_TOOLTIPS.multiCodeClose in copy.ts.
    await user.click(
      screen.getByRole("button", { name: /close the highlight-and-code tool without adding codes/i }),
    );

    expect(
      screen.getByRole("button", { name: /highlight text for more codes/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText("upper", { selector: "[data-word-index]" })).not.toBeInTheDocument();
  });

  it("after confirming a drag-selected sub-phrase, opens MultiConceptPicker seeded with just that phrase", async () => {
    const user = userEvent.setup();
    mockSearch([]);
    render(<RowMultiCodeHighlight item={ROW} onAddCriterion={jest.fn()} />);

    await user.click(screen.getByRole("button", { name: /highlight text for more codes/i }));

    const low = getWordChunk("low");
    const level = getWordChunk("level");
    await user.pointer([
      { keys: "[MouseLeft>]", target: low },
      { target: level },
      { keys: "[/MouseLeft]", target: level },
    ]);
    await user.click(screen.getByRole("button", { name: /confirm selection/i }));

    expect(screen.getByLabelText(/search clinical terms/i)).toHaveValue(
      "low haemoglobin level",
    );
  });

  it("confirming a pick calls onAddCriterion and collapses back to the toggle button", async () => {
    const user = userEvent.setup();
    mockSearch([NAUSEA]);
    const onAddCriterion = jest.fn();
    render(<RowMultiCodeHighlight item={ROW} onAddCriterion={onAddCriterion} />);

    await user.click(screen.getByRole("button", { name: /highlight text for more codes/i }));
    const upper = getWordChunk("upper");
    await user.pointer([
      { keys: "[MouseLeft>]", target: upper },
      { keys: "[/MouseLeft]", target: upper },
    ]);
    await user.click(screen.getByRole("button", { name: /confirm selection/i }));

    await user.click(await screen.findByRole("checkbox", { name: /select nausea/i }));
    await user.click(screen.getByRole("button", { name: "Add 1 code" }));

    expect(onAddCriterion).toHaveBeenCalledTimes(1);
    expect(onAddCriterion.mock.calls[0][0].snomed_concept_id).toBe("422587007");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /highlight text for more codes/i }),
      ).toBeInTheDocument(),
    );
  });

  it("renders full contextText when provided so disconnected modifiers ahead of a split row can be clicked", async () => {
    const user = userEvent.setup();
    const bleedHit = {
      snomed_concept_id: "890094005",
      term: "Bleeding from genital region",
      semantic_tag: "finding",
    };
    mockSearch([bleedHit]);
    const onAddCriterion = jest.fn();
    const bleedRow: RecommendationStructureItem = {
      text: "bleeding",
      start: 39,
      end: 47,
    };

    render(
      <RowMultiCodeHighlight
        item={bleedRow}
        contextText="unexplained vulval lump, ulceration or bleeding."
        onAddCriterion={onAddCriterion}
      />,
    );

    await user.click(screen.getByRole("button", { name: /highlight text for more codes/i }));
    await user.click(getWordChunk("unexplained"));
    await user.click(getWordChunk("vulval"));
    await user.click(getWordChunk("bleeding."));
    await user.click(screen.getByRole("button", { name: /confirm selection/i }));

    expect(screen.getByLabelText(/search clinical terms/i)).toHaveValue(
      "unexplained vulval bleeding.",
    );

    await user.click(
      await screen.findByRole("checkbox", { name: /select bleeding from genital region/i }),
    );
    await user.click(screen.getByRole("button", { name: "Add 1 code" }));

    expect(onAddCriterion).toHaveBeenCalledWith(
      expect.objectContaining({ snomed_concept_id: "890094005" }),
      "unexplained vulval bleeding.",
    );
  });
});
