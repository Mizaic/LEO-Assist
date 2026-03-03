"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  ButtonGroup,
  Chip,
  CircularProgress,
  Divider,
  Menu,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ArrowDropDownIcon from "@mui/icons-material/ArrowDropDown";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RefreshIcon from "@mui/icons-material/Refresh";
import TabFlowDiagram, { type TabStage } from "@/components/operations/TabFlowDiagram";
import TermSearch from "@/components/TermSearch";
import type { TermSearchResult } from "@/lib/types";

const jsonFetch = async <T,>(url: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...init?.headers,
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
};

interface CodingReviewItem {
  review_id: string;
  label_id: string;
  entity_index: number;
  entity_text: string;
  entity_label: string;
  coded: boolean;
  snomed_concept_id: string | null;
  snomed_term: string | null;
  score: number | null;
  semantic_tag: string | null;
  created_at: string;
  encounter_text: string;
  source: string;
}

interface CodingStats {
  total: number;
  coded: number;
  uncoded: number;
  resolved: number;
  pending: number;
  low_confidence: number;
}

interface QueueResponse {
  items: CodingReviewItem[];
  page: number;
  page_size: number;
  total_pages: number;
  pending: number;
  stats: CodingStats;
}

const CODING_STAGES: TabStage[] = [
  {
    id: "cod1", num: 1,
    label: "Word Found",
    tooltip: "The AI pulls a medical word out of a patient note. For example, it might find the word 'asthma' or 'blood pressure'.",
    detailIn: "A patient note processed by the pipeline",
    detailOut: "An extracted medical word with its label type",
  },
  {
    id: "cod2", num: 2,
    label: "Code Lookup",
    tooltip: "The system searches the SNOMED library to find the official code that matches the medical word.",
    detailIn: "The extracted medical word",
    detailOut: "A best-match SNOMED code with a confidence score",
    branches: [
      {
        label: "Good match found",
        description: "If a high-confidence match is found, the code is saved automatically and will not appear here",
      },
    ],
  },
  {
    id: "cod3", num: 3,
    label: "No Match",
    tooltip: "No good match was found, or the best match has a low confidence score. The word needs a human to assign the correct code.",
    detailIn: "A word with no match or a low-confidence match",
    detailOut: "A review item added to this queue",
  },
  {
    id: "cod4", num: 4,
    label: "You Search",
    tooltip: "You can search the SNOMED library yourself, or type the concept ID directly if you already know it.",
    detailIn: "Your search term or SNOMED concept ID",
    detailOut: "Up to 5 candidate SNOMED concepts to choose from",
    branches: [
      {
        label: "Manual entry",
        description: "If you know the exact SNOMED concept ID, you can type it directly without searching",
      },
    ],
  },
  {
    id: "cod5", num: 5,
    label: "Code Confirmed",
    tooltip: "The correct SNOMED code is saved and linked to that medical word in the patient record.",
    detailIn: "Your chosen SNOMED concept",
    detailOut: "The word coded correctly and saved to the database",
  },
];

export default function CodingReviewPanel() {
  const [items, setItems] = useState<CodingReviewItem[]>([]);
  const [stats, setStats] = useState<CodingStats>({
    total: 0, coded: 0, uncoded: 0, resolved: 0, pending: 0, low_confidence: 0,
  });
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [creatingRuleId, setCreatingRuleId] = useState<string | null>(null);

  const [manualConceptId, setManualConceptId] = useState<Record<string, string>>({});
  const [manualTerm, setManualTerm] = useState<Record<string, string>>({});
  const [manualSpanText, setManualSpanText] = useState<Record<string, string>>({});
  const [contextContains, setContextContains] = useState<Record<string, string>>({});
  const [searchReviewId, setSearchReviewId] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [rechecking, setRechecking] = useState(false);
  const [recheckMode, setRecheckMode] = useState<"quick" | "llm" | null>(null);
  const [recheckMenuOpen, setRecheckMenuOpen] = useState(false);
  const recheckAnchorRef = useRef<HTMLDivElement>(null);
  const [llmLimit, setLlmLimit] = useState<number>(200);
  const [recheckResult, setRecheckResult] = useState<{
    rechecked: number;
    auto_resolved: number;
    ignored_by_rule: number;
    resolved_direct?: number;
    resolved_llm?: number;
    writeback_llm_success?: number;
    writeback_llm_failed?: number;
  } | null>(null);

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jsonFetch<QueueResponse>(
        `/api/training/coding-review/queue?page=${page}&page_size=${pageSize}`
      );
      setItems(data.items);
      setStats(data.stats);
      setTotalPages(data.total_pages);
      setLastChecked(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load coding review queue");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  const stopRechecking = useCallback((errorMsg?: string) => {
    setRechecking(false);
    setRecheckMode(null);
    if (errorMsg) setError(errorMsg);
  }, []);

  const recheckList = useCallback(async (tryAlternatives: boolean) => {
    setRechecking(true);
    setRecheckMode(tryAlternatives ? "llm" : "quick");
    setRecheckResult(null);
    try {
      const limit = tryAlternatives && llmLimit > 0 ? llmLimit : 0;
      const qs = `try_alternatives=${tryAlternatives}&item_limit=${limit}`;
      await jsonFetch<{ status: string }>(
        `/api/training/coding-review/recheck?${qs}`,
        { method: "POST" }
      );
    } catch (e) {
      stopRechecking(e instanceof Error ? e.message : "Recheck failed. The terminology server may be unavailable.");
    }
  }, [stopRechecking, llmLimit]);

  // Poll recheck status every 2 s while a job is running.
  useEffect(() => {
    if (!rechecking) return;

    const MAX_POLL_MS = 10 * 60 * 1000; // 10 minutes hard stop
    const startedAt = Date.now();
    let consecutiveErrors = 0;

    const id = setInterval(async () => {
      if (Date.now() - startedAt > MAX_POLL_MS) {
        clearInterval(id);
        stopRechecking("Recheck timed out. It may still be running in the background -- check the server logs.");
        return;
      }

      try {
        const state = await jsonFetch<{
          status: string;
          rechecked?: number;
          auto_resolved?: number;
          ignored_by_rule?: number;
          resolved_direct?: number;
          resolved_llm?: number;
          writeback_llm_success?: number;
          writeback_llm_failed?: number;
        }>("/api/training/coding-review/recheck/status");

        consecutiveErrors = 0;

        if (state.status === "done") {
          clearInterval(id);
          setRechecking(false);
          setRecheckMode(null);
          setLastChecked(new Date());
          setRecheckResult({
            rechecked: state.rechecked ?? 0,
            auto_resolved: state.auto_resolved ?? 0,
            ignored_by_rule: state.ignored_by_rule ?? 0,
            resolved_direct: state.resolved_direct ?? 0,
            resolved_llm: state.resolved_llm ?? 0,
            writeback_llm_success: state.writeback_llm_success ?? 0,
            writeback_llm_failed: state.writeback_llm_failed ?? 0,
          });
          setPage(1);
          fetchQueue();
        } else if (state.status === "failed" || state.status === "idle") {
          clearInterval(id);
          stopRechecking(
            state.status === "idle"
              ? "Recheck stopped unexpectedly (server may have restarted). Check the server logs."
              : "Recheck failed. Check the server logs for details."
          );
        }
      } catch {
        consecutiveErrors += 1;
        if (consecutiveErrors >= 5) {
          clearInterval(id);
          stopRechecking("Lost contact with the server after 5 attempts. The recheck may still be running.");
        }
      }
    }, 2000);
    return () => clearInterval(id);
  }, [rechecking, fetchQueue, stopRechecking]);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const handleSelectTermSearchResult = (reviewId: string, result: TermSearchResult) => {
    setManualConceptId((prev) => ({ ...prev, [reviewId]: result.snomed_concept_id }));
    setManualTerm((prev) => ({ ...prev, [reviewId]: result.term }));
    setSearchReviewId(null);
  };

  const getSpanText = (item: CodingReviewItem): string =>
    (manualSpanText[item.review_id] ?? item.entity_text ?? "").trim();

  const handleResolve = async (item: CodingReviewItem) => {
    const conceptId = manualConceptId[item.review_id] || item.snomed_concept_id || "";
    const term = manualTerm[item.review_id] || item.snomed_term || "";
    const resolvedSpanText = getSpanText(item);
    if (!conceptId || !term) {
      setError("Select or enter a SNOMED concept before resolving");
      return;
    }
    if (!resolvedSpanText) {
      setError("Entity span cannot be empty");
      return;
    }
    setResolvingId(item.review_id);
    try {
      await jsonFetch(`/api/training/coding-review/${item.review_id}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          resolved_concept_id: conceptId,
          resolved_term: term,
          resolved_entity_text: resolvedSpanText,
          reviewer: "operations_ui",
        }),
      });
      setItems((prev) => prev.filter((i) => i.review_id !== item.review_id));
      setStats((s) => ({
        ...s,
        pending: Math.max(0, s.pending - 1),
        resolved: s.resolved + 1,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to resolve coding review");
    } finally {
      setResolvingId(null);
    }
  };

  const handleCreateIgnoreRule = async (item: CodingReviewItem) => {
    const spanText = getSpanText(item);
    if (!spanText) {
      setError("Entity text cannot be empty to create an ignore rule");
      return;
    }

    const contextPhrase = (contextContains[item.review_id] ?? "").trim();
    const escaped = contextPhrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const contextRegex = contextPhrase ? `(?i)${escaped}` : null;

    setCreatingRuleId(item.review_id);
    try {
      await jsonFetch("/api/training/post-processor-rules", {
        method: "POST",
        body: JSON.stringify({
          action: "suppress",
          match_text: spanText,
          match_label: item.entity_label,
          context_regex: contextRegex,
          priority: 50,
          notes: `Created from coding review ${item.review_id}`,
          created_by: "operations_ui",
          active: true,
        }),
      });
      await jsonFetch(`/api/training/coding-review/${item.review_id}/ignore`, {
        method: "POST",
        body: JSON.stringify({ reviewer: "operations_ui" }),
      });
      // Hide the current queue item immediately after rule creation so users
      // can continue working without manually refreshing.
      setItems((prev) => prev.filter((i) => i.review_id !== item.review_id));
      setStats((s) => ({
        ...s,
        pending: Math.max(0, s.pending - 1),
        uncoded: item.coded ? s.uncoded : Math.max(0, s.uncoded - 1),
        low_confidence: item.coded ? Math.max(0, s.low_confidence - 1) : s.low_confidence,
      }));
      setSuccess("Ignore rule created. Re-run label verification to apply it to new items.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create ignore rule");
    } finally {
      setCreatingRuleId(null);
    }
  };

  const summaryChips = useMemo(
    () => [
      { label: `Total: ${stats.total}`, color: "default" as const },
      { label: `Uncoded: ${stats.uncoded}`, color: stats.uncoded > 0 ? "error" as const : "default" as const },
      { label: `Low confidence: ${stats.low_confidence}`, color: stats.low_confidence > 0 ? "warning" as const : "default" as const },
      { label: `Resolved: ${stats.resolved}`, color: "success" as const },
      { label: `Pending: ${stats.pending}`, color: stats.pending > 0 ? "warning" as const : "default" as const },
    ],
    [stats]
  );

  return (
    <Box sx={{ maxWidth: 960, mx: "auto", py: 3, px: 3 }}>
      <Typography variant="h5" sx={{ mb: 1 }}>Coding Review</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Review entities where terminology resolution failed or returned low-confidence SNOMED matches.
      </Typography>

      {/* How this works */}
      <Accordion variant="outlined" disableGutters sx={{ mb: 3 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            How this tab works
          </Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0 }}>
          <TabFlowDiagram
            stages={CODING_STAGES}
            color="#3B5FD9"
            lightColor="#DBEAFE"
            trackLabel="Coding Review"
          />
        </AccordionDetails>
      </Accordion>

      <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center" sx={{ mb: 2 }}>
        {summaryChips.map((chip) => (
          <Chip key={chip.label} label={chip.label} color={chip.color} size="small" />
        ))}
        <ButtonGroup
          size="small"
          variant="contained"
          ref={recheckAnchorRef}
          disabled={loading}
        >
          <Button
            startIcon={rechecking ? <CircularProgress size={14} color="inherit" /> : <RefreshIcon />}
            onClick={() => rechecking ? stopRechecking() : recheckList(false)}
            sx={{ minWidth: 110 }}
          >
            {rechecking
              ? recheckMode === "llm" ? "LLM running..." : "Running..."
              : "Recheck"}
          </Button>
          <Button
            sx={{ px: 0.5 }}
            onClick={() => setRecheckMenuOpen((o) => !o)}
            disabled={rechecking}
          >
            <ArrowDropDownIcon fontSize="small" />
          </Button>
        </ButtonGroup>
        <Menu
          open={recheckMenuOpen}
          anchorEl={recheckAnchorRef.current}
          onClose={() => setRecheckMenuOpen(false)}
          anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
          transformOrigin={{ vertical: "top", horizontal: "right" }}
        >
          <MenuItem
            dense
            onClick={() => { setRecheckMenuOpen(false); recheckList(false); }}
          >
            Quick recheck
          </MenuItem>
          <MenuItem
            dense
            onClick={() => { setRecheckMenuOpen(false); recheckList(true); }}
          >
            LLM-assisted recheck
          </MenuItem>
          <Divider />
          <Box sx={{ px: 2, py: 1 }}>
            <TextField
              label="LLM item limit"
              helperText="0 = process all"
              type="number"
              size="small"
              value={llmLimit}
              onChange={(e) => setLlmLimit(Math.max(0, parseInt(e.target.value, 10) || 0))}
              inputProps={{ min: 0, step: 50 }}
              sx={{ width: 140 }}
              onClick={(e) => e.stopPropagation()}
            />
          </Box>
        </Menu>
        {lastChecked && (
          <Typography variant="caption" color="text.secondary">
            Last checked {lastChecked.toLocaleTimeString()}
          </Typography>
        )}
      </Stack>

      {recheckResult && (
        <Alert
          severity={recheckResult.auto_resolved > 0 ? "success" : "info"}
          onClose={() => setRecheckResult(null)}
          sx={{ mb: 2 }}
        >
          {(() => {
            const {
              rechecked,
              auto_resolved,
              ignored_by_rule = 0,
              resolved_direct = 0,
              resolved_llm = 0,
              writeback_llm_success = 0,
              writeback_llm_failed = 0,
            } = recheckResult;
            const stillPending = rechecked - auto_resolved;
            if (auto_resolved === 0 && ignored_by_rule === 0) {
              return `Checked ${rechecked} item${rechecked !== 1 ? "s" : ""}. None resolved automatically - the list is up to date.`;
            }
            const parts: string[] = [];
            if (auto_resolved > 0) parts.push(`${auto_resolved} coded automatically`);
            if (ignored_by_rule > 0) parts.push(`${ignored_by_rule} suppressed by ignore rule`);
            if (resolved_direct > 0) parts.push(`${resolved_direct} direct`);
            if (resolved_llm > 0) {
              parts.push(`${resolved_llm} via LLM`);
              if (writeback_llm_success > 0) {
                parts.push(`${writeback_llm_success} LLM writebacks`);
              }
              if (writeback_llm_failed > 0) {
                parts.push(`${writeback_llm_failed} writebacks failed`);
              }
            }
            return `${parts.join(", ")}. ${stillPending} still need review.`;
          })()}
        </Alert>
      )}

      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" onClose={() => setSuccess(null)} sx={{ mb: 2 }}>
          {success}
        </Alert>
      )}

      {loading && (
        <Paper variant="outlined" sx={{ p: 3, textAlign: "center", mb: 2 }}>
          <CircularProgress size={20} />
        </Paper>
      )}

      <Stack spacing={2}>
        {items.map((item) => {
          const selectedConcept = manualConceptId[item.review_id] || "";
          const selectedTerm = manualTerm[item.review_id] || "";
          const selectedSpanText = manualSpanText[item.review_id] ?? item.entity_text;

          return (
            <Paper key={item.review_id} variant="outlined" sx={{ p: 2 }}>
              <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 1 }}>
                <Chip label={item.source} size="small" />
                <Chip
                  label={item.coded ? "Low confidence" : "Uncoded"}
                  color={item.coded ? "warning" : "error"}
                  size="small"
                />
                <Chip label={item.entity_label} size="small" variant="outlined" />
              </Stack>

              <Typography
                variant="body2"
                sx={{ mb: 1, fontFamily: "monospace", bgcolor: "grey.50", p: 1, borderRadius: 1 }}
              >
                {item.encounter_text}
              </Typography>

              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="subtitle2">Entity:</Typography>
                <Chip label={selectedSpanText} color="primary" size="small" />
                {item.snomed_concept_id && (
                  <Typography variant="caption" color="text.secondary">
                    Best match: {item.snomed_term} ({item.snomed_concept_id}) score={item.score?.toFixed(2)}
                  </Typography>
                )}
              </Stack>

              <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                <TextField
                  size="small"
                  label="Entity span"
                  value={selectedSpanText}
                  onChange={(e) =>
                    setManualSpanText((prev) => ({ ...prev, [item.review_id]: e.target.value }))
                  }
                  helperText="Edit to increase or trim the extracted span"
                  sx={{ minWidth: 320, flex: 1 }}
                />
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => setSearchReviewId(item.review_id)}
                >
                  Search terminology
                </Button>
              </Stack>

              <Stack
                direction={{ xs: "column", md: "row" }}
                spacing={1}
                alignItems={{ xs: "stretch", md: "center" }}
                sx={{ mb: 1 }}
              >
                <TextField
                  size="small"
                  label="Context contains (optional)"
                  value={contextContains[item.review_id] ?? ""}
                  onChange={(e) =>
                    setContextContains((prev) => ({ ...prev, [item.review_id]: e.target.value }))
                  }
                  helperText='Example: "await chest xray"'
                  sx={{ minWidth: 260, flex: 1 }}
                />
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  onClick={() => handleCreateIgnoreRule(item)}
                  disabled={creatingRuleId === item.review_id}
                >
                  {creatingRuleId === item.review_id ? "Creating rule..." : "Create ignore rule"}
                </Button>
              </Stack>

              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <TextField
                  size="small"
                  label="SNOMED Concept ID"
                  value={selectedConcept}
                  onChange={(e) => setManualConceptId((prev) => ({ ...prev, [item.review_id]: e.target.value }))}
                  sx={{ width: 200 }}
                />
                <TextField
                  size="small"
                  label="SNOMED Term"
                  value={selectedTerm}
                  onChange={(e) => setManualTerm((prev) => ({ ...prev, [item.review_id]: e.target.value }))}
                  sx={{ width: 300 }}
                />
                <Button
                  variant="contained"
                  size="small"
                  onClick={() => handleResolve(item)}
                  disabled={resolvingId === item.review_id || (!selectedConcept && !item.snomed_concept_id)}
                >
                  {resolvingId === item.review_id ? "Resolving..." : "Resolve"}
                </Button>
              </Stack>
            </Paper>
          );
        })}
      </Stack>

      {!loading && items.length === 0 && (
        <Paper variant="outlined" sx={{ p: 3, textAlign: "center" }}>
          <Typography color="text.secondary">
            No coding reviews pending. Run label verification to generate coding reviews.
          </Typography>
        </Paper>
      )}

      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
        <Button size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          Prev
        </Button>
        <Typography variant="body2">
          Page {page} / {totalPages}
        </Typography>
        <Button size="small" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
          Next
        </Button>
      </Stack>

      {searchReviewId && (
        <TermSearch
          initialQuery={
            (() => {
              const active = items.find((i) => i.review_id === searchReviewId);
              return active ? getSpanText(active) : "";
            })()
          }
          hintTags={
            (() => {
              const active = items.find((i) => i.review_id === searchReviewId);
              return active?.semantic_tag ? [active.semantic_tag] : undefined;
            })()
          }
          onSelect={(result) => handleSelectTermSearchResult(searchReviewId, result)}
          onClose={() => setSearchReviewId(null)}
          onCorrection={() => undefined}
        />
      )}
    </Box>
  );
}
