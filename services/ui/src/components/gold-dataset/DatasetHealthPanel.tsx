/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import BuildIcon from "@mui/icons-material/Build";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import IconButton from "@mui/material/IconButton";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  ReferenceLine,
  Cell,
  ResponsiveContainer,
} from "recharts";

// Minimum total span count per label needed for reliable training.
// The exporter uses an 80/20 train/dev split, so 30 total spans -> ~24 in
// training -- the practical floor for the frozen-ClinicalBERT linear head.
const MIN_SPANS_PER_LABEL = 30;
import {
  fetchLabelDistribution,
  fetchExportDiagnostics,
  fetchPhraseConsistency,
  upsertPhraseMultiLabelApproval,
  type LabelDistribution,
  type ExportDiagnostics,
  type PhraseConsistencyResponse,
} from "@/lib/api/legacy";
import { FONT_SIZES } from "@/theme/tokens";
import { entityLabelColour } from "./goldDatasetUtils";

// -- Span-misaligned record list ---------------------------------------------
// Assertion filtering is intentionally disabled: the spancat model trains on
// (start, end, label) only -- assertion is not part of the training signal.
// ConText handles assertion detection post-extraction.  Only span-misaligned
// records (where surface text can't be matched in the sentence) need fixing.

interface MisalignedRecord {
  label_id: string;
  text: string;
  entities: Array<{ entity_text: string; label: string }>;
}

function groupMisaligned(diag: ExportDiagnostics): MisalignedRecord[] {
  const map = new Map<string, MisalignedRecord>();
  for (const item of diag.span_misaligned) {
    if (!map.has(item.label_id)) {
      map.set(item.label_id, {
        label_id: item.label_id,
        text: item.text ?? "",
        entities: [],
      });
    }
    map.get(item.label_id)!.entities.push({
      entity_text: item.entity_text,
      label: item.label,
    });
  }
  return Array.from(map.values());
}

function MisalignedList({
  diag,
  onOpenLabel,
}: {
  diag: ExportDiagnostics;
  onOpenLabel?: (labelId: string) => void;
}) {
  const records = groupMisaligned(diag);
  if (records.length === 0) return null;

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
        <WarningAmberIcon sx={{ fontSize: 15, color: "error.main" }} />
        <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle }}>
          Span mismatch ({records.length} record{records.length !== 1 ? "s" : ""})
        </Typography>
        <Chip
          size="small"
          label={`${diag.summary.span_misaligned_count} entities`}
          color="error"
          sx={{ height: 18, fontSize: "0.68rem" }}
        />
      </Stack>

      <Box
        sx={{
          mb: 1.25,
          p: 1,
          bgcolor: "error.50",
          border: "1px solid",
          borderColor: "error.200",
          borderRadius: 1,
        }}
      >
        <Typography sx={{ fontSize: 11, color: "text.secondary" }}>
          The entity text no longer matches any span in the sentence — usually
          because the record was edited after coding. Open the record, delete
          the mismatched entity, then re-add it by highlighting the correct text.
        </Typography>
      </Box>

      <Stack spacing={0.75}>
        {records.map((rec) => (
          <Box
            key={rec.label_id}
            sx={{
              p: 1,
              border: "1px solid",
              borderColor: "error.200",
              borderLeft: "3px solid",
              borderLeftColor: "error.main",
              borderRadius: 1,
              bgcolor: "background.paper",
              cursor: onOpenLabel ? "pointer" : "default",
              transition: "box-shadow 0.12s",
              "&:hover": onOpenLabel
                ? { boxShadow: "0 2px 6px rgba(0,0,0,0.10)" }
                : undefined,
            }}
            onClick={() => onOpenLabel?.(rec.label_id)}
          >
            <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography
                  sx={{
                    fontSize: 11,
                    fontStyle: "italic",
                    color: "text.secondary",
                    mb: 0.5,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {rec.text || "(sentence not available)"}
                </Typography>
                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                  {rec.entities.map((ent, i) => (
                    <Tooltip
                      key={i}
                      title={`"${ent.entity_text}" could not be found in the sentence text`}
                    >
                      <Chip
                        size="small"
                        label={`${ent.entity_text}${ent.label ? ` [${ent.label}]` : ""}`}
                        color="error"
                        variant="outlined"
                        sx={{ height: 20, fontSize: "0.68rem", maxWidth: 280 }}
                      />
                    </Tooltip>
                  ))}
                </Stack>
              </Box>
              {onOpenLabel && (
                <Tooltip title="Open this record to fix the span">
                  <IconButton
                    size="small"
                    color="error"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenLabel(rec.label_id);
                    }}
                    sx={{ p: 0.4, flexShrink: 0 }}
                  >
                    <BuildIcon sx={{ fontSize: 15 }} />
                  </IconButton>
                </Tooltip>
              )}
            </Stack>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

// -- Main component ----------------------------------------------------------

export default function DatasetHealthPanel({
  onOpenLabel,
  onLabelFilter,
  activeLabel,
  refreshKey = 0,
}: {
  onOpenLabel?: (labelId: string) => void;
  /** Called with a label name when a chart bar is clicked; null to clear. */
  onLabelFilter?: (label: string | null) => void;
  /** Currently active label filter (bar will be highlighted). */
  activeLabel?: string | null;
  /** Increment to trigger a re-fetch of diagnostics (e.g. after a label edit). */
  refreshKey?: number;
}) {
  const [dist, setDist] = useState<LabelDistribution | null>(null);
  const [diag, setDiag] = useState<ExportDiagnostics | null>(null);
  const [phraseConsistency, setPhraseConsistency] =
    useState<PhraseConsistencyResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [phraseFixIndex, setPhraseFixIndex] = useState<Record<string, number>>({});
  const [approvingPhrase, setApprovingPhrase] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [approvalsExpanded, setApprovalsExpanded] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<{
    phrase: string;
    labels: string[];
  } | null>(null);
  const [confirmApprovalChecked, setConfirmApprovalChecked] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      fetchLabelDistribution(),
      fetchExportDiagnostics(),
      fetchPhraseConsistency({ minOccurrences: 2, top: 10 }),
    ])
      .then(([d, diagnostics, phrase]) => {
        if (!cancelled) {
          setDist(d);
          setDiag(diagnostics);
          setPhraseConsistency(phrase);
        }
      })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  const totalNotReady = diag?.summary.span_misaligned_count ?? 0;

  const runApproveMultiLabel = async (
    phrase: string,
    labels: string[],
  ): Promise<boolean> => {
    setApprovingPhrase(phrase);
    try {
      await upsertPhraseMultiLabelApproval({
        phrase,
        allowed_labels: labels,
      });
      setActionMsg(
        `Approved multi-label phrase "${phrase}" with labels: ${labels.join(", ")}.`,
      );
      const [d, diagnostics, phraseData] = await Promise.all([
        fetchLabelDistribution(),
        fetchExportDiagnostics(),
        fetchPhraseConsistency({ minOccurrences: 2, top: 10 }),
      ]);
      setDist(d);
      setDiag(diagnostics);
      setPhraseConsistency(phraseData);
      setApprovalError(null);
      return true;
    } catch (e) {
      const message =
        e instanceof Error ? e.message : "Could not approve multi-label phrase";
      setError(message);
      setApprovalError(message);
      return false;
    } finally {
      setApprovingPhrase(null);
    }
  };

  return (
    <Box
      sx={{
        mb: 2,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1.5,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: 1.5, py: 1, bgcolor: "grey.50", cursor: "pointer" }}
        onClick={() => setExpanded((e) => !e)}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle }}>
            Dataset health
          </Typography>
          {!loading && dist && (
            <Chip
              size="small"
              label={`${dist.total_entities} entity spans`}
              sx={{ height: 18, fontSize: "0.68rem" }}
            />
          )}
          {!loading && totalNotReady > 0 && (
            <Chip
              size="small"
              label={`${totalNotReady} not ready`}
              color="warning"
              sx={{ height: 18, fontSize: "0.68rem" }}
            />
          )}
        </Stack>
        <IconButton size="small" sx={{ p: 0.25 }}>
          {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
        </IconButton>
      </Stack>

      <Collapse in={expanded}>
        <Box sx={{ p: 1.5 }}>
          {actionMsg && (
            <Alert severity="success" sx={{ mb: 1 }}>
              {actionMsg}
            </Alert>
          )}
          {error && (
            <Alert severity="error" sx={{ mb: 1.5, fontSize: FONT_SIZES.body }}>
              {error}
            </Alert>
          )}

          {/* Label distribution chart */}
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle }}>
              Label distribution
            </Typography>
            {activeLabel && onLabelFilter && (
              <Chip
                size="small"
                label={activeLabel.replace(/_/g, " ")}
                onDelete={() => onLabelFilter(null)}
                sx={{
                  height: 20,
                  fontSize: "0.68rem",
                  bgcolor: entityLabelColour(activeLabel),
                  color: "#fff",
                  "& .MuiChip-deleteIcon": { color: "rgba(255,255,255,0.7)" },
                }}
              />
            )}
          </Stack>

          {loading ? (
            <Skeleton variant="rounded" height={Math.max(80, 10 * 22)} />
          ) : dist && dist.distribution.length > 0 ? (
            <ResponsiveContainer
              width="100%"
              height={Math.max(80, dist.distribution.length * 22)}
            >
              <BarChart
                data={dist.distribution}
                layout="vertical"
                margin={{ left: 8, right: 56, top: 2, bottom: 2 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.3} />
                <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
                <YAxis
                  type="category"
                  dataKey="label"
                  tick={({ x, y, payload }) => {
                    const label = String(payload.value ?? "");
                    const count = dist.distribution.find((d) => d.label === label)?.count ?? 0;
                    const below = count < MIN_SPANS_PER_LABEL;
                    return (
                      <text
                        x={x}
                        y={y}
                        dy={4}
                        textAnchor="end"
                        fontSize={11}
                        fill={below ? "#ed6c02" : "#555"}
                      >
                        {below ? `⚠ ${label}` : label}
                      </text>
                    );
                  }}
                  width={150}
                />
                <RTooltip
                  formatter={(v: unknown, _name: unknown, props: unknown) => {
                    const value = Number(v ?? 0);
                    const payload = (props as { payload?: { label?: string } })
                      ?.payload;
                    const label = payload?.label ?? "";
                    const isActive = activeLabel === label;
                    const below = value < MIN_SPANS_PER_LABEL;
                    const suffix = isActive
                      ? " (filtered)"
                      : below
                        ? " - below minimum"
                        : "";
                    return [`${value} spans${suffix}`, "Count"];
                  }}
                  cursor={{ fill: "rgba(0,0,0,0.04)" }}
                />
                <ReferenceLine
                  x={MIN_SPANS_PER_LABEL}
                  stroke="#ed6c02"
                  strokeDasharray="5 3"
                  strokeWidth={1.5}
                  label={{
                    value: `Min ${MIN_SPANS_PER_LABEL}`,
                    position: "right",
                    fontSize: 10,
                    fill: "#ed6c02",
                  }}
                />
                <Bar
                  dataKey="count"
                  maxBarSize={16}
                  radius={[0, 3, 3, 0]}
                  cursor={onLabelFilter ? "pointer" : "default"}
                  onClick={
                    onLabelFilter
                      ? ((data: unknown) => {
                          const clicked =
                            (data as { label?: string })?.label ?? "";
                          onLabelFilter(
                            activeLabel === clicked ? null : clicked,
                          );
                          // Recharts BarMouseEvent expects (data, index, event)
                          // but we only need the label; cast at the boundary.
                        }) as never
                      : undefined
                  }
                >
                  {dist.distribution.map((row) => {
                    const below = row.count < MIN_SPANS_PER_LABEL;
                    const dimmed = activeLabel && activeLabel !== row.label;
                    return (
                      <Cell
                        key={row.label}
                        fill={below ? "#bdbdbd" : entityLabelColour(row.label)}
                        opacity={dimmed ? 0.25 : 1}
                      />
                    );
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <Typography sx={{ fontSize: FONT_SIZES.body, color: "text.secondary" }}>
              No entity data yet.
            </Typography>
          )}
          {dist && dist.distribution.length > 0 && (
            <Typography sx={{ fontSize: 10, color: "text.disabled", mt: 0.5 }}>
              {activeLabel
                ? "Click the bar again or clear the chip to remove the filter."
                : `Dashed line = minimum ${MIN_SPANS_PER_LABEL} spans for reliable training. Grey bars need more examples. Click a bar to filter.`}
            </Typography>
          )}

          {/* Span-misaligned section */}
          {!loading && diag && totalNotReady > 0 && (
            <>
              <Divider sx={{ my: 1.5 }} />
              <MisalignedList diag={diag} onOpenLabel={onOpenLabel} />
            </>
          )}

          {!loading && diag && totalNotReady === 0 && (
            <Typography sx={{ fontSize: 11, color: "success.dark", mt: 1 }}>
              All verified records are ready for training.
            </Typography>
          )}

          {!loading && phraseConsistency && (
            <>
              <Divider sx={{ my: 1.5 }} />

              {/* -- Section header ---------------------------------------- */}
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <WarningAmberIcon
                  sx={{
                    fontSize: 15,
                    color:
                      phraseConsistency.summary.conflicting_phrases > 0
                        ? "warning.main"
                        : "success.main",
                  }}
                />
                <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, flex: 1 }}>
                  Phrase annotation consistency
                </Typography>
                <Chip
                  size="small"
                  label={
                    phraseConsistency.summary.conflicting_phrases === 0
                      ? "Clean"
                      : `${phraseConsistency.summary.conflicting_phrases} conflict${phraseConsistency.summary.conflicting_phrases !== 1 ? "s" : ""}`
                  }
                  color={phraseConsistency.summary.conflicting_phrases > 0 ? "warning" : "success"}
                  sx={{ height: 18, fontSize: "0.68rem" }}
                />
                {(phraseConsistency.summary.approved_multilabel_variants ?? 0) > 0 && (
                  <Chip
                    size="small"
                    icon={<CheckCircleOutlineIcon sx={{ fontSize: "12px !important" }} />}
                    label={`${phraseConsistency.summary.approved_multilabel_variants} approved`}
                    color="success"
                    variant="outlined"
                    sx={{ height: 18, fontSize: "0.68rem" }}
                  />
                )}
              </Stack>

              {/* -- No conflicts state ------------------------------------ */}
              {phraseConsistency.summary.conflicting_phrases === 0 ? (
                <Typography sx={{ fontSize: 11, color: "success.dark" }}>
                  No annotation conflicts in the training set.
                </Typography>
              ) : (
                <>
                  <Typography sx={{ fontSize: 11, color: "text.secondary", mb: 1 }}>
                    The same phrase appears under different labels. Use{" "}
                    <strong>Fix</strong> to open mismatched records directly.
                    Assertion differences are expected and are not counted.
                  </Typography>
                  {(phraseConsistency.summary.assertion_only_variants ?? 0) > 0 && (
                    <Typography sx={{ fontSize: 10, color: "text.disabled", mb: 1 }}>
                      {phraseConsistency.summary.assertion_only_variants} assertion-only
                      variants ignored (not NER conflicts).
                    </Typography>
                  )}

                  {/* -- Conflict cards ------------------------------------ */}
                  <Stack spacing={1}>
                    {phraseConsistency.conflicts.map((item) => {
                      const outliers = item.outlier_examples ?? [];
                      const fixIdx = phraseFixIndex[item.phrase] ?? 0;
                      const allLabels = Array.from(
                        new Set(item.signature_counts.map((s) => s.label)),
                      );
                      return (
                        <Box
                          key={item.phrase}
                          sx={{
                            border: "1px solid",
                            borderColor: "warning.200",
                            borderLeft: "3px solid",
                            borderLeftColor: "warning.main",
                            borderRadius: 1.5,
                            bgcolor: "background.paper",
                            overflow: "hidden",
                            transition: "box-shadow 0.15s",
                            "&:hover": { boxShadow: "0 2px 8px rgba(0,0,0,0.08)" },
                          }}
                        >
                          <Stack
                            direction={{ xs: "column", md: "row" }}
                            alignItems="stretch"
                          >
                            {/* Left: phrase details */}
                            <Box sx={{ p: 1.25, flex: 1, minWidth: 0 }}>
                              <Typography
                                sx={{
                                  fontSize: 12,
                                  fontWeight: 700,
                                  color: "text.primary",
                                  mb: 0.35,
                                }}
                              >
                                &ldquo;{item.phrase}&rdquo;
                              </Typography>
                              <Stack
                                direction="row"
                                spacing={1}
                                alignItems="center"
                                sx={{ mb: 0.6 }}
                              >
                                <Typography sx={{ fontSize: 10, color: "text.secondary" }}>
                                  {item.occurrences} occurrences
                                </Typography>
                                <Typography sx={{ fontSize: 10, color: "text.disabled" }}>
                                  &bull;
                                </Typography>
                                <Typography sx={{ fontSize: 10, color: "text.secondary" }}>
                                  {item.distinct_labels} label{item.distinct_labels !== 1 ? "s" : ""}
                                </Typography>
                                {!!item.primary_label && (
                                  <>
                                    <Typography sx={{ fontSize: 10, color: "text.disabled" }}>
                                      &bull;
                                    </Typography>
                                    <Typography
                                      sx={{
                                        fontSize: 10,
                                        color: "primary.main",
                                        fontWeight: 600,
                                      }}
                                    >
                                      Canonical: {item.primary_label}
                                    </Typography>
                                  </>
                                )}
                              </Stack>
                              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                {item.signature_counts.slice(0, 5).map((sig) => (
                                  <Chip
                                    key={`${item.phrase}-${sig.label}-${sig.assertion}`}
                                    size="small"
                                    label={`${sig.label} (${sig.count})`}
                                    variant="outlined"
                                    sx={{
                                      height: 20,
                                      fontSize: "0.67rem",
                                      borderColor: "warning.300",
                                      color: "warning.dark",
                                    }}
                                  />
                                ))}
                              </Stack>
                              {onOpenLabel && item.examples.length > 0 && (
                                <Stack
                                  direction="row"
                                  spacing={0.5}
                                  flexWrap="wrap"
                                  useFlexGap
                                  sx={{ mt: 0.6 }}
                                >
                                  {item.examples.slice(0, 3).map((ex) => (
                                    <Chip
                                      key={`${item.phrase}-${ex.label_id}-${ex.label}`}
                                      size="small"
                                      label={`${ex.label_id.slice(0, 8)} [${ex.label}]`}
                                      onClick={() => onOpenLabel(ex.label_id)}
                                      clickable
                                      sx={{
                                        height: 18,
                                        fontSize: "0.65rem",
                                        bgcolor: "grey.100",
                                      }}
                                    />
                                  ))}
                                </Stack>
                              )}
                            </Box>

                            {/* Right: actions panel */}
                            <Box
                              sx={{
                                p: 1.25,
                                minWidth: { md: 220 },
                                borderLeft: { xs: "none", md: "1px solid" },
                                borderTop: { xs: "1px solid", md: "none" },
                                borderColor: "divider",
                                bgcolor: "grey.50",
                                display: "flex",
                                flexDirection: "column",
                                gap: 0.75,
                                justifyContent: "center",
                              }}
                            >
                              {onOpenLabel && outliers.length > 0 && (
                                <Box>
                                  <Button
                                    variant="contained"
                                    size="small"
                                    fullWidth
                                    onClick={() => {
                                      const next = fixIdx % outliers.length;
                                      onOpenLabel(outliers[next].label_id);
                                      setPhraseFixIndex((prev) => ({
                                        ...prev,
                                        [item.phrase]: (next + 1) % outliers.length,
                                      }));
                                    }}
                                    sx={{
                                      textTransform: "none",
                                      fontSize: "0.75rem",
                                      fontWeight: 700,
                                      bgcolor: "#1565C0",
                                      "&:hover": { bgcolor: "#0D47A1" },
                                    }}
                                  >
                                    Fix mismatch &mdash; {item.outlier_count ?? outliers.length} to fix
                                  </Button>
                                  <Typography
                                    sx={{
                                      fontSize: "0.65rem",
                                      color: "text.disabled",
                                      mt: 0.35,
                                      textAlign: "center",
                                    }}
                                  >
                                    Opens record {(fixIdx % outliers.length) + 1} of{" "}
                                    {outliers.length}
                                  </Typography>
                                </Box>
                              )}
                              {allLabels.length > 1 && (
                                <Box sx={{ mt: onOpenLabel && outliers.length > 0 ? 0.5 : 0 }}>
                                  <Typography
                                    sx={{
                                      fontSize: "0.62rem",
                                      color: "text.disabled",
                                      fontWeight: 600,
                                      textTransform: "uppercase",
                                      letterSpacing: "0.04em",
                                      mb: 0.4,
                                    }}
                                  >
                                    Exception
                                  </Typography>
                                  <Button
                                    variant="outlined"
                                    color="warning"
                                    size="small"
                                    fullWidth
                                    disabled={approvingPhrase === item.phrase}
                                    onClick={() => {
                                      setConfirmApprovalChecked(false);
                                      setApprovalError(null);
                                      setPendingApproval({
                                        phrase: item.phrase,
                                        labels: allLabels,
                                      });
                                    }}
                                    sx={{
                                      textTransform: "none",
                                      fontSize: "0.72rem",
                                      fontWeight: 600,
                                      borderWidth: 1.5,
                                    }}
                                  >
                                    Approve multi-label
                                  </Button>
                                </Box>
                              )}
                            </Box>
                          </Stack>
                        </Box>
                      );
                    })}
                  </Stack>
                </>
              )}

              {/* -- Approved exceptions ----------------------------------- */}
              {(phraseConsistency.approved_multilabel?.length ?? 0) > 0 && (
                <Box
                  sx={{
                    mt: 1.5,
                    border: "1px solid",
                    borderColor: "success.200",
                    borderRadius: 1.5,
                    overflow: "hidden",
                  }}
                >
                  <Stack
                    direction="row"
                    alignItems="center"
                    spacing={0.75}
                    sx={{
                      px: 1.25,
                      py: 0.85,
                      bgcolor: "success.50",
                      cursor: "pointer",
                      userSelect: "none",
                    }}
                    onClick={() => setApprovalsExpanded((v) => !v)}
                  >
                    <CheckCircleOutlineIcon
                      sx={{ fontSize: 14, color: "success.main", flexShrink: 0 }}
                    />
                    <Typography
                      sx={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: "success.dark",
                        flex: 1,
                      }}
                    >
                      Approved multi-label exceptions (
                      {phraseConsistency.approved_multilabel!.length})
                    </Typography>
                    <Typography sx={{ fontSize: 10, color: "text.disabled" }}>
                      {approvalsExpanded ? "hide" : "show"}
                    </Typography>
                    {approvalsExpanded ? (
                      <ExpandLessIcon sx={{ fontSize: 15, color: "text.secondary" }} />
                    ) : (
                      <ExpandMoreIcon sx={{ fontSize: 15, color: "text.secondary" }} />
                    )}
                  </Stack>
                  <Collapse in={approvalsExpanded}>
                    <Stack spacing={0} divider={<Divider />}>
                      {phraseConsistency.approved_multilabel!.map((item) => (
                        <Box
                          key={`approved-${item.phrase}`}
                          sx={{ px: 1.25, py: 1, bgcolor: "background.paper" }}
                        >
                          <Stack
                            direction="row"
                            alignItems="flex-start"
                            justifyContent="space-between"
                            spacing={1}
                          >
                            <Box sx={{ flex: 1, minWidth: 0 }}>
                              <Typography
                                sx={{
                                  fontSize: 12,
                                  fontWeight: 600,
                                  color: "text.primary",
                                  mb: 0.4,
                                }}
                              >
                                &ldquo;{item.phrase}&rdquo;
                              </Typography>
                              <Stack
                                direction="row"
                                spacing={0.5}
                                flexWrap="wrap"
                                useFlexGap
                              >
                                {item.signature_counts.slice(0, 5).map((sig) => (
                                  <Chip
                                    key={`approved-${item.phrase}-${sig.label}-${sig.assertion}`}
                                    size="small"
                                    label={`${sig.label} (${sig.count})`}
                                    variant="outlined"
                                    color="success"
                                    sx={{ height: 18, fontSize: "0.65rem" }}
                                  />
                                ))}
                              </Stack>
                            </Box>
                            <Chip
                              size="small"
                              icon={<CheckCircleOutlineIcon sx={{ fontSize: "11px !important" }} />}
                              label="Approved"
                              color="success"
                              sx={{ height: 18, fontSize: "0.64rem", flexShrink: 0 }}
                            />
                          </Stack>
                        </Box>
                      ))}
                    </Stack>
                  </Collapse>
                </Box>
              )}
            </>
          )}
        </Box>
      </Collapse>
      <Dialog
        open={!!pendingApproval}
        onClose={() => {
          if (!approvingPhrase) {
            setPendingApproval(null);
            setConfirmApprovalChecked(false);
            setApprovalError(null);
          }
        }}
        maxWidth="xs"
        fullWidth
        PaperProps={{ sx: { borderRadius: 2 } }}
      >
        <DialogTitle sx={{ pb: 0.5, fontWeight: 700, fontSize: "1rem" }}>
          Approve as multi-label exception?
        </DialogTitle>
        <DialogContent sx={{ pt: "8px !important" }}>
          <Typography sx={{ fontSize: 12, color: "text.secondary", mb: 1.25 }}>
            Only approve when this phrase <strong>intentionally</strong> carries
            multiple labels in your training data. It will be excluded from the
            conflict list permanently.
          </Typography>

          {pendingApproval && (
            <Box
              sx={{
                p: 1.25,
                border: "1px solid",
                borderColor: "warning.300",
                borderLeft: "3px solid",
                borderLeftColor: "warning.main",
                borderRadius: 1.5,
                mb: 1.25,
                bgcolor: "warning.50",
              }}
            >
              <Typography
                sx={{ fontSize: 12, fontWeight: 700, color: "text.primary", mb: 0.35 }}
              >
                &ldquo;{pendingApproval.phrase}&rdquo;
              </Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {pendingApproval.labels.map((label) => (
                  <Chip
                    key={label}
                    size="small"
                    label={label}
                    color="warning"
                    variant="outlined"
                    sx={{ height: 18, fontSize: "0.66rem" }}
                  />
                ))}
              </Stack>
            </Box>
          )}

          {approvalError && (
            <Alert severity="error" sx={{ mb: 1.25, fontSize: 12 }}>
              {approvalError}
            </Alert>
          )}

          <FormControlLabel
            control={
              <Checkbox
                checked={confirmApprovalChecked}
                onChange={(e) => setConfirmApprovalChecked(e.target.checked)}
                size="small"
                color="warning"
              />
            }
            label={
              <Typography sx={{ fontSize: 11, color: "text.secondary" }}>
                I confirm this is an intentional multi-label phrase and should
                be excluded from annotation conflicts.
              </Typography>
            }
            sx={{ alignItems: "flex-start", ml: 0 }}
          />
        </DialogContent>
        <DialogActions sx={{ px: 2, pb: 2 }}>
          <Button
            onClick={() => {
              setPendingApproval(null);
              setConfirmApprovalChecked(false);
              setApprovalError(null);
            }}
            disabled={!!approvingPhrase}
            sx={{ textTransform: "none" }}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            color="warning"
            disabled={!pendingApproval || !confirmApprovalChecked || !!approvingPhrase}
            onClick={async () => {
              if (!pendingApproval) return;
              const current = pendingApproval;
              const ok = await runApproveMultiLabel(current.phrase, current.labels);
              if (ok) {
                setPendingApproval(null);
                setConfirmApprovalChecked(false);
                setApprovalError(null);
                setApprovalsExpanded(true);
              }
            }}
            sx={{ textTransform: "none", fontWeight: 700 }}
          >
            {approvingPhrase ? "Saving..." : "Approve exception"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
