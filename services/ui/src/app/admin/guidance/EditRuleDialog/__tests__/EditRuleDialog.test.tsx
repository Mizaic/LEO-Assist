/**
 * EditRuleDialog component tests -- VT-LEO-AI-152.
 *
 * Verify reviewer-facing behaviour:
 *   - Save is gated on a non-empty reason and a valid tree.
 *   - Saving sends action="edit" with an updates payload (name,
 *     logic_tree without node_ids).
 *   - Removing a CONCEPT chip drops it from the persisted tree.
 *   - SNOMED search results swap the focused concept on click.
 */

import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  waitForElementToBeRemoved,
} from "@testing-library/react";

import EditRuleDialog from "..";

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

/**
 * The widescreen editor splits the form across three steps. Tests
 * that need fields from a later step (action chip on step 2, reason
 * on step 3) navigate via the horizontal stepper across the top of
 * the dialog.
 */
function goToStep(stepNumber: 1 | 2 | 3) {
  const stepper = screen.getAllByRole("button", {
    name: new RegExp(`^Step ${stepNumber} of 3`, "i"),
  });
  fireEvent.click(stepper[0]);
}

function fillReason(text: string) {
  goToStep(3);
  fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
    target: { value: text },
  });
}

const VIEW_MODE_STORAGE_KEY = "leo.editRuleDialog.viewMode";

beforeEach(() => {
  // Guided is now the default view, but these tests exercise the
  // chip-based canvas directly (pill aria-labels, chip-anchored
  // search popover) -- force Simple so they keep testing that
  // canvas rather than the highlight-to-build wizard.
  window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, "simple");
});

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

    fillReason("Removed redundant cough chip");
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

  it("removing a CONCEPT chip drops it from the saved tree", async () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={onSave} />
    );

    // The chip aria-label is in plain English with the SNOMED suffix stripped.
    const chip = screen.getByRole("button", {
      name: /^Cough\. Click to swap, X to remove\.$/i,
    });
    const deleteIcon = chip.querySelector(
      "svg[data-testid='CancelIcon'], .MuiChip-deleteIcon"
    );
    expect(deleteIcon).not.toBeNull();
    fireEvent.click(deleteIcon as Element);

    fillReason("Cough was redundant with the OR group");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const tree = onSave.mock.calls[0][0].logic_tree;
    const kinds = (tree.children as Array<{ kind: string }>).map((c) => c.kind);
    expect(kinds).not.toContain("CONCEPT");
  });

  it("clicking a search hit replaces the focused concept", async () => {
    mockSearch([
      {
        snomed_concept_id: "84229001",
        term: "Fatigue (finding)",
        semantic_tag: "finding",
      },
    ]);
    const onSave = jest.fn();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={onSave} />
    );

    const conceptChip = screen.getByRole("button", {
      name: /^Cough\. Click to swap, X to remove\.$/i,
    });
    fireEvent.click(conceptChip);

    // The "Use this" button now carries the friendly term in its aria-label.
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Use Fatigue$/i })
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /^Use Fatigue$/i }));

    fillReason("Swapped cough for fatigue per chest team feedback");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const tree = onSave.mock.calls[0][0].logic_tree;
    const concept = (tree.children as Array<{ kind: string; criterion?: { snomed_concept_id: string } }>).find(
      (c) => c.kind === "CONCEPT"
    );
    expect(concept?.criterion?.snomed_concept_id).toBe("84229001");
  });

  it("does not render a permanent search column; search appears as a chip-anchored popover", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={() => {}} />
    );
    expect(
      screen.queryByRole("button", {
        name: /open search to pick a clinical term/i,
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/search clinical terms/i)).not.toBeInTheDocument();
  });

  it("opens the chip-anchored search popover when a chip is clicked, and closes via the X", async () => {
    mockSearch();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={() => {}} />
    );
    expect(screen.queryByLabelText(/search clinical terms/i)).not.toBeInTheDocument();

    const chip = screen.getByRole("button", {
      name: /^Cough\. Click to swap, X to remove\.$/i,
    });
    fireEvent.click(chip);

    const searchField = await screen.findByLabelText(/search clinical terms/i);
    expect(searchField).toBeInTheDocument();
    const closeBtn = screen.getByRole("button", { name: /^close search$/i });
    fireEvent.click(closeBtn);
    // The popover plays an exit transition before unmounting, so wait
    // for the search field to leave the DOM rather than asserting
    // synchronously.
    await waitForElementToBeRemoved(() =>
      screen.queryByLabelText(/search clinical terms/i),
    );
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
    // Phase 3: the always-visible LivePreviewPane sits to the right of
    // the canvas and explains the rule in plain English on every step.
    // The previous LivePreviewBanner + drawer toggle was deleted.
    expect(
      screen.getByRole("region", { name: /live preview of this rule/i }),
    ).toBeInTheDocument();
    // The pane shows the friendly strength label even before the
    // reviewer opens step 2.
    expect(screen.getByText(/offer this test or referral/i)).toBeInTheDocument();

    // Step 2 owns the short-name and strength fields.
    goToStep(2);
    expect(
      screen.getAllByLabelText(/short name for this rule/i)[0],
    ).toBeInTheDocument();
    expect(
      screen.getAllByLabelText(/what should the system suggest/i)[0],
    ).toBeInTheDocument();

    // Step 3 owns the reason field.
    goToStep(3);
    expect(
      screen.getByLabelText(/why are you changing this rule/i)
    ).toBeInTheDocument();
  });

  it("adds the first symptom to an empty rule via the chip search popover", async () => {
    mockSearch([
      {
        snomed_concept_id: "399208008",
        term: "Plain X-ray of chest",
        semantic_tag: "procedure",
      },
    ]);
    const emptyRule = {
      ...SAMPLE_RULE,
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
      expect(
        screen.queryByText(/this rule has no symptoms yet/i),
      ).not.toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", {
        name: /^Plain X-ray of chest\. Click to swap, X to remove\.$/i,
      }),
    ).toBeInTheDocument();
  });

  // Regression: NG12 1.2.8 ("...in people with haematemesis") persists
  // in Neo4j as a BARE leaf root -- {"kind": "concept", "criterion":
  // {...}} -- with no AND wrapper, because the raw AI-extraction
  // pipeline never wraps a single-criterion recommendation. Before the
  // fix, LogicTreeEditor/GroupBody and SentenceEditor/GroupSentence
  // both unconditionally treated the root as a GROUP (reading
  // node.children, rendering the kind Select, etc.), so a bare leaf
  // root rendered as an empty "nothing yet" group -- the one real
  // criterion was invisible. A reviewer who then used "+ add another
  // symptom" to add the very symptom the guideline already required
  // ended up with it TWICE, because the add flow's own wrapRootInAnd
  // finally surfaced the hidden original alongside the new pick.
  it("shows a bare single-criterion logic_tree (NG12 1.2.8 shape) as one pill, not an empty group", () => {
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

    // The one stored criterion renders as a single removable pill...
    expect(
      screen.getByRole("button", {
        name: /^Hematemesis\. Click to swap, X to remove\.$/i,
      }),
    ).toBeInTheDocument();
    // ...exactly once...
    expect(
      screen.getAllByRole("button", { name: /^Hematemesis\./i }),
    ).toHaveLength(1);
    // ...and the canvas never claims the (non-empty) group is empty.
    expect(screen.queryByText(/nothing yet/i)).not.toBeInTheDocument();
  });
});
