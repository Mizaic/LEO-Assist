/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-6CD07544
 *   Also implements: DO-F8631A82
 *   DI: DI-1B8AC856, DI-A0579B64
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-6CD07544")
 */
"use client";

import { useCallback, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { AskLeoBusyMark } from "@/components/AskLeoBusyMark";
import TermSearch from "@/components/TermSearch";
import { askLeoSmart, searchTerms } from "@/lib/api/legacy";
import ConfirmDialog from "@/components/ConfirmDialog";
import type { AskLeoSmartResult, DecisionTier, TermSearchResult } from "@/lib/types";
import { TIER_META } from "@/lib/types";
import CodingReviewCasesModal from "@/components/operations/CodingReviewCasesModal";
import Tooltip from "@mui/material/Tooltip";
import { getTerminologyConfidenceExplanation } from "@/lib/terminologyConfidence";

// -- Types -------------------------------------------------------------------

export interface ReviewItem {
  id: string;
  kind: "coding" | "hitl" | "context";
  entityText: string;
  entityLabel: string;
  count: number;
  confidence: number | null;
  uncoded: boolean;
  question: string;
  explanation: string;
  taskType?: string;
  reason?: string;
  suggestedSemanticTag?: string;
  /** A sample encounter text from the training label - used to extract unit context. */
  sampleEncounterText?: string;
  /** Assertion from context detection (possible, historical, family, etc). */
  assertion?: string;
  /** Safety layer tier (1 = auto-code, 2 = review, 3 = blocked). */
  decisionTier?: DecisionTier | null;
  /** Machine-readable reason from the tier classifier. */
  tierReason?: string | null;
  /** Tier classifier decision string. */
  tierDecision?: string | null;
  /** When a semantic tag mismatch is detected, the NER label the SNOMED resolver suggests. */
  suggestedLabel?: string;
  /** Score delta between the top candidate's tag and the best same-tag candidate. */
  tagMismatchDelta?: number;
  /** Priority order for surface form tasks (lower = higher priority). */
  surfaceFormPriority?: number;
  /** Pre-resolved suggested concept ID for surface form tasks. */
  suggestedConceptId?: string;
  /** Pre-resolved suggested concept term for surface form tasks. */
  suggestedConceptTerm?: string;
}

type TypeLabel = { text: string; color: "warning" | "info" | "error" | "default" };

function typeLabel(item: ReviewItem): TypeLabel {
  if (item.kind === "context") {
    const assertionChip: Record<string, TypeLabel> = {
      possible: { text: "Uncertain context", color: "warning" },
      historical: { text: "Historical context", color: "info" },
      family: { text: "Family history", color: "info" },
    };
    return assertionChip[item.assertion ?? ""] ?? { text: "Context check", color: "warning" };
  }
  if (item.kind === "coding") {
    if (item.uncoded) return { text: "Missing code", color: "warning" };
    return { text: "Check this code", color: "info" };
  }
  const map: Record<string, TypeLabel> = {
    exclusion_conflict: { text: "Inclusion check", color: "error" },
    peer_review: { text: "Peer review", color: "info" },
    classification: { text: "Classification check", color: "info" },
  };
  return map[item.taskType ?? ""] ?? { text: "Review needed", color: "default" };
}

// -- Tier badge --------------------------------------------------------------

const TIER_REASON_LABELS: Record<string, string> = {
  surface_form_match: "Approved surface form with high score",
  high_confidence: "High confidence match",
  medium_confidence: "Medium confidence -- check the match",
  pending_surface_form: "Surface form not yet approved",
  qualifier_assertion: "Historical or family context",
  low_confidence: "Low confidence score",
  context_failure: "Context detection failed",
  informational: "Informational mention (not a diagnosis)",
  uncertain_assertion: "Uncertain or possible assertion",
  non_codeable_assertion: "Negated, declined or hypothetical",
};

function TierBadge({ tier, reason }: { tier: DecisionTier; reason?: string | null }) {
  const meta = TIER_META[tier];
  const reasonLabel = reason ? (TIER_REASON_LABELS[reason] ?? reason) : meta.description;
  return (
    <Tooltip title={reasonLabel} arrow>
      <Chip
        label={meta.label}
        color={meta.color}
        size="small"
        variant="outlined"
        sx={{ fontWeight: 600, cursor: "default" }}
      />
    </Tooltip>
  );
}

// -- Plain-language question builders ----------------------------------------

export function buildQuestion(item: ReviewItem): string {
  if (item.kind === "context") {
    const assertionLabel: Record<string, string> = {
      possible: "uncertain",
      historical: "historical",
      family: "a family member's",
    };
    const label = assertionLabel[item.assertion ?? ""] ?? "uncertain";
    return `Is '${item.entityText}' really ${label}?`;
  }
  if (item.kind === "coding" && item.uncoded) {
    return `What code should we use for '${item.entityText}'?`;
  }
  if (item.kind === "coding") {
    return `Is the code for '${item.entityText}' correct?`;
  }
  if (item.taskType === "exclusion_conflict") {
    return "Should this patient be in the measure?";
  }
  return "Does this look right to you?";
}

export function buildExplanation(item: ReviewItem): string {
  if (item.kind === "context") {
    const assertionDesc: Record<string, string> = {
      possible: "Our system is not sure if this is confirmed. Check the record and change the context label or assign a code if it is confirmed.",
      historical: "This may be a past condition. Check the record and confirm whether it is current or historical.",
      family: "This may relate to a family member, not the patient. Check the record before coding.",
    };
    return (
      assertionDesc[item.assertion ?? ""] ??
      `We found '${item.entityText}' in ${item.count} ${item.count === 1 ? "record" : "records"} with an uncertain context. Please review.`
    );
  }
  if (item.kind === "coding" && item.uncoded) {
    return (
      `We found '${item.entityText}' in ${item.count} patient ` +
      `${item.count === 1 ? "record" : "records"} but could not match ` +
      `it to a clinical code. Search for the right one, or skip if ` +
      `you are not sure.`
    );
  }
  if (item.kind === "coding") {
    return (
      `We matched '${item.entityText}' to a code. ` +
      `${getTerminologyConfidenceExplanation(item.confidence)} ` +
      `This appears in ${item.count} ${item.count === 1 ? "record" : "records"}.`
    );
  }
  return item.reason ?? "Please review this item.";
}

// -- Bulk LEO state ----------------------------------------------------------

interface SlimCase {
  review_id: string;
  entity_text: string;
  entity_label: string;
  encounter_text: string;
  source: string;
  snomed_concept_id: string | null;
  snomed_term: string | null;
  score: number | null;
  assertion?: string;
}

interface LeoAllState {
  status: "running" | "done";
  done: number;
  total: number;
  cases: SlimCase[];
  results: Record<string, AskLeoSmartResult>;
}

// -- Card component ----------------------------------------------------------

interface Props {
  item: ReviewItem;
  onResolveCoding: (item: ReviewItem, result: TermSearchResult) => void;
  onResolveHitl: (item: ReviewItem, status: "resolved" | "dismissed") => void;
  onSkip: () => void;
  onAllCasesResolved: (item: ReviewItem) => void;
  busy: boolean;
  onAcceptSuggestion?: (item: ReviewItem) => void;
}

export default function ReviewCard({
  item,
  onResolveCoding,
  onResolveHitl,
  onSkip,
  onAllCasesResolved,
  busy,
  onAcceptSuggestion,
}: Props) {
  const [termOpen, setTermOpen] = useState(false);
  const [casesModalOpen, setCasesModalOpen] = useState(false);
  const [leoAll, setLeoAll] = useState<LeoAllState | null>(null);
  const label = typeLabel(item);

  const hintTags =
    item.entityLabel || item.suggestedSemanticTag
      ? [item.entityLabel.replace(/_/g, " ") || item.suggestedSemanticTag!]
      : undefined;

  const handleAskLeoAll = useCallback(async () => {
    // 1. Fetch all individual case records for this entity text.
    const encoded = encodeURIComponent(item.entityText);
    let cases: SlimCase[] = [];
    try {
      const data = await fetch(
        `/api/training/coding-review/queue?entity_text=${encoded}&page_size=200`,
        { credentials: "include", headers: { "X-Requested-With": "XMLHttpRequest" } },
      );
      const json = await data.json() as { items: SlimCase[] };
      cases = json.items ?? [];
    } catch {
      return;
    }
    if (cases.length === 0) {
      setCasesModalOpen(true);
      return;
    }

    setLeoAll({ status: "running", done: 0, total: cases.length, cases, results: {} });

    // 2. Run LEO for each case sequentially so we can show progress.
    const results: Record<string, AskLeoSmartResult> = {};
    for (let i = 0; i < cases.length; i++) {
      const c = cases[i];
      try {
        // Search without semantic tag filter so LEO determines the type from
        // encounter context, not from the NER label which may be wrong.
        const candidates = await searchTerms(c.entity_text, 10);
        const res = await askLeoSmart(
          c.entity_text,
          c.encounter_text,
          candidates as unknown as Array<Record<string, unknown>>,
          [],
          "small",
          c.assertion || "present",
        );
        results[c.review_id] = res;
      } catch {
        // If LEO fails for one record, leave it out so the modal shows manual fallback.
      }
      setLeoAll({ status: "running", done: i + 1, total: cases.length, cases, results: { ...results } });
    }

    // 3. Open the modal with all pre-filled results.
    setLeoAll({ status: "done", done: cases.length, total: cases.length, cases, results });
    setCasesModalOpen(true);
  }, [item.entityText, hintTags]);

  const leoRunning = leoAll?.status === "running";
  const leoReady = leoAll?.status === "done";

  return (
    <>
      <Card sx={{ animation: "cardIn 0.2s ease" }}>
        <CardContent sx={{ p: 3 }}>
          <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 2 }} flexWrap="wrap">
            <Chip label={label.text} color={label.color} size="small" />
            {item.decisionTier != null && (
              <TierBadge tier={item.decisionTier} reason={item.tierReason} />
            )}
            {item.count > 1 && (
              <Chip label={`${item.count} records`} size="small" variant="outlined" />
            )}
            {item.entityLabel && (
              <Chip
                label={item.entityLabel.replace(/_/g, " ")}
                size="small"
                variant="outlined"
                color="primary"
              />
            )}
            {item.suggestedLabel && (
              <Tooltip title={`SNOMED resolver suggests '${item.suggestedLabel.replace(/_/g, " ")}' (delta: ${((item.tagMismatchDelta ?? 0) * 100).toFixed(0)}%)`}>
                <Chip
                  label={`Tag mismatch → ${item.suggestedLabel.replace(/_/g, " ")}`}
                  size="small"
                  color="warning"
                />
              </Tooltip>
            )}
          </Stack>

          <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
            {item.question}
          </Typography>
          <Typography variant="body1" color="text.secondary" sx={{ mb: 3, lineHeight: 1.6, whiteSpace: "pre-line" }}>
            {item.explanation}
          </Typography>

          {/* LEO-all progress bar shown while running */}
          {leoRunning && leoAll && (
            <Box sx={{ mb: 2 }}>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="body2" color="text.secondary">
                  LEO is reading each encounter...
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {leoAll.done} / {leoAll.total}
                </Typography>
              </Stack>
              <LinearProgress
                variant="determinate"
                value={leoAll.total > 0 ? (leoAll.done / leoAll.total) * 100 : 0}
              />
            </Box>
          )}

          {item.kind === "coding" || item.kind === "context" ? (
            <CodingActions
              item={item}
              busy={busy || leoRunning}
              onSearch={() => setTermOpen(true)}
              onReviewCases={() => setCasesModalOpen(true)}
              onAskLeoAll={handleAskLeoAll}
              leoRunning={leoRunning}
              leoReady={leoReady}
              onSkip={onSkip}
              onAcceptSuggestion={onAcceptSuggestion ? () => onAcceptSuggestion(item) : undefined}
            />
          ) : (
            <HitlActions item={item} busy={busy} onResolve={onResolveHitl} onSkip={onSkip} />
          )}
        </CardContent>
      </Card>

      {termOpen && (
        <TermSearch
          initialQuery={item.entityText}
          hintTags={hintTags}
          entityText={item.entityText}
          entityLabel={item.entityLabel.replace(/_/g, " ")}
          initialEvidence={item.sampleEncounterText}
          onSelect={(r) => {
            setTermOpen(false);
            onResolveCoding(item, r);
          }}
          onClose={() => setTermOpen(false)}
          onCorrection={() => {}}
        />
      )}

      {casesModalOpen && (
        <CodingReviewCasesModal
          item={item}
          open={casesModalOpen}
          initialCases={leoAll?.cases}
          prefilledResults={leoReady ? leoAll?.results : undefined}
          onClose={() => { setCasesModalOpen(false); setLeoAll(null); }}
          onAllResolved={() => {
            setCasesModalOpen(false);
            setLeoAll(null);
            onAllCasesResolved(item);
          }}
        />
      )}
    </>
  );
}

// -- Sub-components ----------------------------------------------------------

function CodingActions({
  item,
  busy,
  onSearch,
  onReviewCases,
  onAskLeoAll,
  leoRunning,
  leoReady,
  onSkip,
  onAcceptSuggestion,
}: {
  item: ReviewItem;
  busy: boolean;
  onSearch: () => void;
  onReviewCases: () => void;
  onAskLeoAll: () => void;
  leoRunning: boolean;
  leoReady: boolean;
  onSkip: () => void;
  onAcceptSuggestion?: () => void;
}) {
  return (
    <Stack direction="row" gap={1} flexWrap="wrap">
      {onAcceptSuggestion && (
        <Button
          variant="contained"
          color="success"
          onClick={onAcceptSuggestion}
          disabled={busy}
          sx={{ flex: 1 }}
        >
          Accept suggestion
        </Button>
      )}
      <Button
        variant={onAcceptSuggestion ? "outlined" : "contained"}
        onClick={onSearch}
        disabled={busy}
        sx={{ flex: 1 }}
      >
        {item.uncoded ? "Search for the right code" : "Search for a better code"}
      </Button>
      {item.count > 1 && (
        <>
          <Button
            variant="outlined"
            color="secondary"
            onClick={onAskLeoAll}
            disabled={busy}
            startIcon={leoRunning ? <AskLeoBusyMark /> : undefined}
            aria-busy={leoRunning}
          >
            {leoRunning
              ? "LEO working..."
              : leoReady
              ? `Review ${item.count} cases (LEO ready)`
              : `Ask LEO for all ${item.count} cases`}
          </Button>
          <Button variant="outlined" onClick={onReviewCases} disabled={busy}>
            Review {item.count} cases
          </Button>
        </>
      )}
      <Button variant="outlined" onClick={onSkip} disabled={busy}>
        Skip
      </Button>
    </Stack>
  );
}

function HitlActions({
  item,
  busy,
  onResolve,
  onSkip,
}: {
  item: ReviewItem;
  busy: boolean;
  onResolve: (item: ReviewItem, status: "resolved" | "dismissed") => void;
  onSkip: () => void;
}) {
  const [confirmDismiss, setConfirmDismiss] = useState(false);
  return (
    <>
      <Stack direction="row" gap={1}>
        <Button
          variant="contained"
          color="success"
          onClick={() => onResolve(item, "resolved")}
          disabled={busy}
          fullWidth
        >
          Approve
        </Button>
        <Button
          variant="outlined"
          color="error"
          onClick={() => setConfirmDismiss(true)}
          disabled={busy}
          fullWidth
        >
          Dismiss
        </Button>
        <Button variant="outlined" onClick={onSkip} disabled={busy}>
          Skip
        </Button>
      </Stack>
      {confirmDismiss && (
        <ConfirmDialog
          title="Dismiss this review item?"
          body={`"${item.entityText}" will be removed from the review queue. This cannot be undone.`}
          confirmLabel="Dismiss"
          variant="danger"
          onConfirm={() => { onResolve(item, "dismissed"); setConfirmDismiss(false); }}
          onCancel={() => setConfirmDismiss(false)}
        />
      )}
    </>
  );
}

