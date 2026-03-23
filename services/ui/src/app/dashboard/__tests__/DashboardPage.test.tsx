import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import DashboardPage from "../page";
import {
  fetchEpisodeSummary,
  fetchDiagnosedSummary,
  fetchKPIBenchmarks,
  fetchSafetyNetAlerts,
} from "@/lib/analyticsApi";

jest.mock("@/lib/analyticsApi", () => ({
  fetchEpisodeSummary: jest.fn(),
  fetchDiagnosedSummary: jest.fn(),
  fetchKPIBenchmarks: jest.fn(),
  fetchSafetyNetAlerts: jest.fn(),
  actionSafetyNetAlert: jest.fn(),
}));
jest.mock("@/context/OrgContext", () => ({
  useOrgId: () => "org-1",
}));
jest.mock("@/components/dashboard/KPICards", () => function MockKPI() {
  return <div data-testid="kpi-cards" />;
});
jest.mock("@/components/dashboard/EpisodesByTypeChart", () => function MockEpisodes() {
  return <div data-testid="episodes-chart" />;
});
jest.mock("@/components/dashboard/DiagnosedByTypeChart", () => function MockDiagnosed() {
  return <div data-testid="diagnosed-chart" />;
});
jest.mock("@/components/dashboard/SafetyNetAlertsSummary", () => function MockAlerts() {
  return <div data-testid="alerts-summary" />;
});
jest.mock("@/components/dashboard/LLMSpendPanel", () => function MockSpendPanel() {
  return <div data-testid="llm-spend-panel" />;
});

const theme = createTheme();

function renderDashboard() {
  return render(
    <ThemeProvider theme={theme}>
      <DashboardPage />
    </ThemeProvider>,
  );
}

describe("DashboardPage", () => {
  beforeEach(() => {
    (fetchEpisodeSummary as jest.Mock).mockResolvedValue([]);
    (fetchDiagnosedSummary as jest.Mock).mockResolvedValue([]);
    (fetchKPIBenchmarks as jest.Mock).mockResolvedValue([{}]);
    (fetchSafetyNetAlerts as jest.Mock).mockResolvedValue([]);
  });

  it("renders h1 heading", async () => {
    renderDashboard();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Overview");
    await waitFor(() => {
      expect(screen.queryByLabelText("Loading referrals chart")).not.toBeInTheDocument();
    });
  });

  it("shows per-section error when a fetch fails", async () => {
    (fetchEpisodeSummary as jest.Mock).mockRejectedValue(new Error("network error"));
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Unable to load referral data.")).toBeInTheDocument();
    });
  });

  it("shows multiple section errors independently", async () => {
    (fetchEpisodeSummary as jest.Mock).mockRejectedValue(new Error("episodes failed"));
    (fetchKPIBenchmarks as jest.Mock).mockRejectedValue(new Error("kpis failed"));
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Unable to load referral data.")).toBeInTheDocument();
      expect(screen.getByText("Unable to load waiting times.")).toBeInTheDocument();
    });
  });

  it("renders charts when all fetches succeed", async () => {
    (fetchEpisodeSummary as jest.Mock).mockResolvedValue([
      { condition_type: "lung", status: "open", count: 5 },
    ]);
    (fetchDiagnosedSummary as jest.Mock).mockResolvedValue([
      { cancer_type: "lung", count: 2 },
    ]);
    (fetchKPIBenchmarks as jest.Mock).mockResolvedValue([{ avg_days_to_referral: 10 }]);
    (fetchSafetyNetAlerts as jest.Mock).mockResolvedValue([{ id: "a1", severity: "low" }]);
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByTestId("episodes-chart")).toBeInTheDocument();
      expect(screen.getByTestId("diagnosed-chart")).toBeInTheDocument();
      expect(screen.getByTestId("kpi-cards")).toBeInTheDocument();
      expect(screen.getByTestId("alerts-summary")).toBeInTheDocument();
    });
  });
});
