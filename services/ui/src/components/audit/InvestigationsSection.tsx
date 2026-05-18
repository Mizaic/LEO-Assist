/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import Box from "@mui/material/Box";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import SummaryStatsTable from "./SummaryStatsRow";
import type { AuditInvestigations, AuditSectionResult } from "@/lib/analyticsApi";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";
import { buildAuditBarVisibleKeys } from "@/lib/auditVisibleKeys";

/** Display label for each investigation type key (live or benchmark). */
const INV_DISPLAY: Record<string, string> = {
  blood_test:          "Blood test",
  imaging:             "Imaging",
  urinalysis:          "Urinary test",
  urinary_test:        "Urinary test",
  biopsy:              "Biopsy",
  endoscopy:           "Endoscopy",
  symptomatic_fit:     "Symptomatic FIT",
  other_investigation: "Other",
  investigation:       "Other",
};

/**
 * Maps a live investigation type key to the benchmark metric key in the JSON.
 * Returns null for types that have no 2018 benchmark equivalent.
 */
const INV_BM_KEY: Record<string, string> = {
  blood_test:          "investigations.blood_test_pct",
  imaging:             "investigations.imaging_pct",
  urinalysis:          "investigations.urinary_test_pct",
  urinary_test:        "investigations.urinary_test_pct",
  endoscopy:           "investigations.endoscopy_pct",
  symptomatic_fit:     "investigations.symptomatic_fit_pct",
  other_investigation: "investigations.other_investigation_pct",
  investigation:       "investigations.other_investigation_pct",
};

/** Canonical ordered list of investigation types (2018 benchmark order). */
const BM_TYPES = [
  { type: "blood_test",          bmKey: "blood_test_pct"          },
  { type: "imaging",             bmKey: "imaging_pct"             },
  { type: "urinary_test",        bmKey: "urinary_test_pct"        },
  { type: "endoscopy",           bmKey: "endoscopy_pct"           },
  { type: "symptomatic_fit",     bmKey: "symptomatic_fit_pct"     },
  { type: "other_investigation", bmKey: "other_investigation_pct" },
];

const INV_BM_METRICS = BM_TYPES.map(({ type, bmKey }) => ({
  metricKey: bmKey,
  label: INV_DISPLAY[type] ?? type,
}));

interface Props {
  result: AuditSectionResult<AuditInvestigations> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function InvestigationsSection({ result, loading, error, orgSelected = false }: Props) {
  const { showCancerAlliance, showAllPatients } = useAuditBenchmarkOverlay();
  const visibleKeys = buildAuditBarVisibleKeys(orgSelected, showCancerAlliance, showAllPatients);
  const practice    = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive  = result?.scopes.england_live;
  const bm           = result?.benchmark?.metrics;

  const atLeastOneBm = resolveBenchmarkValue(bm, "investigations.at_least_one_pct", orgSelected);

  // ── Summary: had ≥1 investigation vs none ──────────────────────────────────
  const summaryChart: ComparisonDataRow[] = [
    {
      category: "≥1 investigation",
      practice: practice?.has_investigation_pct ?? null,
      similar:  allianceLive?.has_investigation_pct ?? null,
      alliance: englandLive?.has_investigation_pct ?? null,
      national: atLeastOneBm,
    },
    {
      category: "No investigation",
      practice: practice?.no_investigation_pct ?? null,
      similar:  allianceLive?.no_investigation_pct ?? null,
      alliance: englandLive?.no_investigation_pct ?? null,
      national: atLeastOneBm != null ? 100 - atLeastOneBm : null,
    },
  ];

  // ── Type breakdown: union of live types + all 2018 benchmark types ─────────
  const liveTypes = new Set((practice?.types ?? []).map((t) => t.type));

  // canonical order: BM_TYPES first (maintaining 2018 report order), then any
  // live-only types not in the benchmark list
  const allTypes: string[] = [
    ...BM_TYPES.map((b) => b.type),
    ...(practice?.types ?? [])
      .map((t) => t.type)
      .filter((t) => !BM_TYPES.some((b) => b.type === t || INV_BM_KEY[t] === INV_BM_KEY[b.type])),
  ];

  const typeChart: ComparisonDataRow[] = allTypes.map((typeKey) => {
    const liveMatch = (practice?.types ?? []).find((t) => t.type === typeKey);
    const allianceMatch = (allianceLive?.types ?? []).find((t) => t.type === typeKey);
    const englandMatch  = (englandLive?.types ?? []).find((t) => t.type === typeKey);
    const bmKey = INV_BM_KEY[typeKey] ?? null;

    return {
      category: INV_DISPLAY[typeKey] ?? typeKey,
      practice: liveMatch?.pct ?? (liveTypes.size === 0 ? null : 0),
      similar:  allianceMatch?.pct ?? null,
      alliance: englandMatch?.pct ?? null,
      national: bmKey ? resolveBenchmarkValue(bm, bmKey, orgSelected) : null,
    };
  });

  // ── Summary table ──────────────────────────────────────────────────────────
  const tableRows = [
    {
      label:    "Had at least one investigation (%)",
      unit:     "%",
      practice: practice  ? { value: practice.has_investigation_pct  } : null,
      similar:  allianceLive ? { value: allianceLive.has_investigation_pct } : null,
      alliance: englandLive  ? { value: englandLive.has_investigation_pct  } : null,
      national: { value: atLeastOneBm },
    },
    ...BM_TYPES.map(({ type, bmKey }) => {
      const liveP  = (practice?.types      ?? []).find((t) => t.type === type);
      const liveA  = (allianceLive?.types  ?? []).find((t) => t.type === type);
      const liveE  = (englandLive?.types   ?? []).find((t) => t.type === type);
      return {
        label:    `${INV_DISPLAY[type] ?? type} (of investigations) (%)`,
        unit:     "%",
        practice: liveP ? { value: liveP.pct } : null,
        similar:  liveA ? { value: liveA.pct } : null,
        alliance: liveE ? { value: liveE.pct } : null,
        national: { value: resolveBenchmarkValue(bm, `investigations.${bmKey}`, orgSelected) },
      };
    }),
  ];

  return (
    <SectionCard
      id="section-investigations"
      title="Investigations"
      description="Tests ordered by the GP (family doctor) before referring the patient to a specialist."
      availability="pipeline_pending"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />

      {/* Had ≥1 investigation */}
      <ComparisonBarChart
        data={summaryChart}
        unit="percent"
        height={220}
        visibleKeys={visibleKeys}
        orgSelected={orgSelected}
        ariaLabel="Proportion of patients with and without primary care investigations"
      />

      {/* Investigation type breakdown */}
      <Box sx={{ mt: 2 }}>
        <ComparisonBarChart
          data={typeChart}
          unit="percent"
          height={Math.max(280, allTypes.length * 36 + 80)}
          visibleKeys={visibleKeys}
          orgSelected={orgSelected}
          ariaLabel="Type of investigations ordered"
        />
      </Box>

      {/* 2018 per-cancer-type benchmark grid */}
      <CancerTypeBenchmarkGrid
        bm={bm}
        section="investigations"
        metrics={INV_BM_METRICS}
        orgSelected={orgSelected}
        heading="2018 Investigation Types by Cancer Type"
        showAlliance2018={orgSelected ? showCancerAlliance : undefined}
        showNational2018={orgSelected ? showAllPatients : undefined}
      />

      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable
          rows={tableRows}
          visibleKeys={visibleKeys}
          orgSelected={orgSelected}
          caption="Investigation summary"
        />
      </Box>
    </SectionCard>
  );
}
