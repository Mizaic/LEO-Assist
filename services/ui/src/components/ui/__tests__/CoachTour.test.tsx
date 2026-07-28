/**
 * Unit tests for the multi-step CoachTour sequencer.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MotionProvider } from "@leo/design-system";

import CoachTour, { type TourStep } from "../CoachTour";

const STEPS: TourStep[] = [
  {
    id: "step-a",
    title: "First tip",
    body: "This is the first tip body.",
    anchorSelector: '[data-tour="step-a"]',
  },
  {
    id: "step-b",
    title: "Second tip",
    body: "This is the second tip body.",
    anchorSelector: '[data-tour="step-b"]',
  },
];

function renderTour(
  props: Partial<React.ComponentProps<typeof CoachTour>> = {},
) {
  const onFinish = jest.fn();
  const view = render(
    <MotionProvider>
      <div data-tour="step-a">Anchor A</div>
      <div data-tour="step-b">Anchor B</div>
      <CoachTour
        tourId="test-tour"
        steps={STEPS}
        active
        onFinish={onFinish}
        {...props}
      />
    </MotionProvider>,
  );
  return { ...view, onFinish };
}

describe("CoachTour", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders step 0 title and body when active", () => {
    renderTour();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("First tip")).toBeInTheDocument();
    expect(screen.getByText("This is the first tip body.")).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 2")).toBeInTheDocument();
  });

  it("does not render when inactive", () => {
    renderTour({ active: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("disables Back on step 0 and advances with Next", async () => {
    const user = userEvent.setup();
    renderTour();
    expect(screen.getByTestId("coach-tour-back")).toBeDisabled();
    await user.click(screen.getByTestId("coach-tour-next"));
    expect(screen.getByText("Second tip")).toBeInTheDocument();
    expect(screen.getByTestId("coach-tour-back")).not.toBeDisabled();
    expect(screen.getByTestId("coach-tour-next")).toHaveTextContent("Done");
  });

  it("Skip calls onFinish and sets localStorage", async () => {
    const user = userEvent.setup();
    const { onFinish } = renderTour();
    await user.click(screen.getByTestId("coach-tour-skip"));
    expect(onFinish).toHaveBeenCalledTimes(1);
    expect(window.localStorage.getItem("leo-tour-test-tour-done")).toBe(
      "true",
    );
  });

  it("Done on last step finishes the tour", async () => {
    const user = userEvent.setup();
    const { onFinish } = renderTour();
    await user.click(screen.getByTestId("coach-tour-next"));
    await user.click(screen.getByTestId("coach-tour-next"));
    expect(onFinish).toHaveBeenCalledTimes(1);
  });
});
