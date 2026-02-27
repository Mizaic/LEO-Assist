import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AlertDetailPanel from "../AlertDetailPanel";
import type { SafetyNetAlert } from "@/lib/analyticsApi";

jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) =>
    React.createElement("a", { href }, children);
});

function makeAlert(overrides: Partial<SafetyNetAlert> = {}): SafetyNetAlert {
  return {
    id: "ALERT-1",
    type: "missing_safety_netting",
    severity: "high",
    description: "No safety-netting language in pre-referral encounters",
    suggested_action: "Review and add safety-net advice",
    guideline: "NG12",
    patient_id: "P001",
    condition_type: "Colorectal",
    episode_id: "EP-42",
    encounter_date: "2025-11-03",
    created_at: "2025-12-01",
    match_percent: 0.87,
    actioned: false,
    needs_review: true,
    ...overrides,
  };
}

describe("AlertDetailPanel", () => {
  const defaultProps = {
    onClose: jest.fn(),
    onAction: jest.fn(),
    actionLoading: false,
  };

  it("renders alert severity, type, and description", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("missing_safety_netting")).toBeInTheDocument();
    expect(
      screen.getByText("No safety-netting language in pre-referral encounters"),
    ).toBeInTheDocument();
  });

  it("renders suggested action", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    expect(
      screen.getByText("Review and add safety-net advice"),
    ).toBeInTheDocument();
  });

  it("renders guideline", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    expect(screen.getByText("NG12")).toBeInTheDocument();
  });

  it("renders patient link", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    const link = screen.getByText("P001").closest("a");
    expect(link).toHaveAttribute("href", "/patients/P001");
  });

  it("renders episode link", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    const link = screen.getByText("EP-42").closest("a");
    expect(link).toHaveAttribute("href", "/episodes?id=EP-42");
  });

  it("renders cancer type", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    expect(screen.getByText("Colorectal")).toBeInTheDocument();
  });

  it("renders encounter date and flagged date", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    expect(screen.getByText("2025-11-03")).toBeInTheDocument();
    expect(screen.getByText("2025-12-01")).toBeInTheDocument();
  });

  it("renders confidence percentage", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    expect(screen.getByText("87%")).toBeInTheDocument();
  });

  it("shows needs review chip", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    expect(screen.getByText("Needs review")).toBeInTheDocument();
  });

  it("shows 'Mark actioned' button for un-actioned alerts", () => {
    render(<AlertDetailPanel alert={makeAlert()} {...defaultProps} />);
    expect(screen.getByText("Mark actioned")).toBeInTheDocument();
  });

  it("shows 'Mark outstanding' button for actioned alerts", () => {
    render(
      <AlertDetailPanel
        alert={makeAlert({ actioned: true })}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("Mark outstanding")).toBeInTheDocument();
  });

  it("calls onAction with true when clicking Mark actioned", async () => {
    const user = userEvent.setup();
    const onAction = jest.fn();
    render(
      <AlertDetailPanel
        alert={makeAlert()}
        onClose={jest.fn()}
        onAction={onAction}
        actionLoading={false}
      />,
    );
    await user.click(screen.getByText("Mark actioned"));
    expect(onAction).toHaveBeenCalledWith("ALERT-1", true);
  });

  it("calls onAction with false when clicking Mark outstanding", async () => {
    const user = userEvent.setup();
    const onAction = jest.fn();
    render(
      <AlertDetailPanel
        alert={makeAlert({ actioned: true })}
        onClose={jest.fn()}
        onAction={onAction}
        actionLoading={false}
      />,
    );
    await user.click(screen.getByText("Mark outstanding"));
    expect(onAction).toHaveBeenCalledWith("ALERT-1", false);
  });

  it("disables button when actionLoading is true", () => {
    render(
      <AlertDetailPanel
        alert={makeAlert()}
        onClose={jest.fn()}
        onAction={jest.fn()}
        actionLoading={true}
      />,
    );
    expect(screen.getByText("Mark actioned").closest("button")).toBeDisabled();
  });

  it("calls onClose when close button clicked", async () => {
    const user = userEvent.setup();
    const onClose = jest.fn();
    render(
      <AlertDetailPanel
        alert={makeAlert()}
        onClose={onClose}
        onAction={jest.fn()}
        actionLoading={false}
      />,
    );
    await user.click(screen.getByLabelText("close detail panel"));
    expect(onClose).toHaveBeenCalled();
  });

  it("hides optional fields when not present", () => {
    const minimal = makeAlert({
      suggested_action: undefined,
      guideline: undefined,
      patient_id: undefined,
      condition_type: undefined,
      episode_id: undefined,
      encounter_date: undefined,
      created_at: undefined,
      match_percent: undefined,
      needs_review: false,
    });
    render(<AlertDetailPanel alert={minimal} {...defaultProps} />);
    expect(screen.queryByText("Suggested action")).not.toBeInTheDocument();
    expect(screen.queryByText("Guideline")).not.toBeInTheDocument();
    expect(screen.queryByText("Needs review")).not.toBeInTheDocument();
  });
});
