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
 * Blood Result Cancer Signal -- GDS blood test distribution and signal analysis.
 * Standalone report section plus shared dialog/tab implementation.
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

import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";

import {
  fetchAuditBloodSignal,
  fetchAuditBloodSignalPerTest,
  fetchAuditBloodSignalCancerTypeMatrix,
  type AuditBloodSignal,
  type BloodPerTestResult,
  type BloodCancerTypeMatrix,
  type PatientFlagRow,
} from "@/lib/analyticsApi";
import SectionCard from "./SectionCard";
// Plotly loaded client-side only (avoids SSR mismatch)
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

/** Strip verbose SNOMED qualifiers that slip through the backend cleaner. */
function cleanTestLabel(label: string): string {
  return label
    .replace(/\s*\([^)]*(?:observable entity|finding|disorder|procedure)[^)]*\)\s*/gi, "")
    .replace(/\s+level\s*$/i, "")
    .trim();
}

const C_CANCER = "#DC2626";
const C_BENIGN = "#0369A1";

// ---------------------------------------------------------------------------
// Per-test Plotly box plot -- one card per test
// ---------------------------------------------------------------------------



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
      const tLabel = cleanTestLabel(t.label);
      if (!c || c.n_with_data === 0)
        return `${ct} · ${tLabel}<br>No readings`;
      const dir = (c.effect_size ?? 0) > 0 ? "↑ above" : "↓ below";
      return (
        `<b>${ct} · ${tLabel}</b><br>` +
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
          x: tests.map((t) => cleanTestLabel(t.label)),
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
          margin: { t: 8, b: 130, l: 110, r: 120 },
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
                              : `${cleanTestLabel(t.label)}: ${rawVal?.toFixed(2) ?? "—"} (${flag})`
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
// Per-patient combinations dialog
// ---------------------------------------------------------------------------

function PatientCombinationsDialog({
  open,
  onClose,
  matrix,
}: {
  open: boolean;
  onClose: () => void;
  matrix: BloodCancerTypeMatrix;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={false}
      fullWidth
      sx={{ "& .MuiDialog-paper": { width: "min(98vw, 1400px)", maxHeight: "90vh" } }}
    >
      <DialogTitle sx={{ pb: 1 }}>
        Per-patient test results
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
          Each cell shows whether the patient mean value was above, below, or within the NHS reference range.
          Hover for exact values.
        </Typography>
      </DialogTitle>
      <DialogContent sx={{ pt: 0 }}>
        <Box sx={{ display: "flex", gap: 1, mb: 1.5, flexWrap: "wrap" }}>
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
        <PatientFlagMatrix patientFlags={matrix.patient_flags} tests={matrix.tests} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Per-test distributions dialog
// ---------------------------------------------------------------------------

function PerTestDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [data, setData] = useState<BloodPerTestResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || data.length) return;
    setLoading(true);
    fetchAuditBloodSignalPerTest()
      .then(setData)
      .catch(() => setData([]))
      .finally(() => setLoading(false));
  }, [open, data.length]);

  const cancerTypes = useMemo(() => {
    const types = new Set<string>();
    data.forEach((t) => {
      Object.keys(t.groups).forEach((k) => { if (k !== "Benign") types.add(k); });
    });
    return Array.from(types).sort();
  }, [data]);

  const fmt = (v: number | null | undefined) => {
    if (v == null) return "—";
    return Number.isInteger(v) ? String(v) : v.toFixed(2);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      sx={{ "& .MuiDialog-paper": { maxHeight: "90vh" } }}
    >
      <DialogTitle>
        Per Test Ranges by Cancer Type
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
          Interquartile range (Q1–Q3) of actual values recorded in the 12 months before referral,
          against NHS reference ranges. Intended to inform lab and GP thresholds.
        </Typography>
      </DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        {loading && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 4 }}>
            <CircularProgress size={20} />
            <Typography variant="body2" color="text.secondary">Loading...</Typography>
          </Box>
        )}

        {!loading && cancerTypes.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 3 }}>
            No per-test data available. Run the GDS enrichment script first.
          </Typography>
        )}

        {!loading && cancerTypes.map((cancerType) => {
          const rows = data.filter((t) => t.groups[cancerType] != null);
          if (!rows.length) return null;
          return (
            <Box key={cancerType} sx={{ mb: 4 }}>
              <Typography
                variant="subtitle2"
                sx={{ mb: 1, fontWeight: 700, color: "#991B1B", fontSize: "0.85rem" }}
              >
                {cancerType}
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 700, fontSize: "0.75rem" }}>Test</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: "0.75rem" }}>Unit</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.75rem", color: "#991B1B" }}>
                        Cancer Q1
                      </TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.75rem", color: "#991B1B" }}>
                        Cancer Q3
                      </TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.75rem", color: "#16A34A" }}>
                        NHS Low
                      </TableCell>
                      <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.75rem", color: "#16A34A" }}>
                        NHS High
                      </TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rows.map((t) => {
                      const g = t.groups[cancerType];
                      return (
                        <TableRow key={t.key} hover>
                          <TableCell sx={{ fontSize: "0.8rem" }}>{cleanTestLabel(t.label)}</TableCell>
                          <TableCell sx={{ fontSize: "0.8rem", color: "text.secondary" }}>
                            {t.unit || "—"}
                          </TableCell>
                          <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmt(g.q1)}</TableCell>
                          <TableCell align="right" sx={{ fontSize: "0.8rem" }}>{fmt(g.q3)}</TableCell>
                          <TableCell align="right" sx={{ fontSize: "0.8rem", color: "#16A34A" }}>
                            {fmt(t.ref_low)}
                          </TableCell>
                          <TableCell align="right" sx={{ fontSize: "0.8rem", color: "#16A34A" }}>
                            {fmt(t.ref_high)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          );
        })}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Feature Signal dialog
// ---------------------------------------------------------------------------

function FeatureSignalDialog({
  open,
  onClose,
  correlations,
  featureLabels,
}: {
  open: boolean;
  onClose: () => void;
  correlations: Record<string, number>;
  featureLabels: Record<string, string>;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      sx={{ "& .MuiDialog-paper": { maxHeight: "90vh" } }}
    >
      <DialogTitle>Feature Signal (Pearson r)</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <FeatureSignalTab correlations={correlations} featureLabels={featureLabels} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Standalone report section (TOC: section-blood-signal)
// ---------------------------------------------------------------------------

export default function BloodSignalSection() {
  const [bloodData, setBloodData] = useState<AuditBloodSignal | null>(null);
  const [matrix, setMatrix] = useState<BloodCancerTypeMatrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [patientOpen, setPatientOpen] = useState(false);
  const [perTestOpen, setPerTestOpen] = useState(false);
  const [signalOpen, setSignalOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetchAuditBloodSignal(),
      fetchAuditBloodSignalCancerTypeMatrix(),
    ])
      .then(([signal, mat]) => {
        if (!cancelled) {
          setBloodData(signal);
          setMatrix(mat);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError("Blood signal data not available. Run the GDS enrichment script first.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <>
      <SectionCard
        id="section-blood-signal"
        title="Blood Result Cancer Signal"
        description={
          "GDS comparison of coded blood results in the 12 months before referral. " +
          "Heatmap shows how each cancer type deviates from the benign cohort per blood test, " +
          "expressed in standard deviations. Overlaid with NHS reference ranges."
        }
        availability="ready"
        loading={loading}
        loadingSkeletonVariant="bars"
        error={null}
      >
        {error && !matrix && (
          <Alert severity="info" sx={{ mb: 2 }}>{error}</Alert>
        )}

        {bloodData && (
          <Box sx={{ display: "flex", gap: 1.5, mb: 2, flexWrap: "wrap", alignItems: "center" }}>
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
            <Chip
              label={`${bloodData.feature_keys.length} tests`}
              size="small"
              variant="outlined"
            />
            <Typography variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
              12 months before referral
            </Typography>
          </Box>
        )}

        {matrix && (
          <>
            <Alert severity="info" icon={false} sx={{ mb: 2, py: 0.5, fontSize: 12 }}>
              Exploratory only -- max n=7 per cancer type in current cohort. Statistical significance not implied.
              Colour shows how far each cancer type median sits above (red) or below (blue) the benign cohort median,
              expressed in benign standard deviations. Cell annotation = number with readings / total.
            </Alert>

            <Box sx={{ display: "flex", gap: 2.5, mb: 1.5, flexWrap: "wrap", alignItems: "center" }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <Box sx={{ width: 20, height: 12, background: "linear-gradient(to right, #1E40AF, #F9FAFB, #991B1B)", borderRadius: 1 }} />
                <Typography variant="caption">Lower vs benign -- higher</Typography>
              </Box>
              <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
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

            <CancerTypeHeatmap matrix={matrix} />

            <Box sx={{ display: "flex", gap: 1.5, mt: 2.5, flexWrap: "wrap" }}>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setPatientOpen(true)}
              >
                Per-patient combinations
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setPerTestOpen(true)}
              >
                Per test distributions
              </Button>
              {bloodData && (
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => setSignalOpen(true)}
                >
                  Feature signal (Pearson r)
                </Button>
              )}
            </Box>
          </>
        )}
      </SectionCard>

      {matrix && (
        <PatientCombinationsDialog
          open={patientOpen}
          onClose={() => setPatientOpen(false)}
          matrix={matrix}
        />
      )}
      <PerTestDialog open={perTestOpen} onClose={() => setPerTestOpen(false)} />
      {bloodData && (
        <FeatureSignalDialog
          open={signalOpen}
          onClose={() => setSignalOpen(false)}
          correlations={bloodData.correlations}
          featureLabels={bloodData.feature_labels}
        />
      )}
    </>
  );
}
