"use client";

/**
 * Gold dataset health and extraction model quality scorecard.
 *
 * Shows:
 *  - Summary (total reviewed, overall approval rate, gold entities, patients)
 *  - Per-semantic-tag scorecard table — approval / edit / rejection rates per
 *    entity type, mirroring the classification per-class performance view
 *  - Download buttons for MedSpaCy training data
 *
 * "Approval rate" is used as a precision proxy: if the model extracted a term
 * of type X and the reviewer kept it without changes, the model was correct.
 * Rejection rate is the FP proxy. Edit rate indicates partial correctness.
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
  Tooltip,
  Typography,
} from "@mui/material";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DownloadIcon from "@mui/icons-material/Download";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import { api } from "@/lib/api";
import { exportMedSpaCyTraining } from "@/lib/api/legacy";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TagRow {
  tag: string;
  total_candidates: number;
  approved: number;
  edited: number;
  rejected: number;
  escalated: number;
  human_verified: number;
  approval_rate_pct: number | null;
  rejection_rate_pct: number | null;
  gold_entities: number;
}

interface GoldStats {
  generated_at: string;
  total_reviewed: number;
  overall_approval_rate_pct: number | null;
  reviewers: string[];
  gold_entities_by_tag: Record<string, number>;
  total_gold_entities: number;
  patients_covered: number;
  encounters_covered: number;
  date_from: string | null;
  date_to: string | null;
  per_tag_scorecard: TagRow[];
  outcomes: Record<string, number>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TAG_LABELS: Record<string, string> = {
  finding: "Finding",
  disorder: "Disorder",
  procedure: "Procedure",
  observable_entity: "Observable entity",
  body_structure: "Body structure",
  substance: "Substance",
  product: "Product",
  situation: "Situation",
  event: "Event",
  qualifier_value: "Qualifier value",
  unknown: "Unknown",
};

const TAG_COLORS: Record<string, string> = {
  finding: "#1976d2",
  disorder: "#d32f2f",
  procedure: "#388e3c",
  observable_entity: "#7b1fa2",
  body_structure: "#f57c00",
  substance: "#0288d1",
  product: "#455a64",
};

function tagLabel(tag: string) {
  return TAG_LABELS[tag] ?? tag.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function tagColor(tag: string) {
  return TAG_COLORS[tag] ?? "#607d8b";
}

function rateColor(pct: number | null, invert = false): string {
  if (pct === null) return "text.secondary";
  const val = invert ? 100 - pct : pct;
  if (val >= 80) return invert ? "error.main" : "success.main";
  if (val >= 60) return "warning.main";
  return invert ? "success.main" : "error.main";
}

function fmt(val: number | null, suffix = "%"): string {
  return val === null ? "—" : `${val}${suffix}`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function OutcomeChip({ label, count, color }: { label: string; count: number; color: "success" | "warning" | "error" | "info" | "default" }) {
  return (
    <Box sx={{ textAlign: "center", p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 2, minWidth: 110 }}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>{count}</Typography>
      <Chip label={label} color={color} size="small" sx={{ mt: 0.5, fontWeight: 600, fontSize: "0.7rem" }} />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function GoldDatasetPanel() {
  const [stats, setStats] = useState<GoldStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<GoldStats>("/pipeline/gold-dataset-stats");
      setStats(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load gold dataset stats");
    } finally {
      setLoading(false);
    }
  }

  async function downloadTrainingData() {
    setExporting(true);
    setExportMsg(null);
    try {
      const result = await exportMedSpaCyTraining({ export_name: `gold_${new Date().toISOString().slice(0, 10)}` });
      setExportMsg(
        `Export complete — ${result.entity_count} entities, ${result.kb_count} KB entries from ${result.encounter_count} encounters. Saved to: ${result.export_path}`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const outcomes = stats?.outcomes ?? {};
  const approvedCount = (outcomes["approve"] ?? 0) + (outcomes["approved"] ?? 0);
  const editedCount = outcomes["edit"] ?? outcomes["edited"] ?? 0;
  const rejectedCount = outcomes["reject"] ?? outcomes["rejected"] ?? 0;
  const escalatedCount = outcomes["escalate"] ?? outcomes["escalated"] ?? 0;

  return (
    <Box sx={{ maxWidth: 1100, mx: "auto", py: 4, px: 3 }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            Gold Dataset &amp; Extraction Scorecard
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Human-reviewed coding quality signals and training data for MedSpaCy.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          {stats && (
            <Tooltip title="Export all approved candidates as MedSpaCy .jsonl training files">
              <Button
                variant="outlined"
                startIcon={exporting ? <CircularProgress size={14} /> : <DownloadIcon />}
                disabled={exporting}
                onClick={downloadTrainingData}
                size="small"
              >
                Download Training Data
              </Button>
            </Tooltip>
          )}
          <Button
            variant={stats ? "text" : "contained"}
            startIcon={loading ? <CircularProgress size={14} /> : <AssessmentOutlinedIcon />}
            disabled={loading}
            onClick={load}
            size="small"
          >
            {stats ? "Refresh" : "Load Stats"}
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}
      {exportMsg && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setExportMsg(null)}>{exportMsg}</Alert>}

      {!stats && !loading && (
        <Box sx={{ p: 4, textAlign: "center", bgcolor: "action.hover", borderRadius: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Load stats to see extraction model quality and gold dataset health.
          </Typography>
        </Box>
      )}

      {stats && (
        <>
          {/* Summary row */}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mb: 3 }} flexWrap="wrap">
            <OutcomeChip label="Approved" count={approvedCount} color="success" />
            <OutcomeChip label="Edited" count={editedCount} color="warning" />
            <OutcomeChip label="Rejected" count={rejectedCount} color="error" />
            {escalatedCount > 0 && <OutcomeChip label="Escalated" count={escalatedCount} color="info" />}

            <Box sx={{ flex: 1 }} />

            {[
              { label: "Overall approval rate", value: fmt(stats.overall_approval_rate_pct), color: rateColor(stats.overall_approval_rate_pct) },
              { label: "Gold entities", value: stats.total_gold_entities.toLocaleString(), color: "text.primary" },
              { label: "Patients covered", value: String(stats.patients_covered), color: "text.primary" },
              { label: "Encounters in gold", value: String(stats.encounters_covered), color: "text.primary" },
            ].map(({ label, value, color }) => (
              <Box key={label} sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 2, minWidth: 130, textAlign: "center" }}>
                <Typography variant="h6" sx={{ fontWeight: 700, color }}>{value}</Typography>
                <Typography variant="caption" color="text.secondary">{label}</Typography>
              </Box>
            ))}
          </Stack>

          {stats.reviewers.length > 0 && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
              Reviewers: {stats.reviewers.join(", ")} · Period: {stats.date_from ?? "—"} → {stats.date_to ?? "—"}
            </Typography>
          )}

          <Divider sx={{ mb: 3 }} />

          {/* Per-tag scorecard — mirrors the classification per-class view */}
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5, textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.72rem", color: "text.secondary" }}>
            Extraction model — per-semantic-tag quality
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
            Approval rate = candidates where the model&apos;s extracted terms were kept unchanged.
            Rejection rate = candidates where the reviewer discarded all terms. Scoped to reviewed candidates only.
          </Typography>

          <Card variant="outlined">
            <Table size="small" sx={{ "& td, & th": { fontSize: "0.82rem" } }}>
              <TableHead>
                <TableRow sx={{ bgcolor: "action.hover" }}>
                  <TableCell sx={{ fontWeight: 700 }}>
                    <Tooltip title="SNOMED semantic tag assigned by the LLM">
                      <span style={{ borderBottom: "1px dashed", cursor: "help" }}>Semantic tag</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center" sx={{ fontWeight: 700 }}>
                    <Tooltip title="Distinct encounter candidates containing at least one term with this tag">
                      <span style={{ borderBottom: "1px dashed", cursor: "help" }}>Cases reviewed</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center" sx={{ fontWeight: 700 }}>
                    <Tooltip title="Candidates approved without any edits — model was correct">
                      <span style={{ borderBottom: "1px dashed", cursor: "help" }}>Approval rate</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center" sx={{ fontWeight: 700 }}>
                    <Tooltip title="Candidates that needed reviewer corrections — model was partially correct">
                      <span style={{ borderBottom: "1px dashed", cursor: "help" }}>Edit rate</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center" sx={{ fontWeight: 700 }}>
                    <Tooltip title="Candidates rejected outright — model was wrong on these">
                      <span style={{ borderBottom: "1px dashed", cursor: "help" }}>Rejection rate</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center" sx={{ fontWeight: 700 }}>
                    <Tooltip title="Candidates approved or edited (human-verified gold)">
                      <span style={{ borderBottom: "1px dashed", cursor: "help" }}>Gold</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center" sx={{ fontWeight: 700 }}>
                    <Tooltip title="Candidates rejected (false alarm proxy)">
                      <span style={{ borderBottom: "1px dashed", cursor: "help" }}>Rejected</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell align="center" sx={{ fontWeight: 700 }}>
                    <Tooltip title="Total entities of this type in the approved gold set">
                      <span style={{ borderBottom: "1px dashed", cursor: "help" }}>Gold entities</span>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {stats.per_tag_scorecard.map((row) => {
                  const editRate = row.total_candidates > 0
                    ? Math.round(row.edited / row.total_candidates * 100)
                    : null;
                  return (
                    <TableRow key={row.tag} hover>
                      <TableCell>
                        <Chip
                          label={tagLabel(row.tag)}
                          size="small"
                          sx={{
                            fontWeight: 600,
                            bgcolor: tagColor(row.tag) + "22",
                            color: tagColor(row.tag),
                            border: `1px solid ${tagColor(row.tag)}44`,
                          }}
                        />
                      </TableCell>
                      <TableCell align="center">{row.total_candidates}</TableCell>
                      <TableCell align="center" sx={{ fontWeight: 700, color: rateColor(row.approval_rate_pct) }}>
                        {fmt(row.approval_rate_pct)}
                      </TableCell>
                      <TableCell align="center" sx={{ fontWeight: 600, color: editRate !== null && editRate > 20 ? "warning.main" : "text.primary" }}>
                        {editRate !== null ? `${editRate}%` : "—"}
                      </TableCell>
                      <TableCell align="center" sx={{ fontWeight: 700, color: rateColor(row.rejection_rate_pct, true) }}>
                        {fmt(row.rejection_rate_pct)}
                      </TableCell>
                      <TableCell align="center">
                        <Stack direction="row" spacing={0.5} justifyContent="center" alignItems="center">
                          <CheckCircleOutlineIcon sx={{ fontSize: 14, color: "success.main" }} />
                          <span>{row.human_verified}</span>
                        </Stack>
                      </TableCell>
                      <TableCell align="center">
                        <Stack direction="row" spacing={0.5} justifyContent="center" alignItems="center">
                          <CancelOutlinedIcon sx={{ fontSize: 14, color: row.rejected > 0 ? "error.main" : "text.disabled" }} />
                          <span style={{ color: row.rejected > 0 ? undefined : "#bbb" }}>{row.rejected}</span>
                        </Stack>
                      </TableCell>
                      <TableCell align="center" sx={{ fontWeight: 600 }}>{row.gold_entities.toLocaleString()}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Card>

          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
            Approval rate is a precision proxy for each entity type — it measures how often the extraction model&apos;s output was correct without requiring human correction.
            True precision/recall requires a held-out annotated test set; this view uses the review queue outcomes as the signal.
          </Typography>

          {/* Gold entity distribution */}
          {Object.keys(stats.gold_entities_by_tag).length > 0 && (
            <>
              <Divider sx={{ my: 3 }} />
              <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5, textTransform: "uppercase", letterSpacing: 0.5, fontSize: "0.72rem", color: "text.secondary" }}>
                Gold dataset — entity distribution
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {Object.entries(stats.gold_entities_by_tag)
                  .sort(([, a], [, b]) => b - a)
                  .map(([tag, count]) => (
                    <Box key={tag} sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 2, minWidth: 120, textAlign: "center", mb: 1 }}>
                      <Typography variant="h6" sx={{ fontWeight: 700, color: tagColor(tag) }}>
                        {count.toLocaleString()}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {tagLabel(tag)}
                      </Typography>
                    </Box>
                  ))}
              </Stack>
            </>
          )}
        </>
      )}
    </Box>
  );
}
