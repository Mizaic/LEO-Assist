/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
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
 *
 * Phase 6b: when the caller supplies ``onPickObservation`` and the hit's
 * semantic tag looks like an observable (for example "observable entity",
 * "measurement", "laboratory test") a secondary "Compare value..." action
 * appears that creates an OBSERVATION leaf seeded with the observable's
 * id / term / canonical unit instead of a plain CONCEPT leaf. Reviewers
 * can still pick "Use this" for the same concept to insert it as a
 * CONCEPT (for presence checks like "has hypertension").
 */

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { SEARCH_PANEL, friendlyTerm } from "./copy";
import type {
  ConceptSearchHit,
  EditableObservationPayload,
  LogicCriterion,
} from "./types";

/**
 * Seed passed to ``onPickObservation`` when the reviewer picks the
 * "Compare value..." affordance on an observable hit. Mirrors the
 * subset of ``EditableObservationPayload`` we can populate from the
 * SNOMED hit alone: the threshold + operator still require reviewer
 * input.
 */
export type ObservationSeed = Pick<
  EditableObservationPayload,
  "observable_id" | "observable_term" | "unit"
>;

interface Props {
  /** Controls header copy + button label. */
  mode: "replace" | "add" | "replace_action" | "idle";
  /** Friendly description of the focused node, for context. */
  focusLabel: string | null;
  /** Suggested initial query (e.g. the term currently on the focused chip). */
  initialQuery: string;
  onPick: (criterion: LogicCriterion) => void;
  /**
   * Phase 6b: optional handler for the "Compare value..." action on an
   * observable hit. When omitted, the affordance is hidden and the
   * panel keeps the Phase 1 single-button behaviour.
   */
  onPickObservation?: (seed: ObservationSeed) => void;
  /**
   * When true, the search is restricted to SNOMED observable_entity
   * concepts (lab values). Pass when replacing an OBSERVATION leaf so
   * the user only sees measurable quantities, not disorders or procedures.
   */
  filterToObservable?: boolean;
}

/**
 * Heuristic: does this SNOMED hit look like an observable / measurement
 * that can carry a numeric threshold? Based on the SNOMED top-level
 * semantic tags the terminology search can return today. We keep the
 * match permissive -- false positives only cost the reviewer an extra
 * read of the button; false negatives hide a useful affordance.
 *
 * Known observable-ish tags (SNOMED CT US/UK editions):
 *
 *   - "observable entity"     -- e.g. "Platelet count"
 *   - "measurement"           -- e.g. "Haemoglobin A1c measurement"
 *   - "procedure"             -- covers "Blood pressure measurement"
 *   - "laboratory test"       -- covers "Serum creatinine test"
 *   - "qualifier value"       -- rarely but includes some unit qualifiers
 *
 * Anything else (finding, disorder, substance, physical object, ...)
 * is treated as a plain concept.
 */
export function isLikelyObservable(hit: ConceptSearchHit): boolean {
  const tag = (hit.semantic_tag ?? "").toLowerCase().trim();
  if (!tag) return false;
  return (
    tag.includes("observable") ||
    tag.includes("measurement") ||
    tag.includes("laboratory") ||
    // Blood pressure lives under "procedure" in SNOMED CT.
    (tag === "procedure" && /\b(pressure|rate|level|count|ratio)\b/i.test(hit.term))
  );
}

const SEARCH_DEBOUNCE_MS = 250;

export default function ConceptSearchPanel({
  mode,
  focusLabel,
  initialQuery,
  onPick,
  onPickObservation,
  filterToObservable = false,
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
      const tag = filterToObservable ? "&semantic_tag=observable_entity" : "";
      const url = `/api/terminology/search?q=${encodeURIComponent(trimmed)}&limit=15${tag}`;
      fetch(url)
        .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
        .then((rows: ConceptSearchHit[]) => {
          setHits(Array.isArray(rows) ? rows : []);
        })
        .catch(() => setError(SEARCH_PANEL.loadError))
        .finally(() => setLoading(false));
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [query, filterToObservable]);

  const heading =
    mode === "replace_action"
      ? SEARCH_PANEL.headings.replace_action
      : mode === "replace"
        ? SEARCH_PANEL.headings.replace
        : mode === "add"
          ? SEARCH_PANEL.headings.add
          : SEARCH_PANEL.headings.idle;

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
        label={SEARCH_PANEL.searchLabel}
        placeholder={SEARCH_PANEL.searchPlaceholder}
        autoFocus
        inputProps={{ "aria-label": SEARCH_PANEL.searchAriaLabel }}
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
        aria-label={SEARCH_PANEL.resultsAriaLabel}
      >
        {loading && (
          <Stack alignItems="center" sx={{ py: 3 }}>
            <CircularProgress
              size={20}
              aria-label={SEARCH_PANEL.searchingAriaLabel}
            />
          </Stack>
        )}
        {!loading && mode !== "idle" && hits.length === 0 && query.trim().length >= 2 && !error && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 1.5 }}>
            {SEARCH_PANEL.noResults(query.trim())}
          </Typography>
        )}
        {!loading && mode === "idle" && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 1.5 }}>
            {SEARCH_PANEL.idleHintLead} {SEARCH_PANEL.idleHintMid}{" "}
            <strong>{SEARCH_PANEL.idleHintStrong}</strong>{" "}
            {SEARCH_PANEL.idleHintTail}
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
              onPickObservation={
                onPickObservation && isLikelyObservable(hit)
                  ? () =>
                      onPickObservation({
                        observable_id: hit.snomed_concept_id,
                        observable_term: hit.term,
                        // Unit is left blank: the reviewer fills it
                        // in. When the BE canonical-unit registry
                        // knows this observable, the sandbox replay
                        // will canonicalise it; when it does not, the
                        // rule is a plain CONCEPT-style presence check
                        // and the reviewer will see no impact in the
                        // sandbox until they fix the threshold.
                        unit: "",
                      })
                  : undefined
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
  onPickObservation,
}: {
  hit: ConceptSearchHit;
  onPick: () => void;
  /**
   * When set, a secondary "Compare value..." button is rendered. Only
   * passed by the parent when the hit looks like an observable AND the
   * host provided an ``onPickObservation`` handler.
   */
  onPickObservation?: () => void;
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
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Button
          size="small"
          variant="outlined"
          onClick={onPick}
          aria-label={`Use ${friendly}`}
        >
          Use this
        </Button>
        {onPickObservation && (
          <Tooltip
            title={`Compare a patient's ${friendly.toLowerCase()} reading against a number`}
            arrow
          >
            <Button
              size="small"
              variant="contained"
              color="primary"
              onClick={onPickObservation}
              aria-label={`Compare value of ${friendly}`}
              sx={{ whiteSpace: "nowrap" }}
            >
              Compare value...
            </Button>
          </Tooltip>
        )}
      </Stack>
    </Stack>
  );
}
