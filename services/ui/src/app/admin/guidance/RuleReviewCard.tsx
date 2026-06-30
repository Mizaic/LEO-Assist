/**
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 */
"use client";

import { useCallback, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CompareArrowsIcon from "@mui/icons-material/CompareArrows";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import { motion as fm } from "framer-motion";

import {
  RuleDetailPanel,
  type LogicTreeNode,
  type CriterionResult,
  type RuleCriterion as Criterion,
} from "./RuleLogicView";
import { compareIsoDateTimeAsc } from "@/lib/dateSort";
import { STRENGTH_LABELS } from "./EditRuleDialog/copy";

// Imported as types-only to avoid runtime circular dependency
import type { Rule, PromoteResult, RuleStatusFilter } from "./ruleReviewTypes";

// -- Pure utility (re-exported via RuleReviewSection for test compatibility) --

/** Renders an ISO 8601 timestamp as "Updated N minutes ago" style hint. */
export function formatRelativeUpdatedAt(
  iso: string | undefined | null,
  now: Date = new Date(),
): string {
  if (!iso) return "";
  const updated = new Date(iso);
  if (Number.isNaN(updated.getTime())) return "";
  const diffMs = now.getTime() - updated.getTime();
  if (diffMs < 0) return "Updated just now";
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return "Updated just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Updated ${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Updated ${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `Updated ${days} day${days === 1 ? "" : "s"} ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `Updated ${months} month${months === 1 ? "" : "s"} ago`;
  const years = Math.floor(days / 365);
  return `Updated ${years} year${years === 1 ? "" : "s"} ago`;
}

// -- Status accent colours ----------------------------------------------------

const STATUS_ACCENT: Record<RuleStatusFilter, string> = {
  pending_review: "#B45309",
  active: "#047857",
  superseded: "#475569",
};

// -- Interfaces ---------------------------------------------------------------

export interface RuleCardCallbacks {
  onToggle: () => void;
  onEdit: () => void;
  onApprove?: () => void;
  onReject?: () => void;
}

export interface RuleAccordionCardProps {
  rule: Rule;
  expanded: boolean;
  busy: string | null;
  index: number;
  statusFilter: RuleStatusFilter;
  callbacks?: RuleCardCallbacks;
  // Flat prop alternatives (used by RuleReviewSection inline rendering)
  onToggle?: () => void;
  onEdit?: () => void;
  onApprove?: () => void;
  onReject?: () => void;
}

export interface SessionApprovedRowProps {
  rule: Rule;
  promotedResult?: PromoteResult;
  promoteBusy: boolean;
  onEdit: () => void;
  onPromote: () => void;
}

// -- Helpers ------------------------------------------------------------------

function strengthChipLabel(strength: string): string {
  const hit = STRENGTH_LABELS.find((row) => row.value === strength);
  return hit?.label ?? strength.replace(/_/g, " ");
}

function generationOutcomeLabel(outcome: string): string {
  switch (outcome) {
    case "extraction_failed": return "Needs manual authoring";
    case "subgraph_unavailable": return "Generation unavailable";
    case "no_rule_expected": return "Confirm no rule needed";
    default: return outcome.replace(/_/g, " ");
  }
}

// -- Diff components ----------------------------------------------------------

function DiffChip({ criterion, kind }: { criterion: Criterion; kind: "added" | "removed" | "unchanged" }) {
  const palette = {
    added: { bg: "#e8f5e9", border: "#66bb6a", icon: <AddCircleOutlineIcon sx={{ fontSize: 14, color: "success.dark" }} /> },
    removed: { bg: "#ffebee", border: "#ef5350", icon: <RemoveCircleOutlineIcon sx={{ fontSize: 14, color: "error.dark" }} /> },
    unchanged: { bg: "#f5f5f5", border: "#bdbdbd", icon: null as React.ReactNode },
  }[kind];

  return (
    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.4, px: 0.8, py: 0.2, borderRadius: 1, border: `1px solid ${palette.border}`, bgcolor: palette.bg, fontSize: "0.75rem", mr: 0.5, mb: 0.5 }}>
      {palette.icon}
      {criterion.preferred_term || criterion.concept_id}
      <Typography component="span" sx={{ color: "text.disabled", fontSize: "0.65rem", ml: 0.3 }}>
        ({criterion.predicate.toLowerCase()})
      </Typography>
    </Box>
  );
}

interface PredecessorDecision { action: string; reviewer: string; timestamp: string; reason: string; }
interface DiffData {
  has_predecessor: boolean;
  predecessor?: { decisions: PredecessorDecision[]; plain_english: string; };
  diff?: { added: Criterion[]; removed: Criterion[]; unchanged: Criterion[]; };
  diff_summary?: { added_count: number; removed_count: number; unchanged_count: number; };
}

function DiffContentPanel({ data }: { data: DiffData }) {
  if (!data.has_predecessor) {
    return <Typography variant="body2" color="text.secondary">This is the first version of this rule -- no previous decisions to compare.</Typography>;
  }
  const { added_count = 0, removed_count = 0 } = data.diff_summary ?? {};
  return (
    <>
      {(data.predecessor?.decisions?.length ?? 0) > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Previous decisions</Typography>
          <Stack spacing={0.5} sx={{ mt: 0.5 }}>
            {[...data.predecessor!.decisions].sort((a, b) => compareIsoDateTimeAsc(a.timestamp, b.timestamp)).map((d, i) => (
              <Box key={i} sx={{ fontSize: "0.78rem" }}>
                <Chip label={d.action} size="small" color={d.action === "approve" ? "success" : d.action === "reject" ? "error" : "default"} sx={{ mr: 0.5, height: 18, fontSize: "0.68rem" }} />
                <Typography component="span" variant="caption" color="text.secondary">
                  {d.reviewer} · {d.timestamp ? new Date(d.timestamp).toLocaleDateString() : ""}
                  {d.reason ? ` -- "${d.reason}"` : ""}
                </Typography>
              </Box>
            ))}
          </Stack>
        </Box>
      )}
      {data.predecessor?.plain_english && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Previous rule said</Typography>
          <Typography variant="body2" sx={{ mt: 0.3, fontStyle: "italic", color: "text.secondary" }}>{data.predecessor.plain_english}</Typography>
        </Box>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>Criteria changes</Typography>
      <Box sx={{ mt: 0.5 }}>
        {added_count === 0 && removed_count === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.78rem" }}>No criteria changed.</Typography>
        ) : (
          <>
            {(data.diff?.removed ?? []).map((c) => <DiffChip key={c.concept_id} criterion={c} kind="removed" />)}
            {(data.diff?.added ?? []).map((c) => <DiffChip key={c.concept_id} criterion={c} kind="added" />)}
            {(data.diff?.unchanged ?? []).map((c) => <Tooltip key={c.concept_id} title="Unchanged" arrow><span><DiffChip criterion={c} kind="unchanged" /></span></Tooltip>)}
          </>
        )}
      </Box>
    </>
  );
}

function DiffPanel({ ruleId }: { ruleId: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<DiffData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (data) { setOpen((o) => !o); return; }
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`/api/guidance/rules/review/${ruleId}/diff`);
      if (!r.ok) throw new Error(r.statusText);
      setData(await r.json());
      setOpen(true);
    } catch {
      setError("Could not load version history.");
    } finally {
      setLoading(false);
    }
  }, [ruleId, data]);

  const { added_count = 0, removed_count = 0 } = data?.diff_summary ?? {};
  const hasDiff = added_count > 0 || removed_count > 0;

  return (
    <Box sx={{ mt: 1 }}>
      <Button size="small" variant="text" startIcon={loading ? <CircularProgress size={14} /> : <CompareArrowsIcon fontSize="small" />} onClick={load} disabled={loading} aria-expanded={open} sx={{ textTransform: "none", color: "text.secondary", fontSize: "0.78rem" }}>
        {open ? "Hide" : "What changed?"}
        {hasDiff && !open && <Chip label={`${added_count > 0 ? `+${added_count}` : ""}${removed_count > 0 ? ` -${removed_count}` : ""}`} size="small" color={removed_count > 0 ? "error" : "success"} sx={{ ml: 0.5, height: 18, fontSize: "0.68rem" }} />}
      </Button>
      {error && <Alert severity="warning" sx={{ mt: 1, py: 0.5 }}>{error}</Alert>}
      <Collapse in={open}>
        {data && <Box sx={{ mt: 1.5, p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1, bgcolor: "grey.50" }}><DiffContentPanel data={data} /></Box>}
      </Collapse>
    </Box>
  );
}

// -- Card sub-components ------------------------------------------------------

function RuleCardHeader({ rule }: { rule: Rule }) {
  return (
    <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap" sx={{ mb: 0.3 }}>
      <Chip label={rule.guideline_id} size="small" color="primary" />
      {rule.guideline_version && rule.guideline_version > 1 && <Chip label={`v${rule.guideline_version}`} size="small" color="warning" variant="outlined" />}
      {rule.strength && rule.strength !== "unspecified" && <Tooltip title={strengthChipLabel(rule.strength)} arrow><Chip label={rule.strength.replace(/_/g, " ")} size="small" variant="outlined" /></Tooltip>}
      {rule.has_predecessor && <Chip icon={<CompareArrowsIcon />} label="Updated" size="small" color="warning" variant="outlined" />}
      {rule.is_default && <Chip label="Fallback rule" size="small" color="secondary" variant="outlined" />}
      {rule.generation_outcome && rule.generation_outcome !== "success" && <Chip label={generationOutcomeLabel(rule.generation_outcome)} size="small" color="warning" variant="filled" />}
      {rule.needs_human_review && !rule.generation_outcome && <Chip label="Needs review" size="small" color="warning" variant="outlined" />}
      {rule.chapter_title && <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.75rem" }}>{rule.chapter_title}</Typography>}
      {rule.updated_at && (
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.75rem", fontStyle: "italic" }} data-testid="rule-updated-relative">
          {formatRelativeUpdatedAt(rule.updated_at)}
        </Typography>
      )}
    </Stack>
  );
}

function RuleGenerationAlert({ rule }: { rule: Rule }) {
  if (!rule.generation_errors?.length) return null;
  if (rule.generation_outcome === "no_rule_expected") {
    return (
      <Alert severity="info" sx={{ mb: 1.5 }}>
        This recommendation describes a service or discussion -- no coded rule is needed.
        <Box component="ul" sx={{ mt: 1, mb: 0, pl: 2.5 }}>
          {rule.generation_errors.slice(0, 5).map((err) => (
            <Typography key={err} component="li" variant="caption" sx={{ display: "list-item" }}>{err}</Typography>
          ))}
        </Box>
      </Alert>
    );
  }
  return (
    <Alert severity="warning" sx={{ mb: 1.5 }}>
      AI generation did not finish for this recommendation. Open Edit rule to author criteria manually.
      <Box component="ul" sx={{ mt: 1, mb: 0, pl: 2.5 }}>
        {rule.generation_errors.slice(0, 5).map((err) => (
          <Typography key={err} component="li" variant="caption" sx={{ display: "list-item" }}>{err}</Typography>
        ))}
      </Box>
    </Alert>
  );
}

function RuleCardActions({ rule, callbacks, isBusy }: { rule: Rule; callbacks: RuleCardCallbacks; isBusy: boolean }) {
  if (rule.generation_outcome === "no_rule_expected") {
    return (
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 2.5, pt: 2, borderTop: "1px solid", borderColor: "divider" }}>
        {callbacks.onApprove && (
          <Button variant="contained" color="success" size="small" disabled={isBusy} onClick={(e) => { e.stopPropagation(); callbacks.onApprove!(); }} aria-label={`Confirm no rule needed for ${rule.rule_id}`}>
            Confirm no rule needed
          </Button>
        )}
        <Button variant="outlined" size="small" disabled={isBusy} onClick={(e) => { e.stopPropagation(); callbacks.onEdit(); }} aria-label={`Edit rule ${rule.rule_id}`}>Edit</Button>
        {isBusy && <CircularProgress size={16} aria-label="Saving decision" />}
      </Stack>
    );
  }
  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 2.5, pt: 2, borderTop: "1px solid", borderColor: "divider" }}>
      {callbacks.onApprove && <Button variant="contained" color="success" size="small" disabled={isBusy} onClick={(e) => { e.stopPropagation(); callbacks.onApprove!(); }} aria-label={`Approve rule ${rule.rule_id}`}>Looks right</Button>}
      <Button variant="outlined" size="small" disabled={isBusy} onClick={(e) => { e.stopPropagation(); callbacks.onEdit(); }} aria-label={`Edit rule ${rule.rule_id}`}>Edit</Button>
      {callbacks.onReject && <Button variant="outlined" color="error" size="small" disabled={isBusy} onClick={(e) => { e.stopPropagation(); callbacks.onReject!(); }} aria-label={`Reject rule ${rule.rule_id}`}>Reject</Button>}
      {isBusy && <CircularProgress size={16} aria-label="Saving decision" />}
    </Stack>
  );
}

function RuleCardBody({ rule, callbacks, isBusy }: { rule: Rule; callbacks: RuleCardCallbacks; isBusy: boolean }) {
  const recChanged =
    rule.previous_recommendation_text &&
    rule.previous_recommendation_text !== rule.recommendation_text;

  return (
    <Box sx={{ mt: 1.75, ml: { xs: 0, sm: 3 } }}>
      {recChanged && (
        <Alert
          severity="warning"
          sx={{ mb: 1, fontSize: "0.82rem" }}
          icon={false}
        >
          <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.5 }}>
            This recommendation changed in the latest NICE update
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
            Previous wording:
          </Typography>
          <Typography variant="caption" sx={{ display: "block", fontStyle: "italic", color: "text.secondary" }}>
            {rule.previous_recommendation_text}
          </Typography>
        </Alert>
      )}
      {rule.recommendation_text && (
        <Box sx={{ p: 2, bgcolor: "background.paper", borderRadius: 1.5, border: "1px solid", borderColor: "divider", mb: 0.5 }}>
          <Typography variant="overline" color="text.secondary" sx={{ fontWeight: 700, display: "block", mb: 0.75, letterSpacing: 0.6 }}>
            NICE recommendation{recChanged ? " (updated)" : ""}
          </Typography>
          <Typography variant="body2" sx={{ lineHeight: 1.7 }}>{rule.recommendation_text}</Typography>
        </Box>
      )}
      <RuleGenerationAlert rule={rule} />
      <RuleDetailPanel rule={rule} />
      {rule.has_predecessor && <Box sx={{ mt: 1.5 }}><DiffPanel ruleId={rule.rule_id} /></Box>}
      <RuleCardActions rule={rule} callbacks={callbacks} isBusy={isBusy} />
    </Box>
  );
}

// -- Session-approved row (used by RuleReviewList) ----------------------------

export function SessionApprovedRow({ rule, promotedResult, promoteBusy, onEdit, onPromote }: SessionApprovedRowProps) {
  return (
    <Box sx={{ p: 1.5, border: "1px solid", borderColor: "success.200", borderLeft: "3px solid", borderLeftColor: "success.main", borderRadius: 1.5 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
        <CheckCircleOutlineIcon color="success" fontSize="small" />
        <Chip label={rule.guideline_id} size="small" color="success" variant="outlined" />
        <Chip label="Approved" size="small" color="success" />
      </Stack>
      <Typography variant="body2" sx={{ mb: 1, color: "text.secondary", fontSize: "0.82rem" }}>
        {rule.recommendation_text || rule.name || rule.rule_id}
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <Button size="small" variant="outlined" color="primary" onClick={onEdit} aria-label={`Edit approved rule ${rule.rule_id}`}>Edit</Button>
        {promotedResult ? (
          <Typography variant="caption" color="success.main">
            Added {promotedResult.concepts_added} code{promotedResult.concepts_added !== 1 ? "s" : ""} to {promotedResult.domain_name}.
          </Typography>
        ) : (
          <Button size="small" variant="outlined" color="info" disabled={promoteBusy} onClick={onPromote} aria-label={`Add rule ${rule.rule_id} medical codes to domain`}>
            {promoteBusy ? "Adding..." : "Add to domain"}
          </Button>
        )}
      </Stack>
    </Box>
  );
}

// -- Main accordion card ------------------------------------------------------

export function RuleAccordionCard({ rule, expanded, busy, index, statusFilter, callbacks, onToggle, onEdit, onApprove, onReject }: RuleAccordionCardProps) {
  // Support both flat props and callbacks object
  const cb: RuleCardCallbacks = callbacks ?? {
    onToggle: onToggle ?? (() => undefined),
    onEdit: onEdit ?? (() => undefined),
    onApprove,
    onReject,
  };
  const isBusy = busy === rule.rule_id;
  const accent = STATUS_ACCENT[statusFilter] ?? STATUS_ACCENT.pending_review;

  return (
    <fm.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: "easeOut", delay: Math.min(index, 20) * 0.04 }}
      style={{ position: "relative", background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 12, padding: 14, marginBottom: 8 }}
    >
      <span aria-hidden="true" style={{ position: "absolute", left: 0, top: 14, bottom: 14, width: 3, borderRadius: 2, background: accent }} />
      <Stack direction="row" alignItems="flex-start" spacing={1} sx={{ cursor: "pointer" }} onClick={cb.onToggle} role="button" aria-expanded={expanded} aria-label={`Toggle rule from ${rule.guideline_id}`}>
        {expanded ? <ExpandMoreIcon sx={{ color: "primary.main", mt: 0.3, flexShrink: 0, fontSize: 18 }} /> : <ChevronRightIcon sx={{ color: "text.disabled", mt: 0.3, flexShrink: 0, fontSize: 18 }} />}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <RuleCardHeader rule={rule} />
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.8rem", fontStyle: "italic", overflow: "hidden", display: "-webkit-box", WebkitLineClamp: expanded ? undefined : 2, WebkitBoxOrient: "vertical" }}>
            {rule.recommendation_text || rule.plain_english}
          </Typography>
        </Box>
      </Stack>
      <Collapse in={expanded}>
        <RuleCardBody rule={rule} callbacks={cb} isBusy={isBusy} />
      </Collapse>
    </fm.div>
  );
}
