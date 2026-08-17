/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-C4EC82F9
 *   DI: DI-B0832A64
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-C4EC82F9")
 */
"use client";

import { useMemo, useEffect, useRef, useState } from "react";
import { AskLeoBusyMark } from "@/components/AskLeoBusyMark";
import { searchTerms } from "@/lib/api";
import { askLeoSmart } from "@/lib/api/legacy";
import { expandAbbreviations } from "@/lib/abbrev";
import type { TermSearchResult, Correction, AskLeoSmartResult } from "@/lib/types";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import InputAdornment from "@mui/material/InputAdornment";
import LinearProgress from "@mui/material/LinearProgress";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import SearchIcon from "@mui/icons-material/Search";

// -- Types and tier constants -------------------------------------------------

type Tier = "small" | "big" | "max";

const TIER_LABELS: Record<Tier, string> = {
  small: "Claude Haiku",
  big: "Claude Sonnet",
  max: "Claude Opus",
};

const NEXT_TIER: Record<Tier, Tier | null> = { small: "big", big: "max", max: null };

// -- Helpers ------------------------------------------------------------------

function parseSemanticTag(term: string, semanticTag: string | null): string {
  if (semanticTag) return semanticTag;
  const match = term.match(/\(([^)]+)\)\s*$/);
  return match ? match[1].toLowerCase() : "other";
}

/** Derive edition from the SNOMED module ID. */
function snomedEdition(moduleId?: string): "UK" | "INT" | null {
  if (!moduleId) return null;
  if (moduleId.startsWith("999000")) return "UK";
  if (moduleId.startsWith("9000000")) return "INT";
  return null;
}

/**
 * Find the entity text within encounter text and parse value/unit from the
 * surrounding context. Returns null if the entity or unit cannot be found.
 */
function extractEncounterContext(
  entityText: string,
  encounterText: string,
): { value?: string; unit?: string } | null {
  if (!entityText || !encounterText) return null;
  const keyword = entityText.split(/\s+/)[0].toLowerCase();
  const idx = encounterText.toLowerCase().indexOf(keyword);
  if (idx === -1) return null;
  const window = encounterText.slice(idx, idx + 120);
  const parsed = parseLabResult(window);
  if (parsed.value || parsed.unit) return { value: parsed.value, unit: parsed.unit };
  return null;
}

// -- Match quality helpers ----------------------------------------------------

type MatchLabel = "Exact match" | "Very close" | "Close" | "Possible" | "Unlikely";
type MatchColor = "success" | "primary" | "info" | "warning" | "default";

/**
 * Logistic squash: maps unbounded Lucene score to 0-100.
 * k controls the steepness; 4 works well for SNOMED full-text scores.
 */
function squashScore(raw: number): number {
  const k = 4;
  return Math.round(100 * (1 - Math.exp(-raw / k)));
}

/**
 * Determine match label. Word-set equality check runs first so that e.g.
 * "fever" vs "Fever (finding)" is "Exact match" regardless of raw score —
 * the tag in parentheses is stripped before comparison in significantWords().
 */
/**
 * Determine match label.
 *
 * 1. Word-set exact check: if all significant words (semantic tag stripped)
 *    match both ways, always "Exact match" -- e.g. "fever" vs "Fever (finding)".
 * 2. Weighted coverage penalty: common SNOMED structural words (serum, level,
 *    concentration...) get weight 0.3; discriminating clinical terms get 1.0.
 *    Effective strength = raw_strength * weighted_coverage so that a result
 *    missing only "TSH" but matching "serum" and "level" falls to "Unlikely"
 *    rather than inflating to "Very close".
 */
function matchLabel(strength: number, query: string, term: string): MatchLabel {
  const qw = significantWords(query);
  const tw = significantWords(term);

  const isExact =
    qw.size > 0 &&
    qw.size === tw.size &&
    [...qw].every((w) => tw.has(w));
  if (isExact) return "Exact match";

  let totalWeight = 0;
  let matchedWeight = 0;
  for (const w of qw) {
    const wt = wordWeight(w);
    totalWeight += wt;
    const found = [...tw].some((tw2) => tw2.includes(w) || w.includes(tw2));
    if (found) matchedWeight += wt;
  }
  const coverage = totalWeight > 0 ? matchedWeight / totalWeight : 1;
  const effective = strength * coverage;

  if (effective >= 80) return "Very close";
  if (effective >= 60) return "Close";
  if (effective >= 35) return "Possible";
  return "Unlikely";
}

function matchColor(label: MatchLabel): MatchColor {
  const map: Record<MatchLabel, MatchColor> = {
    "Exact match": "success",
    "Very close": "primary",
    "Close": "info",
    "Possible": "warning",
    "Unlikely": "default",
  };
  return map[label];
}

/** Tokenise to significant words, stripping parenthetical semantic tags and noise. */
function significantWords(text: string): Set<string> {
  const stop = new Set(["the", "of", "in", "a", "an", "and", "or", "for", "to", "by", "on", "at"]);
  return new Set(
    text.toLowerCase()
      .replace(/\([^)]*\)/g, "")
      .split(/[\s,;:.\-/]+/)
      .filter((w) => w.length > 1 && !stop.has(w)),
  );
}

/**
 * Common SNOMED structural words that appear across many concepts.
 * They contribute little discriminating power so get low weight.
 * Sample type (serum/plasma/blood) and measurement noun (level/concentration)
 * are both common scaffolding -- the rare clinical noun (e.g. TSH, ferritin)
 * is the real discriminator.
 */
const DOMAIN_COMMON = new Set([
  "serum", "plasma", "blood", "urine", "saliva", "csf", "whole",
  "level", "concentration", "measurement", "amount", "quantity",
  "count", "number", "ratio", "rate", "index", "score", "value",
  "substance", "observable", "entity", "finding", "procedure",
  "disorder", "structure", "function", "feature", "test", "result",
]);

/** Returns a discriminating weight for a word. Common structural words get 0.3x. */
function wordWeight(w: string): number {
  return DOMAIN_COMMON.has(w) ? 0.3 : 1.0;
}

/**
 * Build the query string sent to the terminology server.
 * 1. Abbreviations are expanded in-line so "TSH" becomes
 *    "TSH thyroid stimulating hormone" -- both forms are kept so Lucene
 *    can match whichever appears in the FSN.
 * 2. Selected semantic tags are appended so "Fever (finding)" scores higher
 *    than other concepts when tag "finding" is active.
 * The displayed search box is NOT changed.
 */
function buildServerQuery(q: string, tags: Set<string>): string {
  const expanded = expandAbbreviations(q);
  if (tags.size === 0) return expanded;
  return `${expanded} ${[...tags].join(" ")}`;
}

/** Show which query words matched and which are missing from the result term. */
function matchExplanation(
  queryText: string,
  resultTerm: string,
): { matched: string[]; missing: string[]; keyMissing: string[] } {
  const queryWords = significantWords(queryText);
  const termWords = significantWords(resultTerm);
  const matched: string[] = [];
  const missing: string[] = [];
  const keyMissing: string[] = [];
  for (const w of queryWords) {
    const found = [...termWords].some((tw) => tw.includes(w) || w.includes(tw));
    if (found) {
      matched.push(w);
    } else {
      missing.push(w);
      if (wordWeight(w) >= 1.0) keyMissing.push(w);
    }
  }
  return { matched, missing, keyMissing };
}

/** Infer the expected measurement unit from a SNOMED observable entity term name. */
const UNIT_PATTERNS: Array<[RegExp, string]> = [
  [/mass concentration/i, "g/L"],
  [/substance concentration/i, "mmol/L"],
  [/molar concentration/i, "mmol/L"],
  [/amount.{0,10}substance/i, "mmol/L"],
  [/volume fraction/i, "%"],
  [/\bsaturation\b/i, "%"],
  [/\bpressure\b/i, "mmHg"],
  [/\btemperature\b/i, "degC"],
  [/\bactivity\b/i, "U/L"],
  [/\bcount\b/i, "/L"],
  [/\bindex\b/i, "index"],
  [/\bratio\b/i, "ratio"],
  [/\brate\b/i, "/min"],
  [/\bvolume\b(?!.*fraction)/i, "mL"],
];

function inferUnit(term: string): string | null {
  for (const [pattern, unit] of UNIT_PATTERNS) {
    if (pattern.test(term)) return unit;
  }
  return null;
}

/** Parse value, unit, reference range from lab-style evidence text. */
function parseLabResult(text: string): {
  value?: string;
  unit?: string;
  reference_range?: string;
  interpretation?: "normal" | "low" | "high";
} {
  const out: ReturnType<typeof parseLabResult> = {};
  const rangeMatch = text.match(/\[([^\]]+)\]/);
  if (rangeMatch) out.reference_range = rangeMatch[1].trim();
  const valueWithOp = text.match(/([<>=])\s*(\d+\.?\d*)\s*([a-zA-Z0-9^/\\%-]+?)(?:\s*\[|\s*$)/);
  const simpleValue = text.match(/(\d+\.?\d*)\s*([a-zA-Z0-9^/\\%-]+?)(?:\s*\[|\s*$)/);
  const m = valueWithOp || simpleValue;
  if (m) {
    out.value = valueWithOp ? `${m[1]} ${m[2]}` : m[1];
    out.unit = (valueWithOp ? m[3] : m[2]).trim() || undefined;
  }
  if (out.reference_range && out.value) {
    const val = parseFloat(out.value.replace(/^[<>=]\s*/, ""));
    const rangeNums = out.reference_range.match(/(\d+\.?\d*)\s*[-\u2013\u2014]\s*(\d+\.?\d*)/);
    if (rangeNums && !Number.isNaN(val)) {
      const low = parseFloat(rangeNums[1]);
      const high = parseFloat(rangeNums[2]);
      if (!Number.isNaN(low) && !Number.isNaN(high)) {
        if (val < low) out.interpretation = "low";
        else if (val > high) out.interpretation = "high";
        else out.interpretation = "normal";
      }
    }
  }
  return out;
}

// -- Ask LEO panel (shown inside the dialog when results are ambiguous) -------

/** Displays the verified SNOMED concept with concept ID and LEO confidence. */
function VerifiedConceptBox({
  match,
  leoConfidence,
}: {
  match: TermSearchResult;
  leoConfidence: number;
}) {
  return (
    <Box sx={{ p: 1, bgcolor: "background.paper", borderRadius: 1, border: "1px solid", borderColor: "divider", mb: 0.75 }}>
      <Typography variant="body2" fontWeight={600} sx={{ mb: 0.25 }}>{match.term}</Typography>
      <Stack direction="row" alignItems="center" gap={1}>
        <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace", flexGrow: 1 }}>
          SNOMED: {match.snomed_concept_id}
        </Typography>
        <Tooltip title={`LEO is ${Math.round(leoConfidence * 100)}% confident`}>
          <Box sx={{ width: 40, flexShrink: 0 }}>
            <LinearProgress
              variant="determinate"
              value={leoConfidence * 100}
              color={leoConfidence >= 0.7 ? "success" : "warning"}
              sx={{ height: 4, borderRadius: 2 }}
            />
          </Box>
        </Tooltip>
        <Typography variant="caption" color="text.secondary">
          {Math.round(leoConfidence * 100)}%
        </Typography>
      </Stack>
    </Box>
  );
}

function AskLeoPanel({
  entityText,
  entityLabel,
  encounterText,
  initialCandidates,
  semanticTags,
  onApplyLeoSearch,
  onUseSuggestion,
}: {
  entityText: string;
  entityLabel: string;
  encounterText: string;
  /** Current search results fed directly to LEO -- no blind FSN guessing. */
  initialCandidates: TermSearchResult[];
  /** Active semantic-tag filter from the current search panel state. */
  semanticTags: string[];
  /** Applies a LEO-generated search refinement back into the search panel. */
  onApplyLeoSearch: (query: string, nextSemanticTags: string[]) => Promise<void>;
  /** Called with the verified SNOMED result -- applies code and closes dialog. */
  onUseSuggestion: (result: TermSearchResult) => void;
}) {
  type Step = "idle" | "analysing" | "searching" | "verifying" | "done";
  const STEP_LABELS: Record<Step, string> = {
    idle: "",
    analysing: "LEO is analysing candidates...",
    searching: "LEO is trying a different search...",
    verifying: "LEO is confirming the match...",
    done: "",
  };

  const [step, setStep] = useState<Step>("idle");
  const [tier, setTier] = useState<Tier>("small");
  const [smartResult, setSmartResult] = useState<AskLeoSmartResult | null>(null);
  const [error, setError] = useState("");
  const [searchFeedback, setSearchFeedback] = useState("");

  async function handleAsk(askTier: Tier) {
    setStep("analysing");
    setError("");
    setSearchFeedback("");
    setSmartResult(null);
    setTier(askTier);
    try {
      // Small tier keeps current tag constraints. Harder tiers broaden search.
      const tags = askTier === "small" ? semanticTags : [];
      const res = await askLeoSmart(
        entityText,
        encounterText,
        initialCandidates as unknown as Array<Record<string, unknown>>,
        tags,
        askTier,
      );
      if (res.alternative_query_used) {
        setStep("searching");
        await onApplyLeoSearch(res.alternative_query_used, tags);
        setSearchFeedback(
          tags.length > 0
            ? `LEO updated the search to "${res.alternative_query_used}" using current filters.`
            : `LEO broadened the search to "${res.alternative_query_used}".`,
        );
      } else if (res.matched_candidate) {
        setStep("verifying");
      }
      setSmartResult(res);
    } catch {
      setError("Ask LEO is not available right now.");
    } finally {
      setStep("done");
    }
  }

  const matchedResult = smartResult?.matched_candidate ?? null;
  const nextTier = smartResult ? NEXT_TIER[tier] : null;
  const busy = step !== "idle" && step !== "done";

  return (
    <Box sx={{ px: 0.5, pt: 0.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.75 }}>
        <Typography variant="subtitle2" color="primary">Ask LEO</Typography>
        {smartResult && (
          <Typography variant="caption" color="text.secondary">{TIER_LABELS[tier]}</Typography>
        )}
      </Stack>

      {!smartResult && !busy && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Not sure which code fits? Ask LEO to check.
        </Typography>
      )}

      {busy && (
        <Stack direction="row" alignItems="center" gap={1} sx={{ py: 0.5 }}>
          <AskLeoBusyMark />
          <Typography variant="body2" color="text.secondary">{STEP_LABELS[step]}</Typography>
        </Stack>
      )}

      {error && <Alert severity="error" sx={{ mb: 0.5, py: 0 }}>{error}</Alert>}
      {searchFeedback && !busy && (
        <Alert severity="info" sx={{ mb: 0.75, py: 0.25 }}>
          <Typography variant="caption">{searchFeedback}</Typography>
        </Alert>
      )}

      {smartResult && !busy && (
        <Box sx={{ mb: 1 }}>
          {smartResult.alternative_query_used && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
              Also searched: "{smartResult.alternative_query_used}"
            </Typography>
          )}
          {smartResult.is_ambiguous && (
            <Alert severity="info" sx={{ mb: 0.75, py: 0.25 }}>
              <Typography variant="caption">{smartResult.reason}</Typography>
            </Alert>
          )}
          {matchedResult && (
            <>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                {smartResult.reason}
              </Typography>
              <VerifiedConceptBox match={matchedResult} leoConfidence={0.9} />
            </>
          )}
        </Box>
      )}

      <Stack direction="row" gap={1} flexWrap="wrap">
        {!smartResult && (
          <Button
            size="small"
            variant="outlined"
            onClick={() => handleAsk("small")}
            disabled={busy}
            startIcon={busy ? <AskLeoBusyMark /> : undefined}
            aria-busy={busy}
          >
            Ask LEO
          </Button>
        )}
        {matchedResult && !busy && (
          <Button size="small" variant="contained" onClick={() => onUseSuggestion(matchedResult)}>
            Use this suggestion
          </Button>
        )}
        {nextTier && (
          <Button
            size="small"
            variant="outlined"
            onClick={() => handleAsk(nextTier)}
            disabled={busy}
            startIcon={busy ? <AskLeoBusyMark /> : undefined}
            aria-busy={busy}
          >
            Ask LEO to think harder
          </Button>
        )}
      </Stack>
    </Box>
  );
}

// -- Exported types ----------------------------------------------------------

export interface TermContext {
  negated?: boolean;
  uncertain?: boolean;
  historical?: boolean;
}

// -- Props -------------------------------------------------------------------

interface Props {
  onSelect: (
    result: TermSearchResult,
    modifiers?: { value?: string; unit?: string; reference_range?: string; interpretation?: string },
    context?: TermContext,
  ) => void;
  onClose: () => void;
  onCorrection: (c: Correction) => void;
  initialQuery?: string;
  /** When true, show value/unit form before confirming (for add flow). */
  captureValueUnit?: boolean;
  /** Selected text to try parsing value/unit from. */
  initialEvidence?: string;
  /** Pre-fill value/unit/range (e.g. when recoding). */
  initialModifiers?: {
    value?: string | number;
    unit?: string;
    reference_range?: string;
    interpretation?: string;
  };
  /** Label for confirm button when captureValueUnit. */
  confirmLabel?: string;
  /** Pre-select these semantic tags and pass them to the server to narrow results. */
  hintTags?: string[];
  /** Clinical term being coded - enables Ask LEO when results are ambiguous. */
  entityText?: string;
  /** NLP entity label / semantic category, passed to Ask LEO for context. */
  entityLabel?: string;
  /** Override the dialog title. Defaults to "Search SNOMED terms". */
  title?: string;
  /** Optional subtitle shown below the title (e.g. the clinical term being fixed). */
  contextLabel?: string;
  /**
   * When true, selecting a result calls onSelect but does NOT call onClose.
   * Use this when the caller needs to show a follow-up step before closing.
   */
  preventAutoClose?: boolean;
}

// -- Main component ----------------------------------------------------------

const SEARCH_LIMIT = 15;
const LEO_SEARCH_LIMIT = 25;

export default function TermSearch({
  onSelect,
  onClose,
  onCorrection,
  initialQuery = "",
  captureValueUnit = false,
  initialEvidence = "",
  initialModifiers,
  confirmLabel = "Add code",
  hintTags,
  entityText,
  entityLabel = "",
  title = "Search SNOMED terms",
  contextLabel,
  preventAutoClose = false,
}: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<TermSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(() => new Set(hintTags ?? []));
  const [selectedResult, setSelectedResult] = useState<TermSearchResult | null>(null);
  const queryRef = useRef<string>(initialQuery);
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("");
  const [referenceRange, setReferenceRange] = useState("");
  const [interpretation, setInterpretation] = useState("");
  const [negated, setNegated] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [historical, setHistorical] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const tags = useMemo(() => {
    const seen = new Set<string>(hintTags ?? []);
    for (const r of results) {
      const tag = parseSemanticTag(r.term, r.semantic_tag ?? null);
      if (tag) seen.add(tag);
    }
    return [...seen].sort();
  }, [results, hintTags]);

  const filteredResults = useMemo(() => {
    if (selectedTags.size === 0) return results;
    return results.filter((r) => selectedTags.has(parseSemanticTag(r.term, r.semantic_tag ?? null)));
  }, [results, selectedTags]);

  async function runSearch(
    nextQuery: string,
    tagsSet: Set<string>,
    limit = SEARCH_LIMIT,
  ): Promise<void> {
    if (!nextQuery || nextQuery.trim().length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    const tagArr = tagsSet.size > 0 ? [...tagsSet] : undefined;
    try {
      const nextResults = await searchTerms(
        buildServerQuery(nextQuery, tagsSet),
        limit,
        tagArr,
      );
      setResults(nextResults);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  function toggleTag(tag: string) {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  }

  useEffect(() => {
    if (!initialQuery || initialQuery.length < 2) return;
    setQuery(initialQuery);
    queryRef.current = initialQuery;
    void runSearch(initialQuery, new Set(hintTags ?? []));
  }, [initialQuery]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const q = queryRef.current;
    void runSearch(q, selectedTags);
  }, [selectedTags]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!captureValueUnit) return;
    const m = initialModifiers;
    if (m?.value != null || m?.unit || m?.reference_range || m?.interpretation) {
      setValue(String(m.value ?? ""));
      setUnit(String(m.unit ?? ""));
      setReferenceRange(String(m.reference_range ?? ""));
      setInterpretation(String(m.interpretation ?? ""));
    } else if (initialEvidence) {
      const parsed = parseLabResult(initialEvidence);
      if (parsed.value) setValue(parsed.value);
      if (parsed.unit) setUnit(parsed.unit);
      if (parsed.reference_range) setReferenceRange(parsed.reference_range);
      if (parsed.interpretation) setInterpretation(parsed.interpretation);
    }
  }, [captureValueUnit, initialEvidence, initialModifiers]);

  function handleChange(val: string) {
    setQuery(val);
    queryRef.current = val;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (val.trim().length < 2) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      await runSearch(val, selectedTags);
    }, 300);
  }

  async function applyLeoSearch(
    nextQuery: string,
    nextSemanticTags: string[],
  ): Promise<void> {
    const trimmed = nextQuery.trim();
    if (!trimmed) return;
    const nextTagSet = new Set(nextSemanticTags);
    setQuery(trimmed);
    queryRef.current = trimmed;
    setSelectedResult(null);
    setSelectedTags(nextTagSet);
    await runSearch(trimmed, nextTagSet, LEO_SEARCH_LIMIT);
  }

  function handleResultClick(r: TermSearchResult) {
    if (captureValueUnit) {
      setSelectedResult(r);
      return;
    }
    onSelect(r);
    onCorrection({
      type: "reassign",
      text: r.term,
      detail: `Reassigned to SNOMED ${r.snomed_concept_id}`,
      time: new Date().toISOString(),
    });
    if (!preventAutoClose) onClose();
  }

  function handleConfirm() {
    if (!selectedResult) return;
    const mods: { value?: string; unit?: string; reference_range?: string; interpretation?: string } = {};
    if (value.trim()) mods.value = value.trim();
    if (unit.trim()) mods.unit = unit.trim();
    if (referenceRange.trim()) mods.reference_range = referenceRange.trim();
    if (interpretation.trim()) mods.interpretation = interpretation.trim();
    const ctx: TermContext = {};
    if (negated) ctx.negated = true;
    if (uncertain) ctx.uncertain = true;
    if (historical) ctx.historical = true;
    onSelect(
      selectedResult,
      Object.keys(mods).length ? mods : undefined,
      Object.keys(ctx).length ? ctx : undefined,
    );
    onClose();
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pb: contextLabel ? 0.5 : undefined }}>
        {title}
        {contextLabel && (
          <Typography
            component="div"
            variant="body2"
            color="text.secondary"
            sx={{ fontWeight: 400, mt: 0.25, fontSize: "0.85rem" }}
          >
            {contextLabel}
          </Typography>
        )}
      </DialogTitle>

      <DialogContent dividers sx={{ display: "flex", flexDirection: "column", gap: 1.5, p: 2 }}>
        <TextField
          autoFocus
          fullWidth
          size="small"
          label="Search SNOMED terms"
          placeholder="e.g. type 2 diabetes"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          inputProps={{ "aria-label": "Search SNOMED terms" }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />

        {tags.length > 0 && (
          <Stack direction="row" flexWrap="wrap" gap={0.5} alignItems="center">
            {hintTags && hintTags.length > 0 && (
              <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
                Suggested:
              </Typography>
            )}
            {tags.map((tag) => {
              const isHint = hintTags?.includes(tag) ?? false;
              const isSelected = selectedTags.has(tag);
              return (
                <Chip
                  key={tag}
                  label={tag}
                  size="small"
                  variant={isSelected ? "filled" : "outlined"}
                  color={isSelected ? "primary" : isHint ? "secondary" : "default"}
                  onClick={() => toggleTag(tag)}
                />
              );
            })}
            {selectedTags.size > 0 && (
              <Chip
                label="Clear"
                size="small"
                variant="outlined"
                onDelete={() => setSelectedTags(new Set())}
                onClick={() => setSelectedTags(new Set())}
              />
            )}
          </Stack>
        )}

        {captureValueUnit && selectedResult && (
          <Box sx={{ p: 1.5, bgcolor: "action.hover", borderRadius: 1 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Add: {selectedResult.term}</Typography>
            <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ mb: 1 }}>
              <Chip
                label="Negated"
                size="small"
                variant={negated ? "filled" : "outlined"}
                color={negated ? "error" : "default"}
                onClick={() => setNegated(!negated)}
              />
              <Chip
                label="Uncertain"
                size="small"
                variant={uncertain ? "filled" : "outlined"}
                color={uncertain ? "warning" : "default"}
                onClick={() => setUncertain(!uncertain)}
              />
              <Chip
                label="Historical"
                size="small"
                variant={historical ? "filled" : "outlined"}
                color={historical ? "info" : "default"}
                onClick={() => setHistorical(!historical)}
              />
            </Stack>
            <Stack direction="row" gap={1} flexWrap="wrap">
              <TextField
                size="small"
                label="Value"
                placeholder="e.g. 91 or < 0.2"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                sx={{ width: 120 }}
              />
              <TextField
                size="small"
                label="Unit"
                placeholder="e.g. fL"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                sx={{ width: 120 }}
              />
              <TextField
                size="small"
                label="Ref range"
                placeholder="e.g. 80 - 99"
                value={referenceRange}
                onChange={(e) => setReferenceRange(e.target.value)}
                sx={{ width: 130 }}
              />
              <TextField
                size="small"
                label="Interpretation"
                placeholder="normal / low / high"
                value={interpretation}
                onChange={(e) => setInterpretation(e.target.value)}
                sx={{ width: 140 }}
              />
            </Stack>
          </Box>
        )}

        {(initialEvidence || entityText) && (() => {
          const ctx = extractEncounterContext(entityText ?? initialQuery, initialEvidence ?? "");
          if (!ctx?.value && !ctx?.unit) return null;
          const label = [ctx.value, ctx.unit].filter(Boolean).join(" ");
          return (
            <Stack direction="row" alignItems="center" gap={0.75}>
              <Typography variant="caption" color="text.secondary">
                Record shows:
              </Typography>
              <Chip label={label} size="small" color="info" variant="outlined" />
            </Stack>
          );
        })()}

        {loading && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 2, px: 1 }}>
            <CircularProgress aria-label="Loading" size={18} />
            <Typography variant="body2" color="text.secondary">Searching...</Typography>
          </Box>
        )}

        {!loading && results.length === 0 && query.length >= 2 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2, px: 1 }}>
            No results
          </Typography>
        )}

        {!loading && results.length > 0 && filteredResults.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2, px: 1 }}>
            No results for selected tags. Clear filters or choose different tags.
          </Typography>
        )}

        {filteredResults.length > 0 && (
          <List disablePadding sx={{ overflowY: "auto", maxHeight: entityText ? 200 : 340 }}>
            {filteredResults.map((r, i) => {
              const unitHint = inferUnit(r.term);
              const strength = squashScore(r.score ?? 0);
              const label = matchLabel(strength, query, r.term);
              const color = matchColor(label);
              const explain = matchExplanation(query, r.term);
              return (
                <ListItemButton
                  key={`${r.snomed_concept_id}-${i}`}
                  selected={selectedResult?.snomed_concept_id === r.snomed_concept_id}
                  onClick={() => handleResultClick(r)}
                  sx={{ alignItems: "flex-start", gap: 1, py: 1 }}
                >
                  <ListItemText
                    primary={r.term}
                    secondary={
                      <Box component="span" sx={{ display: "block" }}>
                        <Typography variant="caption" component="span" sx={{ fontFamily: "monospace" }}>
                          SNOMED: {r.snomed_concept_id}
                          {r.read_code && ` · Read: ${r.read_code}`}
                          {r.icd10 && ` · ICD-10: ${r.icd10}${r.icd10_term ? ` ${r.icd10_term}` : ""}`}
                          {r.opcs4 && ` · OPCS-4: ${r.opcs4}${r.opcs4_term ? ` ${r.opcs4_term}` : ""}`}
                        </Typography>
                        {explain.missing.length > 0 && (
                          <Typography variant="caption" component="span" color="text.disabled" sx={{ display: "block" }}>
                            matched: {explain.matched.join(", ") || "none"}
                            {" · missing: "}
                            {explain.missing.map((w, wi) => (
                              <Box
                                key={wi}
                                component="span"
                                sx={explain.keyMissing.includes(w)
                                  ? { color: "error.main", fontWeight: 700 }
                                  : {}}
                              >
                                {wi > 0 ? ", " : ""}{w}
                              </Box>
                            ))}
                          </Typography>
                        )}
                      </Box>
                    }
                    primaryTypographyProps={{ variant: "body2", fontWeight: 500 }}
                  />
                  <Stack direction="column" alignItems="flex-end" gap={0.25} sx={{ mt: 0.25, flexShrink: 0 }}>
                    <Stack direction="row" gap={0.5} alignItems="center">
                      {snomedEdition(r.module_id) === "UK" && (
                        <Box
                          component="img"
                          src="/union-jack.png"
                          alt="UK edition"
                          title="UK SNOMED CT edition"
                          sx={{ width: 24, height: 16, objectFit: "cover", borderRadius: "2px", flexShrink: 0 }}
                        />
                      )}
                      {snomedEdition(r.module_id) === "INT" && (
                        <Chip label="INT" size="small" variant="outlined" />
                      )}
                      {unitHint && (
                        <Chip label={unitHint} size="small" variant="outlined" color="secondary" />
                      )}
                      <Chip
                        label={parseSemanticTag(r.term, r.semantic_tag ?? null)}
                        size="small"
                        color="primary"
                        variant="outlined"
                      />
                    </Stack>
                    <Stack direction="row" gap={0.5} alignItems="center">
                      {r.from_surface_form && (
                        <Tooltip title="This text is already a known surface form alias for this concept -- the pipeline will map it automatically">
                          <Chip
                            label="Known alias"
                            size="small"
                            color="success"
                            variant="outlined"
                            sx={{ fontWeight: 600 }}
                          />
                        </Tooltip>
                      )}
                      <Tooltip title={`${strength}% match strength`}>
                        <Chip label={label} size="small" color={color} variant="filled" />
                      </Tooltip>
                    </Stack>
                  </Stack>
                </ListItemButton>
              );
            })}
          </List>
        )}

        {entityText && (
          <>
            <Divider />
            <AskLeoPanel
              entityText={entityText}
              entityLabel={entityLabel}
              encounterText={initialEvidence ?? ""}
              initialCandidates={filteredResults}
              semanticTags={[...selectedTags]}
              onApplyLeoSearch={applyLeoSearch}
              onUseSuggestion={handleResultClick}
            />
          </>
        )}
      </DialogContent>

      <DialogActions>
        <Button variant="text" onClick={onClose}>Cancel</Button>
        {captureValueUnit && (
          <Button variant="contained" disabled={!selectedResult} onClick={handleConfirm}>
            {confirmLabel}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
