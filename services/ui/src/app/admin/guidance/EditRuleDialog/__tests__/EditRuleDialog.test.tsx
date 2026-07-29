/**
 * EditRuleDialog component tests -- VT-LEO-AI-152.
 *
 * Verify reviewer-facing behaviour with Guided (highlight wizard):
 *   - Save is gated on a non-empty reason and a valid tree.
 *   - Saving sends action="edit" with an updates payload (name,
 *     logic_tree without node_ids).
 *   - Removing a prerequisite drops it from the persisted tree.
 *   - Empty rules start from the empty-state CTA.
 *   - Bare single-criterion trees surface as one prerequisite row.
 */

import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

import EditRuleDialog from "..";
import { goToEditorStep } from "./goToEditorStep";

const SAMPLE_RULE = {
  rule_id: "rule:NG12:abc",
  name: "Mesothelioma urgent X-ray",
  strength: "offer",
  guideline_id: "NG12",
  chapter_title: "Recommendations organised by site of cancer",
  recommendation_text:
    "Offer an urgent chest X-ray (to be done within 2 weeks) for mesothelioma.",
  logic_tree: {
    kind: "AND",
    children: [
      {
        kind: "DEMOGRAPHIC",
        field: "age",
        operator: ">=",
        value: 40,
        unit: "years",
      },
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

function mockSearch(hits: unknown[] = []) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).includes("/api/terminology/search")) {
      return Promise.resolve({
        ok: true,
        json: async () => hits,
        text: async () => JSON.stringify(hits),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => [], text: async () => "[]" } as Response);
  });
}



function fillReason(text: string) {
  goToEditorStep(3);
  fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
    target: { value: text },
  });
}

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
});

describe("EditRuleDialog", () => {
  it("Save button is disabled until a reason is entered", () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={onSave} />
    );
    const saveBtn = screen.getByRole("button", { name: /save your changes/i });
    expect(saveBtn).toBeDisabled();

    fillReason("Removed redundant cough criterion");
    expect(saveBtn).not.toBeDisabled();
  });

  it("calling Save fires onSave with stripped tree, name and reason", async () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={onSave} />
    );
    fillReason("Reviewed and tightened criteria");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const payload = onSave.mock.calls[0][0];
    expect(payload.reason).toBe("Reviewed and tightened criteria");
    expect(payload.name).toBe("Mesothelioma urgent X-ray");
    expect(payload.logic_tree.kind).toBe("AND");
    expect("node_id" in payload.logic_tree).toBe(false);
  });

  it("shows save API errors inside the dialog above the footer", () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
        saveError="Tree is not valid for save"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/tree is not valid for save/i);
  });

  it("removing a CONCEPT prerequisite drops it from the saved tree", async () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={onSave} />
    );

    expect(screen.getByTestId("highlight-wizard")).toBeInTheDocument();
    const coughLabel = screen.getByText(/patient has cough/i);
    const coughRow = coughLabel.closest("[data-testid^='prerequisite-row-']");
    expect(coughRow).not.toBeNull();
    fireEvent.click(
      within(coughRow as HTMLElement).getByRole("button", { name: /remove/i }),
    );

    fillReason("Cough was redundant with the OR group");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const tree = onSave.mock.calls[0][0].logic_tree;
    const kinds = (tree.children as Array<{ kind: string }>).map((c) => c.kind);
    expect(kinds).not.toContain("CONCEPT");
  });

  it("opens the highlight wizard for a rule that already has a logic tree", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={() => {}} />
    );
    expect(screen.getByTestId("highlight-wizard")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /what must always be true/i }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("logic-tree-editor")).not.toBeInTheDocument();
  });

  it("toggles fullscreen mode via the title-bar button", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={() => {}} />
    );
    expect(
      screen.getByRole("button", { name: /use the full screen/i }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /use the full screen/i }));
    expect(
      screen.getByRole("button", { name: /shrink to a window/i }),
    ).toBeInTheDocument();
  });

  it("uses plain-English copy throughout the dialog (health-literacy gate)", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={() => {}} />
    );
    expect(
      screen.getByRole("heading", { name: /change this rule/i, level: 2 })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save your changes/i })
    ).toBeInTheDocument();
    // During Guided build steps the right column shows the NICE quote;
    // the live preview returns on dialog steps 2/3 and Guided Review.
    expect(
      screen.getByRole("region", { name: /nice guideline wording for this rule/i }),
    ).toBeInTheDocument();

    goToEditorStep(2);
    const preview = screen.getByRole("region", {
      name: /live preview of this rule/i,
    });
    expect(preview).toBeInTheDocument();
    expect(within(preview).getByText(/offer this test or referral/i)).toBeInTheDocument();
    expect(
      screen.getAllByLabelText(/short name for this rule/i)[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByLabelText(/what should the system suggest/i)[0],
    ).toBeInTheDocument();

    goToEditorStep(3);
    expect(
      screen.getByLabelText(/why are you changing this rule/i)
    ).toBeInTheDocument();
  });

  it("adds the first symptom to an empty rule via the empty-state search", async () => {
    mockSearch([
      {
        snomed_concept_id: "399208008",
        term: "Plain X-ray of chest",
        semantic_tag: "procedure",
      },
    ]);
    const emptyRule = {
      ...SAMPLE_RULE,
      // No guideline text -- empty-state CTA (wizard needs quote text).
      recommendation_text: "",
      logic_tree: { kind: "AND", children: [] },
    };
    render(
      <EditRuleDialog rule={emptyRule} open onClose={() => {}} onSave={() => {}} />
    );

    fireEvent.click(
      screen.getByRole("button", { name: /add the first symptom/i }),
    );

    const searchField = await screen.findByLabelText(/search clinical terms/i);
    fireEvent.change(searchField, { target: { value: "chest x" } });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Use Plain X-ray of chest$/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole("button", { name: /^Use Plain X-ray of chest$/i }),
    );

    await waitFor(() => {
      expect(screen.getByTestId("highlight-wizard")).toBeInTheDocument();
    });
    expect(screen.getByText(/patient has plain x-ray of chest/i)).toBeInTheDocument();
  });

  // Regression: NG12 1.2.8 bare leaf root must surface as one
  // prerequisite row, not an empty group.
  it("shows a bare single-criterion logic_tree (NG12 1.2.8 shape) as one prerequisite", () => {
    mockSearch();
    const bareLeafRule = {
      rule_id: "rule:NG12:v1:CH002:SEC001:R007:dee9d93f",
      name: "Rule: 1.2.8",
      strength: "consider",
      guideline_id: "NG12",
      recommendation_text:
        "1.2.8 Consider non-urgent, direct access upper gastrointestinal endoscopy to assess for stomach cancer in people with haematemesis. [2015]",
      logic_tree: {
        kind: "concept",
        node_id: "n1",
        criterion: {
          node_id: "n1",
          term: "haematemesis",
          snomed_concept_id: "8765009",
          preferred_term: "Hematemesis (disorder)",
          semantic_tag: "disorder",
        },
      },
    };
    render(
      <EditRuleDialog rule={bareLeafRule} open onClose={() => {}} onSave={() => {}} />,
    );

    expect(screen.getByTestId("highlight-wizard")).toBeInTheDocument();
    expect(screen.getByText(/hematemesis/i)).toBeInTheDocument();
    expect(screen.getAllByText(/hematemesis/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/nothing yet/i)).not.toBeInTheDocument();
  });
});
