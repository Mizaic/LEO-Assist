/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4DADBA3F
 *   DI: DI-87D92943
 *   Risk: R-05B6DDA7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4DADBA3F")
 */
"use client";

/**
 * Demographics -- year-on-year evolution section.
 *
 * Renders four PopulationPyramidCards (2018 NCDA baseline + previous two
 * complete calendar years + current calendar year) followed by four
 * EthnicitySnomedRadarCards for live years plus EthnicityYearCard for the
 * 2018 published white-% baseline. Live years are fetched in parallel via
 * three fetchAuditDemographics calls scoped to Jan-Dec calendar windows.
 *
 * Each demographics card uses the same sex pie and marginal age-band area
 * chart: the 2018 baseline draws published benchmark metrics; live years
 * draw the practice cohort for that Jan-Dec window. The 2018 NCDA baseline
 * does not publish an age x sex cross-tab. The ethnicity row shows SNOMED
 * distribution on live years (radar) plus the 2018 published white-% baseline bar.
 *
 * Decoupled from the global AnalyticsDateFilter context: the new audit
 * model is year-on-year progression against 2018, so on-page date pickers
 * are intentionally not consumed here.
 */

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";

import {
  fetchAuditDemographics,
  type AuditDemographics,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import SectionCard from "./SectionCard";
import ChartZoomDialog from "./ChartZoomDialog";
import PopulationPyramidCard, {
  PYRAMID_AGE_BANDS,
  type BaselineMarginal,
  type PyramidAgeBand,
} from "./PopulationPyramidCard";
import EthnicityYearCard from "./EthnicityYearCard";
import EthnicitySnomedRadarCard from "./EthnicitySnomedRadarCard";

const BASELINE_YEAR = 2018;
const C_MALE = "#2563EB";
const C_FEMALE = "#DB2777";
const C_ETH_RADAR_LIVE = "#1D4ED8";
const C_BENCH18 = "#92400E";

interface LiveYearState {
  year: number;
  loading: boolean;
  data: AuditDemographics | null;
  error: string | null;
}

interface Props {
  result: AuditSectionResult<AuditDemographics> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

function calendarYearWindow(year: number): { from: string; to: string } {
  return {
    from: `${year}-01-01`,
    to: `${year}-12-31`,
  };
}

function resolveBmValue(
  bm:
    | Record<
        string,
        {
          practice?: number | null;
          alliance?: number | null;
          national?: number | null;
        }
      >
    | null
    | undefined,
  key: string,
  orgSelected: boolean,
): number | null {
  if (!bm) return null;
  const entry = bm[key];
  if (!entry) return null;
  const value = orgSelected
    ? (entry.practice ?? entry.national ?? null)
    : (entry.national ?? null);
  return value == null ? null : Number(value);
}

const AGE_BAND_BM_KEY: Record<PyramidAgeBand, string> = {
  "0-24": "demographics.age_band_0_24_pct",
  "25-49": "demographics.age_band_25_49_pct",
  "50-64": "demographics.age_band_50_64_pct",
  "65-74": "demographics.age_band_65_74_pct",
  "75-84": "demographics.age_band_75_84_pct",
  "85+": "demographics.age_band_85_plus_pct",
};

function buildBaselineMarginal(
  bm:
    | Record<
        string,
        {
          practice?: number | null;
          alliance?: number | null;
          national?: number | null;
        }
      >
    | null
    | undefined,
  orgSelected: boolean,
): BaselineMarginal {
  const ageBandPct: Partial<Record<PyramidAgeBand, number | null>> = {};
  for (const band of PYRAMID_AGE_BANDS) {
    ageBandPct[band] = resolveBmValue(bm, AGE_BAND_BM_KEY[band], orgSelected);
  }
  return {
    malePct: resolveBmValue(bm, "demographics.sex_male_pct", orgSelected),
    femalePct: resolveBmValue(bm, "demographics.sex_female_pct", orgSelected),
    ageBandPct,
    medianAge: resolveBmValue(bm, "demographics.median_age", orgSelected),
  };
}

function pickPctByGender(
  data: AuditDemographics | null,
  prefix: "m" | "f",
): number | null {
  if (!data) return null;
  const row = data.sex.find((r) =>
    (r.gender ?? "").toLowerCase().startsWith(prefix),
  );
  return row?.pct ?? null;
}

function ageBandPctFromPractice(
  data: AuditDemographics | null,
): Partial<Record<PyramidAgeBand, number | null>> {
  if (!data?.age_bands?.length) return {};
  const out: Partial<Record<PyramidAgeBand, number | null>> = {};
  for (const band of PYRAMID_AGE_BANDS) {
    const row = data.age_bands.find((r) => r.age_band === band);
    out[band] = row?.pct ?? null;
  }
  return out;
}

function totalDemographicN(data: AuditDemographics | null): number {
  if (!data) return 0;
  return (data.sex ?? []).reduce((acc, r) => acc + (r.n ?? 0), 0);
}

interface LegendSwatchProps {
  colour: string;
  label: string;
  hatched?: boolean;
  dashed?: boolean;
}

function LegendSwatch({
  colour,
  label,
  hatched = false,
  dashed = false,
}: LegendSwatchProps) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
      <Box
        aria-hidden="true"
        sx={{
          width: 18,
          height: 10,
          borderRadius: 0.5,
          border: dashed ? `1.5px dashed ${colour}` : "none",
          bgcolor: dashed ? "transparent" : colour,
          backgroundImage: hatched
            ? `repeating-linear-gradient(45deg, ${colour} 0, ${colour} 3px, #E2E8F0 3px, #E2E8F0 6px)`
            : undefined,
          opacity: dashed ? 1 : 0.85,
          flexShrink: 0,
        }}
      />
      <Typography
        variant="caption"
        sx={{ fontSize: "0.72rem", color: "text.secondary" }}
      >
        {label}
      </Typography>
    </Box>
  );
}

export default function DemographicsEvolutionSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const [zoomedYear, setZoomedYear] = useState<string | null>(null);
  const orgId = useOrgId();
  const bm = result?.benchmark?.metrics;

  const currentYear = new Date().getUTCFullYear();
  const liveYearNumbers = useMemo(
    () => [currentYear - 2, currentYear - 1, currentYear],
    [currentYear],
  );

  const [yearStates, setYearStates] = useState<LiveYearState[]>(() =>
    liveYearNumbers.map((year) => ({
      year,
      loading: true,
      data: null,
      error: null,
    })),
  );

  useEffect(() => {
    let cancelled = false;

    setYearStates(
      liveYearNumbers.map((year) => ({
        year,
        loading: true,
        data: null,
        error: null,
      })),
    );

    const orgArg = orgId ?? undefined;

    Promise.all(
      liveYearNumbers.map(async (year) => {
        const window = calendarYearWindow(year);
        try {
          const res = await fetchAuditDemographics(
            orgArg,
            window.from,
            window.to,
          );
          return {
            year,
            data: res?.scopes?.practice ?? null,
            error: null as string | null,
          };
        } catch (e) {
          return {
            year,
            data: null as AuditDemographics | null,
            error:
              e instanceof Error
                ? e.message
                : `Unable to load ${year} demographics data.`,
          };
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      setYearStates(
        results.map((r) => ({
          year: r.year,
          loading: false,
          data: r.data,
          error: r.error,
        })),
      );
    });

    return () => {
      cancelled = true;
    };
  }, [orgId, liveYearNumbers]);

  const baselineMarginal = useMemo(
    () => buildBaselineMarginal(bm, orgSelected),
    [bm, orgSelected],
  );

  const baseline2018White = useMemo(
    () => resolveBmValue(bm, "demographics.white_ethnicity_pct", orgSelected),
    [bm, orgSelected],
  );

  const sharedAgeMaxPct = useMemo(() => {
    let max = 0;
    for (const band of PYRAMID_AGE_BANDS) {
      const v = baselineMarginal.ageBandPct?.[band];
      if (v != null && v > max) max = v;
    }
    for (const state of yearStates) {
      const banded = ageBandPctFromPractice(state.data);
      for (const band of PYRAMID_AGE_BANDS) {
        const v = banded[band];
        if (v != null && v > max) max = v;
      }
    }
    return max > 0 ? Math.ceil(max / 5) * 5 : null;
  }, [baselineMarginal, yearStates]);

  const sharedEthnicitySnomedScale = useMemo(() => {
    let max = 0;
    for (const state of yearStates) {
      const rows = state.data?.ethnicity_by_snomed ?? [];
      for (const row of rows) {
        if (row.pct != null && row.pct > max) max = row.pct;
      }
    }
    return max > 0 ? Math.min(100, Math.max(8, Math.ceil(max + 4))) : null;
  }, [yearStates]);

  return (
    <SectionCard
      id="section-demographics"
      title="Demographics"
      description="How the practice's demographic mix has evolved against the 2018 NCDA baseline. Each card covers a calendar year (Jan-Dec). Cards may be sparse early in a year -- the n badge and warnings show how reliable each card is."
      availability="ready"
      loading={loading}
      error={error}
    >
      <Box>
        <Box
          sx={{
            display: "flex",
            gap: 2,
            mb: 1.5,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <LegendSwatch colour={C_MALE} label="Males" />
          <LegendSwatch colour={C_FEMALE} label="Females" />
          <LegendSwatch colour="#16A34A" label="Age bands (% of cases)" />
          <LegendSwatch
            colour={C_ETH_RADAR_LIVE}
            label="Ethnicity SNOMED (live years)"
          />
          <LegendSwatch
            colour={C_BENCH18}
            label="2018 NCDA baseline"
            dashed
          />
        </Box>

        <Typography
          variant="subtitle2"
          sx={{ mb: 1, fontWeight: 600, fontSize: "0.85rem" }}
        >
          Sex and age distribution by year
        </Typography>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <PopulationPyramidCard
              yearLabel={String(BASELINE_YEAR)}
              totalN={0}
              malePct={null}
              femalePct={null}
              medianAge={null}
              isBaseline
              baselineMarginal={baselineMarginal}
              ageMaxPct={sharedAgeMaxPct}
              onZoom={() => setZoomedYear(String(BASELINE_YEAR))}
            />
          </Grid>
          {yearStates.map((state) => (
            <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
              <PopulationPyramidCard
                yearLabel={String(state.year)}
                totalN={totalDemographicN(state.data)}
                malePct={pickPctByGender(state.data, "m")}
                femalePct={pickPctByGender(state.data, "f")}
                medianAge={state.data?.median_age ?? null}
                ageBandPct={ageBandPctFromPractice(state.data)}
                ageMaxPct={sharedAgeMaxPct}
                loading={state.loading}
                onZoom={() => setZoomedYear(String(state.year))}
              />
            </Grid>
          ))}
        </Grid>

        {zoomedYear !== null && (() => {
          const isBase = zoomedYear === String(BASELINE_YEAR);
          const zState = yearStates.find((y) => String(y.year) === zoomedYear);
          const zN = isBase ? 0 : totalDemographicN(zState?.data ?? null);
          return (
            <ChartZoomDialog
              open
              onClose={() => setZoomedYear(null)}
              title={`Demographics \u2014 ${zoomedYear}`}
              subtitle={isBase ? "2018 NCDA baseline" : `n = ${zN}`}
              maxWidth="sm"
            >
              <PopulationPyramidCard
                yearLabel={zoomedYear}
                totalN={zN}
                malePct={isBase ? null : pickPctByGender(zState?.data ?? null, "m")}
                femalePct={isBase ? null : pickPctByGender(zState?.data ?? null, "f")}
                medianAge={isBase ? null : (zState?.data?.median_age ?? null)}
                ageBandPct={isBase ? undefined : ageBandPctFromPractice(zState?.data ?? null)}
                isBaseline={isBase}
                baselineMarginal={isBase ? baselineMarginal : null}
                ageMaxPct={sharedAgeMaxPct}
                bare
              />
            </ChartZoomDialog>
          );
        })()}

        <Typography
          variant="subtitle2"
          sx={{ mt: 3, mb: 1, fontWeight: 600, fontSize: "0.85rem" }}
        >
          Ethnicity (SNOMED-coded) by year
        </Typography>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <EthnicityYearCard
              yearLabel={String(BASELINE_YEAR)}
              whitePct={baseline2018White}
              totalN={0}
              baseline2018White={baseline2018White}
              isBaseline
            />
          </Grid>
          {yearStates.map((state) => (
            <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
              <EthnicitySnomedRadarCard
                yearLabel={String(state.year)}
                ethnicityBySnomed={state.data?.ethnicity_by_snomed ?? []}
                demographicsCohortN={
                  state.data?.demographics_cohort_n ??
                  totalDemographicN(state.data)
                }
                patientsWithEthnicitySnomedN={
                  state.data?.patients_with_ethnicity_snomed_n ?? 0
                }
                ethnicitySnomedCoveragePct={
                  state.data?.ethnicity_snomed_coverage_pct ?? null
                }
                loading={state.loading}
                maxScale={sharedEthnicitySnomedScale}
              />
            </Grid>
          ))}
        </Grid>
      </Box>
    </SectionCard>
  );
}
