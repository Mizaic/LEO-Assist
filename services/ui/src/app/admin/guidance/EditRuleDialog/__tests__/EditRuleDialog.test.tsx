/**
 * EditRuleDialog component tests -- VT-LEO-AI-152.
 *
 * Verify reviewer-facing behaviour:
 *   - Save is gated on a non-empty reason and a valid tree.
 *   - Saving sends action="edit" with an updates payload (name, strength,
 *     logic_tree without node_ids).
 *   - Removing a CONCEPT chip drops it from the persisted tree.
 *   - SNOMED search results swap the focused concept on click.
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

afterEach(() => {
  jest.restoreAllMocks();
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

    fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
      target: { value: "Removed redundant cough chip" },
    });
    expect(saveBtn).not.toBeDisabled();
  });

  it("calling Save fires onSave with stripped tree, name, strength and reason", async () => {
    mockSearch();
    const onSave = jest.fn();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={onSave} />
    );
    fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
      target: { value: "Reviewed and tightened criteria" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    const payload = onSave.mock.calls[0][0];
    expect(payload.reason).toBe("Reviewed and tightened criteria");
    expect(payload.name).toBe("Mesothelioma urgent X-ray");
    expect(payload.strength).toBe("offer");
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

    fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
      target: { value: "Cough was redundant with the OR group" },
    });
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

    fireEvent.change(screen.getByLabelText(/why are you changing this rule/i), {
      target: { value: "Swapped cough for fatigue per chest team feedback" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    const tree = onSave.mock.calls[0][0].logic_tree;
    const concept = (tree.children as Array<{ kind: string; criterion?: { snomed_concept_id: string } }>).find(
      (c) => c.kind === "CONCEPT"
    );
    expect(concept?.criterion?.snomed_concept_id).toBe("84229001");
  });

  it("shows the search panel as a slim rail when idle and expands it on click", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={() => {}} />
    );
    // Idle state: rail is shown, search field is not.
    const rail = screen.getByRole("button", {
      name: /open search to pick a clinical term/i,
    });
    expect(rail).toBeInTheDocument();
    expect(screen.queryByLabelText(/search clinical terms/i)).not.toBeInTheDocument();

    fireEvent.click(rail);

    // Pinned state: search field is shown, rail is gone.
    expect(screen.getByLabelText(/search clinical terms/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /open search to pick a clinical term/i }),
    ).not.toBeInTheDocument();
  });

  it("expands the search panel automatically when a chip is clicked", () => {
    mockSearch();
    render(
      <EditRuleDialog rule={SAMPLE_RULE} open onClose={() => {}} onSave={() => {}} />
    );
    expect(screen.queryByLabelText(/search clinical terms/i)).not.toBeInTheDocument();

    const chip = screen.getByRole("button", {
      name: /^Cough\. Click to swap, X to remove\.$/i,
    });
    fireEvent.click(chip);

    expect(screen.getByLabelText(/search clinical terms/i)).toBeInTheDocument();
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
    expect(screen.getByLabelText(/short name for this rule/i)).toBeInTheDocument();
    expect(
      screen.getByLabelText(/what should the system suggest/i)
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/why are you changing this rule/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save your changes/i })
    ).toBeInTheDocument();
    // The summary card explains the rule in plain English; the duplicate
    // "What the patient must have" overline above the editor was removed
    // in favour of letting the SummaryCard + pathway header speak for the
    // editor.
    expect(
      screen.getByRole("region", { name: /plain english summary of this rule/i })
    ).toBeInTheDocument();
    // Strength dropdown shows the friendly label, not the raw "offer" code.
    expect(screen.getByText(/offer this test or referral/i)).toBeInTheDocument();
  });
});
