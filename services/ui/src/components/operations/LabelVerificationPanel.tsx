/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A2553F87
 *   DI: DI-425CA252
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A2553F87")
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
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
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import TabFlowDiagram, { type TabStage } from "@/components/operations/TabFlowDiagram";
import ConfirmDialog from "@/components/ConfirmDialog";
import {
  coerceEntitySemanticLabel,
  normaliseEntitySemanticRows,
  VALID_ENTITY_SEMANTIC_LABELS as VALID_ENTITY_LABELS,
} from "@/lib/entitySemanticLabels";

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
  resolved_label?: string | null;
  resolved_by?: string | null;
  resolved_at?: string | null;
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
  pending?: number;
  page: number;
  page_size: number;
  total_pages: number;
  stats?: VerificationStats;
}

interface LabelEntity {
  text: string;
  label: string;
  start?: number;
  end?: number;
  [k: string]: unknown;
}

const ENTITY_LABEL_DISPLAY: Record<string, string> = {
  disorder: "Health condition",
  finding: "Finding or symptom",
  procedure: "Treatment or procedure",
  observable_entity: "Test or measurement",
  qualifier_value: "Qualifier",
  substance: "Substance",
  medicinal_product: "Medicine",
  clinical_drug: "Drug",
  situation: "Situation",
  event: "Event",
  body_structure: "Body part",
  tumor_staging: "Tumour stage",
  assessment_scale: "Assessment scale",
  staging_scale: "Staging scale",
  regime_therapy: "Therapy plan",
  record_artifact: "Record type",
  physical_object: "Physical object",
  organism: "Organism",
  morphologic_abnormality: "Structural change",
  occupation: "Job or role",
  attribute: "Attribute",
  environment: "Environment",
  product: "Product",
  X_TEMPORAL: "Time or date",
  X_DOSAGE: "Dose",
  X_FREQUENCY: "How often",
  X_ROUTE: "How given",
};

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

const LABEL_STAGES: TabStage[] = [
  {
    id: "lv1", num: 1,
    label: "Two tools read it",
    tooltip: "Two medical AI tools both read the note and pull out key medical words.",
    detailIn: "A patient note",
    detailOut: "Two sets of medical word labels -- one from each tool",
  },
  {
    id: "lv2", num: 2,
    label: "They disagree",
    tooltip: "The two tools give different labels for the same word. For example, one says 'health condition' and the other says 'symptom'.",
    detailIn: "Two different labels for the same word in the note",
    detailOut: "A review record added to this queue",
  },
  {
    id: "lv3", num: 3,
    label: "You see both",
    tooltip: "You see the word highlighted in the note, along with what each tool said and the reason it gave.",
    detailIn: "The word, the note, and both suggestions with reasons",
    detailOut: "A clear picture of the disagreement",
  },
  {
    id: "lv4", num: 4,
    label: "You choose",
    tooltip: "You pick the right label for the word. You can also fix the word, add a new word the AI missed, or remove a word that should not be there.",
    detailIn: "Your knowledge of the medical term",
    detailOut: "A corrected label and word",
    branches: [
      {
        label: "Add a new word",
        description: "If the AI missed an important word entirely, you can add it with the correct label",
      },
      {
        label: "Always ignore this",
        description: "If the AI keeps making the same mistake, you can create a rule to stop it happening again",
      },
    ],
  },
  {
    id: "lv5", num: 5,
    label: "Saved for teaching",
    tooltip: "Your corrected label is saved. It will be used next time the AI learns.",
    detailIn: "Your corrected label and word",
    detailOut: "A checked teaching example added to the records",
  },
];

function parseEntities(raw?: string): LabelEntity[] {
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
}

function findBestStart(
  encounterText: string,
  spanText: string,
  oldStart = 0,
): number | null {
  const exact: number[] = [];
  let p = encounterText.indexOf(spanText);
  while (p !== -1) {
    exact.push(p);
    p = encounterText.indexOf(spanText, p + 1);
  }
  if (exact.length) {
    return exact.reduce(
      (best, cur) =>
        Math.abs(cur - oldStart) < Math.abs(best - oldStart) ? cur : best,
      exact[0],
    );
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
    return ci.reduce(
      (best, cur) =>
        Math.abs(cur - oldStart) < Math.abs(best - oldStart) ? cur : best,
      ci[0],
    );
  }
  return null;
}

export default function LabelVerificationPanel() {
  const [viewMode, setViewMode] = useState<"queue" | "history">("queue");
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
  const [confirmSuppressReview, setConfirmSuppressReview] = useState<LabelVerificationReview | null>(null);
  const [confirmResetAll, setConfirmResetAll] = useState(false);

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    try {
      const endpoint =
        viewMode === "history"
          ? `/api/training/labels/verification-history?page=${page}&page_size=${pageSize}`
          : `/api/training/labels/verification-queue?page=${page}&page_size=${pageSize}`;
      const data = await jsonFetch<QueueResponse>(
        endpoint
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
      if (viewMode === "queue") {
        const status = await jsonFetch<VerifyAllStatus>("/api/training/labels/verify-all/status");
        setVerifyStatus(status);
        setAutoResolvedCount(status.auto_resolved ?? 0);
      }

      const nextSelected: Record<string, string> = {};
      const nextSpans: Record<string, string> = {};
      const nextContext: Record<string, string> = {};
      const nextSelectedIdx: Record<string, number> = {};
      const nextDraftEntities: Record<string, LabelEntity[]> = {};
      const nextNewSpanText: Record<string, string> = {};
      const nextNewSpanLabel: Record<string, string> = {};
      for (const review of data.reviews) {
        const parsedRaw = parseEntities(review.entities_json);
        const labelMatch = (e: LabelEntity) =>
          e.text === review.entity_text &&
          coerceEntitySemanticLabel(e.label) === coerceEntitySemanticLabel(review.current_label);
        const idx = Math.max(0, parsedRaw.findIndex(labelMatch));
        const parsed = normaliseEntitySemanticRows(parsedRaw);
        nextDraftEntities[review.review_id] = parsed;
        nextSelectedIdx[review.review_id] = idx;
        const target = parsed[idx];
        nextSelected[review.review_id] = coerceEntitySemanticLabel(
          target?.label || review.model_a_label || review.current_label || "finding",
        );
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
      setError(e instanceof Error ? e.message : "Could not load the label check data. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, viewMode]);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  useEffect(() => {
    setPage(1);
  }, [viewMode]);

  const handleResolve = async (review: LabelVerificationReview) => {
    const resolvedLabel = coerceEntitySemanticLabel(
      selectedLabels[review.review_id] || review.current_label,
    );
    const resolvedText = (selectedSpans[review.review_id] ?? review.entity_text ?? "").trim();
    if (!resolvedText) {
      setError("The word or phrase cannot be empty.");
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
      setError("The word or phrase cannot be empty.");
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
      setError(e instanceof Error ? e.message : "Could not create the ignore rule. Please try again.");
    } finally {
      setCreatingRuleId(null);
    }
  };

  const summaryChips = useMemo(
    () =>
      viewMode === "history"
        ? [
            { label: `${reviews.length.toLocaleString()} past items` },
            { label: `Page ${page} of ${totalPages}` },
          ]
        : [
            { label: `${stats.total_labels.toLocaleString()} labels total` },
            { label: `${stats.verified_labels.toLocaleString()} checked` },
            { label: `${stats.agreements.toLocaleString()} agreed` },
            { label: `${stats.disagreements.toLocaleString()} disagreed` },
            { label: `${pendingCount.toLocaleString()} waiting for you`, color: "warning" as const },
            { label: `${autoResolvedCount.toLocaleString()} fixed automatically`, color: "success" as const },
            ...(verifyStatus?.status === "running" || verifyStatus?.status === "stopping"
              ? [
                  { label: `${(verifyStatus.progress_pct ?? 0).toFixed(1)}% done`, color: "primary" as const },
                  { label: `${(verifyStatus.remaining ?? 0).toLocaleString()} left`, color: "primary" as const },
                  {
                    label: `About ${typeof verifyStatus.eta_seconds === "number" ? `${Math.max(0, Math.round(verifyStatus.eta_seconds / 60))}m left` : "unknown"}`,
                    color: "primary" as const,
                  },
                  {
                    label: `Should finish by ${
                      typeof verifyStatus.eta_at === "number"
                        ? new Date(verifyStatus.eta_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                        : "unknown"
                    }`,
                    color: "primary" as const,
                  },
                ]
              : []),
          ],
    [autoResolvedCount, page, pendingCount, reviews.length, stats, totalPages, verifyStatus, viewMode]
  );

  const handleAddSpan = (review: LabelVerificationReview) => {
    const reviewId = review.review_id;
    const spanText = (newSpanText[reviewId] ?? "").trim();
    const label = (newSpanLabel[reviewId] ?? "finding").trim();
    if (!spanText) {
      setError("The new word or phrase cannot be empty.");
      return;
    }
    const start = findBestStart(review.text, spanText, 0);
    if (start == null) {
      setError("That word was not found in the record text. Check for typos.");
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
    const entities = normaliseEntitySemanticRows(draftEntitiesByReview[review.review_id] ?? []);
    setSubmittingReviewId(review.review_id);
    try {
      await jsonFetch(`/api/training/labels/${review.label_id}/entities`, {
        method: "PATCH",
        body: JSON.stringify({ entities }),
      });
      await jsonFetch(`/api/training/labels/verification-queue/${review.review_id}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          resolved_label: coerceEntitySemanticLabel(
            selectedLabels[review.review_id] ?? review.current_label,
          ),
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
      setError(e instanceof Error ? e.message : "Could not save. Please try again.");
    } finally {
      setSubmittingReviewId(null);
    }
  };

  const handleStartVerification = async (mode: "all" | "hitl_only" | "resume", resetPending = false) => {
    setStartingVerify(true);
    try {
      const apiMode = mode === "resume" ? "hitl_only" : mode;
      await jsonFetch("/api/training/labels/verify-all", {
        method: "POST",
        body: JSON.stringify({ mode: apiMode, reset_pending: resetPending }),
      });
      await fetchQueue();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the label check. Please try again.");
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
      setError(e instanceof Error ? e.message : "Could not stop the label check. Please try again.");
    } finally {
      setStoppingVerify(false);
    }
  };

  return (
    <Stack spacing={1.5}>
      <Box>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
          Check the labels
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ fontSize: 13 }}>
          Two AI tools read the same record and disagreed. Pick the right answer.
        </Typography>
      </Box>

      {/* How this works */}
      <Accordion variant="outlined" disableGutters sx={{ "&::before": { display: "none" } }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ minHeight: 36, "& .MuiAccordionSummary-content": { my: 0.75 } }}>
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
            How this tab works
          </Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0, pb: 1.5 }}>
          <TabFlowDiagram
            stages={LABEL_STAGES}
            color="#14B8A6"
            lightColor="#CCFBF1"
            trackLabel="Check the labels"
          />
        </AccordionDetails>
      </Accordion>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Stack role="group" aria-label="View mode" direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
        <Button
          variant={viewMode === "queue" ? "contained" : "outlined"}
          size="small"
          aria-pressed={viewMode === "queue"}
          onClick={() => setViewMode("queue")}
        >
          Waiting for you
        </Button>
        <Button
          variant={viewMode === "history" ? "contained" : "outlined"}
          size="small"
          aria-pressed={viewMode === "history"}
          onClick={() => setViewMode("history")}
        >
          Done
        </Button>
        {summaryChips.map((chip) => (
          <Chip key={chip.label} label={chip.label} color={chip.color ?? "default"} size="small" />
        ))}
      </Stack>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <Button variant="outlined" size="small" onClick={fetchQueue} disabled={loading}>
          Refresh
        </Button>
        {viewMode === "queue" && (
          <>
        <Button
          variant="outlined"
          size="small"
          disabled={startingVerify || verifyStatus?.status === "running" || verifyStatus?.status === "stopping"}
          onClick={() => setConfirmResetAll(true)}
        >
          Reset and recheck all
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={startingVerify || verifyStatus?.status === "running" || verifyStatus?.status === "stopping"}
          onClick={() => handleStartVerification("hitl_only", false)}
        >
          Recheck reviewed only
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={startingVerify || verifyStatus?.status === "running" || verifyStatus?.status === "stopping"}
          onClick={() => handleStartVerification("resume", false)}
        >
          Resume checking
        </Button>
        <Button
          variant="outlined"
          color="error"
          size="small"
          disabled={stoppingVerify || (verifyStatus?.status !== "running" && verifyStatus?.status !== "stopping")}
          onClick={handleStopVerification}
        >
          Stop checking
        </Button>
          </>
        )}
      </Stack>

      {loading && (
        <Paper variant="outlined" sx={{ p: 3, textAlign: "center", mb: 2 }}>
          <CircularProgress aria-label="Loading" size={20} />
        </Paper>
      )}

      {!loading && reviews.length === 0 && (
        <Paper variant="outlined" sx={{ p: 3, textAlign: "center", mb: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {viewMode === "history" ? "Nothing has been checked yet." : "No disagreements waiting for you. All caught up!"}
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
                label="New word or phrase"
                value={newSpanText[review.review_id] ?? ""}
                onChange={(e) =>
                  setNewSpanText((prev) => ({ ...prev, [review.review_id]: e.target.value }))
                }
                helperText="Add a word the AI missed from the record"
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
                    <MenuItem key={`new-${label}`} value={label}>{ENTITY_LABEL_DISPLAY[label] ?? label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button
                variant="outlined"
                size="small"
                onClick={() => handleAddSpan(review)}
              >
                Add word
              </Button>
            </Stack>

            <Stack direction={{ xs: "column", md: "row" }} spacing={1.25} sx={{ mb: 1.25 }}>
              <Paper variant="outlined" sx={{ p: 1.25, flex: 1 }}>
                <Typography variant="caption" sx={{ fontWeight: 700 }}>
                  Tool A thinks
                </Typography>
                <Typography variant="body2" sx={{ mt: 0.5 }}>{review.model_a_label}</Typography>
                <Typography variant="caption" color="text.secondary">{review.model_a_rationale || "—"}</Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.25, flex: 1 }}>
                <Typography variant="caption" sx={{ fontWeight: 700 }}>
                  Tool B thinks
                </Typography>
                <Typography variant="body2" sx={{ mt: 0.5 }}>{review.model_b_label}</Typography>
                <Typography variant="caption" color="text.secondary">{review.model_b_rationale || "—"}</Typography>
              </Paper>
            </Stack>

            {viewMode === "history" && (
              <Alert severity="info" sx={{ mb: 1.25 }}>
                Resolved as <strong>{review.resolved_label ?? "unknown"}</strong>
                {review.resolved_by ? ` by ${review.resolved_by}` : ""}
                {review.resolved_at ? ` on ${new Date(review.resolved_at).toLocaleString()}` : ""}.
              </Alert>
            )}

            {viewMode === "queue" && (
              <Stack
                direction={{ xs: "column", md: "row" }}
                spacing={1}
                alignItems={{ xs: "stretch", md: "center" }}
              >
              <TextField
                size="small"
                label="Word or phrase"
                value={selectedSpans[review.review_id] ?? review.entity_text}
                onChange={(e) =>
                  setSelectedSpans((prev) => ({ ...prev, [review.review_id]: e.target.value }))
                }
                helperText="Use the exact words from the record"
                sx={{ minWidth: 260, flex: 1 }}
              />
              <TextField
                size="small"
                label="Nearby words (optional)"
                value={contextContains[review.review_id] ?? ""}
                onChange={(e) =>
                  setContextContains((prev) => ({ ...prev, [review.review_id]: e.target.value }))
                }
                helperText='Example: "if Afro-Caribbean"'
                sx={{ minWidth: 260, flex: 1 }}
              />
              <FormControl size="small" sx={{ minWidth: 210 }}>
                <Select
                  value={coerceEntitySemanticLabel(
                    selectedLabels[review.review_id] ?? review.current_label,
                  )}
                  onChange={(e) =>
                    setSelectedLabels((prev) => ({ ...prev, [review.review_id]: e.target.value }))
                  }
                >
                  {VALID_ENTITY_LABELS.map((label) => (
                    <MenuItem key={label} value={label}>{ENTITY_LABEL_DISPLAY[label] ?? label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Button
                variant="outlined"
                size="small"
                onClick={() => handleResolve(review)}
                disabled={savingReviewId === review.review_id}
              >
                Fix this
              </Button>
              <Button
                variant="outlined"
                color="error"
                size="small"
                onClick={() => handleRemoveFromTraining(review)}
                disabled={savingReviewId === review.review_id}
              >
                Remove this word
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setConfirmSuppressReview(review)}
                disabled={creatingRuleId === review.review_id}
              >
                {creatingRuleId === review.review_id ? "Creating rule..." : "Always ignore this"}
              </Button>
              <Button
                variant="contained"
                size="small"
                onClick={() => handleSubmit(review)}
                disabled={submittingReviewId === review.review_id}
              >
                {submittingReviewId === review.review_id ? "Saving..." : "Save and next"}
              </Button>
              </Stack>
            )}
          </Paper>
        ))}
      </Stack>

      {confirmSuppressReview && (
        <ConfirmDialog
          title="Always ignore this word?"
          body={`The AI will stop picking up "${(selectedSpans[confirmSuppressReview.review_id] ?? confirmSuppressReview.entity_text ?? "").trim()}" in all future runs. The word will also be removed from this record. This cannot be undone.`}
          confirmLabel="Always ignore this"
          variant="danger"
          onConfirm={() => { handleCreateSuppressRule(confirmSuppressReview); setConfirmSuppressReview(null); }}
          onCancel={() => setConfirmSuppressReview(null)}
        />
      )}

      {confirmResetAll && (
        <ConfirmDialog
          title="Start all checks again from scratch?"
          body="This will clear all work in progress and recheck every label from the beginning. This cannot be undone."
          confirmLabel="Reset and recheck all"
          variant="danger"
          onConfirm={() => { handleStartVerification("all", true); setConfirmResetAll(false); }}
          onCancel={() => setConfirmResetAll(false)}
        />
      )}

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
    </Stack>
  );
}
