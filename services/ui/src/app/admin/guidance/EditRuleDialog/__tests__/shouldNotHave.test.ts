/**
 * Unit tests for guided-editor exclusion helpers.
 *
 * Atlas trace: DI-0F0B27D3 / DO-4EA3C153
 */
import {
  beginShouldNotHaveAdd,
  collectShouldNotHaveLeaves,
  findDirectNotGroup,
  shouldNotHaveLabel,
} from "../HighlightWizard/shouldNotHave";
import type { EditableLogicNode, NodeUpdate } from "../types";

function concept(id: string, term: string): EditableLogicNode {
  return {
    node_id: id,
    kind: "CONCEPT",
    criterion: { snomed_concept_id: id, preferred_term: term },
  };
}

function notGroup(children: EditableLogicNode[]): EditableLogicNode {
  return { node_id: "not-1", kind: "NOT", children };
}

describe("findDirectNotGroup", () => {
  it("returns the first direct NOT child", () => {
    const parent: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [concept("wl", "Weight loss"), notGroup([concept("hrt", "HRT")])],
    };
    expect(findDirectNotGroup(parent)?.node_id).toBe("not-1");
  });

  it("returns null when the parent has no NOT child", () => {
    const parent: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [concept("wl", "Weight loss")],
    };
    expect(findDirectNotGroup(parent)).toBeNull();
  });
});

describe("collectShouldNotHaveLeaves", () => {
  it("returns CONCEPT leaves inside a NOT group and ignores must-have siblings", () => {
    const hrt = concept("hrt", "HRT");
    const leaves = collectShouldNotHaveLeaves([
      concept("wl", "Weight loss"),
      notGroup([hrt]),
    ]);
    expect(leaves.map((leaf) => leaf.node_id)).toEqual(["hrt"]);
  });

  it("returns an empty list when there is no NOT group", () => {
    expect(collectShouldNotHaveLeaves([concept("wl", "Weight loss")])).toEqual([]);
  });
});

describe("shouldNotHaveLabel", () => {
  it("labels a CONCEPT as something the patient must not have", () => {
    expect(shouldNotHaveLabel(concept("hrt", "HRT"))).toBe("Patient must not have HRT");
  });
});

describe("beginShouldNotHaveAdd", () => {
  it("reuses an existing NOT group and opens concept search there", () => {
    const parent: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [notGroup([concept("hrt", "HRT")])],
    };
    const onUpdate = jest.fn();
    const onRequestAdd = jest.fn();
    const markPending = jest.fn();
    beginShouldNotHaveAdd({
      parent,
      onUpdate,
      onRequestAdd,
      markPending,
    });
    expect(onUpdate).not.toHaveBeenCalled();
    expect(markPending).not.toHaveBeenCalled();
    expect(onRequestAdd).toHaveBeenCalledWith("not-1", undefined, undefined, true);
  });

  it("creates a NOT group and marks it pending when none exists", () => {
    const parent: EditableLogicNode = {
      node_id: "root",
      kind: "AND",
      children: [concept("wl", "Weight loss")],
    };
    const onUpdate = jest.fn();
    const onRequestAdd = jest.fn();
    const markPending = jest.fn();
    beginShouldNotHaveAdd({
      parent,
      onUpdate,
      onRequestAdd,
      markPending,
    });
    expect(onRequestAdd).not.toHaveBeenCalled();
    expect(markPending).toHaveBeenCalledTimes(1);
    expect(onUpdate).toHaveBeenCalledWith({
      kind: "add_group",
      parentNodeId: "root",
      groupKind: "NOT",
    } satisfies NodeUpdate);
  });
});
