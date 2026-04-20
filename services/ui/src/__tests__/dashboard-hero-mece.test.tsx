/**
 * VT-LEO-AI-531: MECE hero cards on the Care Overview dashboard.
 *
 * Live-renders the dashboard with a stub audit-summary response and
 * asserts the four hero cards display Active / In Review / Cancer
 * Excluded / Confirmed Cancer with the correct counts. Also pins the
 * caption that surfaces the MECE total to the user so the four
 * numbers can never silently drift away from the cohort total.
 */
import React from "react";
import { render, screen, within } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import DashboardPage from "../app/dashboard/page";
import { AnalyticsDateFilterProvider } from "@/context/AnalyticsDateFilterContext";
import {
  fetchAuditSummary,
  fetchEpisodeSummary,
  fetchDiagnosedSummary,
  fetchKPIBenchmarks,
  fetchSafetyNetAlerts,
} from "@/lib/analyticsApi";

jest.mock("@/lib/analyticsApi", () => ({
  fetchAuditSummary: jest.fn(),
  fetchEpisodeSummary: jest.fn(),
  fetchDiagnosedSummary: jest.fn(),
  fetchKPIBenchmarks: jest.fn(),
  fetchSafetyNetAlerts: jest.fn(),
  actionSafetyNetAlert: jest.fn(),
}));
jest.mock("@/context/OrgContext", () => ({
  useOrgId: () => "org-1",
}));
jest.mock(
  "@/components/dashboard/KPICards",
  () =>
    function MockKPI() {
      return <div data-testid="kpi-cards" />;
    },
);
jest.mock(
  "@/components/dashboard/EpisodesByTypeChart",
  () =>
    function MockEpisodes() {
      return <div data-testid="episodes-chart" />;
    },
);
jest.mock(
  "@/components/dashboard/DiagnosedByTypeChart",
  () =>
    function MockDiagnosed() {
      return <div data-testid="diagnosed-chart" />;
    },
);
jest.mock(
  "@/components/dashboard/SafetyNetAlertsSummary",
  () =>
    function MockAlerts() {
      return <div data-testid="alerts-summary" />;
    },
);
jest.mock(
  "@/components/dashboard/LLMSpendPanel",
  () =>
    function MockSpendPanel() {
      return <div data-testid="llm-spend-panel" />;
    },
);
jest.mock(
  "@/components/AreaIntro",
  () =>
    function MockAreaIntro() {
      return <div data-testid="area-intro" />;
    },
);

const theme = createTheme();

function renderDashboard() {
  return render(
    <ThemeProvider theme={theme}>
      <AnalyticsDateFilterProvider>
        <DashboardPage />
      </AnalyticsDateFilterProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  (fetchEpisodeSummary as jest.Mock).mockResolvedValue([]);
  (fetchDiagnosedSummary as jest.Mock).mockResolvedValue([]);
  (fetchKPIBenchmarks as jest.Mock).mockResolvedValue([{}]);
  (fetchSafetyNetAlerts as jest.Mock).mockResolvedValue([]);
  window.localStorage.clear();
});

describe("VT-531-TC-001 MECE hero cards", () => {
  it("renders four cards with values from the audit summary response", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 49,
      active_episodes: 60,
      confirmed_cancers: 49,
      total_cohort_episodes: 141,
      active_lifecycle_episodes: 60,
      in_review_episodes: 20,
      cancer_excluded_episodes: 12,
      confirmed_cancer_episodes: 49,
    });

    renderDashboard();

    // Wait for the data to load before asserting on values (the
    // StatCard renders a skeleton until loading=false).
    const activeCard = await screen.findByLabelText(/^Active: 60$/);
    expect(activeCard).toBeInTheDocument();

    const heroSection = screen.getByRole("region", {
      name: /lifecycle summary/i,
    });

    // Each label appears exactly once inside the hero region.
    expect(within(heroSection).getByText("Active")).toBeInTheDocument();
    expect(within(heroSection).getByText("In Review")).toBeInTheDocument();
    expect(
      within(heroSection).getByText("Cancer Excluded"),
    ).toBeInTheDocument();
    expect(
      within(heroSection).getByText("Confirmed Cancer"),
    ).toBeInTheDocument();

    // And each value renders alongside its label via the StatCard
    // aria-label binding (`${label}: ${value}`).
    expect(
      within(heroSection).getByLabelText(/^In Review: 20$/),
    ).toBeInTheDocument();
    expect(
      within(heroSection).getByLabelText(/^Cancer Excluded: 12$/),
    ).toBeInTheDocument();
    expect(
      within(heroSection).getByLabelText(/^Confirmed Cancer: 49$/),
    ).toBeInTheDocument();
  });

  it("hero region label surfaces the total cohort size", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 49,
      active_episodes: 60,
      confirmed_cancers: 49,
      total_cohort_episodes: 141,
      active_lifecycle_episodes: 60,
      in_review_episodes: 20,
      cancer_excluded_episodes: 12,
      confirmed_cancer_episodes: 49,
    });

    renderDashboard();

    await screen.findByLabelText(/^Active: 60$/);
    const heroSection = screen.getByRole("region", {
      name: /lifecycle summary/i,
    });
    expect(heroSection).toHaveAttribute(
      "aria-label",
      expect.stringMatching(/141/),
    );
  });

  it("renders a caption stating the total cohort size for sighted users", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 49,
      active_episodes: 60,
      confirmed_cancers: 49,
      total_cohort_episodes: 141,
      active_lifecycle_episodes: 60,
      in_review_episodes: 20,
      cancer_excluded_episodes: 12,
      confirmed_cancer_episodes: 49,
    });

    renderDashboard();

    expect(
      await screen.findByText(
        /141 cancer referral pathways across the cohort\./i,
      ),
    ).toBeInTheDocument();
  });

  it("does not render the legacy 'Safety alerts' StatCard in the hero row", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 0,
      active_episodes: 0,
      confirmed_cancers: 0,
      total_cohort_episodes: 0,
      active_lifecycle_episodes: 0,
      in_review_episodes: 0,
      cancer_excluded_episodes: 0,
      confirmed_cancer_episodes: 0,
    });

    renderDashboard();

    // Wait until data has loaded before snapshotting the hero region.
    await screen.findByLabelText(/^Active: 0$/);

    const heroSection = screen.getByRole("region", {
      name: /lifecycle summary/i,
    });
    // 'Safety alerts' is reserved for the alerts card lower down the
    // page; it must NOT appear inside the lifecycle hero region.
    expect(
      within(heroSection).queryByText(/safety alerts/i),
    ).toBeNull();
    expect(
      within(heroSection).queryByText(/cancer referrals/i),
    ).toBeNull();
  });
});

describe("VT-531-TC-002 Hero cards degrade gracefully on missing fields", () => {
  it("falls back to zeros when the new MECE fields are absent", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 7,
      active_episodes: 4,
      confirmed_cancers: 3,
    });

    renderDashboard();

    // Active / In Review / Cancer Excluded fall back to 0; Confirmed
    // Cancer falls back to confirmed_cancers (3) so the historical
    // surface stays meaningful while the API is being upgraded.
    expect(
      await screen.findByLabelText(/^Confirmed Cancer: 3$/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^Active: 0$/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^In Review: 0$/)).toBeInTheDocument();
    expect(
      screen.getByLabelText(/^Cancer Excluded: 0$/),
    ).toBeInTheDocument();
  });
});
