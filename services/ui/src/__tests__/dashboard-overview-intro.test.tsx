import React from "react";
import fs from "fs";
import path from "path";
import { render, screen, waitFor } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import DashboardPage, {
  CARE_OVERVIEW_INTRO,
  CARE_OVERVIEW_CHART_COPY,
  CARE_OVERVIEW_SUMMARY_LABELS,
} from "../app/dashboard/page";
import { AnalyticsDateFilterProvider } from "@/context/AnalyticsDateFilterContext";
import { fleschKincaidGrade } from "../lib/readability";
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
  (fetchAuditSummary as jest.Mock).mockResolvedValue({
    total_episodes: 0,
    active_episodes: 0,
    confirmed_cancers: 0,
  });
  (fetchEpisodeSummary as jest.Mock).mockResolvedValue([]);
  (fetchDiagnosedSummary as jest.Mock).mockResolvedValue([]);
  (fetchKPIBenchmarks as jest.Mock).mockResolvedValue([{}]);
  (fetchSafetyNetAlerts as jest.Mock).mockResolvedValue([]);
  window.localStorage.clear();
});

describe("VT-123-TC-001 PageIntro renders on Care Overview", () => {
  it("renders with screenId='care-overview' and h2 heading", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(
        screen.getByText(/cancer referrals and find cases/i),
      ).toBeInTheDocument();
    });
    const intro = document.getElementById("care-overview-intro-title");
    expect(intro).not.toBeNull();
    expect(intro?.tagName.toLowerCase()).toBe("h2");
  });
});

describe("VT-123-TC-002 PageIntro copy passes Flesch-Kincaid grade <=9", () => {
  it.each(Object.entries(CARE_OVERVIEW_INTRO))(
    "%s copy reads at grade <=9",
    (_key, value) => {
      expect(fleschKincaidGrade(value)).toBeLessThanOrEqual(9);
    },
  );
});

describe("VT-123-TC-003 Summary StatCard labels are sentence case", () => {
  it("exports the four sentence-case labels", () => {
    expect(CARE_OVERVIEW_SUMMARY_LABELS).toEqual({
      referrals: "Cancer referrals",
      active: "Active cases",
      confirmed: "Confirmed cancers",
      alerts: "Safety alerts",
    });
  });

  it("renders labels without shouty uppercase tracking", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Cancer referrals")).toBeInTheDocument();
    });
    expect(screen.getByText("Active cases")).toBeInTheDocument();
    expect(screen.getByText("Confirmed cancers")).toBeInTheDocument();
    expect(screen.getByText("Safety alerts")).toBeInTheDocument();
  });

  it("page source does not apply textTransform: 'uppercase' to the StatCard label", () => {
    const pagePath = path.resolve(
      __dirname,
      "..",
      "app",
      "dashboard",
      "page.tsx",
    );
    const source = fs.readFileSync(pagePath, "utf8");
    expect(source).not.toMatch(/textTransform:\s*["']uppercase["']/);
  });
});

describe("VT-123-TC-004 Chart card descriptions pass Flesch-Kincaid grade <=9", () => {
  it.each(Object.entries(CARE_OVERVIEW_CHART_COPY))(
    "%s description reads at grade <=9",
    (_key, entry) => {
      expect(fleschKincaidGrade(entry.description)).toBeLessThanOrEqual(9);
    },
  );
});
