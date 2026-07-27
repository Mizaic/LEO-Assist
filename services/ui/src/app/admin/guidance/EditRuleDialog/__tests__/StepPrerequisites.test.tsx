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

function makeObservationLeaf(): EditableLogicNode {
  return assignNodeIds({
    kind: "OBSERVATION",
    observation: {
      observable_id: "365632008",
      observable_term: "Platelet count",
      operator: ">=",
      value: 400,
      unit: "10*9/L",
    },
  } as unknown as LogicNodeSeed);
}

function makeMultiSeedConceptLeaf(terms: string[]): EditableLogicNode {
  return assignNodeIds({
    kind: "CONCEPT",
    criterion: {
      snomed_concept_id: "1",
      preferred_term: terms[0],
      seeds: terms.map((term, i) => ({
        snomed_concept_id: String(i + 1),
        preferred_term: term,
      })),
    },
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
        onUpdate={jest.fn()}
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
        onUpdate={jest.fn()}
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
        onUpdate={jest.fn()}
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

describe("StepPrerequisites: multi-seed CONCEPT rows render as chips", () => {
  it("shows each seed as its own chip instead of one packed sentence", () => {
    const leaf = makeMultiSeedConceptLeaf([
      "Abnormal blood test",
      "Hemoglobin below reference range",
      "Raised ESR",
    ]);
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[leaf]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(screen.getByText("Abnormal blood test")).toBeInTheDocument();
    expect(screen.getByText("Hemoglobin below reference range")).toBeInTheDocument();
    expect(screen.getByText("Raised ESR")).toBeInTheDocument();
    expect(screen.queryByText(/one of: abnormal blood test,/i)).not.toBeInTheDocument();
  });

  it("collapses a long seed list behind '+N more' and expands it on click", async () => {
    const user = userEvent.setup();
    const leaf = makeMultiSeedConceptLeaf([
      "Abnormal blood test",
      "Hemoglobin below reference range",
      "Hematocrit below reference range",
      "Serum calcium below reference range",
      "Plasma viscosity above reference range",
      "Erythrocyte sedimentation rate above reference range",
    ]);
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[leaf]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(
      screen.queryByText("Erythrocyte sedimentation rate above reference range"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("+2 more")).toBeInTheDocument();

    await user.click(screen.getByText("+2 more"));

    expect(
      screen.getByText("Erythrocyte sedimentation rate above reference range"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show fewer/i })).toBeInTheDocument();
  });

  it("still renders a plain sentence for a single-seed CONCEPT row", () => {
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[makeConceptLeaf("Smoker", "77176002")]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(screen.getByText("Patient has smoker")).toBeInTheDocument();
  });
});

describe("StepPrerequisites: captured row actions", () => {
  it("calls onEdit with the node id and anchor when Edit is clicked on an OBSERVATION row", async () => {
    const user = userEvent.setup();
    const onEdit = jest.fn();
    const observationLeaf = makeObservationLeaf();
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[observationLeaf]}
        onEdit={onEdit}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /^(edit|tap to place it manually)$/i }));

    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onEdit.mock.calls[0][0]).toBe(observationLeaf.node_id);
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
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(onEditConcept).toHaveBeenCalledWith(conceptLeaf.node_id);
    expect(onEdit).not.toHaveBeenCalled();
  });

  it("expands an inline age editor on a DEMOGRAPHIC row instead of calling onEdit/onEditConcept -- it has no search swap or synonym set of its own", async () => {
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
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(screen.queryByLabelText(/how to compare age/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(onEdit).not.toHaveBeenCalled();
    expect(onEditConcept).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/how to compare age/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Done" })).toBeInTheDocument();
  });

  it("dispatches set_demographic through onUpdate when the inline age editor's operator changes", async () => {
    const user = userEvent.setup();
    const onUpdate = jest.fn();
    const ageLeaf = makeAgeLeaf();
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[ageLeaf]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={onUpdate}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByLabelText(/how to compare age/i));
    await user.click(await screen.findByRole("option", { name: /is at most/i }));

    expect(onUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "set_demographic",
        nodeId: ageLeaf.node_id,
        field: "age",
        operator: "<=",
        value: "55",
      }),
    );
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
        onUpdate={jest.fn()}
        onRemove={onRemove}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /remove/i }));

    expect(onRemove).toHaveBeenCalledWith(ageLeaf.node_id);
  });
});

describe("StepPrerequisites: invisible empty-group problems get their own row", () => {
  it("renders a problem row for an empty group even though it has no leaf of its own", () => {
    const emptyGroup = assignNodeIds({
      kind: "AND",
      children: [],
    } as unknown as LogicNodeSeed);
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[emptyGroup]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    // The empty group produces zero leaves, so this is the ONLY way
    // the reviewer can discover it exists at all.
    expect(screen.getByTestId(`wizard-problem-row-${emptyGroup.node_id}`)).toBeInTheDocument();
    expect(screen.getByText(/one of the groups is empty/i)).toBeInTheDocument();
  });

  it("removes the empty group via its own Remove it action", async () => {
    const user = userEvent.setup();
    const onRemove = jest.fn();
    const emptyGroup = assignNodeIds({
      kind: "AND",
      children: [],
    } as unknown as LogicNodeSeed);
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[emptyGroup]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={onRemove}
        onAddFromSelection={jest.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /remove this problem/i }));

    expect(onRemove).toHaveBeenCalledWith(emptyGroup.node_id);
  });

  it("does not double-report a leaf that already has its own captured row", () => {
    const ageLeaf = makeAgeLeaf();
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[ageLeaf]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(screen.queryByTestId(`wizard-problem-row-${ageLeaf.node_id}`)).not.toBeInTheDocument();
  });
});

describe("StepPrerequisites: adding a global age/sex prerequisite", () => {
  it("hides the Add age / Add sex buttons when onAddDemographic is not provided", () => {
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: /add an age check/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /add a sex check/i }),
    ).not.toBeInTheDocument();
  });

  it("calls onAddDemographic('age') when Add age is clicked", async () => {
    const user = userEvent.setup();
    const onAddDemographic = jest.fn();
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
        onAddDemographic={onAddDemographic}
      />,
    );

    await user.click(screen.getByRole("button", { name: /add an age check/i }));

    expect(onAddDemographic).toHaveBeenCalledWith("age");
  });

  it("hides Add age once an age prerequisite already exists, but still offers Add sex", () => {
    render(
      <StepPrerequisites
        recommendationText={NG12_1_2_9_TEXT}
        prerequisites={[makeAgeLeaf()]}
        onEdit={jest.fn()}
        onEditConcept={jest.fn()}
        onUpdate={jest.fn()}
        onRemove={jest.fn()}
        onAddFromSelection={jest.fn()}
        onAddDemographic={jest.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: /add an age check/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /add a sex check/i }),
    ).toBeInTheDocument();
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
        onUpdate={jest.fn()}
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
        onUpdate={jest.fn()}
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
        onUpdate={jest.fn()}
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
        onUpdate={jest.fn()}
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
        onUpdate={jest.fn()}
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
        onUpdate={jest.fn()}
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
        onUpdate={jest.fn()}
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
