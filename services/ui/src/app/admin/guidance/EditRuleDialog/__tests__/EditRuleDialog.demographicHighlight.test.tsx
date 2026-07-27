/**
 * Regression test for the "aged 40 and over" bug: highlighting an age
 * phrase in Step 1 (prerequisites) must add a DEMOGRAPHIC leaf with the
 * parsed operator/value, not open SNOMED concept search -- age has no
 * SNOMED code of its own, and picking a bare "current age" observable
 * concept added nothing useful and never asked for the threshold.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import EditRuleDialog from "..";

const RULE_MISSING_AGE = {
  rule_id: "rule:NG12:lung-cancer",
  name: "1.1.2",
  strength: "offer",
  guideline_id: "NG12",
  chapter_title: "Recommendations organised by site of cancer",
  recommendation_text:
    "Offer an urgent chest X-ray to assess for lung cancer in people aged 40 and over if they have cough.",
  logic_tree: {
    kind: "AND",
    children: [
      {
        kind: "CONCEPT",
        criterion: {
          snomed_concept_id: "49727002",
          preferred_term: "Cough (finding)",
          semantic_tag: "finding",
        },
      },
    ],
  },
};

function mockSearch() {
  jest.spyOn(global, "fetch").mockImplementation(() =>
    Promise.resolve({ ok: true, json: async () => [], text: async () => "[]" } as Response),
  );
}

function getWordChunk(word: string) {
  return screen.getAllByText(word, { selector: "[data-word-index]" })[0];
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("EditRuleDialog: highlighting an age phrase", () => {
  it("adds a DEMOGRAPHIC row with the parsed threshold instead of opening concept search", async () => {
    mockSearch();
    const user = userEvent.setup();
    render(
      <EditRuleDialog rule={RULE_MISSING_AGE} open onClose={() => {}} onSave={() => {}} />,
    );

    // Nothing has detected an age prerequisite yet.
    expect(screen.queryByText(/patient is .*or older/i)).not.toBeInTheDocument();

    const start = getWordChunk("aged");
    const middle = getWordChunk("40");
    const end = getWordChunk("over");
    await user.pointer([
      { keys: "[MouseLeft>]", target: start },
      { target: middle },
      { target: end },
      { keys: "[/MouseLeft]", target: end },
    ]);
    fireEvent.click(await screen.findByRole("button", { name: /confirm selection/i }));

    // A DEMOGRAPHIC row landed with the parsed operator/value -- not a
    // bare SNOMED "current age" concept, and no search popover opened.
    const ageLabel = await screen.findByText(/patient is 40 years or older/i);
    const ageRow = ageLabel.closest("[data-testid^='prerequisite-row-']");
    expect(ageRow).not.toBeNull();
    expect(
      screen.queryByPlaceholderText(/search for a symptom, sign, procedure/i),
    ).not.toBeInTheDocument();

    // The row expands into the same inline age editor the "+ Add age"
    // button opens, pre-filled with the parsed threshold.
    fireEvent.click(within(ageRow as HTMLElement).getByRole("button", { name: /^edit$/i }));
    expect(
      within(ageRow as HTMLElement).getByLabelText(/how to compare age/i),
    ).toHaveTextContent(/is at least/i);
    expect(within(ageRow as HTMLElement).getByLabelText(/lower bound/i)).toHaveValue("40");
  });
});
