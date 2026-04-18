/**
 * VT-LEO-AI-206 -- Mission Control KPI strip unit clarity + cohort
 * denominator (DI-LEO-AI-214).
 *
 * Live-render verification covering:
 *   TC-001  Confirmed cancer headline shows the PATIENT count and the
 *           pathway count appears as a sub-line (units match tooltip)
 *   TC-002  Pathway closures headline shows the PATIENT count with
 *           pathway sub-line
 *   TC-003  Cohort denominator line shows "Showing X of Y patients - Z
 *           hidden" with a plain-English breakdown of why patients are
 *           excluded
 *   TC-004  When no patients are excluded, the denominator line reads
 *           "Showing all N patients in the cohort"
 *   TC-005  When kpis.cohort is absent, no denominator line is rendered
 *   TC-006  buildCohortDenominatorLine pluralisation handles 1 vs many
 *           hidden patients gracefully
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import KPIStrip, {
  buildCohortDenominatorLine,
} from "@/components/mission-control/KPIStrip";
import type { MissionKPIs } from "@/lib/missionControlApi";

const KPIS_WITH_COHORT: MissionKPIs = {
  total_patients: 89,
  confirmed_cancer: 54,
  confirmed_cancer_patients: 44,
  pathway_closures: 76,
  pathway_closure_patients: 60,
  median_diagnostic_interval_days: null,
  safety_netting_rate: 0.85,
  needs_review_count: 5,
  cohort: {
    total_patients: 107,
    excluded_total: 18,
    excluded_no_pathway: 8,
    excluded_missing_referral_date: 7,
    excluded_outside_window: 3,
  },
};

describe("VT-LEO-AI-206 - KPI strip unit clarity + cohort denominator", () => {
  test("TC-001: confirmed cancer shows patients as headline and pathways as sub-line", () => {
    render(<KPIStrip kpis={KPIS_WITH_COHORT} loading={false} />);
    expect(screen.getByText("44")).toBeInTheDocument();
    expect(screen.getByText(/54\s+pathways/)).toBeInTheDocument();
  });

  test("TC-002: pathway closures shows patients as headline and pathways as sub-line", () => {
    render(<KPIStrip kpis={KPIS_WITH_COHORT} loading={false} />);
    expect(screen.getByText("60")).toBeInTheDocument();
    expect(screen.getByText(/76\s+pathways/)).toBeInTheDocument();
  });

  test("TC-003: cohort denominator line is rendered with breakdown", () => {
    render(<KPIStrip kpis={KPIS_WITH_COHORT} loading={false} />);
    const line = screen.getByTestId("kpi-cohort-denominator");
    expect(line.textContent).toContain("Showing 89 of 107 patients");
    expect(line.textContent).toContain("18 hidden");
    expect(line.textContent).toContain("8 no pathway");
    expect(line.textContent).toContain("7 missing referral date");
    expect(line.textContent).toContain("3 outside the date range");
  });

  test("TC-004: showing-all line when no patients are excluded", () => {
    const all: MissionKPIs = {
      ...KPIS_WITH_COHORT,
      total_patients: 107,
      cohort: {
        total_patients: 107,
        excluded_total: 0,
        excluded_no_pathway: 0,
        excluded_missing_referral_date: 0,
        excluded_outside_window: 0,
      },
    };
    render(<KPIStrip kpis={all} loading={false} />);
    expect(
      screen.getByTestId("kpi-cohort-denominator").textContent,
    ).toContain("Showing all 107 patients");
  });

  test("TC-005: no denominator line when cohort block missing", () => {
    const noCohort: MissionKPIs = {
      ...KPIS_WITH_COHORT,
      cohort: undefined,
    };
    render(<KPIStrip kpis={noCohort} loading={false} />);
    expect(screen.queryByTestId("kpi-cohort-denominator")).toBeNull();
  });

  test("TC-006: buildCohortDenominatorLine pluralisation", () => {
    const onlyOne = buildCohortDenominatorLine(10, {
      total_patients: 11,
      excluded_total: 1,
      excluded_no_pathway: 1,
      excluded_missing_referral_date: 0,
      excluded_outside_window: 0,
    });
    expect(onlyOne).toBe(
      "Showing 10 of 11 patients - 1 hidden (1 no pathway).",
    );

    const empty = buildCohortDenominatorLine(0, {
      total_patients: 0,
      excluded_total: 0,
      excluded_no_pathway: 0,
      excluded_missing_referral_date: 0,
      excluded_outside_window: 0,
    });
    expect(empty).toBe("");
  });
});
