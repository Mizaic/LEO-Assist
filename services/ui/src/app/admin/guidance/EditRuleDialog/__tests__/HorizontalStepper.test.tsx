/**
 * Live-render tests for the flat HorizontalStepper.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import HorizontalStepper from "../HorizontalStepper";
import { buildNavSlots } from "../navSlots";

describe("HorizontalStepper: flat guided slots", () => {
  it("renders Always true and Situations without a nested breadcrumb", () => {
    const { slots, currentId } = buildNavSlots({
      outerStep: "who",
      wizardPhase: "pathway-split",
      situationCount: 0,
      situationIndex: 0,
      reachedCheck: false,
    });
    render(
      <HorizontalStepper
        slots={slots}
        currentSlotId={currentId}
        onJump={jest.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Always true/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Situations/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Conditions/i }),
    ).not.toBeInTheDocument();
  });

  it("renders a letter pill per confirmed situation", () => {
    const { slots, currentId } = buildNavSlots({
      outerStep: "who",
      wizardPhase: "pathway-conditions",
      situationCount: 2,
      situationIndex: 0,
      reachedCheck: false,
    });
    render(
      <HorizontalStepper
        slots={slots}
        currentSlotId={currentId}
        onJump={jest.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Situation A \(1 of 2\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Situation B \(2 of 2\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Check the rule/i }),
    ).toBeInTheDocument();
  });

  it("calls onJump for an open slot and ignores a locked future slot", async () => {
    const user = userEvent.setup();
    const onJump = jest.fn();
    const { slots, currentId } = buildNavSlots({
      outerStep: "who",
      wizardPhase: "pathway-conditions",
      situationCount: 2,
      situationIndex: 0,
      reachedCheck: false,
    });
    render(
      <HorizontalStepper
        slots={slots}
        currentSlotId={currentId}
        onJump={onJump}
      />,
    );
    await user.click(
      screen.getByRole("button", { name: /Always true/i }),
    );
    expect(onJump).toHaveBeenCalledTimes(1);
    await user.click(
      screen.getByRole("button", { name: /Situation B \(2 of 2\)/i }),
    );
    expect(onJump).toHaveBeenCalledTimes(1);
  });
});
