import React from "react";
import { render, screen } from "@testing-library/react";
import SafetyNetAlertsSummary from "../SafetyNetAlertsSummary";
import type { SafetyNetAlert } from "@/lib/analyticsApi";

jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) =>
    React.createElement("a", { href }, children);
});

function makeAlert(overrides: Partial<SafetyNetAlert> = {}): SafetyNetAlert {
  return {
    id: "A1",
    type: "Missing safety-netting",
    severity: "high",
    description: "No follow-up documented",
    episode_id: "EP1",
    ...overrides,
  };
}

describe("SafetyNetAlertsSummary", () => {
  const onAction = jest.fn(async () => undefined);

  it("shows empty message when no alerts", () => {
    render(<SafetyNetAlertsSummary alerts={[]} onAction={onAction} />);
    expect(screen.getByText(/No safety alerts at the moment/)).toBeInTheDocument();
  });

  it("renders alerts with severity, type and description", () => {
    const alerts = [
      makeAlert({ id: "A1", severity: "high", type: "Missing safety-netting", description: "No follow-up documented", episode_id: "EP1" }),
      makeAlert({ id: "A2", severity: "medium", type: "Excessive wait", description: "Referral wait > 14 days", episode_id: "EP2" }),
    ];
    render(<SafetyNetAlertsSummary alerts={alerts} onAction={onAction} />);
    expect(screen.getByText("High priority")).toBeInTheDocument();
    expect(screen.getByText("Medium priority")).toBeInTheDocument();
    expect(screen.getByText("No follow-up documented")).toBeInTheDocument();
  });

  it("renders correct number of alert rows", () => {
    const alerts = [
      makeAlert({ id: "A1", episode_id: "EP1", type: "A", severity: "low", description: "D1" }),
      makeAlert({ id: "A2", episode_id: "EP2", type: "B", severity: "critical", description: "D2" }),
      makeAlert({ id: "A3", episode_id: "EP3", type: "C", severity: "medium", description: "D3" }),
    ];
    render(<SafetyNetAlertsSummary alerts={alerts} onAction={onAction} />);
    expect(screen.getByText("D1")).toBeInTheDocument();
    expect(screen.getByText("D2")).toBeInTheDocument();
    expect(screen.getByText("D3")).toBeInTheDocument();
  });

  it("shows patient ID and cancer type when available", () => {
    const alerts = [
      makeAlert({ patient_id: "P001", condition_type: "Colorectal" }),
    ];
    render(<SafetyNetAlertsSummary alerts={alerts} onAction={onAction} />);
    expect(screen.getByText(/Colorectal/)).toBeInTheDocument();
  });

  it("renders 'View all alerts' link to /css", () => {
    const alerts = [makeAlert()];
    render(<SafetyNetAlertsSummary alerts={alerts} onAction={onAction} />);
    const link = screen.getByText("View all safety alerts →").closest("a");
    expect(link).toHaveAttribute("href", "/care/safety-netting");
  });
});
