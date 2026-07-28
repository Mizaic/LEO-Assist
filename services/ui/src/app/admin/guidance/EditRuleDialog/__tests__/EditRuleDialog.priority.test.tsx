/**
 * EditRuleDialog clinical priority editing tests.
 *
 * Verifies:
 *   - PriorityPanel renders the loaded action_priority / due_days.
 *   - Changing priority marks the field dirty and includes it in save.
 *   - Untouched priority is omitted from the save payload.
 *   - Selecting Routine clears due-days.
 */

import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";

import EditRuleDialog from "..";

async function selectPriority(optionText: string) {
  const input = screen.getByLabelText(/clinical priority for this rule/i);
  const combobox = input.closest('[role="combobox"]') ?? input;
  fireEvent.mouseDown(combobox);
  const listbox = await screen.findByRole("listbox");
  fireEvent.click(within(listbox).getByText(optionText));
}

const SAMPLE_RULE = {
  rule_id: "rule:NG12:1.2.10",
  name: "Rule: 1.2.10",
  strength: "consider",
  guideline_id: "NG12",
  chapter_title: "Recommendations organised by site of cancer",
  recommendation_text:
    "Consider an urgent, direct access ultrasound scan (to be done within 2 weeks).",
  logic_tree: {
    kind: "AND",
    children: [
      {
        kind: "CONCEPT",
        criterion: {
          snomed_concept_id: "300344005",
          preferred_term: "Gallbladder enlarged (finding)",
          semantic_tag: "finding",
        },
      },
    ],
  },
  actions: [
    {
      criterion: {
        snomed_concept_id: "169250003",
        preferred_term: "Ultrasound scan of gallbladder (procedure)",
        semantic_tag: "procedure",
        term: "ultrasound scan",
      },
      strength: "consider",
    },
  ],
  action_priority: "2ww" as const,
  action_due_days: 14,
};

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

describe("EditRuleDialog clinical priority", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("renders the loaded priority and due days on step 2", () => {
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={jest.fn()}
        onSave={jest.fn()}
      />,
    );
    goToStep(2);
    expect(
      screen.getByLabelText(/clinical priority for this rule/i),
    ).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("14"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(/clinical priority: 2 week wait/i),
    ).toBeInTheDocument();
  });

  it("always includes the current priority on save so remounts cannot drop it", () => {
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={jest.fn()}
        onSave={onSave}
      />,
    );
    fillReason("Tightened the criteria only");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
    const payload = onSave.mock.calls[0][0];
    // SAMPLE_RULE loads as 2WW / 14 days -- persist what the form shows.
    expect(payload.priority).toBe("2ww");
    expect(payload.due_days).toBe(14);
  });

  it("includes priority and due_days in save after a change", async () => {
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={jest.fn()}
        onSave={onSave}
      />,
    );
    goToStep(2);
    await selectPriority("Urgent");
    fireEvent.change(screen.getByLabelText(/due within how many days/i), {
      target: { value: "7" },
    });
    fillReason("Corrected priority to urgent 1 week");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
    const payload = onSave.mock.calls[0][0];
    expect(payload.priority).toBe("urgent");
    expect(payload.due_days).toBe(7);
  });

  it("clears due days when Routine is selected", async () => {
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={jest.fn()}
        onSave={onSave}
      />,
    );
    goToStep(2);
    await selectPriority("Routine");
    expect(screen.getByLabelText(/due within how many days/i)).toBeDisabled();
    fillReason("Downgraded to routine after review");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
    const payload = onSave.mock.calls[0][0];
    expect(payload.priority).toBe("routine");
    expect(payload.due_days).toBeNull();
  });

  it("offers Immediate specialist assessment and defaults due days to 0", async () => {
    const onSave = jest.fn();
    render(
      <EditRuleDialog
        rule={SAMPLE_RULE}
        open
        onClose={jest.fn()}
        onSave={onSave}
      />,
    );
    goToStep(2);
    await selectPriority("Immediate specialist assessment");
    expect(screen.getByDisplayValue("0")).toBeInTheDocument();
    fillReason("NG12 immediate specialist assessment for leukaemia");
    fireEvent.click(screen.getByRole("button", { name: /save your changes/i }));
    expect(onSave).toHaveBeenCalledTimes(1);
    const payload = onSave.mock.calls[0][0];
    expect(payload.priority).toBe("immediate");
    expect(payload.due_days).toBe(0);
  });
});
