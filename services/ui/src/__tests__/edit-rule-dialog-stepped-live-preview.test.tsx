/**
 * LivePreviewPane reactivity while editing a rule -- VT-511-TC-003/004.
 *
 * Guided is the only editor. The right column shows the NICE quote
 * during wizard build steps on dialog step 1; live preview returns on
 * dialog steps 2/3 (and Guided Review). These tests mutate via the
 * Guided prerequisite Remove control, then assert the preview.
 */

import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import EditRuleDialog from "../app/admin/guidance/EditRuleDialog";

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

function goToStep(n: 1 | 2 | 3) {
  fireEvent.click(
    screen.getAllByRole("button", { name: new RegExp(`^Step ${n} of 3`, "i") })[0],
  );
}

function removeCoughPrerequisite() {
  const coughLabel = screen.getByText(/patient has cough/i);
  const coughRow = coughLabel.closest("[data-testid^='prerequisite-row-']");
  expect(coughRow).not.toBeNull();
  fireEvent.click(within(coughRow as HTMLElement).getByRole("button", { name: /^remove$/i }));
}

afterEach(() => {
  jest.restoreAllMocks();
  window.localStorage.clear();
});

describe("LivePreviewPane reactivity -- VT-511-TC-003", () => {
  it("updates the preview sentence when a prerequisite is removed", async () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    removeCoughPrerequisite();

    goToStep(2);
    const preview = screen.getByRole("region", {
      name: /live preview of this rule/i,
    });
    await waitFor(() => {
      expect(within(preview).queryByText(/cough/i)).not.toBeInTheDocument();
    });
    expect(within(preview).getByText(/40 years or older/i)).toBeInTheDocument();
  });
});

describe("LivePreviewPane Before/After on step 4 -- VT-511-TC-004", () => {
  it("swaps to a Before/After variant with two side-by-side summaries on step 3", async () => {
    mockSearch();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    removeCoughPrerequisite();

    goToStep(3);
    const beforeAfter = screen.getByRole("region", {
      name: /before and after preview of this rule/i,
    });
    expect(beforeAfter).toBeInTheDocument();
    expect(within(beforeAfter).getByText(/before your change/i)).toBeInTheDocument();
    expect(within(beforeAfter).getByText(/after your change/i)).toBeInTheDocument();
    const beforeColumn = within(beforeAfter).getByText(
      /before your change/i,
    ).parentElement!;
    expect(within(beforeColumn).getByText(/cough/i)).toBeInTheDocument();
    const afterColumn = within(beforeAfter).getByText(
      /after your change/i,
    ).parentElement!;
    expect(within(afterColumn).queryByText(/cough/i)).not.toBeInTheDocument();
  });
});
