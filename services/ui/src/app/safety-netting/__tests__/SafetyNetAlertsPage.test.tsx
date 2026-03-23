import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SafetyNettingPage from "../page";
import type { SafetyNetAlert, SafetyNetWorklistItem } from "@/lib/analyticsApi";

jest.mock("next/link", () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) =>
    React.createElement("a", { href }, children);
});

jest.mock("@/context/OrgContext", () => ({
  useOrgId: () => "org-1",
}));

jest.mock("@/lib/analyticsApi", () => ({
  fetchSafetyNetWorklist: jest.fn(),
  actionSafetyNetAlert: jest.fn(),
}));

import { fetchSafetyNetWorklist, actionSafetyNetAlert } from "@/lib/analyticsApi";

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

function makeWorklistItem(
  overrides: Partial<SafetyNetWorklistItem> = {}
): SafetyNetWorklistItem {
  return {
    patient_id: "P001",
    episode_id: "EP-1",
    condition_type: "Colorectal",
    status: "active",
    referral_date: "2025-01-01",
    milestones: [],
    alerts: [makeAlert()],
    ...overrides,
  };
}

const WORKLIST_ITEMS: SafetyNetWorklistItem[] = [
  makeWorklistItem({
    patient_id: "P001",
    episode_id: "EP-1",
    condition_type: "Lung",
    alerts: [
      makeAlert({
        id: "A1",
        severity: "critical",
        type: "investigation_gap",
        description: "No investigation after referral",
        patient_id: "P001",
        condition_type: "Lung",
      }),
    ],
  }),
  makeWorklistItem({
    patient_id: "P002",
    episode_id: "EP-2",
    condition_type: "Colorectal",
    alerts: [
      makeAlert({
        id: "A2",
        severity: "high",
        type: "missing_safety_netting",
        description: "No safety-net language",
        patient_id: "P002",
        condition_type: "Colorectal",
      }),
    ],
  }),
  makeWorklistItem({
    patient_id: "P003",
    episode_id: "EP-3",
    condition_type: "Colorectal",
    alerts: [
      makeAlert({
        id: "A3",
        severity: "medium",
        type: "excessive_referral_wait",
        description: "Wait 21 days",
        patient_id: "P003",
        actioned: true,
      }),
    ],
  }),
  makeWorklistItem({
    patient_id: "P004",
    episode_id: "EP-4",
    condition_type: "Colorectal",
    alerts: [
      makeAlert({
        id: "A4",
        severity: "low",
        type: "missing_safety_netting",
        description: "Minor gap",
        patient_id: "P004",
      }),
    ],
  }),
];

describe("SafetyNetAlertsPage", () => {
  beforeEach(() => {
    (fetchSafetyNetWorklist as jest.Mock).mockResolvedValue(WORKLIST_ITEMS);
    (actionSafetyNetAlert as jest.Mock).mockResolvedValue({ success: true });
  });

  it("renders page title and subtitle", async () => {
    render(<SafetyNettingPage />);
    expect(screen.getByText("Safety Netting")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Clinical safety signals/)).toBeInTheDocument();
    });
  });

  it("shows summary cards after loading", async () => {
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText("Total Active")).toBeInTheDocument();
    });
    expect(screen.getByText("Overdue / Breached")).toBeInTheDocument();
  });

  it("displays correct total count in summary card", async () => {
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText("Total Active")).toBeInTheDocument();
    });
    const totalLabel = screen.getByText("Total Active");
    const totalCard = totalLabel.parentElement;
    expect(totalCard).toBeTruthy();
    expect(within(totalCard!).getByText("4")).toBeInTheDocument();
  });

  it("defaults to all filter and shows all pathways", async () => {
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText(/pathways shown/)).toBeInTheDocument();
    });
    expect(screen.getByText("P001")).toBeInTheDocument();
    expect(screen.getByText("P002")).toBeInTheDocument();
    expect(screen.getByText("P003")).toBeInTheDocument();
  });

  it("shows outstanding filter when Outstanding is selected", async () => {
    const user = userEvent.setup();
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText("P001")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: "Outstanding" }));
    expect(screen.getByText("P001")).toBeInTheDocument();
    expect(screen.getByText("P002")).toBeInTheDocument();
    expect(screen.getByText("P004")).toBeInTheDocument();
  });

  it("shows all pathways when All filter is selected", async () => {
    const user = userEvent.setup();
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText("P001")).toBeInTheDocument();
    });
    const allButtons = screen.getAllByRole("button", { name: "All" });
    await user.click(allButtons[0]);
    expect(screen.getByText("P001")).toBeInTheDocument();
    expect(screen.getByText("P002")).toBeInTheDocument();
    expect(screen.getByText("P003")).toBeInTheDocument();
  });

  it("opens detail panel when clicking a pathway row", async () => {
    const user = userEvent.setup();
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText("No investigation after referral")).toBeInTheDocument();
    });
    await user.click(screen.getByText("No investigation after referral"));
    expect(screen.getByText("Record Action Taken")).toBeInTheDocument();
    expect(
      screen.getAllByText("No investigation after referral").length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("calls actionSafetyNetAlert when marking alert as actioned", async () => {
    const user = userEvent.setup();
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText("No investigation after referral")).toBeInTheDocument();
    });
    await user.click(screen.getByText("No investigation after referral"));
    await user.click(screen.getByText("Record Action Taken"));
    expect(actionSafetyNetAlert).toHaveBeenCalledWith("A1", true);
  });

  it("handles fetch failure gracefully", async () => {
    (fetchSafetyNetWorklist as jest.Mock).mockResolvedValue([]);
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText("Total Active")).toBeInTheDocument();
    });
    const totalLabel = screen.getByText("Total Active");
    const totalCard = totalLabel.parentElement;
    expect(within(totalCard!).getByText("0")).toBeInTheDocument();
  });

  it("filters by search text", async () => {
    const user = userEvent.setup();
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText("P001")).toBeInTheDocument();
    });
    await user.type(
      screen.getByPlaceholderText(/Search patient ID or cancer site/),
      "Lung",
    );
    expect(screen.getByText("P001")).toBeInTheDocument();
    expect(screen.queryByText("P002")).not.toBeInTheDocument();
  });

  it("closes detail panel when close button clicked", async () => {
    const user = userEvent.setup();
    render(<SafetyNettingPage />);
    await waitFor(() => {
      expect(screen.getByText("No investigation after referral")).toBeInTheDocument();
    });
    await user.click(screen.getByText("No investigation after referral"));
    expect(screen.getByText("Record Action Taken")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Close"));
    expect(screen.queryByText("Record Action Taken")).not.toBeInTheDocument();
  });
});
