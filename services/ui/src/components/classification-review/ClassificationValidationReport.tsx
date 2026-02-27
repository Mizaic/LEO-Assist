"use client";

/**
 * Downloadable validation evidence report for ISO 13485 / ISO 14971.
 *
 * Presents per-model accuracy, per-class precision / recall / F1, and a full
 * audit trail of every human-reviewed disagreement case.  The user can:
 *   • Download the audit trail as a CSV (browser-side generation, no server round-trip)
 *   • Print / Save as PDF via the browser print dialog (print-specific CSS hides
 *     everything except this panel, producing a clean A4-ready document)
 */

import { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import PrintIcon from "@mui/icons-material/Print";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ClassMetrics {
  tp: number;
  fp: number;
  fn: number;
  support: number;
  precision_pct: number | null;
  recall_pct: number | null;
  f1_pct: number | null;
}

interface ConfusionRow {
  haiku_predicted: string;
  gpt_predicted: string;
  human_verdict: string;
  n: number;
}

interface AuditRow {
  patient_id: string;
  encounter_id: string;
  encounter_date: string | null;
  haiku_predicted: string;
  gpt_predicted: string;
  human_verdict: string;
  haiku_correct: boolean;
  gpt_correct: boolean;
  reviewer: string;
  voted_at: string | null;
  notes: string;
}

interface ReportData {
  generated_at: string;
  summary: {
    total_reviewed: number;
    haiku_correct: number;
    haiku_accuracy_pct: number;
    gpt_correct: number;
    gpt_accuracy_pct: number;
    both_wrong: number;
    both_wrong_pct: number;
    date_from: string | null;
    date_to: string | null;
    reviewers: string[];
  };
  haiku_per_class: Record<string, ClassMetrics>;
  gpt_per_class: Record<string, ClassMetrics>;
  confusion_breakdown: ConfusionRow[];
  audit_trail: AuditRow[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CLASS_LABELS: Record<string, string> = {
  clinical: "Clinical",
  admin_only: "Admin only",
  document_transfer: "Document transfer",
};

const CLASSES = ["clinical", "admin_only", "document_transfer"];

function fmt(val: number | null, suffix = "%"): string {
  return val === null ? "—" : `${val}${suffix}`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return iso.replace("T", " ").slice(0, 16) + " UTC";
}

function metricColor(val: number | null): string {
  if (val === null) return "text.secondary";
  if (val >= 80) return "success.main";
  if (val >= 60) return "warning.main";
  return "error.main";
}

/** Expand audit trail, print, then restore. */
async function triggerPrint(setForceExpand: (v: boolean) => void): Promise<void> {
  setForceExpand(true);
  // Allow React to commit the state update and the browser to re-layout before printing
  await new Promise<void>((resolve) => setTimeout(resolve, 200));
  window.print();
  window.addEventListener("afterprint", () => setForceExpand(false), { once: true });
}

/** Generate and download a CSV from the audit trail rows. */
function downloadCsv(rows: AuditRow[], generatedAt: string) {
  const header = [
    "Encounter ID",
    "Patient ref.",
    "Encounter Date",
    "Haiku Predicted",
    "GPT-5-mini Predicted",
    "Human Verdict",
    "Haiku Correct",
    "GPT-5-mini Correct",
    "Reviewer",
    "Reviewed At",
    "Notes",
  ];

  const escape = (v: string | boolean | null | undefined) => {
    const s = v === null || v === undefined ? "" : String(v);
    return `"${s.replace(/"/g, '""')}"`;
  };

  const lines = [
    header.join(","),
    ...rows.map((r) =>
      [
        r.encounter_id,
        r.patient_id,
        r.encounter_date ?? "",
        CLASS_LABELS[r.haiku_predicted] ?? r.haiku_predicted,
        CLASS_LABELS[r.gpt_predicted] ?? r.gpt_predicted,
        CLASS_LABELS[r.human_verdict] ?? r.human_verdict,
        r.haiku_correct ? "Yes" : "No",
        r.gpt_correct ? "Yes" : "No",
        r.reviewer,
        r.voted_at ? fmtDate(r.voted_at) : "",
        r.notes,
      ]
        .map(escape)
        .join(",")
    ),
  ];

  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `classification-validation-audit-${generatedAt.slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SummarySection({ summary }: { summary: ReportData["summary"] }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5, textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary", fontSize: "0.7rem" }}>
        Review Summary
      </Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} flexWrap="wrap">
        <StatBox label="Total reviewed" value={String(summary.total_reviewed)} />
        <StatBox
          label="Claude Haiku accuracy"
          value={`${summary.haiku_accuracy_pct}%`}
          sub={`${summary.haiku_correct} / ${summary.total_reviewed} correct`}
          color={metricColor(summary.haiku_accuracy_pct)}
        />
        <StatBox
          label="GPT-5-mini accuracy"
          value={`${summary.gpt_accuracy_pct}%`}
          sub={`${summary.gpt_correct} / ${summary.total_reviewed} correct`}
          color={metricColor(summary.gpt_accuracy_pct)}
        />
        <StatBox
          label="Both models wrong"
          value={`${summary.both_wrong_pct}%`}
          sub={`${summary.both_wrong} cases`}
          color={summary.both_wrong_pct > 20 ? "error.main" : "text.primary"}
        />
        <StatBox label="Reviewers" value={summary.reviewers.join(", ") || "—"} />
        <StatBox
          label="Review period"
          value={`${summary.date_from ? summary.date_from.slice(0, 10) : "—"} → ${summary.date_to ? summary.date_to.slice(0, 10) : "—"}`}
        />
      </Stack>
    </Box>
  );
}

function StatBox({ label, value, sub, color = "text.primary" }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <Box
      sx={{
        flex: "1 1 150px",
        p: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        bgcolor: "background.paper",
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.25 }}>
        {label}
      </Typography>
      <Typography variant="body1" sx={{ fontWeight: 700, color }}>
        {value}
      </Typography>
      {sub && (
        <Typography variant="caption" color="text.secondary">
          {sub}
        </Typography>
      )}
    </Box>
  );
}

const METRIC_EXPLANATIONS = [
  { term: "Cases reviewed", meaning: "How many encounters of this type were in the test set." },
  { term: "Precision", meaning: "Of all the times the model predicted this category, how often was it right. 100% means no false alarms." },
  { term: "Recall (sensitivity)", meaning: "Of all encounters that truly belonged to this category, how many did the model find. 100% means nothing was missed." },
  { term: "F1 score", meaning: "A single number that balances precision and recall. Higher is better; 100% is perfect." },
  { term: "Correct / False alarms / Missed", meaning: "Counts of right predictions, wrong predictions (false alarms), and cases the model failed to find (missed)." },
];

function MetricExplanationBox() {
  return (
    <Box
      sx={{
        mb: 2.5,
        p: 1.5,
        bgcolor: "action.hover",
        borderRadius: 1,
        borderLeft: "3px solid",
        borderColor: "primary.main",
      }}
    >
      <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.75, color: "text.primary" }}>
        What the columns mean
      </Typography>
      <Stack spacing={0.4}>
        {METRIC_EXPLANATIONS.map(({ term, meaning }) => (
          <Typography key={term} variant="caption" color="text.secondary" sx={{ display: "block" }}>
            <Box component="span" sx={{ fontWeight: 700, color: "text.primary" }}>{term}</Box>
            {" — "}
            {meaning}
          </Typography>
        ))}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75, fontStyle: "italic" }}>
        Scores cover disagreement cases only — encounters where the two models gave different answers. These are the hardest cases to classify correctly.
      </Typography>
    </Box>
  );
}

function PerClassTable({ label, metrics, showExplanation }: { label: string; metrics: Record<string, ClassMetrics>; showExplanation?: boolean }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary", fontSize: "0.7rem" }}>
        {label} — Per-class performance
      </Typography>

      {showExplanation && <MetricExplanationBox />}

      <Table size="small" sx={{ "& td, & th": { fontSize: "0.82rem" } }}>
        <TableHead>
          <TableRow sx={{ bgcolor: "action.hover" }}>
            <TableCell sx={{ fontWeight: 700 }}>Category</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>Cases reviewed</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>Precision</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>Recall (sensitivity)</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>F1 score</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>Correct</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>False alarms</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700 }}>Missed</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {CLASSES.map((cls) => {
            const m = metrics[cls];
            if (!m) return null;
            return (
              <TableRow key={cls} hover>
                <TableCell>
                  <Chip
                    label={CLASS_LABELS[cls] ?? cls}
                    size="small"
                    color={cls === "clinical" ? "success" : cls === "admin_only" ? "warning" : "info"}
                    sx={{ fontWeight: 600 }}
                  />
                </TableCell>
                <TableCell align="center">{m.support}</TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: metricColor(m.precision_pct) }}>
                  {fmt(m.precision_pct)}
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: metricColor(m.recall_pct) }}>
                  {fmt(m.recall_pct)}
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 600, color: metricColor(m.f1_pct) }}>
                  {fmt(m.f1_pct)}
                </TableCell>
                <TableCell align="center">{m.tp}</TableCell>
                <TableCell align="center" sx={{ color: m.fp > 0 ? "warning.main" : "text.primary" }}>{m.fp}</TableCell>
                <TableCell align="center" sx={{ color: m.fn > 0 ? "error.main" : "text.primary" }}>{m.fn}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}

function AuditTrailTable({ rows, forceExpand }: { rows: AuditRow[]; forceExpand?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded || forceExpand ? rows : rows.slice(0, 10);

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary", fontSize: "0.7rem" }}>
        Audit Trail ({rows.length} records)
      </Typography>
      <Table size="small" sx={{ "& td, & th": { fontSize: "0.75rem" } }}>
        <TableHead>
          <TableRow sx={{ bgcolor: "action.hover" }}>
            <TableCell sx={{ fontWeight: 700 }}>Date</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Patient ref.</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Haiku</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>GPT-5-mini</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Human verdict</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Reviewer</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Reviewed at</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Notes</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {visible.map((r) => (
            <TableRow key={r.encounter_id} hover>
              <TableCell sx={{ fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>{r.encounter_date ?? "—"}</TableCell>
              <TableCell sx={{ fontFamily: "var(--font-mono)" }}>{r.patient_id || "—"}</TableCell>
              <TableCell>
                <Chip
                  label={CLASS_LABELS[r.haiku_predicted] ?? r.haiku_predicted}
                  size="small"
                  color={r.haiku_predicted === "clinical" ? "success" : r.haiku_predicted === "admin_only" ? "warning" : "info"}
                  variant={r.haiku_correct ? "filled" : "outlined"}
                  sx={{ fontSize: "0.7rem" }}
                />
              </TableCell>
              <TableCell>
                <Chip
                  label={CLASS_LABELS[r.gpt_predicted] ?? r.gpt_predicted}
                  size="small"
                  color={r.gpt_predicted === "clinical" ? "success" : r.gpt_predicted === "admin_only" ? "warning" : "info"}
                  variant={r.gpt_correct ? "filled" : "outlined"}
                  sx={{ fontSize: "0.7rem" }}
                />
              </TableCell>
              <TableCell>
                <Chip
                  label={CLASS_LABELS[r.human_verdict] ?? r.human_verdict}
                  size="small"
                  color={r.human_verdict === "clinical" ? "success" : r.human_verdict === "admin_only" ? "warning" : "info"}
                  sx={{ fontWeight: 700, fontSize: "0.7rem" }}
                />
              </TableCell>
              <TableCell>{r.reviewer}</TableCell>
              <TableCell sx={{ fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>{r.voted_at ? fmtDate(r.voted_at) : "—"}</TableCell>
              <TableCell sx={{ color: "text.secondary", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.notes || ""}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {rows.length > 10 && (
        <Button size="small" sx={{ mt: 1 }} onClick={() => setExpanded((e) => !e)}>
          {expanded ? "Show less" : `Show all ${rows.length} records`}
        </Button>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ClassificationValidationReport() {
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forceExpandAudit, setForceExpandAudit] = useState(false);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<ReportData>("/pipeline/classification-report");
      setReport(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate report");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box id="validation-report-root" sx={{ mt: 4 }}>
      <Divider sx={{ mb: 3 }} />

      {/* Section header + action buttons — hidden when printing */}
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 2, "@media print": { display: "none" } }}
      >
        <Stack direction="row" spacing={1} alignItems="center">
          <AssessmentOutlinedIcon sx={{ color: "text.secondary" }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Validation Evidence Report
          </Typography>
          <Chip label="ISO 13485 / ISO 14971" size="small" variant="outlined" sx={{ fontSize: "0.7rem" }} />
        </Stack>
        <Stack direction="row" spacing={1}>
          {report && (
            <>
              <Button
                size="small"
                variant="outlined"
                startIcon={<DownloadIcon />}
                onClick={() => downloadCsv(report.audit_trail, report.generated_at)}
              >
                Download CSV
              </Button>
              <Button
                size="small"
                variant="outlined"
                startIcon={<PrintIcon />}
                onClick={() => triggerPrint(setForceExpandAudit)}
              >
                Print / Save PDF
              </Button>
            </>
          )}
          <Button
            size="small"
            variant={report ? "text" : "contained"}
            onClick={generate}
            disabled={loading}
            startIcon={loading ? <CircularProgress size={14} /> : <AssessmentOutlinedIcon />}
          >
            {report ? "Refresh" : "Generate Report"}
          </Button>
        </Stack>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2, "@media print": { display: "none" } }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {!report && !loading && (
        <Box sx={{ p: 3, bgcolor: "action.hover", borderRadius: 2, textAlign: "center", "@media print": { display: "none" } }}>
          <Typography variant="body2" color="text.secondary">
            Generate a full validation evidence report from all human-reviewed disagreement cases.
            Includes per-model accuracy, per-class precision/recall/F1, and a complete audit trail.
          </Typography>
        </Box>
      )}

      {report && (
        <Card
          id="printable-report"
          sx={{
            "@media print": {
              boxShadow: "none",
              border: "none",
              borderRadius: 0,
            },
          }}
        >
          <CardContent sx={{ "@media print": { p: 0 } }}>
            {/* ── Print-only confidentiality banner ───────────────────── */}
            <Box
              sx={{
                display: "none",
                "@media print": {
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  mb: 2,
                  pb: 1,
                  borderBottom: "2px solid #1976d2",
                },
              }}
            >
              <Typography sx={{ fontSize: "0.7rem", fontWeight: 700, color: "#1976d2", letterSpacing: 1, textTransform: "uppercase" }}>
                Confidential — Clinical Governance
              </Typography>
              <Typography sx={{ fontSize: "0.7rem", color: "#666" }}>
                Doc ref: CLS-VAL-{new Date().getFullYear()} &nbsp;|&nbsp; {fmtDate(report.generated_at)}
              </Typography>
            </Box>

            {/* Report title */}
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                AI Classification System — Validation Evidence Report
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Scope: Encounters where Claude Haiku (AWS) and GPT-5-mini (Azure) produced different
                classifications. Each case was adjudicated by a human reviewer to establish ground truth.
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                Generated: {fmtDate(report.generated_at)} &nbsp;·&nbsp; Method: Human-in-the-loop (HITL) review of model disagreements
              </Typography>
            </Box>

            <SummarySection summary={report.summary} />

            <Divider sx={{ my: 3, "@media print": { display: "none" } }} />
            <PerClassTable label="Claude Haiku (AWS)" metrics={report.haiku_per_class} showExplanation />

            <Divider sx={{ my: 3, "@media print": { display: "none" } }} />
            <PerClassTable label="GPT-5-mini (Azure)" metrics={report.gpt_per_class} />

            {/* Audit trail: large enough to always warrant its own page */}
            <Box sx={{ "@media print": { pageBreakBefore: "always" } }}>
              <AuditTrailTable rows={report.audit_trail} forceExpand={forceExpandAudit} />
            </Box>

            {/* Scope note */}
            <Box sx={{ mt: 3, p: 2, bgcolor: "action.hover", borderRadius: 1 }}>
              <Typography variant="caption" color="text.secondary">
                <strong>Scope note:</strong> Performance metrics are calculated on disagreement cases only —
                encounters where the two models produced different labels. Cases where both models agreed
                (consensus cases) are not included in this analysis. Disagreement cases represent the
                hardest classification boundary and therefore form a conservative test set. Metrics should
                be interpreted alongside the overall disagreement rate and total encounter volume when
                preparing a risk management file under ISO 14971.
              </Typography>
            </Box>

            {/* ── Print-only sign-off block ────────────────────────────── */}
            <Box
              sx={{
                display: "none",
                "@media print": {
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr",
                  gap: "16px",
                  mt: 4,
                  pt: 2,
                  borderTop: "1px solid #ccc",
                },
              }}
            >
              {["Validated by", "Clinical lead", "Date"].map((label) => (
                <Box key={label}>
                  <Typography sx={{ fontSize: "0.7rem", color: "#666", mb: 3 }}>{label}</Typography>
                  <Box sx={{ borderBottom: "1px solid #999", width: "100%" }} />
                </Box>
              ))}
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
