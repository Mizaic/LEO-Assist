"use client";

/**
 * Right-column SNOMED concept search.
 *
 * Used in two modes:
 *   - "replace": clicking a result swaps the concept on the focused CONCEPT node.
 *   - "add":     clicking a result inserts a new CONCEPT child under the focused group.
 *
 * Hits come from /api/terminology/search and are debounced ~250 ms so we do
 * not hammer the terminology service while the user is still typing.
 */

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { friendlyTerm } from "./copy";
import type { ConceptSearchHit, LogicCriterion } from "./types";

interface Props {
  /** Controls header copy + button label. */
  mode: "replace" | "add" | "replace_action" | "idle";
  /** Friendly description of the focused node, for context. */
  focusLabel: string | null;
  /** Suggested initial query (e.g. the term currently on the focused chip). */
  initialQuery: string;
  onPick: (criterion: LogicCriterion) => void;
}

const SEARCH_DEBOUNCE_MS = 250;

export default function ConceptSearchPanel({
  mode,
  focusLabel,
  initialQuery,
  onPick,
}: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [hits, setHits] = useState<ConceptSearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setHits([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    const handle = window.setTimeout(() => {
      const url = `/api/terminology/search?q=${encodeURIComponent(trimmed)}&limit=15`;
      fetch(url)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
        .then((rows: ConceptSearchHit[]) => {
          setHits(Array.isArray(rows) ? rows : []);
        })
        .catch(() => setError("Could not search the clinical terms. Please try again."))
        .finally(() => setLoading(false));
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [query]);

  const heading =
    mode === "replace_action"
      ? "Swap the recommended procedure"
      : mode === "replace"
        ? "Swap a symptom or sign"
        : mode === "add"
          ? "Add a symptom or sign"
          : "Find a symptom or sign";

  return (
    <Stack spacing={1.5} sx={{ height: "100%" }}>
      <Box>
        <Typography variant="subtitle2" sx={{ mb: 0.25, fontWeight: 700 }}>
          {heading}
        </Typography>
        {focusLabel && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            {focusLabel}
          </Typography>
        )}
      </Box>
      <TextField
        size="small"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        label="Search clinical terms"
        placeholder="Type a word, like cough or weight loss"
        autoFocus
        inputProps={{ "aria-label": "Search clinical terms" }}
        disabled={mode === "idle"}
      />
      {error && (
        <Alert severity="warning" sx={{ py: 0.5 }}>
          {error}
        </Alert>
      )}
      <Box
        sx={{
          flex: 1,
          minHeight: 200,
          maxHeight: 480,
          overflowY: "auto",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          p: 0.5,
        }}
        aria-label="Search results"
      >
        {loading && (
          <Stack alignItems="center" sx={{ py: 3 }}>
            <CircularProgress size={20} aria-label="Searching clinical terms" />
          </Stack>
        )}
        {!loading && mode !== "idle" && hits.length === 0 && query.trim().length >= 2 && !error && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 1.5 }}>
            No clinical terms match &ldquo;{query.trim()}&rdquo;. Try a shorter
            word or a different spelling.
          </Typography>
        )}
        {!loading && mode === "idle" && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 1.5 }}>
            Click a green pill on the left to swap that symptom for a different
            one, or use one of the <strong>+ Add a symptom</strong> buttons
            inside a group.
          </Typography>
        )}
        {!loading &&
          hits.map((hit) => (
            <SearchHitRow
              key={hit.snomed_concept_id}
              hit={hit}
              onPick={() =>
                onPick({
                  snomed_concept_id: hit.snomed_concept_id,
                  preferred_term: hit.term,
                  semantic_tag: hit.semantic_tag,
                  term: hit.term,
                })
              }
            />
          ))}
      </Box>
    </Stack>
  );
}

function SearchHitRow({
  hit,
  onPick,
}: {
  hit: ConceptSearchHit;
  onPick: () => void;
}) {
  const friendly = friendlyTerm(hit.term);
  return (
    <Stack
      direction="row"
      alignItems="center"
      spacing={1}
      sx={{
        px: 1,
        py: 0.75,
        borderRadius: 1,
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 500, lineHeight: 1.2 }}>
          {friendly}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Clinical code {hit.snomed_concept_id}
          {hit.semantic_tag ? ` - ${hit.semantic_tag}` : ""}
        </Typography>
      </Box>
      <Button
        size="small"
        variant="outlined"
        onClick={onPick}
        aria-label={`Use ${friendly}`}
      >
        Use this
      </Button>
    </Stack>
  );
}
