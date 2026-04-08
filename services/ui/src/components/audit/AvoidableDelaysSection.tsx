"use client";

import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import type { AuditAvoidableDelays, AuditSectionResult } from "@/lib/analyticsApi";

interface Props {
  result: AuditSectionResult<AuditAvoidableDelays> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function AvoidableDelaysSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  const mainChart: ComparisonDataRow[] = [
    {
      category: "Avoidable delay identified",
      practice: practice?.avoidable_delay_pct ?? null,
      similar: allianceLive?.avoidable_delay_pct ?? null,
      alliance: englandLive?.avoidable_delay_pct ?? null,
      national: resolveBenchmarkValue(bm, "avoidable_delays.avoidable_delay_pct", orgSelected),
    },
  ];

  const stageChart: ComparisonDataRow[] = [
    {
      category: "Before presentation",
      practice: practice?.delay_before_presentation_pct ?? null,
      similar: allianceLive?.delay_before_presentation_pct ?? null,
      alliance: englandLive?.delay_before_presentation_pct ?? null,
      national: resolveBenchmarkValue(bm, "avoidable_delays.delay_before_presentation_pct", orgSelected),
    },
    {
      category: "Presentation to referral",
      practice: practice?.delay_pres_to_referral_pct ?? null,
      similar: allianceLive?.delay_pres_to_referral_pct ?? null,
      alliance: englandLive?.delay_pres_to_referral_pct ?? null,
      national: resolveBenchmarkValue(bm, "avoidable_delays.delay_between_presentation_referral_pct", orgSelected),
    },
    {
      category: "After referral",
      practice: practice?.delay_after_referral_pct ?? null,
      similar: allianceLive?.delay_after_referral_pct ?? null,
      alliance: englandLive?.delay_after_referral_pct ?? null,
      national: resolveBenchmarkValue(bm, "avoidable_delays.delay_after_referral_pct", orgSelected),
    },
  ];

  const tableRows = [
    {
      label: "GP-assessed avoidable delay (%)",
      unit: "%",
      practice: practice ? { value: practice.avoidable_delay_pct, n: practice.avoidable_delay_n } : null,
      similar: allianceLive ? { value: allianceLive.avoidable_delay_pct } : null,
      alliance: englandLive ? { value: englandLive.avoidable_delay_pct } : { value: bm?.["avoidable_delays.avoidable_delay_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "avoidable_delays.avoidable_delay_pct", orgSelected) },
    },
    {
      label: "Delay — before presentation (%)",
      unit: "%",
      practice: practice ? { value: practice.delay_before_presentation_pct } : null,
      similar: allianceLive ? { value: allianceLive.delay_before_presentation_pct } : null,
      alliance: englandLive ? { value: englandLive.delay_before_presentation_pct } : { value: bm?.["avoidable_delays.delay_before_presentation_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "avoidable_delays.delay_before_presentation_pct", orgSelected) },
    },
    {
      label: "Delay — presentation to referral (%)",
      unit: "%",
      practice: practice ? { value: practice.delay_pres_to_referral_pct } : null,
      similar: allianceLive ? { value: allianceLive.delay_pres_to_referral_pct } : null,
      alliance: englandLive ? { value: englandLive.delay_pres_to_referral_pct } : { value: bm?.["avoidable_delays.delay_between_presentation_referral_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "avoidable_delays.delay_between_presentation_referral_pct", orgSelected) },
    },
    {
      label: "Delay — after referral (%)",
      unit: "%",
      practice: practice ? { value: practice.delay_after_referral_pct } : null,
      similar: allianceLive ? { value: allianceLive.delay_after_referral_pct } : null,
      alliance: englandLive ? { value: englandLive.delay_after_referral_pct } : { value: bm?.["avoidable_delays.delay_after_referral_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "avoidable_delays.delay_after_referral_pct", orgSelected) },
    },
  ];

  // 0% with real episodes means the GP-hindsight field has not been filled in,
  // not that there were genuinely no avoidable delays.
  const MIN_EPISODES_FOR_ZERO = 5;
  const dataNotCaptured =
    practice != null &&
    practice.avoidable_delay_n === 0 &&
    practice.total_episodes >= MIN_EPISODES_FOR_ZERO;

  return (
    <SectionCard
      id="section-avoidable-delays"
      title="Avoidable Delays"
      description="Cases where the GP (family doctor), looking back, felt that diagnosis could have happened sooner. This needs GPs to fill in a form — it is not calculated automatically."
      availability="manual_entry"
      loading={loading}
      error={error}
    >
      {dataNotCaptured && (
        <Alert severity="warning" sx={{ mb: 2, fontSize: "0.8rem" }}>
          Avoidable delay shows as 0% across {practice!.total_episodes} cases.
          This section needs GPs to fill in a form, which has not been done yet. The 0% figure does not mean there were no delays.
        </Alert>
      )}
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <ComparisonBarChart
        data={mainChart}
        unit="percent"
        height={200}
        visibleKeys={visibleKeys}
        orgSelected={orgSelected}
        ariaLabel="Proportion of patients with GP-assessed avoidable delay"
      />
      <Box sx={{ mt: 2 }}>
        <ComparisonBarChart
          data={stageChart}
          unit="percent"
          height={240}
          visibleKeys={visibleKeys}
          orgSelected={orgSelected}
          ariaLabel="Stage at which avoidable delay occurred"
        />
      </Box>
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={visibleKeys} orgSelected={orgSelected} caption="Avoidable delays by stage in pathway (% of patients with delay)" />
      </Box>
      <CancerTypeBenchmarkGrid
        bm={bm}
        section="avoidable_delays"
        metrics={[{ metricKey: "avoidable_delay_pct", label: "Avoidable delay %" }]}
        orgSelected={orgSelected}
        heading="2018 Baseline by Cancer Type — Avoidable Delay (%)"
      />
    </SectionCard>
  );
}
