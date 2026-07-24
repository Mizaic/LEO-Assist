/**
 * PathwayDemographicsPanel -- per-situation age/sex controls.
 * Atlas: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PathwayDemographicsPanel from "../HighlightWizard/PathwayDemographicsPanel";
import type { EditableLogicNode } from "../types";

function sexLeaf(): EditableLogicNode {
  return {
    node_id: "sex-1",
    kind: "DEMOGRAPHIC",
    field: "sex",
    operator: "=",
    value: "female",
    unit: null,
  };
}

describe("PathwayDemographicsPanel", () => {
  it("shows Add age and Add sex when the pathway has no demographics", () => {
    render(
      <PathwayDemographicsPanel
        demographics={[]}
        onAdd={jest.fn()}
        onUpdate={jest.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /add an age check for this situation only/i }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: /add a sex check for this situation only/i }),
    ).toBeEnabled();
  });

  it("disables Add sex when sex is already on the pathway", () => {
    render(
      <PathwayDemographicsPanel
        demographics={[sexLeaf()]}
        onAdd={jest.fn()}
        onUpdate={jest.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /add a sex check for this situation only/i }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /add an age check for this situation only/i }),
    ).toBeEnabled();
  });

  it("fires onAdd with the chosen field", async () => {
    const user = userEvent.setup();
    const onAdd = jest.fn();
    render(
      <PathwayDemographicsPanel
        demographics={[]}
        onAdd={onAdd}
        onUpdate={jest.fn()}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: /add a sex check for this situation only/i }),
    );
    expect(onAdd).toHaveBeenCalledWith("sex");
  });
});
