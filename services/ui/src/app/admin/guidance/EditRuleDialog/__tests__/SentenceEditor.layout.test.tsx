/**
 * Layout tests for the Simple sentence-style canvas (SentenceEditor/).
 *
 * Mirrors LogicTreeEditor.layout.test.tsx's structure/conventions but
 * asserts on the flowing-prose rendering instead of the boxed tree.
 * Built up task-by-task alongside the sentence-builder plan; this file
 * starts with GroupSentence's flat-leaf case (no nested sub-groups
 * yet) and grows to cover recursion, AT_LEAST parity, pathways, and
 * finally the full NG12 1.2.9 stress-test fixture.
 */
import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";

import SentenceEditor from "../SentenceEditor";
import EmptySentenceState from "../SentenceEditor/EmptySentenceState";
import GroupSentence from "../SentenceEditor/GroupSentence";
import { assignNodeIds } from "../treeOps";
import type { EditableLogicNode } from "../types";
import { makeNg12129Tree } from "./fixtures/ng12129";

const noop = () => {};

function makeFlatAnd(): EditableLogicNode {
  return assignNodeIds({
    kind: "AND",
    children: [
      { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Cough" } },
      { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" } },
    ],
  });
}

function makeFlatOr(): EditableLogicNode {
  return assignNodeIds({
    kind: "OR",
    children: [
      { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Cough" } },
      { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" } },
      { kind: "CONCEPT", criterion: { snomed_concept_id: "3", preferred_term: "Dyspnea" } },
    ],
  });
}

function renderGroup(node: EditableLogicNode, overrides: Partial<Parameters<typeof GroupSentence>[0]> = {}) {
  return render(
    <GroupSentence
      node={node}
      root={node}
      depth={0}
      isTopLevel
      selectedNodeId={null}
      onSelect={noop}
      onUpdate={noop}
      onRequestAdd={noop}
      {...overrides}
    />,
  );
}

describe("GroupSentence -- flat leaf-only groups (task 5)", () => {
  it("renders the AND lead-in phrase and both concept chips", () => {
    renderGroup(makeFlatAnd());
    expect(screen.getByText("Patient must have ALL of these")).toBeInTheDocument();
    expect(screen.getByText("Cough")).toBeInTheDocument();
    expect(screen.getByText("Fatigue")).toBeInTheDocument();
  });

  it("joins 2+ children with the group's connector word", () => {
    renderGroup(makeFlatOr());
    // joinNodes puts ", " between all but the last pair and "or " before
    // the last child -- so the group's flowing text should contain "or".
    const group = screen.getByRole("group", { name: "Patient must have ANY of these" });
    expect(group.textContent).toMatch(/or/);
  });

  it("dispatches change_kind when a different kind is picked from the inline lead-in", () => {
    const onUpdate = jest.fn();
    const tree = makeFlatAnd();
    renderGroup(tree, { onUpdate });
    fireEvent.mouseDown(screen.getByLabelText(/how to match conditions in this group/i));
    fireEvent.click(screen.getByRole("option", { name: "Patient must have ANY of these" }));
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "change_kind",
      nodeId: tree.node_id,
      newKind: "OR",
    });
  });

  it("shows an inline min-count field for AT_LEAST groups", () => {
    const tree = assignNodeIds({
      kind: "AT_LEAST",
      min: 2,
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Cough" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" } },
      ],
    });
    renderGroup(tree);
    expect(screen.getByText("Any 2 or more of these")).toBeInTheDocument();
    const counter = screen.getByLabelText(
      /how many conditions must match/i,
    ) as HTMLInputElement;
    expect(counter.value).toBe("2");
  });

  it("dispatches set_min when the inline min-count field changes", () => {
    const onUpdate = jest.fn();
    const tree = assignNodeIds({
      kind: "AT_LEAST",
      min: 1,
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Cough" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" } },
      ],
    });
    renderGroup(tree, { onUpdate });
    const counter = screen.getByLabelText(/how many conditions must match/i);
    fireEvent.change(counter, { target: { value: "2" } });
    expect(onUpdate).toHaveBeenCalledWith({ kind: "set_min", nodeId: tree.node_id, min: 2 });
  });

  it("renders inline add-links (not boxed AddBar buttons) wired to the group's own node id", () => {
    const onUpdate = jest.fn();
    const tree = makeFlatAnd();
    renderGroup(tree, { onUpdate });
    expect(screen.getByText("+ add another symptom")).toBeInTheDocument();
    expect(screen.getByText("+ add a patient detail")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add.*patient detail/i }));
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "add_demographic",
      parentNodeId: tree.node_id,
    });
  });

  it("hides the add-links for a collapsed nested chunk (but not for its expanded ancestors)", () => {
    // AND(depth0, expanded) > OR(depth1, expanded) > AND(depth2, collapsed)[Cough]
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "OR",
          children: [
            {
              kind: "AND",
              children: [
                { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Cough" } },
              ],
            },
          ],
        },
      ],
    });
    renderGroup(tree);
    // Only the two expanded ancestors (depth 0 and depth 1) show their
    // own add-links; the collapsed depth-2 chunk shows none.
    expect(screen.getAllByText("+ add another symptom")).toHaveLength(2);
  });

  it("shows a friendly placeholder and no crash for an empty group", () => {
    const tree = assignNodeIds({ kind: "AND", children: [] });
    renderGroup(tree);
    expect(screen.getByText(/nothing yet/i)).toBeInTheDocument();
  });

  it("shows a remove button for non-top-level groups only", () => {
    const tree = makeFlatAnd();
    const { rerender } = renderGroup(tree, { isTopLevel: true });
    expect(screen.queryByRole("button", { name: /remove this group/i })).not.toBeInTheDocument();

    rerender(
      <GroupSentence
        node={tree}
        root={tree}
        depth={1}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    expect(screen.getByRole("button", { name: /remove this group/i })).toBeInTheDocument();
  });

  it("mixes a DEMOGRAPHIC leaf and a CONCEPT leaf in the same sentence", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 55, unit: "years" },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Upper abdominal pain" } },
      ],
    });
    renderGroup(tree);
    expect(screen.getByText(/patient's age/i)).toBeInTheDocument();
    expect(screen.getByText("Upper abdominal pain")).toBeInTheDocument();
  });
});

describe("GroupSentence -- recursive nested chunks (task 6)", () => {
  function makeNestedTree(): EditableLogicNode {
    return assignNodeIds({
      kind: "AND",
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Indigestion" } },
        {
          kind: "AT_LEAST",
          min: 1,
          children: [
            { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Nausea" } },
            { kind: "CONCEPT", criterion: { snomed_concept_id: "3", preferred_term: "Vomiting" } },
          ],
        },
      ],
    });
  }

  it("renders a sub-group child as a nested chunk with its own lead-in and children", () => {
    renderGroup(makeNestedTree());
    expect(screen.getByText("Indigestion")).toBeInTheDocument();
    expect(screen.getByText("Any 1 or more of these")).toBeInTheDocument();
    expect(screen.getByText("Nausea")).toBeInTheDocument();
    expect(screen.getByText("Vomiting")).toBeInTheDocument();
  });

  it("nested chunk at depth 1 is expanded by default (no auto-collapse yet)", () => {
    // makeNestedTree()'s AT_LEAST child is a pure-CONCEPT cluster, which
    // (per task 8's AT_LEAST parity) never shows a collapse chevron at
    // any depth -- so the correct "expanded" signal here is that its
    // leaves are already visible, not a "Collapse group" button.
    renderGroup(makeNestedTree());
    expect(screen.queryByRole("button", { name: /expand group/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /collapse group/i })).not.toBeInTheDocument();
    expect(screen.getByText("Nausea")).toBeInTheDocument();
  });

  it("a nested (non-pure) chunk at depth 1 shows its own collapse chevron and starts expanded", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Indigestion" } },
        {
          kind: "OR",
          children: [
            { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Nausea" } },
            { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 55, unit: "years" },
          ],
        },
      ],
    });
    renderGroup(tree);
    expect(screen.queryByRole("button", { name: /expand group/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /collapse group/i })).toBeInTheDocument();
  });

  it("auto-collapses a chunk at depth >= 2, hiding its leaves behind a summary", () => {
    // AND(depth0) > OR(depth1) > AND(depth2)[Cough] -- the depth-2 AND
    // should start collapsed, matching GroupBody's exact threshold.
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "OR",
          children: [
            {
              kind: "AND",
              children: [
                { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Cough" } },
              ],
            },
          ],
        },
      ],
    });
    renderGroup(tree);
    expect(screen.queryByText("Cough")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /expand group/i })).toBeInTheDocument();
  });

  it("clicking the chevron expands a collapsed depth-2 chunk and reveals its leaf", () => {
    const tree = assignNodeIds({
      kind: "AND",
      children: [
        {
          kind: "OR",
          children: [
            {
              kind: "AND",
              children: [
                { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Cough" } },
              ],
            },
          ],
        },
      ],
    });
    renderGroup(tree);
    fireEvent.click(screen.getByRole("button", { name: /expand group/i }));
    expect(screen.getByText("Cough")).toBeInTheDocument();
    // Both the depth-1 OR (always expanded) and the now-expanded
    // depth-2 AND show a "Collapse group" chevron.
    expect(screen.getAllByRole("button", { name: /collapse group/i })).toHaveLength(2);
  });

  it("removing a nested chunk dispatches remove with the sub-group's own node id", () => {
    const onUpdate = jest.fn();
    const tree = makeNestedTree();
    const atLeastNode = tree.children![1];
    renderGroup(tree, { onUpdate });
    const removeButtons = screen.getAllByRole("button", { name: /remove this group/i });
    fireEvent.click(removeButtons[0]);
    expect(onUpdate).toHaveBeenCalledWith({ kind: "remove", nodeId: atLeastNode.node_id });
  });
});

describe("GroupSentence -- AT_LEAST parity with GroupBody's InlineAtLeast (task 8)", () => {
  function makePureAtLeast(min = 2): EditableLogicNode {
    return assignNodeIds({
      kind: "AT_LEAST",
      min,
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Nausea" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Vomiting" } },
        { kind: "CONCEPT", criterion: { snomed_concept_id: "3", preferred_term: "Weight loss" } },
      ],
    });
  }

  it("shows the 'of N' total-count caption next to the min-count field", () => {
    renderGroup(makePureAtLeast(2));
    expect(screen.getByText("of 3")).toBeInTheDocument();
  });

  it("a pure-CONCEPT AT_LEAST cluster gets the pill/remove-button treatment even at the tree root", () => {
    // GroupBody's isPureAtLeast fast path (InlineAtLeast) always shows a
    // remove button, even when the cluster is the literal root -- the
    // sentence canvas must match that precedence over isTopLevel.
    renderGroup(makePureAtLeast(), { isTopLevel: true });
    expect(screen.getByRole("button", { name: /remove this group/i })).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: /any 2 or more of these/i }),
    ).toBeInTheDocument();
  });

  it("a pure-CONCEPT AT_LEAST cluster only offers the concept add-link, not patient detail/lab value/etc", () => {
    renderGroup(makePureAtLeast());
    expect(screen.getByText("+ add another symptom")).toBeInTheDocument();
    expect(screen.queryByText("+ add a patient detail")).not.toBeInTheDocument();
    expect(screen.queryByText("+ add a lab value")).not.toBeInTheDocument();
    expect(screen.queryByText("+ add a condition group")).not.toBeInTheDocument();
  });

  it("a mixed-child (non-pure) AT_LEAST group at the tree root behaves like any other top-level group (no remove button, full add-link menu)", () => {
    const tree = assignNodeIds({
      kind: "AT_LEAST",
      min: 1,
      children: [
        { kind: "CONCEPT", criterion: { snomed_concept_id: "1", preferred_term: "Nausea" } },
        { kind: "DEMOGRAPHIC", field: "age", operator: ">=", value: 55, unit: "years" },
      ],
    });
    renderGroup(tree, { isTopLevel: true });
    expect(screen.queryByRole("button", { name: /remove this group/i })).not.toBeInTheDocument();
    expect(screen.getByText("+ add a patient detail")).toBeInTheDocument();
  });
});

describe("SentenceEditor -- pathway split rendering (task 9, NG12 1.2.9)", () => {
  it("renders 6 lettered pathway cards, not one nested blob", () => {
    render(
      <SentenceEditor
        root={makeNg12129Tree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    for (const letter of ["A", "B", "C", "D", "E", "F"]) {
      expect(screen.getByTestId(`pathway-card-${letter}`)).toBeInTheDocument();
    }
  });

  it("renders the demographic prerequisite once above the pathway list, not inside pathway card A", () => {
    render(
      <SentenceEditor
        root={makeNg12129Tree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const lead = screen.getByRole("group", { name: /applies to every pathway below/i });
    expect(within(lead).getByText(/age/i)).toBeInTheDocument();

    const cardA = screen.getByTestId("pathway-card-A");
    expect(within(cardA).queryByText(/age/i)).not.toBeInTheDocument();
  });

  it("pathway B reads as a sentence: the concept leaf, the AT_LEAST cluster label, and its concept pills", () => {
    render(
      <SentenceEditor
        root={makeNg12129Tree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const cardB = screen.getByTestId("pathway-card-B");
    expect(within(cardB).getByText("indigestion")).toBeInTheDocument();
    expect(within(cardB).getByText("Any 1 or more of these")).toBeInTheDocument();
    expect(within(cardB).getByText("upper abdominal pain")).toBeInTheDocument();
    expect(within(cardB).getByText("weight decreased")).toBeInTheDocument();
  });

  it("each pathway card exposes its own remove button, letter badge, and editable name field", () => {
    render(
      <SentenceEditor
        root={makeNg12129Tree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const cardC = screen.getByTestId("pathway-card-C");
    expect(within(cardC).getByRole("button", { name: /remove pathway c/i })).toBeInTheDocument();
    expect(within(cardC).getByLabelText(/name for pathway c/i)).toBeInTheDocument();
  });

  it("clicking a pathway card's remove button dispatches remove with that pathway's own node id", () => {
    const onUpdate = jest.fn();
    const tree = makeNg12129Tree();
    const pathwayD = tree.children![1].children![3];
    render(
      <SentenceEditor
        root={tree}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={onUpdate}
        onRequestAdd={noop}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /remove pathway d/i }));
    expect(onUpdate).toHaveBeenCalledWith({ kind: "remove", nodeId: pathwayD.node_id });
  });

  it("a non-pathway tree (single AND root) renders one plain sentence, no lettered cards", () => {
    render(<SentenceEditor root={makeFlatAnd()} selectedNodeId={null} onSelect={noop} onUpdate={noop} onRequestAdd={noop} />);
    expect(screen.queryByTestId(/pathway-card-/)).not.toBeInTheDocument();
    expect(screen.getByText("Patient must have ALL of these")).toBeInTheDocument();
  });
});

describe("SentenceEditor -- bare-leaf pathway (NG12 1.2.1-shaped OR child with no AND wrapper)", () => {
  // Mirrors the LogicTreeEditor regression above: PathwaySentenceCard
  // used to guard on GROUP_KINDS.includes(node.kind) and return null
  // for a bare CONCEPT/DEMOGRAPHIC child of the situations OR, so the
  // whole pathway silently vanished from the Simple canvas too.
  function makeBareLeafOrRoot(): EditableLogicNode {
    return assignNodeIds({
      kind: "OR",
      children: [
        {
          kind: "CONCEPT",
          criterion: { snomed_concept_id: "123456", preferred_term: "Abdominal mass" },
        },
        {
          kind: "AND",
          name: "Symptom watch",
          children: [
            { kind: "CONCEPT", criterion: { snomed_concept_id: "2", preferred_term: "Weight loss" } },
          ],
        },
      ],
    });
  }

  it("renders the bare-leaf pathway card instead of vanishing", () => {
    render(
      <SentenceEditor
        root={makeBareLeafOrRoot()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    expect(screen.getByTestId("pathway-card-A")).toBeInTheDocument();
    expect(screen.getByTestId("pathway-card-B")).toBeInTheDocument();
    expect(within(screen.getByTestId("pathway-card-A")).getByText("Abdominal mass")).toBeInTheDocument();
  });

  it("offers a Remove control for the bare-leaf pathway", () => {
    render(
      <SentenceEditor
        root={makeBareLeafOrRoot()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
    const cardA = screen.getByTestId("pathway-card-A");
    expect(within(cardA).getByRole("button", { name: /remove pathway a/i })).toBeInTheDocument();
  });

  it("lets a second condition be added to the bare-leaf pathway, promoting it into an AND group", () => {
    const tree = makeBareLeafOrRoot();
    const leaf = tree.children?.[0];
    const onUpdate = jest.fn();
    render(
      <SentenceEditor
        root={tree}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={onUpdate}
        onRequestAdd={noop}
      />,
    );
    const cardA = screen.getByTestId("pathway-card-A");
    fireEvent.click(within(cardA).getByText("+ add a patient detail"));
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "add_demographic",
      parentNodeId: leaf?.node_id,
    });
  });
});

describe("EmptySentenceState (task 10)", () => {
  it("reads as a prose sentence with an inline 'add the first symptom' link", () => {
    const onAddFirstSymptom = jest.fn();
    render(
      <EmptySentenceState
        onAddFirstSymptom={onAddFirstSymptom}
        onAddFirstDemographic={noop}
        onAddFirstObservation={noop}
      />,
    );
    expect(screen.getByText(/this rule doesn.t check anything yet/i)).toBeInTheDocument();
    const link = screen.getByText("+ add the first symptom");
    expect(link).toBeInTheDocument();
    fireEvent.click(link);
    expect(onAddFirstSymptom).toHaveBeenCalledWith(expect.anything());
  });

  it("shows patient-detail and lab-value links only when their handlers are provided", () => {
    render(<EmptySentenceState onAddFirstSymptom={noop} />);
    expect(screen.queryByText("+ add a patient detail")).not.toBeInTheDocument();
    expect(screen.queryByText("+ add a lab value")).not.toBeInTheDocument();
  });

  it("shows the AI-draft CTA only when both ruleId and onAIDraft are provided", () => {
    render(<EmptySentenceState onAddFirstSymptom={noop} />);
    expect(screen.queryByText(/or let ai draft it/i)).not.toBeInTheDocument();
  });
});

describe("SentenceEditor -- NG12 1.2.9 full stress test against the validated wireframe (task 11)", () => {
  // Wireframe (validated in the plan before any code was written):
  //
  //   This rule applies to patients who are 55 years or older, and
  //   match ANY ONE of these pathways:
  //     [A] Patient has upper abdominal pain.
  //     [B] Patient has indigestion, and any of these -- upper
  //         abdominal pain, nausea, vomiting, or weight decreased.
  //     [C] Patient has upper abdominal pain and hemoglobin below
  //         reference range (advanced), and any of these -- weight
  //         decreased, acid reflux, or indigestion.
  //     [D] mirrors C with platelet count and the full 6-item cluster.
  //     [E] Patient has vomiting, and any of the common cluster.
  //     [F] Patient has nausea, and any of the common cluster.
  //     +Add pathway
  function renderNg12() {
    render(
      <SentenceEditor
        root={makeNg12129Tree()}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={noop}
        onRequestAdd={noop}
      />,
    );
  }

  it("demographic lead-in: 'This rule applies to patients who are 55 years or older'", () => {
    renderNg12();
    const lead = screen.getByRole("group", { name: /applies to every pathway below/i });
    expect(within(lead).getByText(/age/i)).toBeInTheDocument();
    expect(within(lead).getByLabelText("Lower bound")).toHaveValue("55");
  });

  it("[A] a single-condition pathway: just 'upper abdominal pain', no cluster", () => {
    renderNg12();
    const cardA = screen.getByTestId("pathway-card-A");
    expect(within(cardA).getByText("upper abdominal pain")).toBeInTheDocument();
    expect(within(cardA).queryByText(/any \d or more of these/i)).not.toBeInTheDocument();
  });

  it("[B] 'indigestion' plus a 4-item any-of cluster (upper abdominal pain, nausea, vomiting, weight decreased)", () => {
    renderNg12();
    const cardB = screen.getByTestId("pathway-card-B");
    expect(within(cardB).getByText("indigestion")).toBeInTheDocument();
    expect(within(cardB).getByText("Any 1 or more of these")).toBeInTheDocument();
    for (const term of ["upper abdominal pain", "nausea", "vomiting", "weight decreased"]) {
      expect(within(cardB).getByText(term)).toBeInTheDocument();
    }
  });

  it("[C] upper abdominal pain + soft-locked hemoglobin reference-range leaf + 3-item cluster", () => {
    renderNg12();
    const cardC = screen.getByTestId("pathway-card-C");
    expect(within(cardC).getByText("upper abdominal pain")).toBeInTheDocument();
    // Advanced-mode OBSERVATION leaf stays soft-locked, matching today's
    // Advanced-view behaviour -- not editable inline in the Simple canvas.
    expect(within(cardC).getByText("hemoglobin")).toBeInTheDocument();
    expect(within(cardC).getByText(/compared to the patient's normal range/i)).toBeInTheDocument();
    expect(within(cardC).getByText(/open timing settings to edit/i)).toBeInTheDocument();
    for (const term of ["weight decreased", "acid reflux", "indigestion"]) {
      expect(within(cardC).getByText(term)).toBeInTheDocument();
    }
  });

  it("[D] mirrors C with a platelet-count observation and the full 6-item symptom cluster", () => {
    renderNg12();
    const cardD = screen.getByTestId("pathway-card-D");
    expect(within(cardD).getByText("platelet count")).toBeInTheDocument();
    expect(within(cardD).getByText(/compared to the patient's normal range/i)).toBeInTheDocument();
    for (const term of [
      "nausea", "vomiting", "weight decreased",
      "acid reflux", "indigestion", "upper abdominal pain",
    ]) {
      expect(within(cardD).getByText(term)).toBeInTheDocument();
    }
  });

  it("[E] 'vomiting' plus the common any-of cluster", () => {
    renderNg12();
    const cardE = screen.getByTestId("pathway-card-E");
    expect(within(cardE).getByText("vomiting")).toBeInTheDocument();
    for (const term of ["weight decreased", "acid reflux", "indigestion"]) {
      expect(within(cardE).getByText(term)).toBeInTheDocument();
    }
  });

  it("[F] 'nausea' plus the common any-of cluster", () => {
    renderNg12();
    const cardF = screen.getByTestId("pathway-card-F");
    expect(within(cardF).getByText("nausea")).toBeInTheDocument();
    for (const term of ["weight decreased", "acid reflux", "indigestion"]) {
      expect(within(cardF).getByText(term)).toBeInTheDocument();
    }
  });

  it("shows '+ Add pathway' at the bottom of the list, wired to add_group on the OR root", () => {
    const onUpdate = jest.fn();
    const tree = makeNg12129Tree();
    const orNode = tree.children![1];
    render(
      <SentenceEditor
        root={tree}
        selectedNodeId={null}
        onSelect={noop}
        onUpdate={onUpdate}
        onRequestAdd={noop}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /add another pathway/i }));
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "add_group",
      parentNodeId: orNode.node_id,
      groupKind: "AND",
    });
  });

  it("every pathway card is individually short -- no card renders more than one nested any-of cluster", () => {
    renderNg12();
    for (const letter of ["A", "B", "C", "D", "E", "F"]) {
      const card = screen.getByTestId(`pathway-card-${letter}`);
      const clusters = within(card).queryAllByText(/any \d or more of these/i);
      expect(clusters.length).toBeLessThanOrEqual(1);
    }
  });
});

describe("GroupSentence -- reused leaf components stay unmodified (parity check)", () => {
  it("a CONCEPT chip click still calls onSelect with the node id", () => {
    const onSelect = jest.fn();
    const tree = makeFlatAnd();
    renderGroup(tree, { onSelect });
    fireEvent.click(screen.getByText("Cough"));
    expect(onSelect).toHaveBeenCalledWith(tree.children![0].node_id, expect.anything());
  });

  it("removing a chip dispatches remove with the leaf's own node id", () => {
    const onUpdate = jest.fn();
    const tree = makeFlatAnd();
    renderGroup(tree, { onUpdate });
    const chip = screen.getByText("Cough").closest(".MuiChip-root") as HTMLElement;
    const deleteIcon = within(chip).getByTestId("CloseIcon");
    fireEvent.click(deleteIcon);
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "remove",
      nodeId: tree.children![0].node_id,
    });
  });
});
