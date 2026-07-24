/**
 * Live-render tests for StepPrerequisites -- Step 1 of the
 * highlight-to-build wizard ("What must ALWAYS be true?"). Covers
 * automatic fuzzy-matching of existing prerequisite leaves, the
 * captured-list Edit/Remove actions, forwarding a new highlighted
 * selection, the "No, nothing else" / "Highlight more text" question,
 * and both fallback states (no recommendation text; no clean anchor).
 *
 * Per the highlight-to-build wizard plan's `step-prerequisites` todo.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StepPrerequisites, {
  collectPrerequisiteLeaves,
  prerequisiteLabel,
} from "../HighlightWizard/StepPrerequisites";
import { assignNodeIds, type LogicNodeSeed } from "../treeOps";
import type { EditableLogicNode } from "../types";

const NG12_1_2_9_TEXT =
  "Consider non-urgent, direct access upper gastrointestinal endoscopy... " +
  "in people aged 55 or over with: treatment-resistant dyspepsia, or " +
  "upper abdominal pain with low haemoglobin levels, or raised platelet " +
  "count with any of the following: nausea, vomiting, weight loss, " +
  "reflux, dyspepsia, upper abdominal pain, or nausea or vomiting with " +
  "any of the following: weight loss, reflux, dyspepsia, upper " +
  "abdominal pain.";

function makeAgeLeaf(): EditableLogicNode {
  return assignNodeIds({
    kind: "DEMOGRAPHIC",
    field: "age",
    operator: ">=",
    value: 55,
    unit: "years",
  } as LogicNodeSeed);
}

function makeConceptLeaf(term: string, snomedId: string): EditableLogicNode {
  return assignNodeIds({
    kind: "CONCEPT",
    criterion: { snomed_concept_id: snomedId, preferred_term: term },
  } as LogicNodeSeed);
}

describe("StepPrerequisites: pure helpers", () => {
  it("collectPrerequisiteLeaves returns a bare leaf unchanged", () => {
    const leaf = makeAgeLeaf();
    expect(collectPrerequisiteLeaves([leaf])).toEqual([leaf]);
  });

  it("collectPrerequisiteLeaves recurses into a wrapping group", () => {
    const age = makeAgeLeaf();
    const concept = makeConceptLeaf("Smoker", "77176002");
    const group = assignNodeIds({
      kind: "AND",
      children: [age, concept],
    } as unknown as LogicNodeSeed);
    const leaves = collectPrerequisiteLeaves([group]);
    expect(leaves.map((l) => l.kind)).toEqual(["DEMOGRAPHIC", "CONCEPT"]);
  });

  it("prerequisiteLabel describes a DEMOGRAPHIC age leaf in plain English", () => {
    expect(prerequisiteLabel(makeAgeLeaf())).toBe(
      "Patient is 55 years or older",
    );
  });

  it("prerequisiteLabel describes a CONCEPT leaf in plain English", () => {
    expect(prerequisiteLabel(makeConceptLeaf("Smoker (finding)", "77176002"))).toBe(
      "Patient has smoker",
    );
  });
});

describe("StepPrerequisites: automatic fuzzy matching", () => {
  it("highlights the existing age check with no user action needed", () => {
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[makeAgeLeaf()]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    const confirmedChunks = document.querySelectorAll(
      '[data-highlight-kind="confirmed"]',
    );
    expect(confirmedChunks.length).toBeGreaterThan(0);
  });

  it("lists the age check under Captured so far", () => {
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[makeAgeLeaf()]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(screen.getByText("Patient is 55 years or older")).toBeInTheDocument();
  });

  it("shows a warning and 'place manually' action when nothing anchors a leaf", () => {
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[makeConceptLeaf("History of asbestos exposure", "999")]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(
      screen.getByText(/could not find matching words/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /tap to place it manually/i }),
    ).toBeInTheDocument();
  });
});

describe("StepPrerequisites: captured row actions", () => {
  it("calls onEdit with the node id and anchor when Edit is clicked", async () => {
    const user = userEvent.setup();
    const onEdit = jest.fn();
    const ageLeaf = makeAgeLeaf();
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[ageLeaf]}
        onEdit={onEdit}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onEdit.mock.calls[0][0]).toBe(ageLeaf.node_id);
  });

  it("routes Edit on a CONCEPT prerequisite to onEditConcept, not onEdit -- it already has a code, so it needs add/remove, not a single-pick override", async () => {
    const user = userEvent.setup();
    const onEdit = jest.fn();
    const onEditConcept = jest.fn();
    const conceptLeaf = makeConceptLeaf("Smoker", "77176002");
    render(
      <StepPrerequisites
        recommendationText="Consider urgent referral for smokers."
        prerequisites={[conceptLeaf]}
        onEdit={onEdit}
        onEditConcept={onEditConcept}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(onEditConcept).toHaveBeenCalledWith(conceptLeaf.node_id);
    expect(onEdit).not.toHaveBeenCalled();
  });

  it("still routes Edit on a DEMOGRAPHIC prerequisite (e.g. age) to onEdit -- it has no synonym set of its own", async () => {
    const user = userEvent.setup();
    const onEdit = jest.fn();
    const onEditConcept = jest.fn();
    const ageLeaf = makeAgeLeaf();
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[ageLeaf]}
        onEdit={onEdit}
        onEditConcept={onEditConcept}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(onEdit).toHaveBeenCalledWith(ageLeaf.node_id, expect.any(HTMLElement));
    expect(onEditConcept).not.toHaveBeenCalled();
  });

  it("calls onRemove with the node id when Remove is clicked", async () => {
    const user = userEvent.setup();
    const onRemove = jest.fn();
    const ageLeaf = makeAgeLeaf();
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[ageLeaf]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={onRemove}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /remove/i }));

    expect(onRemove).toHaveBeenCalledWith(ageLeaf.node_id);
  });
});

describe("StepPrerequisites: the always-true question", () => {
  it("calls onConfirmNoMore when 'No, nothing else' is clicked", async () => {
    const user = userEvent.setup();
    const onConfirmNoMore = jest.fn();
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
        onConfirmNoMore={onConfirmNoMore}
      />,
    );

    await user.click(screen.getByRole("button", { name: /no, nothing else/i }));

    expect(onConfirmNoMore).toHaveBeenCalledTimes(1);
  });

  it("dismisses the question when 'Highlight more text' is clicked", async () => {
    const user = userEvent.setup();
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(
      screen.getByRole("group", { name: /does anything else/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /highlight more text/i }));

    expect(
      screen.queryByRole("group", { name: /does anything else/i }),
    ).not.toBeInTheDocument();
  });

  it("brings the question back once a new prerequisite is captured, so the reviewer is never stranded without a way to proceed", async () => {
    // Reproduces the reported bug: highlight-dismiss the question, add a
    // new prerequisite (the wizard re-renders with one more row once the
    // add flow completes), then remove it again -- "No, nothing else"
    // must still be reachable throughout, since it is the ONLY action
    // that advances the wizard past this step (see index.tsx's
    // onConfirmNoMore -> CONFIRM_PREREQUISITES).
    const user = userEvent.setup();
    const ageLeaf = makeAgeLeaf();
    const { rerender } = render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /highlight more text/i }));
    expect(
      screen.queryByRole("group", { name: /does anything else/i }),
    ).not.toBeInTheDocument();

    // The reviewer's highlighted selection resolved to a new leaf --
    // the wizard re-renders this step with one more prerequisite.
    rerender(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[ageLeaf]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );
    expect(
      screen.getByRole("group", { name: /does anything else/i }),
    ).toBeInTheDocument();

    // Removing it again must not re-strand the reviewer.
    rerender(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );
    expect(
      screen.getByRole("group", { name: /does anything else/i }),
    ).toBeInTheDocument();
  });
});

describe("StepPrerequisites: forwarding a new selection", () => {
  it("calls onAddFromSelection when a new word chunk is confirmed", async () => {
    const user = userEvent.setup();
    const onAddFromSelection = jest.fn();
    render(
      <StepPrerequisites
        recommendationText="Consider urgent referral for smokers."
        prerequisites={[]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={onAddFromSelection}
      />,
    );

    const smokersChunk = screen.getByText("smokers.");
    await user.click(smokersChunk);
    await user.click(screen.getByRole("button", { name: /confirm selection/i }));

    expect(onAddFromSelection).toHaveBeenCalledTimes(1);
    expect(onAddFromSelection.mock.calls[0][0].text).toBe("smokers.");
  });
});

describe("StepPrerequisites: no recommendation text", () => {
  it("shows a fallback message and no highlight panel", () => {
    render(
      <StepPrerequisites
        recommendationText={null}
        prerequisites={[]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(
      /no guideline text to highlight/i,
    );
    expect(
      document.querySelector('[data-word-index]'),
    ).not.toBeInTheDocument();
  });
});
