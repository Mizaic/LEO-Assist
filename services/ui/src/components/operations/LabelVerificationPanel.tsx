"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";

interface LabelVerificationReview {
  review_id: string;
  label_id: string;
  entity_index: number;
  entity_text: string;
  current_label: string;
  model_a_label: string;
  model_a_rationale: string;
  model_b_label: string;
  model_b_rationale: string;
  text: string;
  entities_json?: string;
  source: string;
}

interface VerificationStats {
  total_labels: number;
  verified_labels: number;
  agreements: number;
  disagreements: number;
  pending: number;
}

interface VerifyAllStatus {
  status?: "idle" | "running" | "stopping" | "cancelled" | "done" | "failed";
  auto_resolved?: number;
  total?: number;
  done?: number;
  remaining?: number;
  progress_pct?: number;
  items_per_min?: number;
  eta_seconds?: number | null;
  eta_at?: number | null;
}

interface QueueResponse {
  reviews: LabelVerificationReview[];
  total: number;
  pending: number;
  page: number;
  page_size: number;
  total_pages: number;
  stats: VerificationStats;
}

interface LabelEntity {
  text: string;
  label: string;
  start?: number;
  end?: number;
  [k: string]: unknown;
}

const VALID_ENTITY_LABELS = [
  "disorder",
  "finding",
  "procedure",
  "observable_entity",
  "qualifier_value",
  "substance",
  "medicinal_product",
  "clinical_drug",
  "situation",
  "event",
  "body_structure",
  "tumor_staging",
  "assessment_scale",
  "staging_scale",
  "regime_therapy",
  "record_artifact",
  "physical_object",
  "organism",
  "morphologic_abnormality",
  "occupation",
  "attribute",
  "environment",
  "product",
  "X_TEMPORAL",
  "X_DOSAGE",
  "X_FREQUENCY",
  "X_ROUTE",
] as const;

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export default function LabelVerificationPanel() {
  const [reviews, setReviews] = useState<LabelVerificationReview[]>([]);
  const [stats, setStats] = useState<VerificationStats>({
    total_labels: 0,
    verified_labels: 0,
    agreements: 0,
    disagreements: 0,
    pending: 0,
  });
  const [pendingCount, setPendingCount] = useState(0);
  const [autoResolvedCount, setAutoResolvedCount] = useState(0);
  const [verifyStatus, setVerifyStatus] = useState<VerifyAllStatus | null>(null);
  const [startingVerify, setStartingVerify] = useState(false);
  const [stoppingVerify, setStoppingVerify] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingReviewId, setSavingReviewId] = useState<string | null>(null);
  const [creatingRuleId, setCreatingRuleId] = useState<string | null>(null);
  const [submittingReviewId, setSubmittingReviewId] = useState<string | null>(null);
  const [selectedLabels, setSelectedLabels] = useState<Record<string, string>>({});
  const [selectedSpans, setSelectedSpans] = useState<Record<string, string>>({});
  const [contextContains, setContextContains] = useState<Record<string, string>>({});
  const [selectedEntityIdx, setSelectedEntityIdx] = useState<Record<string, number>>({});
  const [draftEntitiesByReview, setDraftEntitiesByReview] = useState<Record<string, LabelEntity[]>>({});
  const [newSpanText, setNewSpanText] = useState<Record<string, string>>({});
  const [newSpanLabel, setNewSpanLabel] = useState<Record<string, string>>({});

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jsonFetch<QueueResponse>(
        `/api/training/labels/verification-queue?page=${page}&page_size=${pageSize}`
      );
      setReviews(data.reviews);
      setStats(
        data.stats ?? {
          total_labels: 0,
          verified_labels: 0,
          agreements: 0,
          disagreements: 0,
          pending: 0,
        }
      );
      setPendingCount(data.pending ?? 0);
      setTotalPages(Math.max(1, data.total_pages ?? 1));
      const status = await jsonFetch<VerifyAllStatus>("/api/training/labels/verify-all/status");
      setVerifyStatus(status);
      setAutoResolvedCount(status.auto_resolved ?? 0);

      const nextSelected: Record<string, string> = {};
      const nextSpans: Record<string, string> = {};
      const nextContext: Record<string, string> = {};
      const nextSelectedIdx: Record<string, number> = {};
      const nextDraftEntities: Record<string, LabelEntity[]> = {};
      const nextNewSpanText: Record<string, string> = {};
      const nextNewSpanLabel: Record<string, string> = {};
      for (const review of data.reviews) {
        const parsed = parseEntities(review.entities_json);
        nextDraftEntities[review.review_id] = parsed;
        const idx = Math.max(
          0,
          parsed.findIndex((e) => e.text === review.entity_text && e.label === review.current_label)
        );
        nextSelectedIdx[review.review_id] = idx;
        const target = parsed[idx];
        nextSelected[review.review_id] = target?.label || review.model_a_label || review.current_label || "finding";
        nextSpans[review.review_id] = target?.text || review.entity_text || "";
        nextContext[review.review_id] = "";
        nextNewSpanText[review.review_id] = "";
        nextNewSpanLabel[review.review_id] = "finding";
      }
      setSelectedLabels(nextSelected);
      setSelectedSpans(nextSpans);
      setContextContains(nextContext);
      setSelectedEntityIdx(nextSelectedIdx);
      setDraftEntitiesByReview(nextDraftEntities);
      setNewSpanText(nextNewSpanText);
      setNewSpanLabel(nextNewSpanLabel);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load verification queue");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const handleResolve = async (review: LabelVerificationReview) => {
    const resolvedLabel = selectedLabels[review.review_id] || review.current_label;
    const resolvedText = (selectedSpans[review.review_id] ?? review.entity_text ?? "").trim();
    if (!resolvedText) {
      setError("Span text cannot be empty");
      return;
    }
    const idx = selectedEntityIdx[review.review_id] ?? 0;
    setDraftEntitiesByReview((prev) => {
      const rows = [...(prev[review.review_id] ?? [])];
      if (rows[idx]) {
        const oldStart = typeof rows[idx].start === "number" ? rows[idx].start : 0;
        const bestStart = findBestStart(review.text, resolvedText, oldStart);
        rows[idx] = {
          ...rows[idx],
          text: resolvedText,
          label: resolvedLabel,
          start: bestStart ?? rows[idx].start ?? 0,
          end: bestStart != null ? bestStart + resolvedText.length : rows[idx].end ?? 0,
        };
      }
      return { ...prev, [review.review_id]: rows };
    });
  };

  const removeSpanFromRecord = async (review: LabelVerificationReview) => {
    const idx = selectedEntityIdx[review.review_id] ?? 0;
    setDraftEntitiesByReview((prev) => {
      const rows = [...(prev[review.review_id] ?? [])];
      if (idx >= 0 && idx < rows.length) rows.splice(idx, 1);
      return { ...prev, [review.review_id]: rows };
    });
    setSelectedEntityIdx((prev) => ({ ...prev, [review.review_id]: 0 }));
    return true;
  };

  const handleRemoveFromTraining = async (review: LabelVerificationReview) => {
    await removeSpanFromRecord(review);
  };

  const handleCreateSuppressRule = async (review: LabelVerificationReview) => {
    const spanText = (selectedSpans[review.review_id] ?? review.entity_text ?? "").trim();
    if (!spanText) {
      setError("Span text cannot be empty to create a post-processor rule");
      return;
    }

    const contextPhrase = (contextContains[review.review_id] ?? "").trim();
    const escaped = contextPhrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const contextRegex = contextPhrase ? `(?i)${escaped}` : null;

    setCreatingRuleId(review.review_id);
    try {
      await jsonFetch("/api/training/post-processor-rules", {
        method: "POST",
        body: JSON.stringify({
          action: "suppress",
          match_text: spanText,
          match_label: selectedLabels[review.review_id] ?? review.current_label,
          context_regex: contextRegex,
          priority: 50,
          notes: `Created from verification review ${review.review_id}`,
          created_by: "operations_ui",
          active: true,
        }),
      });
      // Stage a local removal so user can keep fixing this record before submit.
      await removeSpanFromRecord(review);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create post-processor rule");
    } finally {
      setCreatingRuleId(null);
    }
  };

  const summaryChips = useMemo(
    () => [
      { label: `Total labels: ${stats.total_labels.toLocaleString()}` },
      { label: `Verified: ${stats.verified_labels.toLocaleString()}` },
      { label: `Agreements: ${stats.agreements.toLocaleString()}` },
      { label: `Disagreements: ${stats.disagreements.toLocaleString()}` },
      { label: `Pending HITL: ${pendingCount.toLocaleString()}`, color: "warning" as const },
      { label: `Auto-resolved: ${autoResolvedCount.toLocaleString()}`, color: "success" as const },
      ...(verifyStatus?.status === "running" || verifyStatus?.status === "stopping"
        ? [
            { label: `Progress: ${(verifyStatus.progress_pct ?? 0).toFixed(1)}%`, color: "primary" as const },
            { label: `Remaining: ${(verifyStatus.remaining ?? 0).toLocaleString()}`, color: "primary" as const },
            {
              label: `ETA: ${typeof verifyStatus.eta_seconds === "number" ? `${Math.max(0, Math.round(verifyStatus.eta_seconds / 60))}m` : "unknown"}`,
              color: "primary" as const,
            },
            {
              label: `Finish: ${
                typeof verifyStatus.eta_at === "number"
                  ? new Date(verifyStatus.eta_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                  : "unknown"
              }`,
              color: "primary" as const,
            },
          ]
        : []),
    ],
    [autoResolvedCount, pendingCount, stats, verifyStatus]
  );

  const parseEntities = (raw?: string): LabelEntity[] => {
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed
        .map((e) => ({
          text: String(e?.text ?? "").trim(),
          label: String(e?.label ?? "").trim(),
          start: typeof e?.start === "number" ? e.start : undefined,
          end: typeof e?.end === "number" ? e.end : undefined,
        }))
        .filter((e) => !!e.text);
    } catch {
      return [];
    }
  };

  const findBestStart = (encounterText: string, spanText: string, oldStart = 0): number | null => {
    const exact: number[] = [];
    let p = encounterText.indexOf(spanText);
    while (p !== -1) {
      exact.push(p);
      p = encounterText.indexOf(spanText, p + 1);
    }
    if (exact.length) {
      return exact.reduce((best, cur) =>
        Math.abs(cur - oldStart) < Math.abs(best - oldStart) ? cur : best, exact[0]);
    }

    const hay = encounterText.toLowerCase();
    const needle = spanText.toLowerCase();
    const ci: number[] = [];
    p = hay.indexOf(needle);
    while (p !== -1) {
      ci.push(p);
      p = hay.indexOf(needle, p + 1);
    }
    if (ci.length) {
      return ci.reduce((best, cur) =>
        Math.abs(cur - oldStart) < Math.abs(best - oldStart) ? cur : best, ci[0]);
    }
    return null;
  };

  const handleAddSpan = (review: LabelVerificationReview) => {
    const reviewId = review.review_id;
    const spanText = (newSpanText[reviewId] ?? "").trim();
    const label = (newSpanLabel[reviewId] ?? "finding").trim();
    if (!spanText) {
      setError("New span text cannot be empty");
      return;
    }
    const start = findBestStart(review.text, spanText, 0);
    if (start == null) {
      setError("New span text was not found in encounter text");
      return;
    }
    const ent: LabelEntity = { text: spanText, label, start, end: start + spanText.length };
    setDraftEntitiesByReview((prev) => {
      const rows = [...(prev[reviewId] ?? [])];
      rows.push(ent);
      return { ...prev, [reviewId]: rows };
    });
    setSelectedEntityIdx((prev) => {
      const nextIdx = (draftEntitiesByReview[reviewId] ?? []).length;
      return { ...prev, [reviewId]: nextIdx };
    });
    setSelectedSpans((prev) => ({ ...prev, [reviewId]: spanText }));
    setSelectedLabels((prev) => ({ ...prev, [reviewId]: label }));
    setNewSpanText((prev) => ({ ...prev, [reviewId]: "" }));
  };

  const handleSubmit = async (review: LabelVerificationReview) => {
    const entities = draftEntitiesByReview[review.review_id] ?? [];
    setSubmittingReviewId(review.review_id);
    try {
      await jsonFetch(`/api/training/labels/${review.label_id}/entities`, {
        method: "PATCH",
        body: JSON.stringify({ entities }),
      });
      await jsonFetch(`/api/training/labels/verification-queue/${review.review_id}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          resolved_label: selectedLabels[review.review_id] ?? review.current_label,
          resolved_text: selectedSpans[review.review_id] ?? review.entity_text,
          resolve_only: true,
          reviewer: "operations_ui",
        }),
      });
      setReviews((prev) => prev.filter((r) => r.review_id !== review.review_id));
      setPendingCount((n) => Math.max(0, n - 1));
      setStats((s) => ({
        ...s,
        verified_labels: s.verified_labels + 1,
        pending: Math.max(0, s.pending - 1),
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not submit record updates");
    } finally {
      setSubmittingReviewId(null);
    }
  };

  const handleStartVerification = async (mode: "all" | "hitl_only", resetPending = false) => {
    setStartingVerify(true);
    try {
      await jsonFetch("/api/training/labels/verify-all", {
        method: "POST",
        body: JSON.stringify({ mode, reset_pending: resetPending }),
      });
      await fetchQueue();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start label verification");
    } finally {
      setStartingVerify(false);
    }
  };

  const handleStopVerification = async () => {
    setStoppingVerify(true);
    try {
      await jsonFetch("/api/training/labels/verify-all/cancel", { method: "POST" });
      const status = await jsonFetch<VerifyAllStatus>("/api/training/labels/verify-all/status");
      setVerifyStatus(status);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not stop label verification");
    } finally {
      setStoppingVerify(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 1100, mx: "auto", px: 3, py: 3 }}>
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>
        Label Review
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
        Resolve AWS/Azure disagreements on label extraction quality.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 2 }}>
        {summaryChips.map((chip) => (
          <Chip key={chip.label} label={chip.label} color={chip.color ?? "default"} size="small" />
        ))}
      </Stack>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <Button variant="outlined" size="small" onClick={fetchQueue} disabled={loading}>
          Refresh
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={startingVerify || verifyStatus?.status === "running" || verifyStatus?.status === "stopping"}
          onClick={() => handleStartVerification("all", true)}
        >
          Reset + reverify all
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={startingVerify || verifyStatus?.status === "running" || verifyStatus?.status === "stopping"}
          onClick={() => handleStartVerification("hitl_only", false)}
        >
          Reverify HITL only
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={startingVerify || verifyStatus?.status === "running" || verifyStatus?.status === "stopping"}
          onClick={() => handleStartVerification("resume", false)}
        >
          Resume
        </Button>
        <Button
          variant="outlined"
          color="error"
          size="small"
          disabled={stoppingVerify || (verifyStatus?.status !== "running" && verifyStatus?.status !== "stopping")}
          onClick={handleStopVerification}
        >
          Stop verify
        </Button>
      </Stack>

      {loading && (
        <Paper variant="outlined" sx={{ p: 3, textAlign: "center", mb: 2 }}>
          <CircularProgress size={20} />
        </Paper>
      )}

      {!loading && reviews.length === 0 && (
        <Paper variant="outlined" sx={{ p: 3, textAlign: "center", mb: 2 }}>
          <Typography variant="body2" color="text.secondary">
            No pending disagreements.
          </Typography>
        </Paper>
      )}

      <Stack spacing={1.5}>
        {reviews.map((review) => (
          <Paper key={review.review_id} variant="outlined" sx={{ p: 2 }}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <Chip label={review.source} size="small" variant="outlined" />
              <Chip label={`Current: ${review.current_label}`} size="small" />
              <Chip label={`Span: ${review.entity_text}`} size="small" color="info" variant="outlined" />
            </Stack>

            <Box
              sx={{
                bgcolor: (t) => (t.palette.mode === "dark" ? "#0f172a" : "#f8fafc"),
                borderRadius: 1,
                p: 1.25,
                border: "1px solid",
                borderColor: "divider",
                mb: 1.5,
                fontFamily: "monospace",
                fontSize: 12,
                whiteSpace: "pre-wrap",
                lineHeight: 1.75,
              }}
            >
              {review.text}
            </Box>

            <Box sx={{ mb: 1.5 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                Extracted spans in this record
              </Typography>
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                {(draftEntitiesByReview[review.review_id] ?? []).length === 0 ? (
                  <Typography variant="caption" color="text.disabled">No other spans found</Typography>
                ) : (
                  (draftEntitiesByReview[review.review_id] ?? []).map((ent, idx) => {
                    const isCurrent = idx === (selectedEntityIdx[review.review_id] ?? 0);
                    return (
                      <Chip
                        key={`${review.review_id}-${idx}-${ent.text}-${ent.label}`}
                        label={`${ent.text} · ${ent.label}`}
                        size="small"
                        color={isCurrent ? "warning" : "default"}
                        variant={isCurrent ? "filled" : "outlined"}
                        onClick={() => {
                          setSelectedEntityIdx((prev) => ({ ...prev, [review.review_id]: idx }));
                          setSelectedSpans((prev) => ({ ...prev, [review.review_id]: ent.text }));
                          setSelectedLabels((prev) => ({ ...prev, [review.review_id]: ent.label }));
                        }}
                      />
                    );
                  })
                )}
              </Stack>
            </Box>

            <Stack
              direction={{ xs: "column", md: "row" }}
              spacing={1}
              alignItems={{ xs: "stretch", md: "center" }}
              sx={{ mb: 1.25 }}
            >
              <TextField
                size="small"
                label="New span text"
                value={newSpanText[review.review_id] ?? ""}
                onChange={(e) =>
                  setNewSpanText((prev) => ({ ...prev, [review.review_id]: e.target.value }))
                }
                helperText="Add a brand-new span from encounter text"
                sx={{ minWidth: 280, flex: 1 }}
              />
              <FormControl size="small" sx={{ minWidth: 210 }}>
                <Select
                  value={newSpanLabel[review.review_id] ?? "finding"}
                  onChange={(e) =>
                    setNewSpanLabel((prev) => ({ ...prev, [review.review_id]: e.target.value }))
                  }
                >
                  {VALID_ENTITY_LABELS.map((label) => (
                    <MenuItem key={`new-${label}`} value={label}>{label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button
                variant="outlined"
                size="small"
                onClick={() => handleAddSpan(review)}
              >
                Add span
              </Button>
            </Stack>

            <Stack direction={{ xs: "column", md: "row" }} spacing={1.25} sx={{ mb: 1.25 }}>
              <Paper variant="outlined" sx={{ p: 1.25, flex: 1 }}>
                <Typography variant="caption" sx={{ fontWeight: 700 }}>
                  AWS suggestion
                </Typography>
                <Typography variant="body2" sx={{ mt: 0.5 }}>{review.model_a_label}</Typography>
                <Typography variant="caption" color="text.secondary">{review.model_a_rationale || "—"}</Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.25, flex: 1 }}>
                <Typography variant="caption" sx={{ fontWeight: 700 }}>
                  Azure suggestion
                </Typography>
                <Typography variant="body2" sx={{ mt: 0.5 }}>{review.model_b_label}</Typography>
                <Typography variant="caption" color="text.secondary">{review.model_b_rationale || "—"}</Typography>
              </Paper>
            </Stack>

            <Stack
              direction={{ xs: "column", md: "row" }}
              spacing={1}
              alignItems={{ xs: "stretch", md: "center" }}
            >
              <TextField
                size="small"
                label="Span text"
                value={selectedSpans[review.review_id] ?? review.entity_text}
                onChange={(e) =>
                  setSelectedSpans((prev) => ({ ...prev, [review.review_id]: e.target.value }))
                }
                helperText="Use exact text from encounter"
                sx={{ minWidth: 260, flex: 1 }}
              />
              <TextField
                size="small"
                label="Context contains (optional)"
                value={contextContains[review.review_id] ?? ""}
                onChange={(e) =>
                  setContextContains((prev) => ({ ...prev, [review.review_id]: e.target.value }))
                }
                helperText='Example: "if Afro-Caribbean"'
                sx={{ minWidth: 260, flex: 1 }}
              />
              <FormControl size="small" sx={{ minWidth: 210 }}>
                <Select
                  value={selectedLabels[review.review_id] ?? review.current_label}
                  onChange={(e) =>
                    setSelectedLabels((prev) => ({ ...prev, [review.review_id]: e.target.value }))
                  }
                >
                  {VALID_ENTITY_LABELS.map((label) => (
                    <MenuItem key={label} value={label}>{label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button
                variant="outlined"
                size="small"
                onClick={() => handleResolve(review)}
                disabled={savingReviewId === review.review_id}
              >
                Apply edit
              </Button>
              <Button
                variant="outlined"
                color="error"
                size="small"
                onClick={() => handleRemoveFromTraining(review)}
                disabled={savingReviewId === review.review_id}
              >
                Remove span
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => handleCreateSuppressRule(review)}
                disabled={creatingRuleId === review.review_id}
              >
                {creatingRuleId === review.review_id ? "Creating rule..." : "Create ignore rule"}
              </Button>
              <Button
                variant="contained"
                size="small"
                onClick={() => handleSubmit(review)}
                disabled={submittingReviewId === review.review_id}
              >
                {submittingReviewId === review.review_id ? "Submitting..." : "Submit"}
              </Button>
            </Stack>
          </Paper>
        ))}
      </Stack>

      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
        <Button size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          ← Prev
        </Button>
        <Typography variant="caption" color="text.secondary">
          {page} / {totalPages}
        </Typography>
        <Button size="small" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
          Next →
        </Button>
        <FormControl size="small" sx={{ minWidth: 100, ml: 1 }}>
          <Select
            value={pageSize}
            onChange={(e) => {
              setPageSize(Number(e.target.value));
              setPage(1);
            }}
          >
            {[10, 25, 50, 100, 500].map((n) => (
              <MenuItem key={n} value={n}>{n === 500 ? "All" : n}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <Typography variant="caption" color="text.secondary">per page</Typography>
      </Stack>
    </Box>
  );
}
