/**
 * EditRuleDialog action editing tests -- VT-LEO-AI-168 (DI-LEO-AI-170).
 *
 * Verifies:
 *   - The recommended SNOMED procedure ("action") is rendered as a
 *     chip with a tooltip including the SNOMED code.
 *   - Clicking the action chip targets the right-hand search panel.
 *   - Picking a search hit while the action is targeted updates the
 *     ``action`` field in the save payload (and the action panel).
 *   - The save payload omits ``action`` when the reviewer never touched
 *     it, so the server preserves the predecessor's actionJson
 *     unchanged.
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

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
        kind: "CONCEPT",
        criterion: {
          snomed_concept_id: "49727002",
          preferred_term: "Cough (finding)",
          semantic_tag: "finding",
        },
      },
    ],
  },
  action: {
    snomed_concept_id: "168731009",
    preferred_term: "Plain chest X-ray (procedure)",
    semantic_tag: "procedure",
    term: "chest X-ray",
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
    return Promise.resolve({
      ok: true,
      json: async () => [],
      text: async () => "[]",
    } as Response);
  });
}

/**
 * The widescreen editor splits the form across four steps. The action
 * chip lives on step 2 ("What should the system suggest?") and the
 * reason field lives on step 4 ("Save your change").
 */
function goToStep(stepNumber: 1 | 2 | 3 | 4) {
  const rail = screen.getAllByRole("button", {
    name: new RegExp(`^Step ${stepNumber} of 4`, "i"),
  });
  fireEvent.click(rail[0]);
}

function fillReason(text: string) {
  goToStep(4);
  fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
    target: { value: text },
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("EditRuleDialog -- action editing (VT-LEO-AI-168)", () => {
  // VT-168-TC-005
  it("renders the action chip with the friendly label and SNOMED tooltip", () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    goToStep(2);
    const region = screen.getByRole("region", {
      name: /recommended procedure for this rule/i,
    });
    expect(region).toBeInTheDocument();

    const chip = screen.getByRole("button", {
      name: /plain chest x-ray\. click to pick a different procedure\./i,
    });
    expect(chip).toBeInTheDocument();
    // Tooltip carries the SNOMED code.
    expect(chip).toHaveAttribute(
      "aria-label",
      expect.stringContaining("Plain chest X-ray"),
    );
  });

  it("shows an empty-state when the rule has no action coded", () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={{ ...SAMPLE_RULE, action: null }}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );
    goToStep(2);
    expect(
      screen.getByRole("button", {
        name: /no procedure picked yet\. click to pick a different procedure\./i,
      }),
    ).toBeInTheDocument();
  });

  // VT-168-TC-006
  it("picking a search hit while the action chip is selected updates the saved action", async () => {
    mockSearch([
      {
        snomed_concept_id: "16310003",
        term: "Diagnostic ultrasound (procedure)",
        semantic_tag: "procedure",
      },
    ]);
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={onSave}
      />,
    );

    goToStep(2);
    fireEvent.click(
      screen.getByRole("button", {
        name: /plain chest x-ray\. click to pick a different procedure\./i,
      }),
    );

    // Search panel heading switches to the action variant.
    expect(
      screen.getByRole("heading", { name: /swap the recommended procedure/i }),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Use Diagnostic ultrasound$/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole("button", { name: /^Use Diagnostic ultrasound$/i }),
    );

    // Action chip refreshes with the new label.
    expect(
      screen.getByRole("button", {
        name: /diagnostic ultrasound\. click to pick a different procedure\./i,
      }),
    ).toBeInTheDocument();

    fillReason("Switched to ultrasound per chest team feedback");
    fireEvent.click(
      screen.getByRole("button", { name: /save your changes/i }),
    );
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const payload = onSave.mock.calls[0][0];
    expect(payload.action).toBeDefined();
    expect(payload.action.snomed_concept_id).toBe("16310003");
    expect(payload.action.preferred_term).toBe(
      "Diagnostic ultrasound (procedure)",
    );
    expect(payload.action.semantic_tag).toBe("procedure");
  });

  it("omits action from the save payload when the reviewer never touched it", async () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={onSave}
      />,
    );

    fillReason("Tightened criteria only");
    fireEvent.click(
      screen.getByRole("button", { name: /save your changes/i }),
    );
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const payload = onSave.mock.calls[0][0];
    expect(payload.action).toBeUndefined();
  });
});
