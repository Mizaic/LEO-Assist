/**
 * Live-render tests for HorizontalStepper -- specifically the
 * `wizardPhase` breadcrumb it renders attached to the "Who" pill so
 * the outer numbered stepper and the guided wizard's own phases read
 * as one navigation surface instead of two separate ones.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import React from "react";
import { render, screen } from "@testing-library/react";

import HorizontalStepper, { type StepDescriptor } from "../HorizontalStepper";

const STEPS: StepDescriptor[] = [
  { id: "who", state: "in_progress" },
  { id: "suggest", state: "not_started" },
  { id: "save", state: "not_started" },
];

describe("HorizontalStepper: wizardPhase breadcrumb", () => {
  it("shows no breadcrumb when wizardPhase is null", () => {
    render(
      <HorizontalStepper
        steps={STEPS}
        currentStepId="who"
        onJump={jest.fn()}
        wizardPhase={null}
      />,
    );
    expect(screen.queryByText("Always true")).not.toBeInTheDocument();
  });

  it("shows the breadcrumb attached under the Who pill when wizardPhase is set and Who is current", () => {
    render(
      <HorizontalStepper
        steps={STEPS}
        currentStepId="who"
        onJump={jest.fn()}
        wizardPhase="pathway-split"
      />,
    );
    expect(screen.getByText("Always true")).toBeInTheDocument();
    expect(screen.getByText("Situations")).toBeInTheDocument();
    expect(screen.getByText("Conditions")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
  });

  it("hides the breadcrumb when a different outer step is current, even if wizardPhase is stale", () => {
    render(
      <HorizontalStepper
        steps={STEPS}
        currentStepId="suggest"
        onJump={jest.fn()}
        wizardPhase="review"
      />,
    );
    expect(screen.queryByText("Always true")).not.toBeInTheDocument();
  });
});
