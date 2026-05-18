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

  it("each MECE card is a link into Mission Control filtered by lifecycle bucket", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 141,
      active_episodes: 60,
      confirmed_cancers: 45,
      total_cohort_episodes: 141,
      total_cohort_patients: 97,
      total_cohort_episodes_all: 144,
      active_lifecycle_episodes: 28,
      in_review_episodes: 37,
      cancer_excluded_episodes: 31,
      confirmed_cancer_episodes: 45,
    });

    renderDashboard();
    await screen.findByLabelText(/^Active: 28$/);

    // Every MECE card must render as a real link with the matching
    // lifecycle_bucket query parameter -- this is what guarantees a
    // click-through opens the same cohort the headline number used.
    const expected: Record<string, string> = {
      Active: "active",
      "In Review": "in_review",
      "Cancer Excluded": "cancer_excluded",
      "Confirmed Cancer": "confirmed_cancer",
    };
    for (const [label, bucket] of Object.entries(expected)) {
      const heroSection = screen.getByRole("region", {
        name: /lifecycle summary/i,
      });
      const link = within(heroSection)
        .getByText(label)
        .closest("a");
      expect(link).not.toBeNull();
      expect(link?.getAttribute("href")).toMatch(/^\/patients\?/);
      expect(link?.getAttribute("href")).toContain(`lifecycle_bucket=${bucket}`);
    }
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

describe("VT-531-TC-003 Cohort summary card", () => {
  it("renders 'X of Y patients' + total pathways as a clickable card", async () => {
    // 97 of 107 patients have a cancer pathway; the dashboard cohort
    // denominator (107) MUST match Mission Control's denominator
    // (DI-CA1B4C6E / R-D32A2AC2). Before this fix the dashboard
    // silently dropped patients-without-pathway and disagreed with
    // Mission Control by 10 patients.
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 141,
      active_episodes: 60,
      confirmed_cancers: 45,
      total_cohort_episodes: 141,
      total_cohort_patients: 107,
      total_cohort_patients_with_pathway: 97,
      patients_without_pathway: 10,
      total_cohort_episodes_all: 144,
      active_lifecycle_episodes: 28,
      in_review_episodes: 37,
      cancer_excluded_episodes: 31,
      confirmed_cancer_episodes: 45,
    });

    renderDashboard();

    // Wait for the data to land (StatCard renders skeletons until then).
    await screen.findByLabelText(/^Active: 28$/);

    const cohortRegion = screen.getByRole("region", {
      name: /cohort summary/i,
    });
    // Both with-pathway (97) and total (107) denominators must be
    // visible to sighted users so the discrepancy can be SEEN, not
    // hidden. The text spans two elements ("97 " plus "<span>of 107</span>")
    // so we assert on the cohort region's normalised textContent
    // rather than searching for a single text node.
    expect(cohortRegion.textContent).toMatch(/97/);
    expect(cohortRegion.textContent).toMatch(/of 107/);
    expect(cohortRegion.textContent).toMatch(/144/);

    // The card itself is a real link to the unfiltered patient list.
    const links = within(cohortRegion).getAllByRole("link");
    const cardLink = links.find(
      (a) =>
        a.getAttribute("aria-label")?.match(/^Cohort:/) !== null,
    );
    expect(cardLink).toBeDefined();
    expect(cardLink?.getAttribute("href")).toMatch(/^\/patients\?/);
    expect(cardLink?.getAttribute("href")).not.toContain(
      "lifecycle_bucket=",
    );
    expect(cardLink).toHaveAccessibleName(
      /Cohort: 97 of 107 patients have a cancer pathway, 144 cancer pathways in total/i,
    );
  });

  it("renders a clickable 'X have no cancer pathway yet' caption that deep-links to lifecycle_bucket=no_pathway", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 141,
      active_episodes: 60,
      confirmed_cancers: 45,
      total_cohort_episodes: 141,
      total_cohort_patients: 107,
      total_cohort_patients_with_pathway: 97,
      patients_without_pathway: 10,
      total_cohort_episodes_all: 144,
      active_lifecycle_episodes: 28,
      in_review_episodes: 37,
      cancer_excluded_episodes: 31,
      confirmed_cancer_episodes: 45,
    });

    renderDashboard();

    // Wait for data to load (the no-pathway caption is hidden while
    // patientsWithoutPathway is undefined / 0 during loading).
    await screen.findByLabelText(/^Active: 28$/);

    const cohortRegion = screen.getByRole("region", {
      name: /cohort summary/i,
    });
    // The clickable caption MUST be rendered as a real <a> with
    // lifecycle_bucket=no_pathway so the click opens exactly the 10
    // patients-without-pathway behind the cohort denominator.
    const noPathwayLink = within(cohortRegion).getByRole("link", {
      name: /no cancer pathway yet/i,
    });
    expect(noPathwayLink.getAttribute("href")).toMatch(/^\/patients\?/);
    expect(noPathwayLink.getAttribute("href")).toContain(
      "lifecycle_bucket=no_pathway",
    );
    // Visible text must explicitly state the count so clinicians see
    // exactly how many patients they are about to review.
    expect(noPathwayLink.textContent).toMatch(
      /10 patients have no cancer pathway yet/i,
    );
  });

  it("hides the no-pathway caption when every patient has a cancer pathway", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 141,
      active_episodes: 60,
      confirmed_cancers: 45,
      total_cohort_episodes: 141,
      total_cohort_patients: 97,
      total_cohort_patients_with_pathway: 97,
      patients_without_pathway: 0,
      total_cohort_episodes_all: 141,
      active_lifecycle_episodes: 28,
      in_review_episodes: 37,
      cancer_excluded_episodes: 31,
      confirmed_cancer_episodes: 45,
    });

    renderDashboard();

    await screen.findByLabelText(/^Active: 28$/);
    expect(screen.queryByText(/no cancer pathway yet/i)).toBeNull();
  });

  it("shows an admin-only footnote when totals exceed the MECE sum", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 141,
      active_episodes: 60,
      confirmed_cancers: 45,
      total_cohort_episodes: 141,
      total_cohort_patients: 107,
      total_cohort_patients_with_pathway: 97,
      patients_without_pathway: 10,
      total_cohort_episodes_all: 144,
      active_lifecycle_episodes: 28,
      in_review_episodes: 37,
      cancer_excluded_episodes: 31,
      confirmed_cancer_episodes: 45,
    });

    renderDashboard();

    expect(
      await screen.findByText(
        /3 admin-only episodes are not shown in the four cards above\./i,
      ),
    ).toBeInTheDocument();
  });

  it("hides the admin-only footnote when totals match the MECE sum", async () => {
    (fetchAuditSummary as jest.Mock).mockResolvedValue({
      total_episodes: 141,
      active_episodes: 60,
      confirmed_cancers: 45,
      total_cohort_episodes: 141,
      total_cohort_patients: 107,
      total_cohort_patients_with_pathway: 97,
      patients_without_pathway: 10,
      total_cohort_episodes_all: 141,
      active_lifecycle_episodes: 28,
      in_review_episodes: 37,
      cancer_excluded_episodes: 31,
      confirmed_cancer_episodes: 45,
    });

    renderDashboard();

    await screen.findByLabelText(/^Active: 28$/);
    expect(
      screen.queryByText(/admin-only episodes are not shown/i),
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
