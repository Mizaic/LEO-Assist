"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import { keyframes } from "@mui/material/styles";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import TermSearch from "@/components/TermSearch";
import { askLeoSmart, searchTerms } from "@/lib/api/legacy";
import type { ReviewItem } from "@/components/operations/ReviewCard";
import type { AskLeoSmartResult, TermSearchResult } from "@/lib/types";
import { ASSERTION_CHIP } from "@/lib/types";

const ASSERTION_OPTIONS = [
  "present", "absent", "refuted", "possible", "historical", "hypothetical", "family", "declined",
] as const;

// Common NER entity types a reviewer might need to correct to.
const ENTITY_LABEL_OPTIONS = [
  "finding",
  "disorder",
  "procedure",
  "observable_entity",
  "qualifier_value",
  "situation",
  "substance",
  "medicinal_product",
  "clinical_drug",
  "event",
  "body_structure",
];

const safetyPulse = keyframes`
  0%, 100% { box-shadow: 0 0 4px 0 rgba(211, 47, 47, 0.35); }
  50%      { box-shadow: 0 0 14px 5px rgba(211, 47, 47, 0.55); }
`;

function isClinicalSafetyWarning(warning: string | null | undefined): boolean {
  if (!warning) return false;
  return /^lab-value guard/i.test(warning) || /clinical safety/i.test(warning) || /\blab result\b/i.test(warning);
}

function _isLabValueWarning(warning: string): boolean {
  return /^lab-value guard/i.test(warning) || /\blab result\b/i.test(warning);
}

function warningHeadline(warning: string): string {
  if (_isLabValueWarning(warning)) {
    return "Clinical safety: this is NOT a diagnosis.";
  }
  return "LEO says: this procedure was not performed.";
}

// -- Types -------------------------------------------------------------------

interface CaseRecord {
  review_id: string;
  label_id?: string;
  entity_text: string;
  entity_label: string;
  snomed_concept_id: string | null;
  snomed_term: string | null;
  score: number | null;
  encounter_text: string;
  source: string;
  assertion?: string;
  suggested_label?: string | null;
  tag_mismatch_delta?: number | null;
}

interface SiblingEntity {
  review_id: string;
  entity_text: string;
  entity_label: string;
  snomed_concept_id: string | null;
  snomed_term: string | null;
  score: number | null;
  assertion: string;
  resolved: boolean;
  resolved_concept_id: string | null;
  resolved_term: string | null;
}

interface Props {
  item: ReviewItem;
  open: boolean;
  onClose: () => void;
  onAllResolved: () => void;
  /** Case records already fetched by the parent (skips the internal fetch). */
  initialCases?: CaseRecord[];
  /** Pre-filled LEO results keyed by review_id (from the bulk Ask LEO flow). */
  prefilledResults?: Record<string, AskLeoSmartResult>;
}

// -- Fetch helper ------------------------------------------------------------

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
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
}

// -- Component ---------------------------------------------------------------

export default function CodingReviewCasesModal({
  item,
  open,
  onClose,
  onAllResolved,
  initialCases,
  prefilledResults,
}: Props) {
  const [cases, setCases] = useState<CaseRecord[]>(initialCases ?? []);
  const [loading, setLoading] = useState(!initialCases);
  const [error, setError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [singleTarget, setSingleTarget] = useState<CaseRecord | null>(null);

  // Sibling entities for encounter context.
  const [siblings, setSiblings] = useState<Record<string, SiblingEntity[]>>({});

  // Entity-label correction state.
  const rawLabel = item.entityLabel.replace(/_/g, " ") || "";
  const [labelOverride, setLabelOverride] = useState(rawLabel);
  const [labelMenuAnchor, setLabelMenuAnchor] = useState<null | HTMLElement>(null);
  const [savingLabel, setSavingLabel] = useState(false);
  const labelChipRef = useRef<HTMLDivElement>(null);

  const loadCases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const encoded = encodeURIComponent(item.entityText);
      const data = await jsonFetch<{ items: CaseRecord[] }>(
        `/api/training/coding-review/queue?entity_text=${encoded}&page_size=200`
      );
      setCases(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load cases");
    } finally {
      setLoading(false);
    }
  }, [item.entityText]);

  useEffect(() => {
    // Skip fetch when parent has already provided the case records.
    if (open && !initialCases) loadCases();
  }, [open, loadCases, initialCases]);

  // Fetch sibling entities once cases are loaded.
  useEffect(() => {
    if (cases.length === 0) return;
    const labelIds = cases.map((c) => c.label_id).filter(Boolean) as string[];
    if (labelIds.length === 0) return;

    const unique = [...new Set(labelIds)];
    jsonFetch<{ siblings: Record<string, SiblingEntity[]> }>(
      "/api/training/coding-review/encounter-siblings",
      { method: "POST", body: JSON.stringify({ label_ids: unique }) },
    )
      .then((res) => setSiblings(res.siblings))
      .catch(() => { /* non-critical -- context panel just won't appear */ });
  }, [cases]);

  const handleCorrectLabel = useCallback(async (newLabel: string) => {
    setLabelMenuAnchor(null);
    if (newLabel === labelOverride) return;
    setLabelOverride(newLabel);
    setSavingLabel(true);
    try {
      await jsonFetch("/api/training/coding-review/entity-label", {
        method: "PATCH",
        body: JSON.stringify({
          entity_text: item.entityText,
          entity_label: newLabel.replace(/ /g, "_"),
          corrected_by: "operations_ui",
        }),
      });
    } catch {
      // Non-fatal: the UI override is already applied for this session.
    } finally {
      setSavingLabel(false);
    }
  }, [labelOverride, item.entityText]);

  // Track whether cases have ever been loaded so we don't fire onAllResolved
  // at mount when initialCases is an empty array or before the fetch completes.
  const [casesInitialized, setCasesInitialized] = useState(
    initialCases !== undefined && initialCases.length > 0,
  );

  useEffect(() => {
    if (cases.length > 0) setCasesInitialized(true);
  }, [cases.length]);

  // Call onAllResolved after the render in which the last case is removed --
  // never from inside a state updater, which would be a render-phase side effect.
  useEffect(() => {
    if (casesInitialized && cases.length === 0 && !loading) {
      onAllResolved();
    }
  }, [casesInitialized, cases.length, loading, onAllResolved]);

  const removeCase = useCallback((reviewId: string) => {
    setCases((prev) => prev.filter((c) => c.review_id !== reviewId));
  }, []);

  const handleSingleResolve = useCallback(
    async (caseRecord: CaseRecord, result: TermSearchResult, assertion = "present") => {
      setResolvingId(caseRecord.review_id);
      setSingleTarget(null);
      try {
        await jsonFetch(`/api/training/coding-review/${caseRecord.review_id}/resolve`, {
          method: "POST",
          body: JSON.stringify({
            resolved_concept_id: result.snomed_concept_id,
            resolved_term: result.term,
            reviewer: "operations_ui",
            resolved_assertion: assertion,
          }),
        });
        removeCase(caseRecord.review_id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save. Please try again.");
      } finally {
        setResolvingId(null);
      }
    },
    [removeCase]
  );

  const handleBatchResolve = useCallback(
    async (result: TermSearchResult) => {
      setBatchOpen(false);
      setResolvingId("__batch__");
      try {
        await jsonFetch("/api/training/coding-review/batch-resolve", {
          method: "POST",
          body: JSON.stringify({
            entity_text: item.entityText,
            entity_label: item.entityLabel,
            resolved_concept_id: result.snomed_concept_id,
            resolved_term: result.term,
            reviewer: "operations_ui",
            resolved_assertion: item.assertion ?? "present",
          }),
        });
        onAllResolved();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save. Please try again.");
      } finally {
        setResolvingId(null);
      }
    },
    [item.entityText, item.entityLabel, onAllResolved]
  );

  // hintTags uses the corrected label so all searches and LEO calls benefit immediately.
  const hintTags = labelOverride ? [labelOverride] : undefined;

  const isBatchBusy = resolvingId === "__batch__";
  const isAcceptAllBusy = resolvingId === "__accept_all__";

  // Only present-assertion cases are eligible for bulk accept.
  // historical/possible/family assertions require individual human review.
  // Cases where LEO flagged an assertion warning (declined, awaiting, etc.) are
  // also excluded -- they need human review before coding.
  const bulkAcceptable = cases.filter(
    (c) => {
      if (c.assertion && c.assertion !== "present") return false;
      if (prefilledResults?.[c.review_id]?.assertion_warning) return false;
      return true;
    },
  );

  // Count cases where LEO has a confident (non-ambiguous) match, no assertion warning,
  // and the assertion is present.
  const confidentCount = prefilledResults
    ? bulkAcceptable.filter((c) => prefilledResults[c.review_id]?.matched_candidate).length
    : 0;

  // Count cases LEO flagged as not codeable so the title bar can show a summary.
  const warningCount = prefilledResults
    ? cases.filter((c) => prefilledResults[c.review_id]?.assertion_warning).length
    : 0;

  const safetyCount = prefilledResults
    ? cases.filter((c) => isClinicalSafetyWarning(prefilledResults[c.review_id]?.assertion_warning)).length
    : 0;

  const handleAcceptAll = useCallback(async () => {
    if (!prefilledResults) return;
    setResolvingId("__accept_all__");
    setError(null);
    const toResolve = bulkAcceptable.filter((c) => prefilledResults[c.review_id]?.matched_candidate);
    let remaining = [...cases];
    for (const c of toResolve) {
      const leoResult = prefilledResults[c.review_id]!;
      const match = leoResult.matched_candidate!;
      try {
        await jsonFetch(`/api/training/coding-review/${c.review_id}/resolve`, {
          method: "POST",
          body: JSON.stringify({
            resolved_concept_id: match.snomed_concept_id,
            resolved_term: match.term,
            reviewer: "operations_ui",
            resolved_assertion: leoResult.assertion ?? "present",
          }),
        });
        remaining = remaining.filter((r) => r.review_id !== c.review_id);
        setCases([...remaining]);
      } catch {
        // Leave failed cases in the list for manual review.
      }
    }
    setResolvingId(null);
    if (remaining.length === 0) onAllResolved();
  }, [cases, prefilledResults, onAllResolved]);

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth scroll="paper">
        <DialogTitle>
          <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
            <Box>
              <Typography variant="h6" component="span">
                Cases for &apos;{item.entityText}&apos;
              </Typography>
              {cases.length > 0 && (
                <Chip
                  label={`${cases.length} remaining`}
                  size="small"
                  sx={{ ml: 1.5 }}
                />
              )}
              {labelOverride && (
                <Tooltip title="The NER entity type used to guide searches and Ask LEO. Click to correct if wrong.">
                  <Chip
                    ref={labelChipRef}
                    label={savingLabel ? "Saving..." : labelOverride}
                    size="small"
                    color={labelOverride !== rawLabel ? "warning" : "default"}
                    variant="outlined"
                    onClick={(e) => setLabelMenuAnchor(e.currentTarget)}
                    sx={{ ml: 1, cursor: "pointer" }}
                  />
                </Tooltip>
              )}
              <Menu
                open={Boolean(labelMenuAnchor)}
                anchorEl={labelMenuAnchor}
                onClose={() => setLabelMenuAnchor(null)}
              >
                <MenuItem disabled>
                  <Typography variant="caption" color="text.secondary">
                    Correct entity type
                  </Typography>
                </MenuItem>
                {ENTITY_LABEL_OPTIONS.map((opt) => (
                  <MenuItem
                    key={opt}
                    selected={opt === labelOverride}
                    onClick={() => handleCorrectLabel(opt)}
                    dense
                  >
                    {opt}
                  </MenuItem>
                ))}
              </Menu>
            </Box>
            <Stack direction="row" gap={1} flexWrap="wrap">
              {confidentCount > 0 && (
                <Button
                  variant="contained"
                  color="success"
                  size="small"
                  disabled={isAcceptAllBusy || isBatchBusy}
                  onClick={handleAcceptAll}
                  startIcon={isAcceptAllBusy ? <CircularProgress aria-label="Loading" size={14} color="inherit" /> : undefined}
                >
                  {isAcceptAllBusy
                    ? "Accepting..."
                    : `Accept ${confidentCount} LEO suggestion${confidentCount !== 1 ? "s" : ""}`}
                </Button>
              )}
              <Button
                variant="outlined"
                size="small"
                disabled={isBatchBusy || isAcceptAllBusy || loading || cases.length === 0}
                onClick={() => setBatchOpen(true)}
                startIcon={isBatchBusy ? <CircularProgress aria-label="Loading" size={14} color="inherit" /> : undefined}
              >
                {isBatchBusy ? "Coding all..." : `Code all ${cases.length} at once`}
              </Button>
            </Stack>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {prefilledResults
              ? [
                  `LEO has analysed each encounter. Accept individual suggestions, accept all ${confidentCount} confident ones, or override any.`,
                  safetyCount > 0
                    ? ` ${safetyCount} clinical safety alert${safetyCount !== 1 ? "s" : ""} detected (red glow below).`
                    : "",
                  warningCount - safetyCount > 0
                    ? ` ${warningCount - safetyCount} case${warningCount - safetyCount !== 1 ? "s" : ""} flagged as not suitable for coding.`
                    : "",
                ].join("")
              : "Review each encounter below. Code individually, or use \"Code all at once\" if the same code fits every case."}
          </Typography>
        </DialogTitle>

        <DialogContent dividers>
          {error && (
            <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          {loading && (
            <Box sx={{ textAlign: "center", py: 4 }}>
              <CircularProgress aria-label="Loading" size={28} />
            </Box>
          )}

          {!loading && cases.length === 0 && !error && (
            <Typography color="text.secondary" sx={{ textAlign: "center", py: 4 }}>
              All cases resolved.
            </Typography>
          )}

          <Stack spacing={2}>
            {cases.map((c, idx) => (
              <CaseCard
                key={c.review_id}
                caseRecord={c}
                index={idx + 1}
                total={cases.length}
                busy={resolvingId === c.review_id || resolvingId === "__accept_all__"}
                onCodeThis={() => setSingleTarget(c)}
                onAcceptLeo={(result, assertion) => handleSingleResolve(c, result, assertion)}
                onSuppressed={() => removeCase(c.review_id)}
                hintTags={hintTags}
                initialLeoResult={prefilledResults?.[c.review_id]}
                encounterSiblings={c.label_id ? siblings[c.label_id] : undefined}
              />
            ))}
          </Stack>
        </DialogContent>

        <DialogActions>
          <Button onClick={onClose} variant="outlined">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Batch code picker */}
      {batchOpen && (
        <TermSearch
          initialQuery={item.entityText}
          hintTags={hintTags}
          entityText={item.entityText}
          entityLabel={item.entityLabel.replace(/_/g, " ")}
          initialEvidence={item.sampleEncounterText}
          onSelect={handleBatchResolve}
          onClose={() => setBatchOpen(false)}
          onCorrection={() => {}}
        />
      )}

      {/* Per-record code picker */}
      {singleTarget && (
        <TermSearch
          initialQuery={singleTarget.entity_text}
          hintTags={hintTags}
          entityText={singleTarget.entity_text}
          entityLabel={singleTarget.entity_label.replace(/_/g, " ")}
          initialEvidence={singleTarget.encounter_text}
          onSelect={(r) => handleSingleResolve(singleTarget, r)}
          onClose={() => setSingleTarget(null)}
          onCorrection={() => {}}
        />
      )}
    </>
  );
}

// -- Helper: extract a suggested context phrase from LEO's warning ----------

/**
 * LEO naturally quotes the key phrase that triggered the warning, e.g.
 * "the encounter text explicitly states 'awaiting appt for biopsy'".
 * We pull the first quoted phrase (4-80 chars) as the suggested suppress phrase.
 * Falls back to a short window around the entity in the encounter text.
 */
function extractSuggestedPhrase(
  warning: string,
  entityText: string,
  encounterText: string,
): string {
  const quoted = warning.match(/'([^']{4,80})'/);
  if (quoted) return quoted[1];

  const lower = encounterText.toLowerCase();
  const idx = lower.indexOf(entityText.toLowerCase());
  if (idx >= 0) {
    const start = Math.max(0, idx - 15);
    const end = Math.min(encounterText.length, idx + entityText.length + 15);
    return encounterText.slice(start, end).trim();
  }

  return "";
}

// -- Encounter context panel -------------------------------------------------

const LABEL_COLORS: Record<string, string> = {
  finding: "#6366f1",
  disorder: "#dc2626",
  procedure: "#2563eb",
  observable_entity: "#0891b2",
  qualifier_value: "#7c3aed",
  situation: "#ca8a04",
  substance: "#059669",
  medicinal_product: "#d946ef",
  event: "#ea580c",
  body_structure: "#64748b",
};

function EncounterContextPanel({
  siblings,
  currentReviewId,
}: {
  siblings?: SiblingEntity[];
  currentReviewId: string;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!siblings || siblings.length === 0) return null;

  const others = siblings.filter((s) => s.review_id !== currentReviewId);
  if (others.length === 0) return null;

  return (
    <Box sx={{ mb: 1.5 }}>
      <Button
        size="small"
        variant="outlined"
        onClick={() => setExpanded((p) => !p)}
        endIcon={expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
        sx={{
          textTransform: "none",
          fontWeight: 500,
          color: "text.primary",
          borderColor: "divider",
          px: 1,
          "&:hover": { borderColor: "text.secondary", bgcolor: "action.hover" },
        }}
      >
        {expanded
          ? "Hide other items from this note"
          : `Show ${others.length} other item${others.length === 1 ? "" : "s"} from this note`}
      </Button>
      {expanded && (
        <Box sx={{ mt: 0.5, pl: 1, borderLeft: "2px solid", borderColor: "divider" }}>
          {others.map((s) => {
            const color = LABEL_COLORS[s.entity_label] || "#64748b";
            return (
              <Stack key={s.review_id} direction="row" spacing={1} alignItems="center" sx={{ py: 0.3 }}>
                <Chip
                  label={s.entity_label.replace(/_/g, " ")}
                  size="small"
                  sx={{ bgcolor: color, color: "#fff", fontSize: "0.65rem", height: 18, minWidth: 60 }}
                />
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  {s.entity_text}
                </Typography>
                {s.resolved && s.resolved_term ? (
                  <Chip label={s.resolved_term} size="small" color="success" variant="outlined" sx={{ fontSize: "0.7rem", height: 20 }} />
                ) : s.snomed_term ? (
                  <Chip
                    label={`${s.snomed_term} (${((s.score ?? 0) * 100).toFixed(0)}%)`}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: "0.7rem", height: 20 }}
                  />
                ) : (
                  <Chip label="uncoded" size="small" variant="outlined" color="warning" sx={{ fontSize: "0.7rem", height: 20 }} />
                )}
                {s.assertion !== "present" && (
                  <Chip label={s.assertion} size="small" sx={{ fontSize: "0.65rem", height: 18 }} />
                )}
              </Stack>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

// -- Individual case card with inline Ask LEO --------------------------------

type LeoStep = "idle" | "loading" | "done" | "error";

function CaseCard({
  caseRecord,
  index,
  total,
  busy,
  onCodeThis,
  onAcceptLeo,
  onSuppressed,
  hintTags,
  initialLeoResult,
  encounterSiblings,
}: {
  caseRecord: CaseRecord;
  index: number;
  total: number;
  busy: boolean;
  onCodeThis: () => void;
  onAcceptLeo: (result: TermSearchResult, assertion: string) => void;
  onSuppressed: () => void;
  hintTags?: string[];
  initialLeoResult?: AskLeoSmartResult;
  encounterSiblings?: SiblingEntity[];
}) {
  const [leoStep, setLeoStep] = useState<LeoStep>(initialLeoResult ? "done" : "idle");
  const [leoResult, setLeoResult] = useState<AskLeoSmartResult | null>(initialLeoResult ?? null);
  const [leoError, setLeoError] = useState("");

  // Assertion correction state.
  const [assertionOverride, setAssertionOverride] = useState(caseRecord.assertion || "present");
  const [assertionMenuAnchor, setAssertionMenuAnchor] = useState<null | HTMLElement>(null);

  // Suppress / ignore rule state.
  const [suppressOpen, setSuppressOpen] = useState(false);
  const [contextPhrase, setContextPhrase] = useState("");
  // "leo" = auto-filled from LEO warning; "user" = reviewer edited; "none" = empty
  const [phraseSource, setPhraseSource] = useState<"leo" | "user" | "none">("none");
  const [suppressing, setSuppressing] = useState(false);
  const [suppressError, setSuppressError] = useState("");

  // Auto-open suppress form when the entity is truly negated or LEO detected
  // the procedure was not performed. Declined care is NOT auto-suppressed
  // because it is a codeable clinical event in UK primary care.
  // When LEO has an assertion_warning, pre-fill the context phrase from the
  // phrase LEO quoted in its reasoning so the reviewer is not starting blind.
  useEffect(() => {
    const a = caseRecord.assertion || "present";
    const warning = initialLeoResult?.assertion_warning;
    if (a === "absent" || Boolean(warning)) {
      setSuppressOpen(true);
      if (warning) {
        const suggested = extractSuggestedPhrase(
          warning,
          caseRecord.entity_text,
          caseRecord.encounter_text,
        );
        if (suggested) {
          setContextPhrase(suggested);
          setPhraseSource("leo");
        }
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When the reviewer runs Ask LEO inline and it returns an assertion_warning,
  // auto-open the suppress form and pre-fill the phrase (if still blank).
  useEffect(() => {
    if (!leoResult?.assertion_warning) return;
    setSuppressOpen(true);
    if (!contextPhrase) {
      const suggested = extractSuggestedPhrase(
        leoResult.assertion_warning,
        caseRecord.entity_text,
        caseRecord.encounter_text,
      );
      if (suggested) {
        setContextPhrase(suggested);
        setPhraseSource("leo");
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leoResult?.assertion_warning]);

  // Keep the top-right assertion badge in sync with what LEO detected.
  // The pipeline's initial assertion (caseRecord.assertion) can be stale --
  // LEO re-reads the full encounter context and may resolve a more precise
  // assertion (e.g. "declined") that the NER pass missed.
  useEffect(() => {
    if (leoResult?.assertion && leoResult.assertion !== assertionOverride) {
      setAssertionOverride(leoResult.assertion);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leoResult?.assertion]);

  const handleSuppress = useCallback(async () => {
    setSuppressing(true);
    setSuppressError("");
    const escaped = contextPhrase.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const contextRegex = contextPhrase.trim() ? `(?i)${escaped}` : null;
    try {
      await jsonFetch("/api/training/post-processor-rules", {
        method: "POST",
        body: JSON.stringify({
          action: "suppress",
          match_text: caseRecord.entity_text,
          match_label: caseRecord.entity_label,
          context_regex: contextRegex,
          priority: 50,
          notes: `Created from coding review ${caseRecord.review_id}`,
          created_by: "operations_ui",
          active: true,
        }),
      });
      await jsonFetch(`/api/training/coding-review/${caseRecord.review_id}/ignore`, {
        method: "POST",
        body: JSON.stringify({ reviewer: "operations_ui" }),
      });
      onSuppressed();
    } catch {
      setSuppressError("Could not create ignore rule. Please try again.");
    } finally {
      setSuppressing(false);
    }
  }, [caseRecord, contextPhrase, onSuppressed]);

  const handleCorrectAssertion = useCallback(async (newAssertion: string) => {
    setAssertionMenuAnchor(null);
    if (newAssertion === assertionOverride) return;
    setAssertionOverride(newAssertion);
    if (newAssertion === "absent" || newAssertion === "declined") {
      setSuppressOpen(true);
    }
    try {
      await jsonFetch(`/api/training/coding-review/${caseRecord.review_id}/assertion`, {
        method: "PATCH",
        body: JSON.stringify({ assertion: newAssertion, corrected_by: "operations_ui" }),
      });
    } catch {
      // Non-fatal: the UI already shows the updated assertion for this session.
    }
  }, [assertionOverride, caseRecord.review_id]);

  const handleAskLeo = useCallback(async () => {
    setLeoStep("loading");
    setLeoResult(null);
    setLeoError("");
    try {
      // Search broadly -- no semantic tag filter -- so LEO can determine the
      // correct type from encounter context rather than being constrained by
      // the NER label, which may be wrong.
      const candidates = await searchTerms(caseRecord.entity_text, 10);
      const res = await askLeoSmart(
        caseRecord.entity_text,
        caseRecord.encounter_text,
        candidates as unknown as Array<Record<string, unknown>>,
        [],
        "small",
        assertionOverride,
      );
      setLeoResult(res);
      setLeoStep("done");
    } catch {
      setLeoError("Ask LEO is not available right now.");
      setLeoStep("error");
    }
  }, [caseRecord.entity_text, caseRecord.encounter_text]);

  const leoMatch = leoResult?.matched_candidate ?? null;

  const assertionChip = ASSERTION_CHIP[assertionOverride];

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" sx={{ mb: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {index} / {total}
        </Typography>
        <Chip label={caseRecord.source} size="small" />
        {caseRecord.snomed_term && (
          <Chip
            label={`Best match: ${caseRecord.snomed_term} (${((caseRecord.score ?? 0) * 100).toFixed(0)}%)`}
            size="small"
            color="warning"
            variant="outlined"
          />
        )}
        {/* Assertion badge -- always visible; click to correct */}
        <Tooltip title="Click to correct assertion">
          <Chip
            label={assertionChip ? assertionChip.label : "Present"}
            size="small"
            color={assertionChip ? assertionChip.color : "default"}
            variant={assertionChip ? "filled" : "outlined"}
            onClick={(e) => setAssertionMenuAnchor(e.currentTarget)}
            sx={{ cursor: "pointer", ml: "auto !important" }}
          />
        </Tooltip>
        <Menu
          anchorEl={assertionMenuAnchor}
          open={Boolean(assertionMenuAnchor)}
          onClose={() => setAssertionMenuAnchor(null)}
        >
          {ASSERTION_OPTIONS.map((opt) => (
            <MenuItem
              key={opt}
              selected={opt === assertionOverride}
              onClick={() => handleCorrectAssertion(opt)}
            >
              {opt}
            </MenuItem>
          ))}
        </Menu>
      </Stack>

      <Divider sx={{ mb: 1 }} />

      {/* LEO assertion warning -- shown when LEO detected the entity is not codeable */}
      {leoResult?.assertion_warning && (
        <Alert
          severity={isClinicalSafetyWarning(leoResult.assertion_warning) ? "error" : "warning"}
          sx={{
            mb: 1.5,
            py: 0.5,
            ...(isClinicalSafetyWarning(leoResult.assertion_warning) && {
              borderLeft: "4px solid",
              borderColor: "error.main",
              animation: `${safetyPulse} 2s ease-in-out infinite`,
            }),
          }}
        >
          <strong>{warningHeadline(leoResult.assertion_warning)}</strong>{" "}
          {leoResult.assertion_warning}
        </Alert>
      )}

      {/* Contextual alerts based on assertion */}
      {assertionOverride === "absent" && (
        <Alert severity="warning" sx={{ mb: 1.5, py: 0.5 }}>
          This finding appears to be negated in the record. Suppressing is likely correct.
        </Alert>
      )}
      {assertionOverride === "declined" && (
        <Alert severity="info" sx={{ mb: 1.5, py: 0.5 }}>
          The patient declined this. Code the underlying procedure using its normal SNOMED
          concept -- Ask LEO will suggest the right code and mark it as declined. The
          timeline will then show it was offered but not accepted.
        </Alert>
      )}
      {assertionOverride === "hypothetical" && (
        <Alert severity="info" sx={{ mb: 1.5, py: 0.5 }}>
          This procedure was planned or awaiting. Check whether it was completed
          before accepting a code.
        </Alert>
      )}

      {caseRecord.suggested_label && (
        <Alert severity="warning" sx={{ mb: 1.5, py: 0.5 }}>
          <strong>Semantic tag mismatch:</strong> LLM extracted this as &apos;{caseRecord.entity_label.replace(/_/g, " ")}&apos;,
          but the SNOMED resolver suggests &apos;{caseRecord.suggested_label.replace(/_/g, " ")}&apos;
          {caseRecord.tag_mismatch_delta != null && (
            <> (score delta: {((caseRecord.tag_mismatch_delta) * 100).toFixed(0)}%)</>
          )}.
          Consider correcting the entity type above before coding.
        </Alert>
      )}

      <Typography
        variant="body2"
        sx={{ fontFamily: "monospace", bgcolor: "grey.50", p: 1.5, borderRadius: 1, mb: 2, whiteSpace: "pre-wrap", wordBreak: "break-word" }}
      >
        {caseRecord.encounter_text}
      </Typography>

      {/* Encounter context -- other entities extracted from the same encounter */}
      <EncounterContextPanel
        siblings={encounterSiblings}
        currentReviewId={caseRecord.review_id}
      />

      {/* Ask LEO inline result */}
      {leoStep === "loading" && (
        <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 1.5 }}>
          <CircularProgress aria-label="Loading" size={14} />
          <Typography variant="body2" color="text.secondary">LEO is reading the encounter context...</Typography>
        </Stack>
      )}

      {leoStep === "error" && (
        <Alert severity="warning" sx={{ mb: 1.5, py: 0.5 }}>{leoError}</Alert>
      )}

      {leoStep === "done" && leoResult && (
        <Box sx={{ mb: 1.5, p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1, bgcolor: "background.paper" }}>
          {leoResult.alternative_query_used && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
              Also searched: &quot;{leoResult.alternative_query_used}&quot;
            </Typography>
          )}
          {leoResult.is_ambiguous || !leoMatch ? (
            <Alert severity="info" sx={{ py: 0.25, mb: 1 }}>
              <Typography variant="caption">{leoResult.reason || "LEO could not determine the correct code from this context. Please search manually."}</Typography>
            </Alert>
          ) : (
            <>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                {leoResult.reason}
              </Typography>
              <Box sx={{ p: 1, bgcolor: "action.hover", borderRadius: 1, mb: 0.75 }}>
                <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" sx={{ mb: 0.5 }}>
                  <Typography variant="body2" fontWeight={600}>{leoMatch.term}</Typography>
                  {leoResult.assertion && leoResult.assertion !== "present" && (
                    <Tooltip title={`LEO: code the procedure with assertion '${leoResult.assertion}' -- it will show as ${leoResult.assertion} in the patient timeline`}>
                      <Chip
                        label={leoResult.assertion}
                        size="small"
                        color={leoResult.assertion === "declined" ? "warning" : "default"}
                        variant="filled"
                        sx={{ fontWeight: 600, fontSize: "0.7rem" }}
                      />
                    </Tooltip>
                  )}
                </Stack>
                <Stack direction="row" alignItems="center" gap={1} sx={{ mt: 0.25 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace", flexGrow: 1 }}>
                    SNOMED: {leoMatch.snomed_concept_id}
                  </Typography>
                  <Tooltip title="LEO confidence">
                    <Box sx={{ width: 40, flexShrink: 0 }}>
                      <LinearProgress
                        variant="determinate"
                        value={90}
                        color="success"
                        sx={{ height: 4, borderRadius: 2 }}
                      />
                    </Box>
                  </Tooltip>
                  <Typography variant="caption" color="text.secondary">90%</Typography>
                </Stack>
              </Box>
            </>
          )}
        </Box>
      )}

      {/* Inline suppress form */}
      {suppressOpen && (() => {
        const activeWarning = leoResult?.assertion_warning || initialLeoResult?.assertion_warning;
        const isSafety = isClinicalSafetyWarning(activeWarning);
        return (
        <Box sx={{
          mt: 1, mb: 1.5, p: 1.5, border: "1px solid",
          borderColor: isSafety ? "error.main" : "warning.main",
          borderRadius: 1,
          ...(isSafety && { bgcolor: "rgba(220, 38, 38, 0.04)" }),
        }}>
          {activeWarning ? (
            <Typography variant="caption" color={isSafety ? "error.main" : "text.secondary"} sx={{ display: "block", mb: 1 }}>
              {isSafety
                ? <>This entity was incorrectly extracted as a diagnosis from a lab value. Suppressing will prevent this false positive in future pipeline runs.{" "}
                    <strong>A context phrase is required</strong> so only this specific context is suppressed,
                    not every mention of &apos;{caseRecord.entity_text}&apos;.
                    LEO has suggested a phrase below -- edit it if needed.</>
                : <>This will suppress &apos;{caseRecord.entity_text}&apos; in future pipeline runs.{" "}
                    <strong>A context phrase is required</strong> so only this specific context is suppressed,
                    not every mention of &apos;{caseRecord.entity_text}&apos;.
                    LEO has suggested a phrase below -- edit it if needed.</>
              }
            </Typography>
          ) : (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              This will suppress &apos;{caseRecord.entity_text}&apos; in future pipeline runs.
              Add a context phrase to make the rule narrower (recommended for short terms).
            </Typography>
          )}
          <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap">
            <TextField
              size="small"
              placeholder="Type a phrase from the encounter text"
              label="Context phrase"
              value={contextPhrase}
              onChange={(e) => {
                setContextPhrase(e.target.value);
                setPhraseSource("user");
              }}
              helperText={
                phraseSource === "leo"
                  ? "LEO suggested this -- edit to narrow the rule further if needed"
                  : undefined
              }
              FormHelperTextProps={{ sx: { color: "info.main" } }}
              required={Boolean(leoResult?.assertion_warning || initialLeoResult?.assertion_warning)}
              sx={{ flex: 1, minWidth: 200 }}
            />
            <Button
              size="small"
              variant="contained"
              color="warning"
              onClick={handleSuppress}
              disabled={
                suppressing ||
                (Boolean(leoResult?.assertion_warning || initialLeoResult?.assertion_warning) &&
                  contextPhrase.trim() === "")
              }
              startIcon={suppressing ? <CircularProgress aria-label="Loading" size={14} color="inherit" /> : undefined}
            >
              {suppressing ? "Suppressing..." : "Confirm suppress"}
            </Button>
            <Button size="small" variant="text" onClick={() => { setSuppressOpen(false); setSuppressError(""); }}>
              Cancel
            </Button>
          </Stack>
          {suppressError && (
            <Typography variant="caption" color="error" sx={{ display: "block", mt: 0.5 }}>
              {suppressError}
            </Typography>
          )}
        </Box>
        );
      })()}

      <Stack direction="row" spacing={1} flexWrap="wrap">
        {leoStep === "done" && leoMatch && !leoResult?.assertion_warning ? (
          <>
            <Button
              variant="contained"
              size="small"
              onClick={() => onAcceptLeo(leoMatch, leoResult?.assertion ?? "present")}
              disabled={busy || suppressing}
              startIcon={busy ? <CircularProgress aria-label="Loading" size={14} color="inherit" /> : undefined}
            >
              {busy ? "Coding..." : "Accept LEO suggestion"}
            </Button>
            <Button variant="outlined" size="small" onClick={onCodeThis} disabled={busy || suppressing}>
              Search differently
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="outlined"
              size="small"
              onClick={onCodeThis}
              disabled={busy || leoStep === "loading" || suppressing}
              startIcon={busy ? <CircularProgress aria-label="Loading" size={14} /> : undefined}
            >
              {busy ? "Coding..." : "Code this record"}
            </Button>
            {leoStep !== "loading" && (
              <Button
                variant="outlined"
                size="small"
                color="secondary"
                onClick={handleAskLeo}
                disabled={busy || suppressing}
              >
                Ask LEO
              </Button>
            )}
          </>
        )}
        {!suppressOpen && (
          <Button
            size="small"
            variant="outlined"
            color="warning"
            onClick={() => setSuppressOpen(true)}
            disabled={busy || suppressing || leoStep === "loading"}
            sx={{ ml: "auto" }}
          >
            Suppress
          </Button>
        )}
      </Stack>
    </Paper>
  );
}
