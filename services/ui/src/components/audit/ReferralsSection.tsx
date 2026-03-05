"use client";

import Box from "@mui/material/Box";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import type { AuditReferralRow, AuditSectionResult } from "@/lib/analyticsApi";

const ROUTE_DISPLAY: Record<string, string> = {
  tww: "TWW",
  two_week_wait: "TWW",
  urgent: "Urgent",
  mdc: "MDC/RDC",
  rdc: "MDC/RDC",
  emergency: "Emergency",
  "not recorded": "Not Recorded",
};

function formatRoute(raw: string): string {
  return ROUTE_DISPLAY[raw.toLowerCase()] ?? raw;
}

interface Props {
  result: AuditSectionResult<AuditReferralRow[]> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function ReferralsSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice ?? [];
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "similar", "alliance", "national"] as const)
    : (["practice", "national"] as const);

  const chartData: ComparisonDataRow[] = practice.slice(0, 8).map((row) => {
    const label = formatRoute(row.referral_route);
    const aRow = allianceLive?.find((r) => formatRoute(r.referral_route) === label);
    const eRow = englandLive?.find((r) => formatRoute(r.referral_route) === label);
    const isTWW = label === "TWW";
    const isEmergency = label === "Emergency";
    const metricKey = isTWW ? "referrals.tww_pct" : isEmergency ? "referrals.emergency_pct" : "";
    return {
      category: label,
      practice: row.pct,
      similar: aRow?.pct ?? null,
      alliance: eRow?.pct ?? null,
      national: metricKey ? (bm?.[metricKey]?.national ?? null) : null,
    };
  });

  const twwP = practice.find((r) => formatRoute(r.referral_route) === "TWW");
  const emP = practice.find((r) => formatRoute(r.referral_route) === "Emergency");
  const twwA = allianceLive?.find((r) => formatRoute(r.referral_route) === "TWW");
  const emA = allianceLive?.find((r) => formatRoute(r.referral_route) === "Emergency");
  const twwE = englandLive?.find((r) => formatRoute(r.referral_route) === "TWW");
  const emE = englandLive?.find((r) => formatRoute(r.referral_route) === "Emergency");

  const tableRows = [
    {
      label: "Two Week Wait (TWW) (%)",
      unit: "%",
      practice: twwP ? { value: twwP.pct } : null,
      similar: twwA ? { value: twwA.pct } : null,
      alliance: twwE ? { value: twwE.pct } : { value: bm?.["referrals.tww_pct"]?.alliance ?? null },
      national: { value: bm?.["referrals.tww_pct"]?.national ?? null },
    },
    {
      label: "Emergency (%)",
      unit: "%",
      practice: emP ? { value: emP.pct } : null,
      similar: emA ? { value: emA.pct } : null,
      alliance: emE ? { value: emE.pct } : { value: bm?.["referrals.emergency_pct"]?.alliance ?? null },
      national: { value: bm?.["referrals.emergency_pct"]?.national ?? null },
    },
  ];

  return (
    <SectionCard
      id="section-referrals"
      title="Referrals"
      description="Type of referral that led most directly to a cancer diagnosis. TWW = Two Week Wait for suspected cancer."
      availability="pipeline_pending"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        visibleKeys={visibleKeys}
        ariaLabel="Referral routes compared to alliance and national benchmarks"
      />
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={visibleKeys} caption="Key referral route comparisons" />
      </Box>
    </SectionCard>
  );
}
