import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SafetyNetAlertsPage from "../page";
import type { SafetyNetAlert } from "@/lib/analyticsApi";

jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) =>
    React.createElement("a", { href }, children);
});

jest.mock("@/context/OrgContext", () => ({
  useOrgId: () => "org-1",
}));

jest.mock("@/lib/analyticsApi", () => ({
  fetchSafetyNetAlerts: jest.fn(),
  actionSafetyNetAlert: jest.fn(),
}));

import { fetchSafetyNetAlerts, actionSafetyNetAlert } from "@/lib/analyticsApi";

function makeAlert(overrides: Partial<SafetyNetAlert> = {}): SafetyNetAlert {
  return {
    id: "A1",
    type: "missing_safety_netting",
    severity: "high",
    description: "No safety-netting language found",
    patient_id: "P001",
    condition_type: "Colorectal",
    episode_id: "EP-1",
    actioned: false,
    ...overrides,
  };
}

const ALERTS: SafetyNetAlert[] = [
  makeAlert({ id: "A1", severity: "critical", type: "investigation_gap", description: "No investigation after referral", patient_id: "P001", condition_type: "Lung" }),
  makeAlert({ id: "A2", severity: "high", type: "missing_safety_netting", description: "No safety-net language", patient_id: "P002", condition_type: "Colorectal" }),
  makeAlert({ id: "A3", severity: "medium", type: "excessive_referral_wait", description: "Wait 21 days", patient_id: "P003", actioned: true }),
  makeAlert({ id: "A4", severity: "low", type: "missing_safety_netting", description: "Minor gap", patient_id: "P004" }),
];

describe("SafetyNetAlertsPage", () => {
  beforeEach(() => {
    (fetchSafetyNetAlerts as jest.Mock).mockResolvedValue(ALERTS);
    (actionSafetyNetAlert as jest.Mock).mockResolvedValue({ success: true });
  });

  it("renders page title and subtitle", async () => {
    render(<SafetyNetAlertsPage />);
    expect(screen.getByText("Safety Netting")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Clinical safety signals/)).toBeInTheDocument();
    });
  });

  it("shows summary cards after loading", async () => {
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("Total alerts")).toBeInTheDocument();
    });
    expect(screen.getByText("Critical / High")).toBeInTheDocument();
  });

  it("displays correct total count in summary card", async () => {
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("Total alerts")).toBeInTheDocument();
    });
    const totalCard = screen.getByText("Total alerts").closest("[class*=CardContent]")!;
    expect(within(totalCard).getByText("4")).toBeInTheDocument();
  });

  it("defaults to grouped view and outstanding filter", async () => {
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("3 patients, 3 alerts")).toBeInTheDocument();
    });
    expect(screen.getByText("P001")).toBeInTheDocument();
    expect(screen.getByText("P002")).toBeInTheDocument();
    expect(screen.queryByText("P003")).not.toBeInTheDocument();
  });

  it("switches to flat view and shows flat count text", async () => {
    const user = userEvent.setup();
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("3 patients, 3 alerts")).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText("flat list"));
    expect(screen.getByText("Showing 3 of 4 alerts")).toBeInTheDocument();
  });

  it("shows all alerts when 'All' filter is selected", async () => {
    const user = userEvent.setup();
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("3 patients, 3 alerts")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByText("4 patients, 4 alerts")).toBeInTheDocument();
  });

  it("filters by severity chip", async () => {
    const user = userEvent.setup();
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("critical (1)")).toBeInTheDocument();
    });
    await user.click(screen.getByText("critical (1)"));
    expect(screen.getByText("1 patients, 1 alerts")).toBeInTheDocument();
  });

  it("opens detail panel when clicking an alert row cell", async () => {
    const user = userEvent.setup();
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("investigation_gap")).toBeInTheDocument();
    });
    await user.click(screen.getByText("investigation_gap"));
    expect(screen.getByText("Alert Detail")).toBeInTheDocument();
    expect(
      screen.getAllByText("No investigation after referral").length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("calls actionSafetyNetAlert when marking alert as actioned", async () => {
    const user = userEvent.setup();
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("investigation_gap")).toBeInTheDocument();
    });
    await user.click(screen.getByText("investigation_gap"));
    await user.click(screen.getByText("Mark actioned"));
    expect(actionSafetyNetAlert).toHaveBeenCalledWith("A1", true);
  });

  it("handles fetch failure gracefully", async () => {
    (fetchSafetyNetAlerts as jest.Mock).mockRejectedValue(new Error("Network error"));
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("Total alerts")).toBeInTheDocument();
    });
    const totalCard = screen.getByText("Total alerts").closest("[class*=CardContent]")!;
    expect(within(totalCard).getByText("0")).toBeInTheDocument();
  });

  it("filters by search text", async () => {
    const user = userEvent.setup();
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("P001")).toBeInTheDocument();
    });
    await user.type(
      screen.getByPlaceholderText(/Search by patient/),
      "Lung",
    );
    expect(screen.getByText("1 patients, 1 alerts")).toBeInTheDocument();
    expect(screen.getByText("P001")).toBeInTheDocument();
    expect(screen.queryByText("P002")).not.toBeInTheDocument();
  });

  it("closes detail panel when close button clicked", async () => {
    const user = userEvent.setup();
    render(<SafetyNetAlertsPage />);
    await waitFor(() => {
      expect(screen.getByText("investigation_gap")).toBeInTheDocument();
    });
    await user.click(screen.getByText("investigation_gap"));
    expect(screen.getByText("Alert Detail")).toBeInTheDocument();
    await user.click(screen.getByLabelText("close detail panel"));
    expect(screen.queryByText("Alert Detail")).not.toBeInTheDocument();
  });
});
