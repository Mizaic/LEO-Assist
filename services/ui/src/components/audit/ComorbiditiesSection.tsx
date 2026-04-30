/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4DADBA3F
 *   DI: DI-87D92943
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4DADBA3F")
 */
"use client";

/**
 * Comorbidities at Diagnosis section.
 *
 * Registry-driven multimorbidity radars plus a drill-down dialog for age /
 * gender / referral-outcome slices (DO-D5B9FE5F).
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import SectionCard from "./SectionCard";
import ComorbidityRadarCard from "./ComorbidityRadarCard";
import ComorbiditiesDrilldownDialog from "./ComorbiditiesDrilldownDialog";
import ChartZoomDialog from "./ChartZoomDialog";
import type {
  AuditComorbidities,
  AuditComorbidityRadarRow,
  AuditSectionResult,
} from "@/lib/analyticsApi";
import { fetchAuditComorbidities } from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";

import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

interface Props {
  result: AuditSectionResult<AuditComorbidities> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
  /** @deprecated Resolved internally via useOrgId. */
  orgId?: string;
  dateFrom?: string;
  dateTo?: string;
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
  key: string | null | undefined,
  orgSelected: boolean,
): number | null {
  if (!bm || !key) return null;
  const candidateKeys = metricKeyCandidates(key);
  const entry = candidateKeys.map((k) => bm[k]).find(Boolean);
  if (!entry) return null;
  const value = orgSelected
    ? (entry.practice ?? entry.national ?? null)
    : (entry.national ?? null);
  return value == null ? null : Number(value);
}

function metricKeyCandidates(key: string): string[] {
  const out = [key];
  if (key.startsWith("comorbidity_")) {
    const short = key.replace(/^comorbidity_/, "");
    out.push(`demographics.${key}`);
    out.push(`demographics.${short}`);
    out.push(`comorbidities.${short}`);
    out.push(`comorbidities.${key}`);
    out.push(`comorbidity.${short}`);
  }
  const aliases: Record<string, string[]> = {
    comorbidity_cvd_pct: [
      "demographics.comorbidity_cvd_pct",
      "comorbidities.cvd_pct",
      "comorbidities.cardiovascular_disease_pct",
      "comorbidities.cerebrovascular_disease_pct",
    ],
    comorbidity_copd_pct: [
      "demographics.comorbidity_copd_pct",
      "comorbidities.copd_pct",
      "comorbidities.respiratory_disease_pct",
      "comorbidities.chronic_respiratory_illness_pct",
    ],
    comorbidity_arthritis_pct: [
      "demographics.comorbidity_arthritis_pct",
      "comorbidities.arthritis_pct",
      "comorbidities.musculoskeletal_disease_pct",
      "comorbidities.musculoskeletal_disorder_pct",
    ],
    comorbidity_disability_pct: [
      "demographics.comorbidity_disability_pct",
      "comorbidities.disability_pct",
      "comorbidities.physical_disability_pct",
      "comorbidities.longstanding_physical_disability_pct",
    ],
    comorbidity_mental_health_pct: [
      "demographics.comorbidity_mental_health_pct",
      "comorbidities.mental_health_pct",
      "comorbidities.mental_illness_pct",
      "comorbidities.severe_longstanding_mental_illness_pct",
      "comorbidities.cognitive_impairment_pct",
    ],
  };
  out.push(...(aliases[key] ?? []));
  return Array.from(new Set(out));
}

export default function ComorbiditiesSection({
  result,
  loading,
  error,
  orgSelected = false,
  dateFrom,
  dateTo,
}: Props) {
  const orgId = useOrgId();
  const [drillArgs, setDrillArgs] = useState<{
    from: string;
    to: string;
  } | null>(null);
  const [zoomedYear, setZoomedYear] = useState<string | null>(null);

  const comorbBm = result?.benchmark?.metrics;
  const practice = result?.scopes.practice;
  const radar = practice?.radar ?? [];

  const { liveYears: yearStates } = useAuditYearWindows<AuditComorbidities>(
    fetchAuditComorbidities,
    { orgId },
  );

  const baselineRadar: AuditComorbidityRadarRow[] = useMemo(
    () =>
      radar.map((row) => ({
        ...row,
        n: 0,
        pct: resolveBmValue(comorbBm, row.benchmark_key, orgSelected),
      })),
    [radar, comorbBm, orgSelected],
  );

  const sharedRadarScale = useMemo(() => {
    const allRows: AuditComorbidityRadarRow[][] = [
      baselineRadar,
      ...yearStates.map((s) => s.data?.radar ?? []),
    ];
    let maxPct = 0;
    for (const rows of allRows) {
      for (const row of rows) {
        if (row.pct != null && row.pct > maxPct) maxPct = row.pct;
      }
    }
    return Math.min(100, Math.max(8, Math.ceil(maxPct + 4)));
  }, [baselineRadar, yearStates]);

  return (
    <SectionCard
      id="section-comorbidities"
      title="Comorbidities at Diagnosis"
      description="Other long-term health conditions recorded for audited patients (SNOMED rollup under the cancer_audit comorbidities subdomain). Use the breakdown dialog for slices by age, gender, and referral versus cancer diagnosis outcome."
      availability="ready"
      loading={loading}
      error={error}
    >
      {radar.length > 0 ? (
        <Box>
          <Typography
            variant="subtitle2"
            sx={{ mb: 1, fontWeight: 600, fontSize: "0.85rem" }}
          >
            Comorbidity profile by year
          </Typography>
          <Grid container spacing={2} sx={{ mb: 2, alignItems: "stretch" }}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <ComorbidityRadarCard
                yearLabel={String(BASELINE_YEAR)}
                radar={baselineRadar}
                totalPatients={0}
                isBaseline
                maxScale={sharedRadarScale}
                onZoom={() => setZoomedYear(String(BASELINE_YEAR))}
              />
            </Grid>
            {yearStates.map((state) => {
              const window = calendarYearWindow(state.year);
              return (
                <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
                  <ComorbidityRadarCard
                    yearLabel={String(state.year)}
                    radar={state.data?.radar ?? radar}
                    totalPatients={state.data?.total_patients ?? 0}
                    loading={state.loading}
                    maxScale={sharedRadarScale}
                    onBreakdown={() => setDrillArgs(window)}
                    onZoom={() => setZoomedYear(String(state.year))}
                  />
                </Grid>
              );
            })}
          </Grid>

          {zoomedYear !== null && (() => {
            const isBase = zoomedYear === String(BASELINE_YEAR);
            const zState = yearStates.find((y) => String(y.year) === zoomedYear);
            const zN = isBase ? 0 : (zState?.data?.total_patients ?? 0);
            return (
              <ChartZoomDialog
                open
                onClose={() => setZoomedYear(null)}
                title={`Comorbidities \u2014 ${zoomedYear}`}
                subtitle={isBase ? "2018 NCDA baseline" : `n = ${zN}`}
                maxWidth="sm"
              >
                <Box sx={{ width: "100%", aspectRatio: "1" }}>
                  <ComorbidityRadarCard
                    yearLabel={zoomedYear}
                    radar={isBase ? baselineRadar : (zState?.data?.radar ?? radar)}
                    totalPatients={zN}
                    isBaseline={isBase}
                    maxScale={sharedRadarScale}
                    bare
                  />
                </Box>
              </ChartZoomDialog>
            );
          })()}

          <ComorbiditiesDrilldownDialog
            open={drillArgs != null}
            onClose={() => setDrillArgs(null)}
            orgId={orgId ?? undefined}
            dateFrom={drillArgs?.from ?? dateFrom}
            dateTo={drillArgs?.to ?? dateTo}
          />
        </Box>
      ) : (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ py: 1.5, fontSize: "0.82rem" }}
        >
          Comorbidity data is not yet available for this practice.
        </Typography>
      )}
    </SectionCard>
  );
}
