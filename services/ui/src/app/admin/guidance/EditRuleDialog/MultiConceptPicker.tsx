/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-C21AE387 / DI-42246DA7
 *   DO: DO-AA74E9A6 / DO-F8C56339
 *   VT: VT-5632FA0D
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-C21AE387")
 */
"use client";

/**
 * "Highlight a word, assign one or more SNOMED codes" picker.
 *
 * Sibling to ConceptSearchPanel, for the one situation that panel does not
 * cover: picking more than one code for the same highlighted phrase in a
 * single confirm (e.g. a rule that lists several near-synonymous findings
 * for one row), with each pick's descendant-matching depth asked
 * explicitly instead of silently defaulting -- see multiConceptSeed.ts.
 *
 * Observable hits also expose operator / value / unit. With one measurable
 * code selected and a value filled, confirm creates an OBSERVATION leaf
 * via onConfirmObservation; otherwise confirm stays CONCEPT via onConfirm.
 */
import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import type { ObservationSeed } from "./ConceptSearchPanel";
import { MULTI_CONCEPT_PICKER, friendlyTerm } from "./copy";
import DepthInclusionTooltip from "./DepthInclusionTooltip";
import MultiConceptObsFields from "./MultiConceptObsFields";
import {
  DEFAULT_CONCEPT_DEPTH,
  buildMultiSeedCriterion,
  emptyThresholdForHit,
  isConflictingObsMultiPick,
  observationSeedFromPick,
  seedFromHit,
  type ObservableThresholdDraft,
} from "./multiConceptSeed";
import { isLikelyObservable } from "./observableHit";
import type { ConceptSearchHit, LogicCriterion } from "./types";

const SEARCH_DEBOUNCE_MS = 250;

interface Props {
  /** Suggested initial query -- typically the highlighted phrase. */
  initialQuery: string;
  onConfirm: (criterion: LogicCriterion) => void;
  /**
   * When the reviewer sets a numeric threshold on a single observable
   * hit, confirm calls this instead of onConfirm.
   */
  onConfirmObservation?: (seed: ObservationSeed) => void;
  /** When true, the results list fills remaining popover height. */
  embedded?: boolean;
}

export default function MultiConceptPicker({
  initialQuery,
  onConfirm,
  onConfirmObservation,
  embedded = false,
}: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [hits, setHits] = useState<ConceptSearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [depthByConceptId, setDepthByConceptId] = useState<
    Map<string, number>
  >(new Map());
  const [thresholdByConceptId, setThresholdByConceptId] = useState<
    Map<string, ObservableThresholdDraft>
  >(new Map());

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
        .then((rows: ConceptSearchHit[]) => setHits(Array.isArray(rows) ? rows : []))
        .catch(() => setError(MULTI_CONCEPT_PICKER.loadError))
        .finally(() => setLoading(false));
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [query]);

  const selectedIds = [...depthByConceptId.keys()];
  const selectedHits = hits.filter((h) =>
    depthByConceptId.has(h.snomed_concept_id),
  );
  const selectedDrafts = selectedHits.map(
    (h) =>
      thresholdByConceptId.get(h.snomed_concept_id) ??
      emptyThresholdForHit(h, initialQuery),
  );
  const multiConflict = isConflictingObsMultiPick(
    selectedHits.length,
    selectedDrafts,
  );
  const singleObsSeed =
    selectedHits.length === 1 && onConfirmObservation
      ? observationSeedFromPick(
          selectedHits[0],
          thresholdByConceptId.get(selectedHits[0].snomed_concept_id) ??
            emptyThresholdForHit(selectedHits[0], initialQuery),
        )
      : null;

  function toggle(hit: ConceptSearchHit) {
    setDepthByConceptId((prev) => {
      const next = new Map(prev);
      if (next.has(hit.snomed_concept_id)) {
        next.delete(hit.snomed_concept_id);
      } else {
        next.set(hit.snomed_concept_id, DEFAULT_CONCEPT_DEPTH);
      }
      return next;
    });
    setThresholdByConceptId((prev) => {
      const next = new Map(prev);
      if (next.has(hit.snomed_concept_id)) {
        next.delete(hit.snomed_concept_id);
      } else if (isLikelyObservable(hit)) {
        next.set(hit.snomed_concept_id, emptyThresholdForHit(hit, initialQuery));
      }
      return next;
    });
  }

  function setDepth(conceptId: string, depth: number) {
    setDepthByConceptId((prev) => new Map(prev).set(conceptId, depth));
  }

  function setThreshold(conceptId: string, draft: ObservableThresholdDraft) {
    setThresholdByConceptId((prev) => new Map(prev).set(conceptId, draft));
  }

  function handleConfirm() {
    if (selectedHits.length === 0 || multiConflict) return;
    if (singleObsSeed && onConfirmObservation) {
      onConfirmObservation(singleObsSeed);
      return;
    }
    const seeds = selectedHits.map((h) =>
      seedFromHit(
        h,
        depthByConceptId.get(h.snomed_concept_id) ?? DEFAULT_CONCEPT_DEPTH,
      ),
    );
    onConfirm(buildMultiSeedCriterion(seeds));
  }

  const confirmDisabled = selectedIds.length === 0 || multiConflict;
  const confirmLabel = singleObsSeed
    ? MULTI_CONCEPT_PICKER.confirmObservationLabel
    : MULTI_CONCEPT_PICKER.confirmLabel(selectedIds.length);

  return (
    <Stack
      spacing={1.5}
      sx={{ height: "100%", ...(embedded ? { flex: 1, minHeight: 0 } : {}) }}
    >
      <TextField
        size="small"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        label={MULTI_CONCEPT_PICKER.searchLabel}
        placeholder={MULTI_CONCEPT_PICKER.searchPlaceholder}
        autoFocus
        inputProps={{ "aria-label": MULTI_CONCEPT_PICKER.searchLabel }}
      />
      <Typography variant="caption" color="text.secondary">
        {MULTI_CONCEPT_PICKER.emptyHint}
      </Typography>
      {error && (
        <Alert severity="warning" sx={{ py: 0.5 }}>
          {error}
        </Alert>
      )}
      {multiConflict && (
        <Alert severity="info" sx={{ py: 0.5 }}>
          {MULTI_CONCEPT_PICKER.obsMultiConflict}
        </Alert>
      )}
      <Box
        sx={{
          flex: 1,
          minHeight: embedded ? 0 : 200,
          maxHeight: embedded ? 320 : 480,
          overflowY: "auto",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          p: 0.5,
        }}
        aria-label={MULTI_CONCEPT_PICKER.resultsAriaLabel}
      >
        {loading && (
          <Stack alignItems="center" sx={{ py: 3 }}>
            <CircularProgress size={20} aria-label="Searching clinical terms" />
          </Stack>
        )}
        {!loading && hits.length === 0 && query.trim().length >= 2 && !error && (
          <Typography variant="body2" color="text.secondary" sx={{ p: 1.5 }}>
            {MULTI_CONCEPT_PICKER.noResults(query.trim())}
          </Typography>
        )}
        {!loading &&
          hits.map((hit) => (
            <MultiConceptHitRow
              key={hit.snomed_concept_id}
              hit={hit}
              checked={depthByConceptId.has(hit.snomed_concept_id)}
              depth={
                depthByConceptId.get(hit.snomed_concept_id) ??
                DEFAULT_CONCEPT_DEPTH
              }
              threshold={thresholdByConceptId.get(hit.snomed_concept_id)}
              onToggle={() => toggle(hit)}
              onDepthChange={(d) => setDepth(hit.snomed_concept_id, d)}
              onThresholdChange={(draft) =>
                setThreshold(hit.snomed_concept_id, draft)
              }
            />
          ))}
      </Box>
      <Button
        variant="contained"
        disabled={confirmDisabled}
        onClick={handleConfirm}
      >
        {confirmLabel}
      </Button>
    </Stack>
  );
}

function MultiConceptHitRow({
  hit,
  checked,
  depth,
  threshold,
  onToggle,
  onDepthChange,
  onThresholdChange,
}: {
  hit: ConceptSearchHit;
  checked: boolean;
  depth: number;
  threshold?: ObservableThresholdDraft;
  onToggle: () => void;
  onDepthChange: (depth: number) => void;
  onThresholdChange: (draft: ObservableThresholdDraft) => void;
}) {
  const friendly = friendlyTerm(hit.term);
  const showObs = checked && isLikelyObservable(hit) && threshold;
  return (
    <Stack
      spacing={0.5}
      sx={{
        px: 1,
        py: 0.75,
        borderRadius: 1,
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      <Stack direction="row" alignItems="center" spacing={1}>
        <Checkbox
          size="small"
          checked={checked}
          onChange={onToggle}
          inputProps={{
            "aria-label": MULTI_CONCEPT_PICKER.selectAriaLabel(friendly),
          }}
        />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="body2" sx={{ fontWeight: 500, lineHeight: 1.2 }}>
            {friendly}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Clinical code {hit.snomed_concept_id}
            {hit.semantic_tag ? ` - ${hit.semantic_tag}` : ""}
          </Typography>
        </Box>
      </Stack>
      {checked && (
        <Box sx={{ pl: 4.5 }}>
          <DepthInclusionTooltip
            conceptId={hit.snomed_concept_id}
            term={hit.term}
            depth={depth}
          >
            <TextField
              size="small"
              type="number"
              value={depth}
              onChange={(e) => {
                const n = Number(e.target.value);
                onDepthChange(
                  Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0,
                );
              }}
              label="Depth"
              inputProps={{
                min: 0,
                max: 12,
                "aria-label": MULTI_CONCEPT_PICKER.depthAriaLabel(friendly),
                style: { width: 64 },
              }}
            />
          </DepthInclusionTooltip>
          {showObs && (
            <MultiConceptObsFields
              term={friendly}
              draft={threshold}
              onChange={onThresholdChange}
            />
          )}
        </Box>
      )}
    </Stack>
  );
}
