/**
 * VT-LEO-AI-511 -- TC-003 (live preview reactivity) and TC-004 (step 4
 * Before / After variant).
 */

import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

import EditRuleDialog from "../app/admin/guidance/EditRuleDialog";

const SAMPLE_RULE = {
  rule_id: "rule:NG12:abc",
  name: "Lung red flags",
  strength: "offer",
  guideline_id: "NG12",
  chapter_title: "Lung and pleural cancers",
  recommendation_text: "Offer urgent chest X-ray.",
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

function goToStep(n: 1 | 2 | 3 | 4) {
  fireEvent.click(
    screen.getAllByRole("button", { name: new RegExp(`^Step ${n} of 4`, "i") })[0],
  );
}

afterEach(() => {
  jest.restoreAllMocks();
});

describe("LivePreviewPane reactivity -- VT-511-TC-003", () => {
  it("updates the preview sentence when the focused chip is swapped (no network call beyond search)", async () => {
    mockSearch([
      {
        snomed_concept_id: "84229001",
        term: "Fatigue (finding)",
        semantic_tag: "finding",
      },
    ]);
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    const preview = screen.getByRole("region", {
      name: /live preview of this rule/i,
    });
    expect(within(preview).getByText(/cough/i)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: /^Cough\. Click to swap, X to remove\.$/i,
      }),
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Use Fatigue$/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /^Use Fatigue$/i }));

    // The preview sentence reflects the new concept on the next render.
    await waitFor(() => {
      const livePreview = screen.getByRole("region", {
        name: /live preview of this rule/i,
      });
      expect(within(livePreview).getByText(/fatigue/i)).toBeInTheDocument();
      expect(within(livePreview).queryByText(/cough/i)).not.toBeInTheDocument();
    });
  });
});

describe("LivePreviewPane Before/After on step 4 -- VT-511-TC-004", () => {
  it("swaps to a Before/After variant with two side-by-side summaries on step 4", async () => {
    mockSearch([
      {
        snomed_concept_id: "84229001",
        term: "Fatigue (finding)",
        semantic_tag: "finding",
      },
    ]);
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={() => {}}
        onSave={() => {}}
      />,
    );

    // Edit the tree: swap Cough -> Fatigue.
    fireEvent.click(
      screen.getByRole("button", {
        name: /^Cough\. Click to swap, X to remove\.$/i,
      }),
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^Use Fatigue$/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /^Use Fatigue$/i }));

    // Jump to step 4. The preview swaps to the Before/After region.
    goToStep(4);
    const beforeAfter = screen.getByRole("region", {
      name: /before and after preview of this rule/i,
    });
    expect(beforeAfter).toBeInTheDocument();
    expect(within(beforeAfter).getByText(/before your change/i)).toBeInTheDocument();
    expect(within(beforeAfter).getByText(/after your change/i)).toBeInTheDocument();
    // "Before" still mentions Cough (the original criterion).
    const beforeColumn = within(beforeAfter).getByText(
      /before your change/i,
    ).parentElement!;
    expect(within(beforeColumn).getByText(/cough/i)).toBeInTheDocument();
    // "After" mentions Fatigue (the edited criterion).
    const afterColumn = within(beforeAfter).getByText(
      /after your change/i,
    ).parentElement!;
    expect(within(afterColumn).getByText(/fatigue/i)).toBeInTheDocument();
  });
});
