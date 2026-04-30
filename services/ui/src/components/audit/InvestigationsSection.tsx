/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

/**
 * Investigations -- year-on-year evolution + GDS blood signal analysis.
 *
 * Year cards show % of patients with >= 1 primary-care investigation.
 * The Blood Signal Analysis section below exposes three views:
 *
 *   Scatter    -- raw value scatter for two user-selected tests (actual
 *                 values, NHS reference band shaded), filtered to patients
 *                 with at least one reading in the window.
 *   Feature Signal -- Pearson correlation of z-scores vs cancer label.
 *   Per Test   -- Box plots of actual values for cancer vs benign,
 *                 overlaid with the NHS reference range.
 */

import dynamic from "next/dynamic";
import { Fragment, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import MuiTooltip from "@mui/material/Tooltip";
import {
  BarChart,
  Bar,
  Cell,
  LabelList,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

import {
  fetchAuditInvestigations,
  fetchAuditBloodSignal,
  fetchAuditBloodSignalDistributions,
  fetchAuditBloodSignalCancerTypeMatrix,
  type AuditInvestigations,
  type AuditSectionResult,
  type AuditBloodSignal,
  type BloodTestDistribution,
  type BloodCancerTypeMatrix,
  type PatientFlagRow,
  type HeatmapCell,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import SectionCard from "./SectionCard";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import EvolutionDetailDialog from "./EvolutionDetailDialog";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

// Plotly loaded client-side only (avoids SSR mismatch)
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const ACCENT = "#0369A1";
const C_BENCH18 = "#92400E";
const C_CANCER = "#DC2626";
const C_BENIGN = "#0369A1";

const INV_DISPLAY: Record<string, string> = {
  blood_test: "Blood test",
  imaging: "Imaging",
  urinalysis: "Urinary test",
  urinary_test: "Urinary test",
  biopsy: "Biopsy",
  endoscopy: "Endoscopy",
  symptomatic_fit: "Symptomatic FIT",
  other_investigation: "Other",
  investigation: "Other",
};

const BM_TYPES = [
  { type: "blood_test", bmKey: "blood_test_pct" },
  { type: "imaging", bmKey: "imaging_pct" },
  { type: "urinary_test", bmKey: "urinary_test_pct" },
  { type: "endoscopy", bmKey: "endoscopy_pct" },
  { type: "symptomatic_fit", bmKey: "symptomatic_fit_pct" },
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

function formatPct(v: number | null | undefined): string | null {
  if (v == null) return null;
  return `${Math.round(v * 10) / 10}%`;
}

// ---------------------------------------------------------------------------
// Per-test Plotly box plot -- one card per test
// ---------------------------------------------------------------------------

function TestBoxCard({ dist }: { dist: BloodTestDistribution }) {
  const traces: object[] = [];

  if (dist.cancer) {
    traces.push({
      type: "box",
      name: "Cancer",
      q1: [dist.cancer.q1],
      median: [dist.cancer.median],
      q3: [dist.cancer.q3],
      lowerfence: [dist.cancer.p10],
      upperfence: [dist.cancer.p90],
      mean: [dist.cancer.mean],
      x: ["Cancer"],
      marker: { color: C_CANCER },
      line: { color: C_CANCER },
      fillcolor: `${C_CANCER}30`,
      showlegend: false,
    });
  }

  if (dist.benign) {
    traces.push({
      type: "box",
      name: "Benign",
      q1: [dist.benign.q1],
      median: [dist.benign.median],
      q3: [dist.benign.q3],
      lowerfence: [dist.benign.p10],
      upperfence: [dist.benign.p90],
      mean: [dist.benign.mean],
      x: ["Benign"],
      marker: { color: C_BENIGN },
      line: { color: C_BENIGN },
      fillcolor: `${C_BENIGN}30`,
      showlegend: false,
    });
  }

  const allValues = [
    dist.cancer?.p10, dist.cancer?.p90,
    dist.benign?.p10, dist.benign?.p90,
    dist.ref_low, dist.ref_high,
  ].filter((v): v is number => v != null);
  const yPad = (Math.max(...allValues) - Math.min(...allValues)) * 0.15 || 1;
  const yMin = Math.min(...allValues) - yPad;
  const yMax = Math.max(...allValues) + yPad;

  const shapes: object[] = dist.ref_low != null && dist.ref_high != null
    ? [{
        type: "rect",
        xref: "paper",
        yref: "y",
        x0: 0, x1: 1,
        y0: dist.ref_low,
        y1: dist.ref_high,
        fillcolor: "#16A34A18",
        line: { width: 0 },
      }]
    : [];

  const annotations: object[] = dist.ref_high != null
    ? [{
        xref: "paper",
        yref: "y",
        x: 1,
        y: dist.ref_high,
        text: "NHS ref",
        showarrow: false,
        xanchor: "right",
        yanchor: "bottom",
        font: { size: 9, color: "#16A34A" },
      }]
    : [];

  const nLabel = [
    dist.cancer ? `C:${dist.cancer.n}` : null,
    dist.benign ? `B:${dist.benign.n}` : null,
  ].filter(Boolean).join(" ");

  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1 }}>
      <Typography variant="caption" sx={{ fontWeight: 600, display: "block" }}>
        {dist.label}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block">
        {dist.unit} &nbsp;·&nbsp; n={nLabel}
      </Typography>
      <Plot
        data={traces as Plotly.Data[]}
        layout={{
          height: 200,
          margin: { t: 4, b: 24, l: 36, r: 8 },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          yaxis: { range: [yMin, yMax], tickfont: { size: 10 }, gridcolor: "#E5E7EB" },
          xaxis: { tickfont: { size: 10 } },
          shapes,
          annotations,
          font: { family: "inherit" },
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%", height: 200 }}
        useResizeHandler
      />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// By Cancer Type tab
// ---------------------------------------------------------------------------

const FLAG_COLOUR: Record<string, string> = {
  high:    C_CANCER,
  low:     C_BENIGN,
  normal:  "#6B7280",
  no_data: "#E5E7EB",
};
const FLAG_SYMBOL: Record<string, string> = {
  high:    "↑",
  low:     "↓",
  normal:  "✓",
  no_data: "—",
};

function CancerTypeHeatmap({
  matrix,
}: {
  matrix: BloodCancerTypeMatrix;
}) {
  const { cancer_types, tests, heatmap_cells } = matrix;

  // Build z-values matrix: rows = cancer types (ordered desc n), cols = tests
  const cellMap = new Map(
    heatmap_cells.map((c) => [`${c.cancer_type}||${c.test_key}`, c]),
  );

  const zValues: (number | null)[][] = cancer_types.map((ct) =>
    tests.map((t) => {
      const c = cellMap.get(`${ct}||${t.key}`);
      return c?.effect_size ?? null;
    }),
  );

  const textValues: string[][] = cancer_types.map((ct) =>
    tests.map((t) => {
      const c = cellMap.get(`${ct}||${t.key}`);
      if (!c || c.n_with_data === 0) return "—";
      return `n=${c.n_with_data}`;
    }),
  );

  const hoverText: string[][] = cancer_types.map((ct) =>
    tests.map((t) => {
      const c = cellMap.get(`${ct}||${t.key}`);
      if (!c || c.n_with_data === 0)
        return `${ct} · ${t.label}<br>No readings`;
      const dir = (c.effect_size ?? 0) > 0 ? "↑ above" : "↓ below";
      return (
        `<b>${ct} · ${t.label}</b><br>` +
        `n with readings: ${c.n_with_data} / ${c.n_total}<br>` +
        `Cancer median: ${c.median_value?.toFixed(2) ?? "—"}<br>` +
        `Benign median: ${c.benign_median.toFixed(2)}<br>` +
        `Effect size: ${c.effect_size?.toFixed(2) ?? "—"} (${dir} benign)<br>` +
        `% high: ${c.pct_high ?? "—"}% · % low: ${c.pct_low ?? "—"}%<br>` +
        `NHS ref: ${c.ref_range_raw ?? "not recorded"}`
      );
    }),
  );

  return (
    <Plot
      data={[
        {
          type: "heatmap",
          z: zValues,
          x: tests.map((t) => t.label),
          y: cancer_types,
          // text is 2-D for heatmap; cast via unknown to satisfy @types/plotly.js
          text: textValues as unknown as string[],
          hovertext: hoverText as unknown as string[],
          hoverinfo: "text",
          texttemplate: "%{text}",
          textfont: { size: 9 },
          colorscale: [
            [0,    "#1E40AF"],
            [0.35, "#BFDBFE"],
            [0.5,  "#F9FAFB"],
            [0.65, "#FCA5A5"],
            [1,    "#991B1B"],
          ],
          zmid: 0,
          zmin: -4,
          zmax: 4,
          showscale: true,
          colorbar: {
            title: { text: "Effect vs benign", side: "right" },
            tickvals: [-4, -2, 0, 2, 4],
            ticktext: ["-4 (low)", "-2", "0", "+2", "+4 (high)"],
            len: 0.8,
          },
        } as Plotly.Data,
      ]}
      layout={{
        height: Math.max(300, cancer_types.length * 36 + 80),
        margin: { t: 8, b: 100, l: 100, r: 110 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        xaxis: { tickangle: -40, tickfont: { size: 10 }, side: "bottom" },
        yaxis: { tickfont: { size: 11 }, autorange: "reversed" },
        font: { family: "inherit" },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
      useResizeHandler
    />
  );
}

function PatientFlagMatrix({
  patientFlags,
  tests,
}: {
  patientFlags: PatientFlagRow[];
  tests: BloodCancerTypeMatrix["tests"];
}) {
  // Group by cancer type to render section headers
  const groups = useMemo(() => {
    const seen = new Set<string>();
    const order: string[] = [];
    for (const r of patientFlags) {
      if (!seen.has(r.cancer_type)) { seen.add(r.cancer_type); order.push(r.cancer_type); }
    }
    return order.map((ct) => ({
      ct,
      rows: patientFlags.filter((r) => r.cancer_type === ct),
    }));
  }, [patientFlags]);

  return (
    <Box sx={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "4px 8px", minWidth: 100, fontWeight: 600, whiteSpace: "nowrap" }}>
              Patient
            </th>
            {tests.map((t) => (
              <th
                key={t.key}
                style={{
                  padding: "4px 4px",
                  fontWeight: 500,
                  fontSize: 10,
                  writingMode: "vertical-rl",
                  transform: "rotate(180deg)",
                  whiteSpace: "nowrap",
                  height: 80,
                  verticalAlign: "bottom",
                }}
              >
                {t.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map(({ ct, rows }) => (
            <Fragment key={ct}>
              <tr>
                <td
                  colSpan={tests.length + 1}
                  style={{
                    background: "#F3F4F6",
                    fontWeight: 600,
                    fontSize: 11,
                    padding: "3px 8px",
                    borderTop: "2px solid #D1D5DB",
                  }}
                >
                  {ct} &nbsp;
                  <span style={{ fontWeight: 400, color: "#6B7280" }}>
                    (n={rows.length})
                  </span>
                </td>
              </tr>
              {rows.map((row) => (
                <tr key={row.episode_id} style={{ borderBottom: "1px solid #F3F4F6" }}>
                  <td style={{ padding: "3px 8px", whiteSpace: "nowrap", color: "#374151", fontSize: 11 }}>
                    {row.label}
                  </td>
                  {tests.map((t) => {
                    const flag = row.flags[t.key] ?? "no_data";
                    const rawVal = row.values[t.key];
                    const colour = FLAG_COLOUR[flag];
                    const symbol = FLAG_SYMBOL[flag];
                    const isNoData = flag === "no_data";
                    return (
                      <td key={t.key} style={{ padding: "2px 3px", textAlign: "center" }}>
                        <MuiTooltip
                          title={
                            isNoData
                              ? "No reading in window"
                              : `${t.label}: ${rawVal?.toFixed(2) ?? "—"} (${flag})`
                          }
                          arrow
                        >
                          <span
                            style={{
                              display: "inline-block",
                              width: 20,
                              height: 20,
                              lineHeight: "20px",
                              borderRadius: 3,
                              fontSize: 11,
                              fontWeight: 600,
                              color: isNoData ? "#D1D5DB" : "#FFFFFF",
                              background: isNoData ? "transparent" : colour,
                              cursor: "default",
                            }}
                          >
                            {symbol}
                          </span>
                        </MuiTooltip>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </Box>
  );
}

function CancerTypeTab() {
  const [matrix, setMatrix] = useState<BloodCancerTypeMatrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAuditBloodSignalCancerTypeMatrix()
      .then((d) => { setMatrix(d); setError(null); })
      .catch(() => setError("Could not load cancer type matrix."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 4 }}>
      <CircularProgress size={20} />
      <Typography variant="body2" color="text.secondary">Loading...</Typography>
    </Box>
  );
  if (error) return <Alert severity="error">{error}</Alert>;
  if (!matrix) return null;

  return (
    <Box>
      <Alert severity="info" icon={false} sx={{ mb: 2, py: 0.5, fontSize: 12 }}>
        Exploratory only — max n=7 per cancer type in current cohort. Statistical significance not implied.
        Colour shows how far each cancer type's median sits above (red) or below (blue) the benign cohort median,
        expressed in benign standard deviations. Cell annotation = number with readings / total.
      </Alert>

      <Box sx={{ display: "flex", gap: 2.5, mb: 1.5, flexWrap: "wrap" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Box sx={{ width: 20, height: 12, background: "linear-gradient(to right, #1E40AF, #F9FAFB, #991B1B)", borderRadius: 1 }} />
          <Typography variant="caption">Heatmap: lower vs benign → higher</Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          {["high", "low", "normal", "no_data"].map((f) => (
            <Box key={f} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
              <span style={{
                display: "inline-block", width: 16, height: 16, lineHeight: "16px",
                borderRadius: 2, fontSize: 10, fontWeight: 600, textAlign: "center",
                color: f === "no_data" ? "#9CA3AF" : "#FFF",
                background: f === "no_data" ? "transparent" : FLAG_COLOUR[f],
                border: f === "no_data" ? "1px solid #D1D5DB" : "none",
              }}>
                {FLAG_SYMBOL[f]}
              </span>
              <Typography variant="caption">
                {f === "high" ? "Above ref" : f === "low" ? "Below ref" : f === "normal" ? "In range" : "No data"}
              </Typography>
            </Box>
          ))}
        </Box>
      </Box>

      <Typography variant="subtitle2" sx={{ mb: 0.5, mt: 1 }}>
        Blood profile deviation by cancer type
      </Typography>
      <CancerTypeHeatmap matrix={matrix} />

      <Typography variant="subtitle2" sx={{ mb: 0.5, mt: 3 }}>
        Per-patient test results — combinations
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        Each cell shows whether the patient's mean value was above (↑), below (↓), or within (✓) the NHS reference range.
        Hover for exact values.
      </Typography>
      <PatientFlagMatrix patientFlags={matrix.patient_flags} tests={matrix.tests} />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Feature Signal tab (Pearson r bar chart)
// ---------------------------------------------------------------------------

function FeatureSignalTab({
  correlations,
  featureLabels,
}: {
  correlations: Record<string, number>;
  featureLabels: Record<string, string>;
}) {
  const rows = useMemo(
    () =>
      Object.entries(correlations)
        .map(([key, r]) => ({
          label: featureLabels[key] ?? key,
          r,
          direction: r > 0 ? "cancer" : "benign",
        }))
        .sort((a, b) => Math.abs(b.r) - Math.abs(a.r)),
    [correlations, featureLabels],
  );

  return (
    <Box>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
        Pearson correlation between z-score and cancer diagnosis (n={Object.keys(correlations).length} tests).
        Positive = higher in cancer; negative = higher in benign.
        Small cohort — treat as exploratory signal.
      </Typography>
      <ResponsiveContainer width="100%" height={Math.max(300, rows.length * 32 + 60)}>
        <BarChart
          layout="vertical"
          data={rows}
          margin={{ top: 4, right: 60, bottom: 24, left: 90 }}
        >
          <CartesianGrid horizontal={false} strokeDasharray="3 3" opacity={0.3} />
          <XAxis
            type="number"
            domain={[-0.35, 0.35]}
            tickFormatter={(v) => v.toFixed(2)}
            label={{ value: "Pearson r", position: "insideBottom", offset: -16, fontSize: 11 }}
          />
          <YAxis type="category" dataKey="label" width={80} tick={{ fontSize: 12 }} />
          <ReferenceLine x={0} stroke="#6B7280" />
          <RechartsTooltip formatter={(v: unknown) => [typeof v === "number" ? v.toFixed(4) : String(v), "r"]} />
          <Bar dataKey="r" radius={[0, 3, 3, 0]}>
            {rows.map((row, i) => (
              <Cell key={i} fill={row.direction === "cancer" ? C_CANCER : C_BENIGN} fillOpacity={0.8} />
            ))}
            <LabelList
              dataKey="r"
              position="right"
              formatter={(v: unknown) => (typeof v === "number" ? v.toFixed(3) : "")}
              style={{ fontSize: 11, fill: "#6B7280" }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <Typography variant="caption" color="text.secondary">
        Red: elevated in cancer patients &nbsp;·&nbsp; Blue: elevated in benign/no-cancer patients
      </Typography>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Blood Signal Dialog
// ---------------------------------------------------------------------------

type BloodTab = "bytype" | "signal" | "pertest";

function BloodSignalDialog({
  open,
  onClose,
  data,
}: {
  open: boolean;
  onClose: () => void;
  data: AuditBloodSignal;
}) {
  const [tab, setTab] = useState<BloodTab>("bytype");
  const [distributions, setDistributions] = useState<BloodTestDistribution[]>([]);
  const [distLoading, setDistLoading] = useState(false);

  useEffect(() => {
    if (!open || distributions.length) return;
    setDistLoading(true);
    fetchAuditBloodSignalDistributions()
      .then(setDistributions)
      .catch(() => setDistributions([]))
      .finally(() => setDistLoading(false));
  }, [open, distributions.length]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ pb: 0 }}>
        Blood Result Cancer Signal
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {data.cancer_n} cancer &nbsp;·&nbsp; {data.benign_n} benign / no-cancer &nbsp;·&nbsp;
          12 months before referral + 28 days &nbsp;·&nbsp; {data.feature_keys.length} tests
        </Typography>
      </DialogTitle>

      <Box sx={{ borderBottom: 1, borderColor: "divider", px: 3 }}>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v as BloodTab)}
          textColor="primary"
          indicatorColor="primary"
        >
          <Tab label="By Cancer Type" value="bytype" />
          <Tab label="Per Test" value="pertest" />
          <Tab label="Feature Signal" value="signal" />
        </Tabs>
      </Box>

      <DialogContent sx={{ pt: 2 }}>
        {tab === "pertest" && (
          <Box>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
              Box shows P10–P90 with median line and mean marker. Green band = NHS reference range.
              Only patients with at least one reading in the window included.
            </Typography>
            <Box sx={{ display: "flex", gap: 1.5, mb: 2 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <Box sx={{ width: 12, height: 12, borderRadius: "2px", bgcolor: `${C_CANCER}80` }} />
                <Typography variant="caption">Cancer</Typography>
              </Box>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <Box sx={{ width: 12, height: 12, borderRadius: "2px", bgcolor: `${C_BENIGN}80` }} />
                <Typography variant="caption">Benign / no cancer</Typography>
              </Box>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <Box sx={{ width: 12, height: 6, bgcolor: "#16A34A20", border: "1px solid #16A34A40" }} />
                <Typography variant="caption">NHS reference range</Typography>
              </Box>
            </Box>
            {distLoading && (
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 4 }}>
                <CircularProgress size={20} />
                <Typography variant="body2" color="text.secondary">Loading distributions...</Typography>
              </Box>
            )}
            {!distLoading && (
              <Grid container spacing={2}>
                {distributions.map((dist) => (
                  <Grid key={dist.key} size={{ xs: 12, sm: 6, md: 4 }}>
                    <TestBoxCard dist={dist} />
                  </Grid>
                ))}
              </Grid>
            )}
          </Box>
        )}

        {tab === "bytype" && <CancerTypeTab />}

        {tab === "signal" && (
          <FeatureSignalTab
            correlations={data.correlations}
            featureLabels={data.feature_labels}
          />
        )}
      </DialogContent>

      <DialogActions>
        <Typography variant="caption" color="text.secondary" sx={{ mr: "auto", pl: 1 }}>
          Enriched by GDS 2026.04.0 &nbsp;·&nbsp; 585 BLOOD_SIMILAR relationships &nbsp;·&nbsp;
          Refresh: scripts/gds/build_blood_feature_vectors.py --apply
        </Typography>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function InvestigationsSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const { showCancerAlliance, showAllPatients } = useAuditBenchmarkOverlay();
  const bm = result?.benchmark?.metrics;

  const { liveYears } = useAuditYearWindows<AuditInvestigations>(
    fetchAuditInvestigations,
    { orgId },
  );

  const [zoomYear, setZoomYear] = useState<number | null>(null);
  const [bloodDialogOpen, setBloodDialogOpen] = useState(false);
  const [bloodData, setBloodData] = useState<AuditBloodSignal | null>(null);
  const [bloodLoading, setBloodLoading] = useState(false);
  const [bloodError, setBloodError] = useState<string | null>(null);

  useEffect(() => {
    setBloodLoading(true);
    fetchAuditBloodSignal()
      .then((d) => { setBloodData(d); setBloodError(null); })
      .catch(() =>
        setBloodError("Blood signal data not available. Run the GDS enrichment script first."),
      )
      .finally(() => setBloodLoading(false));
  }, []);

  const baselinePct = useMemo(
    () => resolveBenchmarkValue(bm, "investigations.at_least_one_pct", orgSelected),
    [bm, orgSelected],
  );

  const detailRows: ComparisonDataRow[] = useMemo(() => {
    if (zoomYear == null) return [];
    const state = liveYears.find((s) => s.year === zoomYear);
    const data = state?.data;
    if (!data) return [];
    return BM_TYPES.map(({ type, bmKey }) => {
      const live = (data.types ?? []).find((t) => t.type === type);
      return {
        category: INV_DISPLAY[type] ?? type,
        practice: live?.pct ?? 0,
        national: resolveBenchmarkValue(bm, `investigations.${bmKey}`, orgSelected),
      } satisfies ComparisonDataRow;
    });
  }, [zoomYear, liveYears, bm, orgSelected]);

  const visibleKeys = ["practice", "national"] as const;

  return (
    <SectionCard
      id="section-investigations"
      title="Investigations"
      description="Tests ordered by the GP before referring the patient to a specialist. Each card covers a Jan-Dec calendar year. The Blood Signal Analysis uses GDS to compare blood test values across cancer and benign FTR cohorts."
      availability="pipeline_pending"
      loading={loading}
      loadingSkeletonVariant="cardGrid"
      error={error}
    >
      <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
        <EvolutionLegendSwatch colour={C_BENCH18} label="2018 NCDA baseline" dashed />
        <EvolutionLegendSwatch colour={ACCENT} label="Live year" />
      </Box>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <EvolutionYearCard
            yearLabel={String(BASELINE_YEAR)}
            headlineValue={formatPct(baselinePct)}
            headlineSubLabel=">= 1 investigation"
            isBaseline
            baselineFootnote={
              baselinePct == null
                ? "No published 2018 NCDA value for the selected scope."
                : "Per-type breakdown shown below in the cancer-type grid."
            }
          />
        </Grid>
        {liveYears.map((state) => (
          <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
            <EvolutionYearCard
              yearLabel={String(state.year)}
              loading={state.loading}
              error={state.error}
              totalN={state.data?.total_episodes ?? 0}
              headlineValue={formatPct(state.data?.has_investigation_pct)}
              headlineSubLabel=">= 1 investigation"
              accentColor={ACCENT}
              onZoom={() => setZoomYear(state.year)}
              zoomAriaLabel={`Open per-type investigation breakdown for ${state.year}`}
            />
          </Grid>
        ))}
      </Grid>

      <Box sx={{ mt: 3 }}>
        <CancerTypeBenchmarkGrid
          bm={bm}
          section="investigations"
          metrics={INV_BM_METRICS}
          orgSelected={orgSelected}
          heading="2018 Investigation Types by Cancer Type"
          showAlliance2018={orgSelected ? showCancerAlliance : undefined}
          showNational2018={orgSelected ? showAllPatients : undefined}
        />
      </Box>

      {/* Blood Signal subsection */}
      <Divider sx={{ my: 3 }} />
      <Box>
        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          Blood Result Cancer Signal
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5, maxWidth: 680 }}>
          GDS analysis of coded blood results in the 12 months before referral. Box plots show
          actual value ranges for cancer vs benign FTR patients, overlaid with NHS reference ranges.
        </Typography>

        {bloodLoading && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <CircularProgress size={16} />
            <Typography variant="body2" color="text.secondary">Loading...</Typography>
          </Box>
        )}
        {bloodError && !bloodLoading && (
          <Alert severity="info" sx={{ maxWidth: 560 }}>{bloodError}</Alert>
        )}
        {bloodData && !bloodLoading && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
            <Box sx={{ display: "flex", gap: 1.5 }}>
              <Chip
                label={`${bloodData.cancer_n} cancer`}
                size="small"
                sx={{ bgcolor: "#FEE2E2", color: "#991B1B", fontWeight: 600 }}
              />
              <Chip
                label={`${bloodData.benign_n} benign / no cancer`}
                size="small"
                sx={{ bgcolor: "#DBEAFE", color: "#1E40AF", fontWeight: 600 }}
              />
              <Chip label={`${bloodData.feature_keys.length} tests`} size="small" variant="outlined" />
            </Box>
            <Button variant="outlined" size="small" onClick={() => setBloodDialogOpen(true)}>
              Open analysis
            </Button>
          </Box>
        )}
      </Box>

      {/* Year zoom dialog */}
      <EvolutionDetailDialog
        open={zoomYear != null}
        onClose={() => setZoomYear(null)}
        title={`Investigations by type - ${zoomYear ?? ""}`}
        subtitle="% of patients receiving each investigation type, compared to the 2018 NCDA baseline."
      >
        {detailRows.length > 0 ? (
          <ComparisonBarChart
            data={detailRows}
            unit="percent"
            height={Math.max(280, detailRows.length * 36 + 80)}
            visibleKeys={visibleKeys}
            orgSelected={orgSelected}
            ariaLabel={`Investigations by type for ${zoomYear}`}
          />
        ) : (
          <Box sx={{ p: 2, fontSize: "0.85rem", color: "text.secondary" }}>
            No investigation data captured for this year.
          </Box>
        )}
      </EvolutionDetailDialog>

      {/* Blood Signal dialog */}
      {bloodData && (
        <BloodSignalDialog
          open={bloodDialogOpen}
          onClose={() => setBloodDialogOpen(false)}
          data={bloodData}
        />
      )}
    </SectionCard>
  );
}
