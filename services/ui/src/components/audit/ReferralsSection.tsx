"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
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
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  const MAX_ROUTE_BARS = 8;
  const hiddenRouteCount = Math.max(0, practice.length - MAX_ROUTE_BARS);

  const chartData: ComparisonDataRow[] = practice.slice(0, MAX_ROUTE_BARS).map((row) => {
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
      national: metricKey ? resolveBenchmarkValue(bm, metricKey, orgSelected) : null,
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
      national: { value: resolveBenchmarkValue(bm, "referrals.tww_pct", orgSelected) },
    },
    {
      label: "Emergency (%)",
      unit: "%",
      practice: emP ? { value: emP.pct } : null,
      similar: emA ? { value: emA.pct } : null,
      alliance: emE ? { value: emE.pct } : { value: bm?.["referrals.emergency_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "referrals.emergency_pct", orgSelected) },
    },
  ];

  return (
    <SectionCard
      id="section-referrals"
      title="Referrals"
      description="How patients were referred for tests that led to their diagnosis. TWW (Two Week Wait) is an urgent referral when cancer is suspected."
      availability="pipeline_pending"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <Box>
        <ComparisonBarChart
          data={chartData}
          unit="percent"
          visibleKeys={visibleKeys}
          orgSelected={orgSelected}
          ariaLabel="Referral routes compared to alliance and national benchmarks"
        />
        {hiddenRouteCount > 0 && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "right", mt: 0.5 }}>
            {`+${hiddenRouteCount} less common route${hiddenRouteCount !== 1 ? "s" : ""} not shown`}
          </Typography>
        )}
      </Box>
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={visibleKeys} orgSelected={orgSelected} caption="Key referral route comparisons" />
      </Box>
      <CancerTypeBenchmarkGrid
        bm={bm}
        section="referrals"
        metrics={[{ metricKey: "emergency_pct", label: "Emergency %" }]}
        orgSelected={orgSelected}
        heading="2018 Baseline by Cancer Type — Emergency Referral (%)"
      />
    </SectionCard>
  );
}
