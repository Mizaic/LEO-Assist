/**
 * Pins the structure of <PriorConsultationsSection>:
 *
 *   1. Section title and 2018 baseline card render even when the
 *      benchmark set has no published value for
 *      ``prior_consultations.multiple_consultations_pct`` (the
 *      EvolutionYearCard handles the missing-value case gracefully
 *      with an em-dash).
 *   2. Each live year card with data has an "Open detail" zoom button
 *      that opens an EvolutionDetailDialog containing the
 *      distribution histogram (0 / 1 / 2-3 / 4-6 / 7+) AND the top
 *      NCDA factor codes proposed by the LLM.
 *   3. Empty years (total_episodes: 0) do NOT render a zoom button.
 *   4. The dialog footer surfaces the cohort-level Haiku spend so the
 *      auditor can see what the LLM enrichment cost.
 */
import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";

import PriorConsultationsSection from "../PriorConsultationsSection";
import type {
  AuditPriorConsultations,
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

jest.mock("../_useAuditYearWindows", () => {
  const actual = jest.requireActual("../_useAuditYearWindows");
  return {
    ...actual,
    useAuditYearWindows: jest.fn(),
  };
});

import { useAuditYearWindows, BASELINE_YEAR } from "../_useAuditYearWindows";

const sampleData: AuditPriorConsultations = {
  total_episodes: 30,
  enriched_n: 28,
  enriched_pct: 93.3,
  multiple_consultations_pct: 60.0,
  multiple_consultations_n: 18,
  buckets:     { "0": 5, "1": 7, "2-3": 9, "4-6": 6, "7+": 3 },
  buckets_pct: { "0": 16.7, "1": 23.3, "2-3": 30.0, "4-6": 20.0, "7+": 10.0 },
  mean_per_episode: {
    total: 2.29,
    f2f: 1.05,
    phone: 0.6,
    nurse: 0.2,
    email: 0.1,
    specialist_clinic: 0.15,
    home_visit: 0.0,
    phlebotomy: 0.19,
    result_review: 0.85,
  },
  total_consultations: 64,
  unrelated_filtered_total: 12,
  top_factors: [
    { factor: "different_initial_diagnosis", n: 8 },
    { factor: "consultations_to_discuss_test_results", n: 5 },
    { factor: "reassurance_from_negative_investigation", n: 4 },
  ],
  llm_cost_usd: 0.7321,
  llm_input_tokens: 350000,
  llm_output_tokens: 80000,
  llm_calls: 28,
};

const sampleResult: AuditSectionResult<AuditPriorConsultations> = {
  scopes: { practice: sampleData, alliance_live: null, england_live: null },
  benchmark: null,
};

beforeEach(() => {
  (useAuditYearWindows as jest.Mock).mockReturnValue({
    liveYears: [
      {
        year: 2024,
        loading: false,
        data: { ...sampleData, multiple_consultations_pct: 48.0, total_episodes: 25 },
        error: null,
      },
      { year: 2025, loading: false, data: sampleData, error: null },
      {
        year: 2026,
        loading: false,
        data: {
          ...sampleData,
          multiple_consultations_pct: 0,
          multiple_consultations_n: 0,
          buckets:     { "0": 0, "1": 0, "2-3": 0, "4-6": 0, "7+": 0 },
          buckets_pct: { "0": 0, "1": 0, "2-3": 0, "4-6": 0, "7+": 0 },
          total_episodes: 0,
          enriched_n: 0,
        },
        error: null,
      },
    ],
    anyLoading: false,
    allYearsEmpty: false,
  });
});

describe("PriorConsultationsSection", () => {
  it("renders the section title and the 2018 baseline card", () => {
    render(<PriorConsultationsSection result={sampleResult} loading={false} />);
    expect(
      screen.getByText("Prior Consultations (NCDA Section 7)"),
    ).toBeInTheDocument();
    expect(screen.getByText(String(BASELINE_YEAR))).toBeInTheDocument();
  });

  it("renders an Open-detail zoom button on each live year card with data", () => {
    render(<PriorConsultationsSection result={sampleResult} loading={false} />);
    // 2024 + 2025 have data; 2026 has total_episodes: 0 -> no button.
    const zoomButtons = screen.getAllByRole("button", {
      name: /open \d{4} prior-consultations breakdown/i,
    });
    expect(zoomButtons).toHaveLength(2);
  });

  it("opens the dialog with the histogram + top NCDA factors", () => {
    render(<PriorConsultationsSection result={sampleResult} loading={false} />);

    const button2025 = screen.getByRole("button", {
      name: /open 2025 prior-consultations breakdown/i,
    });
    fireEvent.click(button2025);

    const dialog = screen.getByRole("dialog");

    // Title + headline tile.
    expect(
      within(dialog).getByText(/Prior consultations -- 2025 breakdown/i),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/Multiple consultations \(.+2\)/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/60\.0%/)).toBeInTheDocument();
    expect(within(dialog).getByText(/18 of 30 confirmed cancers/)).toBeInTheDocument();

    // Distribution histogram includes the >=2 bucket label.
    expect(
      within(dialog).getByText(/2-3 consultations \(NCDA "multiple"\)/),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/7\+ consultations/)).toBeInTheDocument();

    // Top NCDA factors are surfaced with the human-readable label.
    expect(
      within(dialog).getByText(/Symptoms suggested different initial diagnosis/i),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Consultation\(s\) to discuss test results/i),
    ).toBeInTheDocument();

    // LLM cost telemetry footer.
    expect(within(dialog).getByText(/LLM enrichment/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/\$0\.7321/)).toBeInTheDocument();
  });

  it("does NOT render a zoom button on empty years", () => {
    render(<PriorConsultationsSection result={sampleResult} loading={false} />);
    const zoomButtons = screen.getAllByRole("button", {
      name: /open \d{4} prior-consultations breakdown/i,
    });
    const buttonYears = zoomButtons.map((b) =>
      (b.getAttribute("aria-label") ?? "").match(/\d{4}/)?.[0],
    );
    expect(buttonYears).not.toContain("2026");
  });
});
