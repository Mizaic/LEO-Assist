/**
 * EditRuleDialog multi-action editing tests -- VT-LEO-AI-168 (DI-42246DA7).
 *
 * Verifies:
 *   - A rule with one recommended procedure renders it as a single row
 *     (SNOMED chip + strength Select), with the delete icon disabled.
 *   - "Add another procedure" appends a second, independently-editable
 *     row with its own strength.
 *   - Removing a row is allowed once there are 2+ rows; removing the
 *     last remaining row is blocked (disabled with a tooltip / inline
 *     hint), never producing an empty ``actions`` array.
 *   - Picking a search hit while a row is targeted updates only that
 *     row's criterion.
 *   - The save payload carries the full ``actions`` array once any row
 *     has been touched, and omits it entirely when the reviewer never
 *     touched the procedures.
 */

import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import EditRuleDialog from "..";

/** MUI Select is not a native <select>; open its listbox and click an option. */
async function selectStrength(labelPattern: RegExp, optionText: string) {
  const input = screen.getByLabelText(labelPattern);
  const combobox = input.closest('[role="combobox"]') ?? input;
  fireEvent.mouseDown(combobox);
  const listbox = await screen.findByRole("listbox");
  fireEvent.click(within(listbox).getByText(optionText));
}

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
  actions: [
    {
      criterion: {
        snomed_concept_id: "168731009",
        preferred_term: "Plain chest X-ray (procedure)",
        semantic_tag: "procedure",
        term: "chest X-ray",
      },
      strength: "offer",
    },
  ],
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
 * The widescreen editor splits the form across three steps. The
 * recommended-procedures panel lives on step 2 ("What should the
 * system suggest?") and the reason field lives on step 3 ("Save your
 * change").
 */
function goToStep(stepNumber: 1 | 2 | 3) {
  const rail = screen.getAllByRole("button", {
    name: new RegExp(`^Step ${stepNumber} of 3`, "i"),
  });
  fireEvent.click(rail[0]);
}

function fillReason(text: string) {
  goToStep(3);
  fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
    target: { value: text },
  });
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("EditRuleDialog -- recommended procedures (VT-LEO-AI-168)", () => {
  it("renders a single action row with the friendly label and SNOMED tooltip, delete disabled", () => {
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
      name: /recommended procedures for this rule/i,
    });
    expect(region).toBeInTheDocument();

    const chip = screen.getByRole("button", {
      name: /plain chest x-ray\. click to pick a different procedure\./i,
    });
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveAttribute(
      "aria-label",
      expect.stringContaining("Plain chest X-ray"),
    );

    const removeButton = screen.getByRole("button", {
      name: /remove procedure 1/i,
    });
    expect(removeButton).toBeDisabled();
  });

  it("shows an empty-state row when the rule has no action coded", () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={{ ...SAMPLE_RULE, actions: [] }}
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

  it("adding another procedure appends an independently-editable second row", async () => {
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

    fireEvent.click(
      screen.getByRole("button", { name: /add another recommended procedure/i }),
    );

    expect(
      screen.getByRole("button", {
        name: /no procedure picked yet\. click to pick a different procedure\./i,
      }),
    ).toBeInTheDocument();
    // Both rows can now have their strengths set independently.
    expect(
      screen.getByLabelText(/what should the system suggest for procedure 1/i),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/what should the system suggest for procedure 2/i),
    ).toBeInTheDocument();
    // With 2 rows, both delete icons are enabled.
    expect(screen.getByRole("button", { name: /remove procedure 1/i })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: /remove procedure 2/i })).not.toBeDisabled();
  });

  it("removing a row is allowed with 2+ rows; removing the last remaining row is blocked", async () => {
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

    fireEvent.click(
      screen.getByRole("button", { name: /add another recommended procedure/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: /remove procedure 2/i }));

    // Back down to a single row; its delete icon is disabled again.
    expect(
      screen.queryByLabelText(/what should the system suggest for procedure 2/i),
    ).not.toBeInTheDocument();
    const removeButton = screen.getByRole("button", { name: /remove procedure 1/i });
    expect(removeButton).toBeDisabled();
  });

  it("picking a search hit while a row is selected updates only that row's saved procedure", async () => {
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
    expect(payload.actions).toBeDefined();
    expect(payload.actions).toHaveLength(1);
    expect(payload.actions[0].criterion.snomed_concept_id).toBe("16310003");
    expect(payload.actions[0].criterion.preferred_term).toBe(
      "Diagnostic ultrasound (procedure)",
    );
    expect(payload.actions[0].criterion.semantic_tag).toBe("procedure");
    expect(payload.actions[0].strength).toBe("offer");
  });

  it("adding a second procedure with a different strength and saving persists both", async () => {
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
      screen.getByRole("button", { name: /add another recommended procedure/i }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: /no procedure picked yet\. click to pick a different procedure\./i,
      }),
    );
    fireEvent.change(screen.getByLabelText(/search clinical terms/i), {
      target: { value: "ultrasound" },
    });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Use Diagnostic ultrasound$/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole("button", { name: /^Use Diagnostic ultrasound$/i }),
    );

    await selectStrength(
      /what should the system suggest for procedure 2/i,
      "Refer urgently",
    );

    fillReason("Added a second procedure at a different strength");
    fireEvent.click(
      screen.getByRole("button", { name: /save your changes/i }),
    );
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const payload = onSave.mock.calls[0][0];
    expect(payload.actions).toHaveLength(2);
    expect(payload.actions[0].strength).toBe("offer");
    expect(payload.actions[1].criterion.snomed_concept_id).toBe("16310003");
    expect(payload.actions[1].strength).toBe("refer");
  });

  it("omits actions from the save payload when the reviewer never touched them", async () => {
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
    expect(payload.actions).toBeUndefined();
  });

  it("renders without crash when actions[] uses flat API shape (no criterion wrapper)", () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={{
          ...SAMPLE_RULE,
          actions: [
            {
              snomed_concept_id: "168731009",
              preferred_term: "Plain chest X-ray (procedure)",
              semantic_tag: "procedure",
              term: "chest X-ray",
              strength: "offer",
            } as unknown as (typeof SAMPLE_RULE.actions)[0],
          ],
        }}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    goToStep(2);
    expect(
      screen.getByRole("button", {
        name: /plain chest x-ray\. click to pick a different procedure\./i,
      }),
    ).toBeInTheDocument();
  });
});
