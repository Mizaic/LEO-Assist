/**
 * Pins the structure of <CareObstructionsSection>:
 *
 *   1. Section title and 2018 baseline card render even though the
 *      2018 NCDA does not publish a comparable baseline (the
 *      EvolutionYearCard handles the missing-value case gracefully).
 *   2. Each live year card with data has an "Open detail" zoom
 *      button that opens an EvolutionDetailDialog containing the
 *      five-bucket severity breakdown for that year (rejection /
 *      DNA / cancellation / access barrier / none).
 *   3. Empty years (total_episodes: 0) do NOT render a zoom button.
 */
import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import CareObstructionsSection from "../CareObstructionsSection";
import type {
  AuditAvoidableDelays,
  AuditCareObstruction,
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

const sampleData: AuditCareObstruction = {
  total_episodes: 42,
  recorded_n: 13,
  recorded_pct: 31.0,
  not_recorded_pct: 69.0,
  signal_counts: { rejection: 5, dna: 6, cancellation: 1, access_barrier: 1, none: 29 },
  signal_pct: { rejection: 11.9, dna: 14.3, cancellation: 2.4, access_barrier: 2.4, none: 69.0 },
  severe_n: 11,
  severe_pct: 26.2,
  confirmed_n: 4,
  confirmed_pct: 9.5,
  confirmed_events: 11,
  unrelated_filtered_events: 3,
};

const sampleResult: AuditSectionResult<AuditCareObstruction> = {
  scopes: { practice: sampleData, alliance_live: null, england_live: null },
  benchmark: null,
};

beforeEach(() => {
  (useAuditYearWindows as jest.Mock).mockReturnValue({
    liveYears: [
      {
        year: 2024,
        loading: false,
        data: { ...sampleData, recorded_pct: 18.0, recorded_n: 7, total_episodes: 39 },
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
          signal_counts: { rejection: 0, dna: 0, cancellation: 0, access_barrier: 0, none: 0 },
          signal_pct: { rejection: 0, dna: 0, cancellation: 0, access_barrier: 0, none: 0 },
          total_episodes: 0,
        },
        error: null,
      },
    ],
    anyLoading: false,
    allYearsEmpty: false,
  });
});

describe("CareObstructionsSection", () => {
  it("renders the section title and the 2018 baseline card", () => {
    render(<CareObstructionsSection result={sampleResult} loading={false} />);
    expect(screen.getByText("Avoidable Delays")).toBeInTheDocument();
    expect(screen.getByText(String(BASELINE_YEAR))).toBeInTheDocument();
  });

  it("renders an Open-detail zoom button on each live year card with data", () => {
    render(<CareObstructionsSection result={sampleResult} loading={false} />);
    const zoomButtons = screen.getAllByRole("button", {
      name: /Open .* avoidable-delay type breakdown/i,
    });
    expect(zoomButtons).toHaveLength(2);
  });

  it("opens the severity dialog when a year card's zoom button is clicked", () => {
    render(<CareObstructionsSection result={sampleResult} loading={false} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: /Open 2025 care-obstruction severity breakdown/i,
      }),
    );

    const dialog = screen.getByRole("dialog");
    const within$ = within(dialog);

    expect(
      within$.getByText(/Care obstructions -- 2025 severity breakdown/i),
    ).toBeInTheDocument();

    expect(within$.getByText("31.0%")).toBeInTheDocument();
    expect(
      within$.getByText("13 of 42 confirmed cancers"),
    ).toBeInTheDocument();

    expect(within$.getByText("26.2%")).toBeInTheDocument();
    expect(
      within$.getByText("11 of 42 pathways hard-stopped or no-shows"),
    ).toBeInTheDocument();

    expect(within$.getByRole("progressbar", { name: /Rejection/ })).toBeInTheDocument();
    expect(within$.getByRole("progressbar", { name: /^DNA/ })).toBeInTheDocument();
    expect(within$.getByRole("progressbar", { name: /Cancellation/ })).toBeInTheDocument();
    expect(within$.getByRole("progressbar", { name: /Access barrier/ })).toBeInTheDocument();
    expect(within$.getByRole("progressbar", { name: /^None/ })).toBeInTheDocument();
  });

  it("does not render a zoom button on a year card with zero episodes", () => {
    render(<CareObstructionsSection result={sampleResult} loading={false} />);
    expect(
      screen.queryByRole("button", {
        name: /Open 2026 care-obstruction severity breakdown/i,
      }),
    ).not.toBeInTheDocument();
  });

  it("uses the GP-noted avoidable-delay benchmark as the 2018 baseline when no obstruction baseline is published", () => {
    /**
     * NCDA does not publish a "care obstruction" baseline -- it is
     * not a Section-8 metric.  The closest published comparator is
     * the GP-noted avoidable delay rate (NCDA Section 5).  When
     * the avoidableDelaysResult prop carries that benchmark, the
     * baseline card MUST surface it (with an honest "GP-noted
     * delay" sub-label) instead of rendering an em-dash.
     */
    const avoidableResult: AuditSectionResult<AuditAvoidableDelays> = {
      scopes: { practice: null, alliance_live: null, england_live: null },
      benchmark: {
        set_id: "ncda-2018",
        set_name: "NCDA 2018",
        metrics: {
          "avoidable_delays.avoidable_delay_pct": {
            national: 23.7,
            alliance: null,
            practice: null,
          },
        },
      },
    };
    render(
      <CareObstructionsSection
        result={sampleResult}
        loading={false}
        avoidableDelaysResult={avoidableResult}
      />,
    );
    expect(screen.getByText("23.7%")).toBeInTheDocument();
    expect(screen.getByText(/GP-noted delay/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /NCDA does not publish a care-obstruction baseline.*GP-noted avoidable delay/i,
      ),
    ).toBeInTheDocument();
  });

  it("surfaces the pathway-relatedness panel inside the year-detail dialog", () => {
    /**
     * The footer of the dialog must explain to a clinician how many
     * obstructions were confirmed cancer-pathway and how many events
     * were filtered out as unrelated noise -- otherwise an auditor
     * looking at the headline rate has no way to tell whether the
     * filter is doing useful work.  Asserts both.
     */
    render(<CareObstructionsSection result={sampleResult} loading={false} />);
    fireEvent.click(
      screen.getByRole("button", {
        name: /Open 2025 care-obstruction severity breakdown/i,
      }),
    );
    const dialog = screen.getByRole("dialog");
    const within$ = within(dialog);

    expect(within$.getAllByText(/Pathway-relatedness/i).length).toBeGreaterThan(0);
    expect(
      within$
        .getAllByText(
          (_, node) =>
            (node?.textContent ?? "").includes("13 obstructed episodes") &&
            (node?.textContent ?? "").includes("4"),
        )
        .length,
    ).toBeGreaterThan(0);
    expect(
      within$
        .getAllByText(
          (_, node) =>
            (node?.textContent ?? "").includes("filtered out") &&
            (node?.textContent ?? "").includes("3 event"),
        )
        .length,
    ).toBeGreaterThan(0);
  });
});
