/**
 * Pins the new behaviour of <SafetyNettingSection>:
 *
 *   1. The legacy "2018 Baseline by Cancer Type — Safety Netting
 *      Positive Contribution (%)" grid was removed, because per-cancer-
 *      type contribution is NOT the question Section 8 is answering.
 *   2. Each live year card has an "Open detail" zoom button that
 *      opens an EvolutionDetailDialog containing the four-bucket
 *      signal-strength breakdown (strong / medium / advice-only /
 *      none) for that year. This is the right drill for "did we
 *      record safety netting?".
 */
import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import SafetyNettingSection from "../SafetyNettingSection";
import type {
  AuditSafetyNetting,
  AuditSectionResult,
} from "@/lib/analyticsApi";

jest.mock("@/context/OrgContext", () => ({
  useOrgId: () => "demo-practice",
}));
jest.mock("@/context/AuditBenchmarkOverlayContext", () => ({
  useAuditBenchmarkOverlay: () => ({
    showCancerAlliance: false,
    showAllPatients: false,
  }),
}));

// useAuditYearWindows fires off network calls. Mock it directly so the
// test owns the year cards' state without going through fetch.
jest.mock("../_useAuditYearWindows", () => {
  const actual = jest.requireActual("../_useAuditYearWindows");
  return {
    ...actual,
    useAuditYearWindows: jest.fn(),
  };
});

import { useAuditYearWindows, BASELINE_YEAR } from "../_useAuditYearWindows";

const sampleData: AuditSafetyNetting = {
  total_episodes: 42,
  recorded_n: 20,
  recorded_pct: 47.6,
  not_recorded_pct: 52.4,
  signal_counts: { strong: 13, medium: 7, advice_only: 3, none: 19 },
  signal_pct: { strong: 31.0, medium: 16.7, advice_only: 7.1, none: 45.2 },
  strong_n: 13,
  strong_pct: 31.0,
};

const sampleResult: AuditSectionResult<AuditSafetyNetting> = {
  scopes: { practice: sampleData, alliance_live: null, england_live: null },
  benchmark: {
    set_id: "bm-2018",
    set_name: "2018 NCDA",
    metrics: {
      "safety_netting.recorded_pct": { national: 78.2, alliance: 81.0 },
    },
  },
};

beforeEach(() => {
  (useAuditYearWindows as jest.Mock).mockReturnValue({
    liveYears: [
      {
        year: 2024,
        loading: false,
        data: { ...sampleData, recorded_pct: 12.5, recorded_n: 5, total_episodes: 40 },
        error: null,
      },
      { year: 2025, loading: false, data: sampleData, error: null },
      {
        year: 2026,
        loading: false,
        data: {
          ...sampleData,
          recorded_pct: 0,
          recorded_n: 0,
          signal_counts: { strong: 0, medium: 0, advice_only: 0, none: 0 },
          signal_pct: { strong: 0, medium: 0, advice_only: 0, none: 0 },
          total_episodes: 0,
        },
        error: null,
      },
    ],
    anyLoading: false,
    allYearsEmpty: false,
  });
});

describe("SafetyNettingSection (post-redesign)", () => {
  it("renders the section title and the 2018 baseline card", () => {
    render(<SafetyNettingSection result={sampleResult} loading={false} />);
    expect(screen.getByText("Safety Netting")).toBeInTheDocument();
    expect(screen.getByText(String(BASELINE_YEAR))).toBeInTheDocument();
  });

  it("does NOT render the by-cancer-type contribution grid anymore", () => {
    render(<SafetyNettingSection result={sampleResult} loading={false} />);
    // Heading from the old CancerTypeBenchmarkGrid block must be gone.
    expect(
      screen.queryByText(/2018 Baseline by Cancer Type/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Positive Contribution \(%\)/i),
    ).not.toBeInTheDocument();
  });

  it("renders an Open-detail zoom button on each live year card with data", () => {
    render(<SafetyNettingSection result={sampleResult} loading={false} />);
    // Two of the three live years have non-empty data (2024 and 2025).
    // The 2026 card is empty (total_episodes: 0) so the underlying
    // EvolutionYearCard intentionally hides the zoom button -- there
    // is nothing to break down for an empty year.
    const zoomButtons = screen.getAllByRole("button", {
      name: /Open .* safety-netting signal-strength breakdown/i,
    });
    expect(zoomButtons).toHaveLength(2);
  });

  it("opens the signal-strength dialog when a year card's zoom button is clicked", () => {
    render(<SafetyNettingSection result={sampleResult} loading={false} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /Open 2025 safety-netting signal-strength breakdown/i,
      }),
    );

    const dialog = screen.getByRole("dialog");
    const within$ = within(dialog);

    expect(
      within$.getByText(/Safety netting -- 2025 signal-strength breakdown/i),
    ).toBeInTheDocument();

    // Headline tile -- strong + medium = 47.6%.
    expect(within$.getByText("47.6%")).toBeInTheDocument();
    expect(
      within$.getByText("20 of 42 confirmed cancers (strong + medium)"),
    ).toBeInTheDocument();

    // Strict tile -- strong only = 31.0%.
    expect(within$.getByText("31.0%")).toBeInTheDocument();
    expect(
      within$.getByText("13 of 42 confirmed cancers (strong only)"),
    ).toBeInTheDocument();

    // Each signal-strength row exposes its share via a progressbar
    // role; pin the four expected aria labels.
    expect(within$.getByRole("progressbar", { name: /Strong/ })).toBeInTheDocument();
    expect(within$.getByRole("progressbar", { name: /Medium/ })).toBeInTheDocument();
    expect(
      within$.getByRole("progressbar", { name: /Advice-only/ }),
    ).toBeInTheDocument();
    expect(within$.getByRole("progressbar", { name: /^None/ })).toBeInTheDocument();
  });

  it("does not render a zoom button on a year card with zero episodes", () => {
    // 2026 is the empty year in the fixture above -- its underlying
    // EvolutionYearCard intentionally hides the zoom button so the
    // user is not invited to open an empty drill.
    render(<SafetyNettingSection result={sampleResult} loading={false} />);
    expect(
      screen.queryByRole("button", {
        name: /Open 2026 safety-netting signal-strength breakdown/i,
      }),
    ).not.toBeInTheDocument();
  });
});
