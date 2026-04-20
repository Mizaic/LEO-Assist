/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A23404E0
 *   DI: DI-23822663, DO-671C15BF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A23404E0")
 */
"use client";

import SectionCard from "./SectionCard";
import CancerStageBulletChart from "./CancerStageBulletChart";
import CancerStageAccordion from "./CancerStageAccordion";
import { resolveBenchmarkValue } from "./BenchmarkLegend";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import type { AuditCancerStageSummary, AuditSectionResult } from "@/lib/analyticsApi";

// -- Stage classification helpers -----------------------------------------

type StageGroup = "early" | "late" | "other";

const ROMAN_WEIGHT: Record<string, number> = {
  I: 1, IA: 1.1, IB: 1.2, IC: 1.3,
  II: 2, IIA: 2.1, IIB: 2.2, IIC: 2.3,
  III: 3, IIIA: 3.1, IIIB: 3.2, IIIC: 3.3,
  IV: 4, IVA: 4.1, IVB: 4.2,
};

function stageWeight(stage: string): number {
  const s = stage.trim().toUpperCase();
  if (ROMAN_WEIGHT[s] !== undefined) return ROMAN_WEIGHT[s];
  const n = parseFloat(s);
  return isNaN(n) ? 99 : n;
}

function classifyStage(stage: string): StageGroup {
  const w = stageWeight(stage);
  if (w <= 2.9) return "early";
  if (w <= 4.9) return "late";
  return "other";
}

interface StageRow { cancer_stage_group: string; n: number }

function buildStageGroups(rows: StageRow[]): {
  early: StageRow[];
  late: StageRow[];
  other: StageRow[];
  total: number;
} {
  const sorted = [...rows].sort((a, b) => stageWeight(a.cancer_stage_group) - stageWeight(b.cancer_stage_group));
  const early: StageRow[] = [];
  const late: StageRow[] = [];
  const other: StageRow[] = [];
  for (const r of sorted) {
    const g = classifyStage(r.cancer_stage_group);
    if (g === "early") early.push(r);
    else if (g === "late") late.push(r);
    else other.push(r);
  }
  const total = rows.reduce((s, r) => s + r.n, 0);
  return { early, late, other, total };
}

interface Props {
  result: AuditSectionResult<AuditCancerStageSummary> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

// -- StageBreakdown component ---------------------------------------------

interface StagePillProps { row: StageRow; total: number; color: string }

function StagePill({ row, total, color }: StagePillProps) {
  const barPct = total > 0 ? Math.round((row.n / total) * 100) : 0;
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
      <Chip
        label={`Stage ${row.cancer_stage_group}`}
        size="small"
        sx={{
          fontWeight: 600,
          bgcolor: `${color}.50`,
          color: `${color}.800`,
          border: "1px solid",
          borderColor: `${color}.200`,
          flexShrink: 0,
          "& .MuiChip-label": { px: 1 },
        }}
      />
      <Box
        sx={{
          flex: 1,
          height: 6,
          borderRadius: 3,
          bgcolor: "grey.100",
          minWidth: 40,
          maxWidth: 120,
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            height: "100%",
            width: `${barPct}%`,
            borderRadius: 3,
            bgcolor: `${color}.main`,
            transition: "width 0.4s ease",
          }}
        />
      </Box>
      <Typography variant="caption" sx={{ color: "text.secondary", whiteSpace: "nowrap", flexShrink: 0 }}>
        {row.n} {row.n === 1 ? "patient" : "patients"}
      </Typography>
    </Box>
  );
}

interface StageGroupBlockProps {
  label: string;
  rows: StageRow[];
  total: number;
  color: string;
  description: string;
}

function StageGroupBlock({ label, rows, total, color, description }: StageGroupBlockProps) {
  if (rows.length === 0) return null;
  const groupTotal = rows.reduce((s, r) => s + r.n, 0);
  const groupPct = total > 0 ? Math.round((groupTotal / total) * 100) : 0;
  return (
    <Box
      sx={{
        flex: "1 1 200px",
        border: "1px solid",
        borderColor: `${color}.100`,
        borderRadius: 2,
        p: 1.5,
        bgcolor: `${color}.50`,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", mb: 0.5 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: `${color}.800` }}>
          {label}
        </Typography>
        <Typography variant="caption" sx={{ color: `${color}.700`, fontWeight: 600 }}>
          {groupTotal} patients ({groupPct}%)
        </Typography>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        {description}
      </Typography>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
        {rows.map((r) => (
          <StagePill key={r.cancer_stage_group} row={r} total={total} color={color} />
        ))}
      </Box>
    </Box>
  );
}

function StageBreakdown({ rows }: { rows: StageRow[] }) {
  const { early, late, other, total } = buildStageGroups(rows);
  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 0.5, fontWeight: 600 }}>
        Patients by stage
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
        Stage 0, 1, and 2 (or I and II) = early. Stage 3 and 4 (or III and IV) = late.
        Some cancer types use Roman numerals instead of numbers.
      </Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1.5 }}>
        <StageGroupBlock
          label="Early stages"
          rows={early}
          total={total}
          color="success"
          description="Usually more treatable. Better long-term outcomes."
        />
        <StageGroupBlock
          label="Late stages"
          rows={late}
          total={total}
          color="warning"
          description="Cancer has spread further. More complex to treat."
        />
        {other.length > 0 && (
          <StageGroupBlock
            label="Other / not classified"
            rows={other}
            total={total}
            color="info"
            description="Staging system does not map to early/late categories."
          />
        )}
      </Box>
    </Box>
  );
}

// -------------------------------------------------------------------------

export default function CancerStageSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice?.rows ?? [];
  const practiceBySource = result?.scopes.practice?.by_source ?? [];
  const practiceCoverage = result?.scopes.practice?.coverage_pct ?? 0;
  const practiceCoverageN = result?.scopes.practice?.coverage_numerator ?? 0;
  const practiceCoverageD = result?.scopes.practice?.coverage_denominator ?? 0;
  const stageDetail = result?.scopes.practice?.by_stage_group_detail ?? [];
  const bm = result?.benchmark?.metrics;
  const byCancerType = result?.scopes.practice?.by_cancer_type ?? [];

  const earlyRow = practice.find((r) => r.stage_group === "early");
  const lateRow  = practice.find((r) => r.stage_group === "late");
  const totalN   = practice.reduce((s, r) => s + r.n, 0);

  return (
    <SectionCard
      id="section-cancer-stage"
      title="Cancer Stage at Diagnosis"
      description="Whether cancer was found early (stage 0, 1, or 2) or late (stage 3 or 4). Finding cancer early usually leads to better outcomes."
      availability="ready"
      loading={loading}
      error={error}
    >
      {practice.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          No stage data is available yet for the selected filters.
        </Typography>
      )}

      <Box sx={{ mb: 1.5 }}>
        <Typography variant="body2" color="text.secondary">
          Stage recorded for {practiceCoverage}% of confirmed cases ({practiceCoverageN} of {practiceCoverageD})
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Data sources: {practiceBySource.map((s) => `${s.staging_source} (${s.n})`).join(", ") || "none"}
        </Typography>
      </Box>

      <CancerStageBulletChart
        earlyPct={earlyRow?.pct ?? null}
        earlyN={earlyRow?.n ?? null}
        latePct={lateRow?.pct ?? null}
        lateN={lateRow?.n ?? null}
        totalN={totalN > 0 ? totalN : null}
        benchmark2018Early={resolveBenchmarkValue(bm, "cancer_stage.early_stage_pct", orgSelected)}
        orgSelected={orgSelected}
      />

      {stageDetail.length > 0 && (
        <StageBreakdown rows={stageDetail} />
      )}

      <Box sx={{ mt: 2 }}>
        <CancerStageAccordion
          byCancerType={byCancerType}
          bm={bm}
          orgSelected={orgSelected}
        />
      </Box>
    </SectionCard>
  );
}
