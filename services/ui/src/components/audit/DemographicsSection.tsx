"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import SummaryStatsTable from "./SummaryStatsRow";
import type { AuditDemographics, AuditSectionResult } from "@/lib/analyticsApi";

interface Props {
  result: AuditSectionResult<AuditDemographics> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function DemographicsSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  const sexChart: ComparisonDataRow[] = (practice?.sex ?? []).map((row) => {
    const key = row.gender.toLowerCase();
    const aRow = allianceLive?.sex.find((r) => r.gender.toLowerCase() === key);
    const eRow = englandLive?.sex.find((r) => r.gender.toLowerCase() === key);
    const metricKey = `demographics.sex_${key}_pct`;
    return {
      category: row.gender,
      practice: row.pct,
      similar: aRow?.pct ?? null,
      alliance: eRow?.pct ?? null,
      national: resolveBenchmarkValue(bm, metricKey, orgSelected),
    };
  });

  // Map each age band label to its benchmark key in the JSON
  const AGE_BAND_BM_KEY: Record<string, string> = {
    "0-24":  "demographics.age_band_0_24_pct",
    "25-49": "demographics.age_band_25_49_pct",
    "50-64": "demographics.age_band_50_64_pct",
    "65-74": "demographics.age_band_65_74_pct",
    "75-84": "demographics.age_band_75_84_pct",
    "85+":   "demographics.age_band_85_plus_pct",
  };

  const ageChart: ComparisonDataRow[] = (practice?.age_bands ?? []).map((row) => {
    const bmKey = AGE_BAND_BM_KEY[row.age_band] ?? null;
    return {
      category: row.age_band,
      practice: row.pct,
      national: bmKey ? resolveBenchmarkValue(bm, bmKey, orgSelected) : null,
    };
  });

  const ageBenchmarkKeys = ageChart.some((r) => r.national != null)
    ? (["practice", "national"] as const)
    : (["practice"] as const);

  const ethChart: ComparisonDataRow[] = (practice?.ethnicity ?? []).slice(0, 6).map((row) => {
    const aRow = allianceLive?.ethnicity.find((r) => r.ethnicity === row.ethnicity);
    const eRow = englandLive?.ethnicity.find((r) => r.ethnicity === row.ethnicity);
    const isWhite = row.ethnicity?.toLowerCase().startsWith("white");
    return {
      category: row.ethnicity,
      practice: row.pct,
      similar: aRow?.pct ?? null,
      alliance: eRow?.pct ?? null,
      national: isWhite ? resolveBenchmarkValue(bm, "demographics.white_ethnicity_pct", orgSelected) : null,
    };
  });

  const summaryRows = [
    {
      label: "Male (%)",
      unit: "%",
      practice: practice?.sex.find((s) => s.gender.toLowerCase() === "male")
        ? { value: practice!.sex.find((s) => s.gender.toLowerCase() === "male")!.pct }
        : null,
      similar: allianceLive?.sex.find((s) => s.gender.toLowerCase() === "male")
        ? { value: allianceLive.sex.find((s) => s.gender.toLowerCase() === "male")!.pct }
        : null,
      alliance: englandLive?.sex.find((s) => s.gender.toLowerCase() === "male")
        ? { value: englandLive.sex.find((s) => s.gender.toLowerCase() === "male")!.pct }
        : { value: bm?.["demographics.sex_male_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "demographics.sex_male_pct", orgSelected) },
    },
    {
      label: "Female (%)",
      unit: "%",
      practice: practice?.sex.find((s) => s.gender.toLowerCase() === "female")
        ? { value: practice!.sex.find((s) => s.gender.toLowerCase() === "female")!.pct }
        : null,
      similar: allianceLive?.sex.find((s) => s.gender.toLowerCase() === "female")
        ? { value: allianceLive.sex.find((s) => s.gender.toLowerCase() === "female")!.pct }
        : null,
      alliance: englandLive?.sex.find((s) => s.gender.toLowerCase() === "female")
        ? { value: englandLive.sex.find((s) => s.gender.toLowerCase() === "female")!.pct }
        : { value: bm?.["demographics.sex_female_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "demographics.sex_female_pct", orgSelected) },
    },
    {
      label: "White ethnicity (%)",
      unit: "%",
      practice: practice?.ethnicity.find((e) => e.ethnicity?.toLowerCase().startsWith("white"))
        ? { value: practice!.ethnicity.find((e) => e.ethnicity?.toLowerCase().startsWith("white"))!.pct }
        : null,
      similar: allianceLive?.ethnicity.find((e) => e.ethnicity?.toLowerCase().startsWith("white"))
        ? { value: allianceLive.ethnicity.find((e) => e.ethnicity?.toLowerCase().startsWith("white"))!.pct }
        : null,
      alliance: englandLive?.ethnicity.find((e) => e.ethnicity?.toLowerCase().startsWith("white"))
        ? { value: englandLive.ethnicity.find((e) => e.ethnicity?.toLowerCase().startsWith("white"))!.pct }
        : { value: bm?.["demographics.white_ethnicity_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "demographics.white_ethnicity_pct", orgSelected) },
    },
  ];

  return (
    <SectionCard
      id="section-demographics"
      title="Demographics"
      description="Sex, age at diagnosis, ethnicity and comorbidities of audited patients."
      availability="ready"
      loading={loading}
      error={error}
    >
      <SummaryStatsTable rows={summaryRows} visibleKeys={visibleKeys} orgSelected={orgSelected} caption="Key demographic comparisons" />

      <Divider sx={{ my: 2 }} />

      {sexChart.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600, fontSize: "0.85rem" }}>Sex</Typography>
          <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
          <ComparisonBarChart data={sexChart} unit="percent" height={220} visibleKeys={visibleKeys} orgSelected={orgSelected} ariaLabel="Sex distribution compared to benchmarks" />
        </Box>
      )}

      {ageChart.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600, fontSize: "0.85rem" }}>Age at Diagnosis (years)</Typography>
          <BenchmarkLegend visibleKeys={ageBenchmarkKeys} orgSelected={orgSelected} />
          <ComparisonBarChart data={ageChart} unit="percent" height={220} visibleKeys={ageBenchmarkKeys} orgSelected={orgSelected} ariaLabel="Age band distribution compared to 2018 benchmark" />
          <CancerTypeBenchmarkGrid
            bm={bm}
            section="demographics"
            metrics={[
              { metricKey: "age_band_0_24_pct",    label: "0–24"   },
              { metricKey: "age_band_25_49_pct",   label: "25–49"  },
              { metricKey: "age_band_50_64_pct",   label: "50–64"  },
              { metricKey: "age_band_65_74_pct",   label: "65–74"  },
              { metricKey: "age_band_75_84_pct",   label: "75–84"  },
              { metricKey: "age_band_85_plus_pct", label: "85+"    },
            ]}
            orgSelected={orgSelected}
            heading="2018 Age at Diagnosis by Cancer Type"
          />
        </Box>
      )}

      {ethChart.length > 0 && (
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600, fontSize: "0.85rem" }}>Ethnicity</Typography>
          <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
          <ComparisonBarChart data={ethChart} unit="percent" height={240} visibleKeys={visibleKeys} orgSelected={orgSelected} ariaLabel="Ethnicity distribution compared to benchmarks" />
        </Box>
      )}
    </SectionCard>
  );
}
