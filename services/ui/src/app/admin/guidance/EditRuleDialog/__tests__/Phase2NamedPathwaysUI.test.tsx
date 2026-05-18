/**
 * Phase 2 of the wizard redesign: pathway name input UI.
 *
 * The editor's pathway-cards layout must:
 *   - render a small text input next to each pathway's positional letter chip
 *   - prefill with the saved name and show the placeholder otherwise
 *   - emit a `set_name` update on blur with the trimmed value
 *   - clear the name (no `name` field on the wire) when the user blanks it
 *
 * Atlas trace: DI-2E01CC45 / DO-E67AFBE2 / VT-8C96CBC0.
 */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import LogicTreeEditor from "../LogicTreeEditor";
import { assignNodeIds } from "../treeOps";
import type { EditableLogicNode, NodeUpdate } from "../types";

function pathwayTree(): EditableLogicNode {
  return assignNodeIds({
    kind: "OR",
    children: [
      {
        kind: "AND",
        name: "Possible cancer",
        children: [
          {
            kind: "CONCEPT",
            criterion: { snomed_concept_id: "1", preferred_term: "Cough" },
          },
        ],
      },
      {
        kind: "AND",
        children: [
          {
            kind: "CONCEPT",
            criterion: { snomed_concept_id: "2", preferred_term: "Fatigue" },
          },
        ],
      },
    ],
  });
}

function renderEditor(tree: EditableLogicNode) {
  const onUpdate = jest.fn<void, [NodeUpdate]>();
  const onSelect = jest.fn();
  const onRequestAdd = jest.fn();
  render(
    <LogicTreeEditor
      root={tree}
      selectedNodeId={null}
      onSelect={onSelect}
      onUpdate={onUpdate}
      onRequestAdd={onRequestAdd}
    />,
  );
  return { onUpdate };
}

describe("Phase 2: pathway name input UI", () => {
  it("renders one name input per pathway card", () => {
    renderEditor(pathwayTree());
    expect(
      screen.getByRole("textbox", { name: /Name for Pathway A\./i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: /Name for Pathway B\./i }),
    ).toBeInTheDocument();
  });

  it("prefills the input with the existing pathway name", () => {
    renderEditor(pathwayTree());
    const inputA = screen.getByRole("textbox", {
      name: /Name for Pathway A\./i,
    }) as HTMLInputElement;
    const inputB = screen.getByRole("textbox", {
      name: /Name for Pathway B\./i,
    }) as HTMLInputElement;
    expect(inputA.value).toBe("Possible cancer");
    expect(inputB.value).toBe("");
  });

  it("emits a set_name update on blur with the trimmed value", () => {
    const { onUpdate } = renderEditor(pathwayTree());
    const inputB = screen.getByRole("textbox", {
      name: /Name for Pathway B\./i,
    });
    fireEvent.change(inputB, { target: { value: "  Symptom watch  " } });
    fireEvent.blur(inputB);
    expect(onUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "set_name",
        name: "Symptom watch",
      }),
    );
  });

  it("emits a set_name update with empty string when the user clears the field", () => {
    const { onUpdate } = renderEditor(pathwayTree());
    const inputA = screen.getByRole("textbox", {
      name: /Name for Pathway A\./i,
    });
    fireEvent.change(inputA, { target: { value: "" } });
    fireEvent.blur(inputA);
    expect(onUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "set_name",
        name: "",
      }),
    );
  });

  it("does not emit a set_name update when the value is unchanged", () => {
    const { onUpdate } = renderEditor(pathwayTree());
    const inputA = screen.getByRole("textbox", {
      name: /Name for Pathway A\./i,
    });
    fireEvent.blur(inputA);
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it("commits the value when the user presses Enter", () => {
    const { onUpdate } = renderEditor(pathwayTree());
    const inputB = screen.getByRole("textbox", {
      name: /Name for Pathway B\./i,
    });
    fireEvent.change(inputB, { target: { value: "Symptom watch" } });
    fireEvent.keyDown(inputB, { key: "Enter" });
    fireEvent.blur(inputB);
    expect(onUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "set_name",
        name: "Symptom watch",
      }),
    );
  });
});
