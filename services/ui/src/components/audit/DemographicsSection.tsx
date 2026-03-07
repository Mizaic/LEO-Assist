"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import SummaryStatsTable from "./SummaryStatsRow";
import type { AuditDemographics, AuditComorbidities, AuditSectionResult } from "@/lib/analyticsApi";

interface Props {
  result: AuditSectionResult<AuditDemographics> | null;
  comorbidities?: AuditSectionResult<AuditComorbidities> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function DemographicsSection({ result, comorbidities, loading, error, orgSelected = false }: Props) {
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

  // Canonical age band order — always show all 6, even if a scope has zero patients in a band
  const AGE_BANDS = ["0-24", "25-49", "50-64", "65-74", "75-84", "85+"] as const;

  // Map each age band label to its benchmark key in the JSON
  const AGE_BAND_BM_KEY: Record<string, string> = {
    "0-24":  "demographics.age_band_0_24_pct",
    "25-49": "demographics.age_band_25_49_pct",
    "50-64": "demographics.age_band_50_64_pct",
    "65-74": "demographics.age_band_65_74_pct",
    "75-84": "demographics.age_band_75_84_pct",
    "85+":   "demographics.age_band_85_plus_pct",
  };

  const hasAgeLive = (practice?.age_bands ?? []).length > 0;

  const ageChart: ComparisonDataRow[] = AGE_BANDS.map((band) => {
    const pRow  = practice?.age_bands?.find((r) => r.age_band === band);
    const aRow  = allianceLive?.age_bands?.find((r) => r.age_band === band);
    const eRow  = englandLive?.age_bands?.find((r) => r.age_band === band);
    const bmKey = AGE_BAND_BM_KEY[band] ?? null;
    return {
      category: band,
      practice: pRow?.pct ?? (hasAgeLive ? 0 : null),
      similar:  aRow?.pct ?? null,
      alliance: eRow?.pct ?? null,
      national: bmKey ? resolveBenchmarkValue(bm, bmKey, orgSelected) : null,
    };
  });

  const ageKeys = orgSelected
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  // Only show benchmark and live comparators that have at least one non-null value
  const ageBenchmarkKeys = (ageKeys as readonly string[]).filter((k) =>
    ageChart.some((r) => r[k as keyof ComparisonDataRow] != null),
  ) as typeof ageKeys;

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

  const maleLive  = (scope: typeof practice) => scope?.sex.find((s) => s.gender.toLowerCase() === "male");
  const femLive   = (scope: typeof practice) => scope?.sex.find((s) => s.gender.toLowerCase() === "female");
  const whiteLive = (scope: typeof practice) => scope?.ethnicity.find((e) => e.ethnicity?.toLowerCase().startsWith("white"));

  const summaryRows = [
    {
      label: "Male (%)", unit: "%",
      practice: maleLive(practice)     ? { value: maleLive(practice)!.pct }     : null,
      similar:  maleLive(allianceLive) ? { value: maleLive(allianceLive)!.pct } : null,
      alliance: maleLive(englandLive)  ? { value: maleLive(englandLive)!.pct }  : { value: bm?.["demographics.sex_male_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "demographics.sex_male_pct", orgSelected) },
    },
    {
      label: "Female (%)", unit: "%",
      practice: femLive(practice)     ? { value: femLive(practice)!.pct }     : null,
      similar:  femLive(allianceLive) ? { value: femLive(allianceLive)!.pct } : null,
      alliance: femLive(englandLive)  ? { value: femLive(englandLive)!.pct }  : { value: bm?.["demographics.sex_female_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "demographics.sex_female_pct", orgSelected) },
    },
    {
      label: "Median age at diagnosis (years)", unit: "years",
      practice: practice?.median_age != null     ? { value: practice.median_age }     : null,
      similar:  allianceLive?.median_age != null  ? { value: allianceLive.median_age }  : null,
      alliance: englandLive?.median_age != null   ? { value: englandLive.median_age }   : { value: bm?.["demographics.median_age"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "demographics.median_age", orgSelected) },
    },
    {
      label: "White ethnicity (%)", unit: "%",
      practice: whiteLive(practice)     ? { value: whiteLive(practice)!.pct }     : null,
      similar:  whiteLive(allianceLive) ? { value: whiteLive(allianceLive)!.pct } : null,
      alliance: whiteLive(englandLive)  ? { value: whiteLive(englandLive)!.pct }  : { value: bm?.["demographics.white_ethnicity_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "demographics.white_ethnicity_pct", orgSelected) },
    },
  ];

  // Comorbidity chart — built from the separate comorbidities result
  const comorbBm = comorbidities?.benchmark?.metrics;
  const practiceComorbidities = comorbidities?.scopes.practice?.comorbidities ?? [];

  // Show all comorbidity rows; use benchmark_key when set, omit 2018 bar otherwise.
  const comorbChart: ComparisonDataRow[] = practiceComorbidities.map((row) => ({
    category: row.condition,
    practice: row.pct,
    similar: null,
    alliance: null,
    national: row.benchmark_key
      ? resolveBenchmarkValue(comorbBm, row.benchmark_key, orgSelected)
      : null,
  }));

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

      {comorbChart.length > 0 && (
        <>
          <Divider sx={{ my: 2 }} />
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600, fontSize: "0.85rem" }}>
              Comorbidities
            </Typography>
            <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
            <ComparisonBarChart
              data={comorbChart}
              unit="percent"
              height={280}
              visibleKeys={visibleKeys}
              orgSelected={orgSelected}
              ariaLabel="Comorbidity prevalence compared to 2018 NCDA benchmark"
            />
          </Box>
        </>
      )}
    </SectionCard>
  );
}
