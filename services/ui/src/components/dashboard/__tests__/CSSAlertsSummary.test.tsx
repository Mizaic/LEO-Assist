import React from "react";
import { render, screen } from "@testing-library/react";
import CSSAlertsSummary from "../CSSAlertsSummary";
import type { CSSAlert } from "@/lib/analyticsApi";

jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) =>
    React.createElement("a", { href }, children);
});

function makeAlert(overrides: Partial<CSSAlert> = {}): CSSAlert {
  return {
    id: "A1",
    type: "Missing safety-netting",
    severity: "high",
    description: "No follow-up documented",
    episode_id: "EP1",
    ...overrides,
  };
}

describe("CSSAlertsSummary", () => {
  it("shows empty message when no alerts", () => {
    render(<CSSAlertsSummary alerts={[]} />);
    expect(screen.getByText(/No safety netting alerts/)).toBeInTheDocument();
  });

  it("renders alerts with severity, type and description", () => {
    const alerts = [
      makeAlert({ id: "A1", severity: "high", type: "Missing safety-netting", description: "No follow-up documented", episode_id: "EP1" }),
      makeAlert({ id: "A2", severity: "medium", type: "Excessive wait", description: "Referral wait > 14 days", episode_id: "EP2" }),
    ];
    render(<CSSAlertsSummary alerts={alerts} />);
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText("medium")).toBeInTheDocument();
    expect(screen.getByText("Missing safety-netting")).toBeInTheDocument();
    expect(screen.getByText("No follow-up documented")).toBeInTheDocument();
    expect(screen.getByText("EP1")).toBeInTheDocument();
  });

  it("renders correct number of alert rows", () => {
    const alerts = [
      makeAlert({ id: "A1", episode_id: "EP1", type: "A", severity: "low", description: "D1" }),
      makeAlert({ id: "A2", episode_id: "EP2", type: "B", severity: "critical", description: "D2" }),
      makeAlert({ id: "A3", episode_id: "EP3", type: "C", severity: "medium", description: "D3" }),
    ];
    render(<CSSAlertsSummary alerts={alerts} />);
    expect(screen.getByText("EP1")).toBeInTheDocument();
    expect(screen.getByText("EP2")).toBeInTheDocument();
    expect(screen.getByText("EP3")).toBeInTheDocument();
  });

  it("shows patient ID and cancer type when available", () => {
    const alerts = [
      makeAlert({ patient_id: "P001", cancer_type: "Colorectal" }),
    ];
    render(<CSSAlertsSummary alerts={alerts} />);
    expect(screen.getByText(/P001/)).toBeInTheDocument();
    expect(screen.getByText(/Colorectal/)).toBeInTheDocument();
  });

  it("renders 'View all alerts' link to /css", () => {
    const alerts = [makeAlert()];
    render(<CSSAlertsSummary alerts={alerts} />);
    const link = screen.getByText("View all alerts").closest("a");
    expect(link).toHaveAttribute("href", "/css");
  });
});
