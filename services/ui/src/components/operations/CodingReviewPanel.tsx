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
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import TabFlowDiagram, { type TabStage } from "@/components/operations/TabFlowDiagram";

const jsonFetch = async <T,>(url: string, init?: RequestInit): Promise<T> => {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
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

interface TermCandidate {
  snomed_concept_id: string;
  snomed_term: string;
  score: number;
  semantic_tag: string;
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
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  const [lookupResults, setLookupResults] = useState<Record<string, TermCandidate[]>>({});
  const [lookupLoading, setLookupLoading] = useState<Record<string, boolean>>({});
  const [manualConceptId, setManualConceptId] = useState<Record<string, string>>({});
  const [manualTerm, setManualTerm] = useState<Record<string, string>>({});

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    try {
      const data = await jsonFetch<QueueResponse>(
        `/api/training/coding-review/queue?page=${page}&page_size=${pageSize}`
      );
      setItems(data.items);
      setStats(data.stats);
      setTotalPages(data.total_pages);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load coding review queue");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const handleLookup = async (item: CodingReviewItem) => {
    setLookupLoading((prev) => ({ ...prev, [item.review_id]: true }));
    try {
      const data = await jsonFetch<{ results: Record<string, TermCandidate[]> }>(
        "/api/terminology/resolve",
        { method: "POST", body: JSON.stringify({ terms: [item.entity_text] }) }
      );
      const candidates = data.results?.[item.entity_text] ?? [];
      setLookupResults((prev) => ({ ...prev, [item.review_id]: candidates }));
    } catch {
      setLookupResults((prev) => ({ ...prev, [item.review_id]: [] }));
    } finally {
      setLookupLoading((prev) => ({ ...prev, [item.review_id]: false }));
    }
  };

  const handleSelectCandidate = (reviewId: string, candidate: TermCandidate) => {
    setManualConceptId((prev) => ({ ...prev, [reviewId]: candidate.snomed_concept_id }));
    setManualTerm((prev) => ({ ...prev, [reviewId]: candidate.snomed_term }));
  };

  const handleResolve = async (item: CodingReviewItem) => {
    const conceptId = manualConceptId[item.review_id] || item.snomed_concept_id || "";
    const term = manualTerm[item.review_id] || item.snomed_term || "";
    if (!conceptId || !term) {
      setError("Select or enter a SNOMED concept before resolving");
      return;
    }
    setResolvingId(item.review_id);
    try {
      await jsonFetch(`/api/training/coding-review/${item.review_id}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          resolved_concept_id: conceptId,
          resolved_term: term,
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

      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 2 }}>
        {summaryChips.map((chip) => (
          <Chip key={chip.label} label={chip.label} color={chip.color} size="small" />
        ))}
        <Button size="small" variant="outlined" onClick={fetchQueue}>
          Refresh
        </Button>
      </Stack>

      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {loading && (
        <Paper variant="outlined" sx={{ p: 3, textAlign: "center", mb: 2 }}>
          <CircularProgress size={20} />
        </Paper>
      )}

      <Stack spacing={2}>
        {items.map((item) => {
          const candidates = lookupResults[item.review_id] ?? [];
          const isLookingUp = lookupLoading[item.review_id] ?? false;
          const selectedConcept = manualConceptId[item.review_id] || "";
          const selectedTerm = manualTerm[item.review_id] || "";

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
                <Chip label={item.entity_text} color="primary" size="small" />
                {item.snomed_concept_id && (
                  <Typography variant="caption" color="text.secondary">
                    Best match: {item.snomed_term} ({item.snomed_concept_id}) score={item.score?.toFixed(2)}
                  </Typography>
                )}
              </Stack>

              <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => handleLookup(item)}
                  disabled={isLookingUp}
                >
                  {isLookingUp ? "Searching..." : "Search terminology"}
                </Button>
              </Stack>

              {candidates.length > 0 && (
                <Stack spacing={0.5} sx={{ mb: 1, pl: 1 }}>
                  {candidates.slice(0, 5).map((c) => (
                    <Stack
                      key={c.snomed_concept_id}
                      direction="row"
                      spacing={1}
                      alignItems="center"
                      sx={{
                        cursor: "pointer",
                        p: 0.5,
                        borderRadius: 1,
                        bgcolor: selectedConcept === c.snomed_concept_id ? "primary.50" : "transparent",
                        "&:hover": { bgcolor: "grey.100" },
                      }}
                      onClick={() => handleSelectCandidate(item.review_id, c)}
                    >
                      <Typography variant="body2" sx={{ fontWeight: selectedConcept === c.snomed_concept_id ? 700 : 400 }}>
                        {c.snomed_term}
                      </Typography>
                      <Chip label={c.snomed_concept_id} size="small" variant="outlined" />
                      <Chip label={c.semantic_tag} size="small" />
                      <Typography variant="caption" color="text.secondary">
                        score={c.score.toFixed(2)}
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              )}

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
    </Box>
  );
}
