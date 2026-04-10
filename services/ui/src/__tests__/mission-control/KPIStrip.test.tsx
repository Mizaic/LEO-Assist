/**
 * VT-LEO-AI-092 TC-003: KPIStrip diagnostic interval colour thresholds.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import KPIStrip from "@/components/mission-control/KPIStrip";
import type { MissionKPIs } from "@/lib/missionControlApi";

const BASE_KPIS: MissionKPIs = {
  total_patients: 100,
  confirmed_cancer: 42,
  pathway_closures: 15,
  median_diagnostic_interval_days: null,
  safety_netting_rate: 0.85,
  needs_review_count: 5,
};

describe("KPIStrip", () => {
  test("renders all 6 metric cards when kpis provided", () => {
    render(<KPIStrip kpis={BASE_KPIS} loading={false} />);
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("85%")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("--")).toBeInTheDocument();
  });

  test("renders 6 skeleton cards when loading", () => {
    const { container } = render(<KPIStrip kpis={null} loading={true} />);
    // MUI Skeleton renders with role="generic" by default; check for skeleton elements
    const skeletons = container.querySelectorAll(".MuiSkeleton-root");
    expect(skeletons.length).toBeGreaterThanOrEqual(6);
  });

  test("median interval card shows '28d' for 28 days (green threshold)", () => {
    const kpis = { ...BASE_KPIS, median_diagnostic_interval_days: 28 };
    render(<KPIStrip kpis={kpis} loading={false} />);
    expect(screen.getByText("28d")).toBeInTheDocument();
  });

  test("median interval card shows '50d' for 50 days (amber threshold)", () => {
    const kpis = { ...BASE_KPIS, median_diagnostic_interval_days: 50 };
    render(<KPIStrip kpis={kpis} loading={false} />);
    expect(screen.getByText("50d")).toBeInTheDocument();
  });

  test("median interval card shows '70d' for 70 days (red threshold)", () => {
    const kpis = { ...BASE_KPIS, median_diagnostic_interval_days: 70 };
    render(<KPIStrip kpis={kpis} loading={false} />);
    expect(screen.getByText("70d")).toBeInTheDocument();
  });

  test("needs review card shows 0 when no episodes need review", () => {
    const kpis = { ...BASE_KPIS, needs_review_count: 0 };
    render(<KPIStrip kpis={kpis} loading={false} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
