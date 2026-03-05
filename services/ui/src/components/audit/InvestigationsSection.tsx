"use client";

import Box from "@mui/material/Box";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import type { AuditInvestigations, AuditSectionResult } from "@/lib/analyticsApi";

const INV_DISPLAY: Record<string, string> = {
  blood_test: "Blood test",
  imaging: "Imaging",
  urinalysis: "Urinalysis",
  biopsy: "Biopsy",
  endoscopy: "Endoscopy",
  other_investigation: "Other",
  investigation: "Other",
};

interface Props {
  result: AuditSectionResult<AuditInvestigations> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function InvestigationsSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "similar", "alliance", "national"] as const)
    : (["practice", "national"] as const);

  const summaryChart: ComparisonDataRow[] = [
    {
      category: "≥1 investigation",
      practice: practice?.has_investigation_pct ?? null,
      similar: allianceLive?.has_investigation_pct ?? null,
      alliance: englandLive?.has_investigation_pct ?? null,
      national: bm?.["investigations.at_least_one_pct"]?.national ?? null,
    },
    {
      category: "No investigation",
      practice: practice?.no_investigation_pct ?? null,
      similar: allianceLive?.no_investigation_pct ?? null,
      alliance: englandLive?.no_investigation_pct ?? null,
      national: bm?.["investigations.at_least_one_pct"]?.national != null
        ? 100 - bm["investigations.at_least_one_pct"].national
        : null,
    },
  ];

  const typeChart: ComparisonDataRow[] = (practice?.types ?? []).slice(0, 6).map((t) => {
    const aType = allianceLive?.types.find((at) => at.type === t.type);
    const eType = englandLive?.types.find((et) => et.type === t.type);
    return {
      category: INV_DISPLAY[t.type] ?? t.type,
      practice: t.pct,
      similar: aType?.pct ?? null,
      alliance: eType?.pct ?? null,
      national: t.type === "blood_test" ? (bm?.["investigations.blood_test_pct"]?.national ?? null) : null,
    };
  });

  const btPractice = practice?.types.find((t) => t.type === "blood_test");
  const btAlliance = allianceLive?.types.find((t) => t.type === "blood_test");
  const btEngland = englandLive?.types.find((t) => t.type === "blood_test");

  const tableRows = [
    {
      label: "Had at least one investigation (%)",
      unit: "%",
      practice: practice ? { value: practice.has_investigation_pct } : null,
      similar: allianceLive ? { value: allianceLive.has_investigation_pct } : null,
      alliance: englandLive ? { value: englandLive.has_investigation_pct } : { value: bm?.["investigations.at_least_one_pct"]?.alliance ?? null },
      national: { value: bm?.["investigations.at_least_one_pct"]?.national ?? null },
    },
    {
      label: "Blood test (of investigations) (%)",
      unit: "%",
      practice: btPractice ? { value: btPractice.pct } : null,
      similar: btAlliance ? { value: btAlliance.pct } : null,
      alliance: btEngland ? { value: btEngland.pct } : { value: bm?.["investigations.blood_test_pct"]?.alliance ?? null },
      national: { value: bm?.["investigations.blood_test_pct"]?.national ?? null },
    },
  ];

  return (
    <SectionCard
      id="section-investigations"
      title="Investigations"
      description="Primary care–led investigations ordered as part of the diagnostic assessment prior to referral."
      availability="pipeline_pending"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <ComparisonBarChart
        data={summaryChart}
        unit="percent"
        height={220}
        visibleKeys={visibleKeys}
        ariaLabel="Proportion of patients with and without primary care investigations"
      />
      {typeChart.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <ComparisonBarChart
            data={typeChart}
            unit="percent"
            height={240}
            visibleKeys={visibleKeys}
            ariaLabel="Type of investigations ordered"
          />
        </Box>
      )}
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={visibleKeys} caption="Investigation summary" />
      </Box>
    </SectionCard>
  );
}
