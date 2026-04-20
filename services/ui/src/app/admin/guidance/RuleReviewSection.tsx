/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E647765A")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CompareArrowsIcon from "@mui/icons-material/CompareArrows";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import ConfirmDialog from "@/components/ConfirmDialog";
import EditRuleDialog, { type EditableRule } from "./EditRuleDialog";
import type { LogicCriterion } from "./EditRuleDialog/types";
import { compareIsoDateTimeAsc } from "@/lib/dateSort";
import {
  RuleDetailPanel,
  type CriterionResult,
  type LogicTreeNode,
  type RuleCriterion as Criterion,
} from "./RuleLogicView";

interface ActionConcept {
  snomed_concept_id: string | null;
  preferred_term: string;
  semantic_tag?: string;
  term?: string;
}

interface Rule {
  rule_id: string;
  name: string;
  status: string;
  strength: string;
  schema_version?: number;
  guideline_id: string;
  guideline_version?: number;
  chapter_title?: string;
  recommendation_text: string;
  plain_english: string;
  present_criteria: Criterion[];
  absent_criteria: Criterion[];
  logic_tree?: LogicTreeNode | null;
  criteria_concepts?: CriterionResult[];
  action?: ActionConcept | null;
  has_predecessor: boolean;
  predecessor_id?: string;
  // Surfaced by the BE list endpoint for the Active-list staleness sort
  // (DI-LEO-AI-528 AC-001 / AC-002). updated_at coalesces server-side
  // to created_at when the rule has never been edited; reviewed_at +
  // reviewed_by are empty strings until the first decision lands so
  // the JSON shape stays stable for FE consumers.
  created_at?: string;
  updated_at?: string;
  reviewed_at?: string;
  reviewed_by?: string;
}

interface PromoteResult {
  domain_id: string;
  domain_name: string;
  concepts_added: number;
}

interface PredecessorDecision {
  action: string;
  reviewer: string;
  timestamp: string;
  reason: string;
}

interface DiffData {
  has_predecessor: boolean;
  predecessor?: {
    rule_id: string;
    name: string;
    status: string;
    recommendation_text: string;
    recommendation_number: string;
    superseded_at: string;
    plain_english: string;
    present_criteria: Criterion[];
    absent_criteria: Criterion[];
    decisions: PredecessorDecision[];
  };
  diff?: {
    added: Criterion[];
    removed: Criterion[];
    unchanged: Criterion[];
  };
  diff_summary?: {
    added_count: number;
    removed_count: number;
    unchanged_count: number;
  };
}

interface Props {
  refreshKey?: number;
}

/**
 * Render a FastAPI / Pydantic ``detail`` payload as a human-readable string.
 *
 * - A 422 returns ``detail`` as an array of ``{loc, msg, type, ...}`` objects.
 *   The previous code did ``String(arr)`` which produced
 *   ``"[object Object],[object Object],..."`` and hid the real cause.
 * - A 4xx raised via ``HTTPException(detail=...)`` returns ``detail`` as a
 *   plain string -- pass it through.
 * - Anything else: best-effort JSON.stringify so the reviewer at least sees
 *   the shape, never an opaque ``[object Object]``.
 */
export function formatApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d === "string") return d;
        if (d && typeof d === "object") {
          const obj = d as Record<string, unknown>;
          const loc = Array.isArray(obj.loc)
            ? (obj.loc as unknown[])
                .filter((x) => x !== "body" && x !== "updates")
                .join(".")
            : "";
          const msg = typeof obj.msg === "string" ? obj.msg : "";
          if (loc && msg) return `${loc}: ${msg}`;
          if (msg) return msg;
        }
        try {
          return JSON.stringify(d);
        } catch {
          return String(d);
        }
      })
      .filter((s) => s.length > 0);
    return parts.join("; ");
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return "";
}

/**
 * Build the in-session "approved" cache row from the pre-edit ``Rule`` plus
 * the payload the dialog just POSTed. Exposed (and exported) so a
 * regression test can pin the merge: a previous version of this code only
 * carried ``name`` / ``strength`` over from the payload, which silently
 * dropped any newly added synonym seeds, exclusions, or concept swaps --
 * so re-opening the rule after save looked like a persistence failure
 * even though Neo4j had the new tree.
 *
 * The merge MUST always overlay ``logic_tree`` from the payload (the dialog
 * is the source of truth for the new tree), and overlay ``action`` only when
 * the reviewer changed it (the BE _decide_rule_with_edits coalesces null
 * action_json back to the predecessor's action for the same reason).
 */
export function mergeEditedRuleIntoCache(
  previous: Rule,
  newRuleId: string,
  payload: {
    name: string;
    strength: string;
    logic_tree: Record<string, unknown>;
    action?: ActionConcept;
  },
): Rule {
  return {
    ...previous,
    rule_id: newRuleId,
    status: "active",
    name: payload.name || previous.name,
    strength: payload.strength || previous.strength,
    logic_tree: payload.logic_tree as unknown as LogicTreeNode,
    ...(payload.action ? { action: payload.action } : {}),
  };
}

// EditRuleDialog uses a narrower LogicCriterion shape (snomed_concept_id is
// required and non-null) than the wire Rule shape (where actions can carry a
// null SNOMED id while awaiting coding). Drop the action when it has no
// concept id so the dialog never tries to render an uncoded recommendation.
function ruleToEditable(rule: Rule): EditableRule {
  let action: LogicCriterion | null = null;
  if (rule.action && rule.action.snomed_concept_id) {
    action = {
      snomed_concept_id: rule.action.snomed_concept_id,
      preferred_term: rule.action.preferred_term,
      semantic_tag: rule.action.semantic_tag,
      term: rule.action.term,
    };
  }
  return {
    rule_id: rule.rule_id,
    name: rule.name,
    strength: rule.strength,
    guideline_id: rule.guideline_id,
    chapter_title: rule.chapter_title,
    recommendation_text: rule.recommendation_text,
    logic_tree: rule.logic_tree,
    action,
  };
}

/** Colour-coded chip for a diff criterion. */
function DiffChip({
  criterion,
  kind,
}: {
  criterion: Criterion;
  kind: "added" | "removed" | "unchanged";
}) {
  const palette = {
    added: { bg: "#e8f5e9", border: "#66bb6a", icon: <AddCircleOutlineIcon sx={{ fontSize: 14, color: "success.dark" }} /> },
    removed: { bg: "#ffebee", border: "#ef5350", icon: <RemoveCircleOutlineIcon sx={{ fontSize: 14, color: "error.dark" }} /> },
    unchanged: { bg: "#f5f5f5", border: "#bdbdbd", icon: null },
  }[kind];

  return (
    <Box
      component="span"
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.4,
        px: 0.8,
        py: 0.2,
        borderRadius: 1,
        border: `1px solid ${palette.border}`,
        bgcolor: palette.bg,
        fontSize: "0.75rem",
        mr: 0.5,
        mb: 0.5,
      }}
    >
      {palette.icon}
      {criterion.preferred_term || criterion.concept_id}
      <Typography component="span" sx={{ color: "text.disabled", fontSize: "0.65rem", ml: 0.3 }}>
        ({criterion.predicate.toLowerCase()})
      </Typography>
    </Box>
  );
}

/** Expandable panel showing what changed vs the previous version. */
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
      const json: DiffData = await r.json();
      setData(json);
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
      <Button
        size="small"
        variant="text"
        startIcon={loading ? <CircularProgress size={14} /> : <CompareArrowsIcon fontSize="small" />}
        onClick={load}
        disabled={loading}
        aria-expanded={open}
        sx={{ textTransform: "none", color: "text.secondary", fontSize: "0.78rem" }}
      >
        {open ? "Hide" : "What changed?"}{" "}
        {hasDiff && !open && (
          <Chip
            label={`${added_count > 0 ? `+${added_count}` : ""}${removed_count > 0 ? ` −${removed_count}` : ""}`}
            size="small"
            color={removed_count > 0 ? "error" : "success"}
            sx={{ ml: 0.5, height: 18, fontSize: "0.68rem" }}
          />
        )}
      </Button>

      {error && <Alert severity="warning" sx={{ mt: 1, py: 0.5 }}>{error}</Alert>}

      <Collapse in={open}>
        {data && (
          <Box
            sx={{
              mt: 1.5,
              p: 1.5,
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              bgcolor: "grey.50",
            }}
          >
            {!data.has_predecessor ? (
              <Typography variant="body2" color="text.secondary">
                This is the first version of this rule — no previous decisions to compare.
              </Typography>
            ) : (
              <>
                {/* Previous decisions */}
                {(data.predecessor?.decisions?.length ?? 0) > 0 && (
                  <Box sx={{ mb: 1.5 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                      Previous decisions on this recommendation
                    </Typography>
                    <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                      {[...data.predecessor!.decisions]
                        .sort((a, b) => compareIsoDateTimeAsc(a.timestamp, b.timestamp))
                        .map((d, i) => (
                        <Box key={i} sx={{ fontSize: "0.78rem" }}>
                          <Chip
                            label={d.action}
                            size="small"
                            color={d.action === "approve" ? "success" : d.action === "reject" ? "error" : "default"}
                            sx={{ mr: 0.5, height: 18, fontSize: "0.68rem" }}
                          />
                          <Typography component="span" variant="caption" color="text.secondary">
                            {d.reviewer} · {d.timestamp ? new Date(d.timestamp).toLocaleDateString() : ""}
                            {d.reason ? ` — "${d.reason}"` : ""}
                          </Typography>
                        </Box>
                      ))}
                    </Stack>
                  </Box>
                )}

                {/* Previous rule plain-English */}
                {data.predecessor?.plain_english && (
                  <Box sx={{ mb: 1.5 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                      Previous rule said
                    </Typography>
                    <Typography variant="body2" sx={{ mt: 0.3, fontStyle: "italic", color: "text.secondary" }}>
                      {data.predecessor.plain_english}
                    </Typography>
                  </Box>
                )}

                <Divider sx={{ my: 1 }} />

                {/* Criteria diff */}
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                  Criteria changes
                </Typography>
                <Box sx={{ mt: 0.5 }}>
                  {(data.diff?.removed?.length ?? 0) === 0 && (data.diff?.added?.length ?? 0) === 0 ? (
                    <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.78rem" }}>
                      No criteria changed — only recommendation wording may differ.
                    </Typography>
                  ) : (
                    <>
                      {(data.diff?.removed ?? []).map((c) => (
                        <DiffChip key={c.concept_id} criterion={c} kind="removed" />
                      ))}
                      {(data.diff?.added ?? []).map((c) => (
                        <DiffChip key={c.concept_id} criterion={c} kind="added" />
                      ))}
                      {(data.diff?.unchanged ?? []).map((c) => (
                        <Tooltip
                          key={c.concept_id}
                          title="Unchanged from previous version"
                          arrow
                        >
                          <span>
                            <DiffChip criterion={c} kind="unchanged" />
                          </span>
                        </Tooltip>
                      ))}
                    </>
                  )}
                </Box>
              </>
            )}
          </Box>
        )}
      </Collapse>
    </Box>
  );
}

// ---- Accordion rule card -----------------------------------------------------

interface RuleAccordionCardProps {
  rule: Rule;
  expanded: boolean;
  busy: string | null;
  onToggle: () => void;
  onEdit: () => void;
  // Optional so the same card renders for active rules (no Looks right /
  // Reject) and superseded rules (read-only). When omitted the button
  // does not render -- callers express the affordance set, the card
  // does not infer it from rule.status.
  onApprove?: () => void;
  onReject?: () => void;
}

function RuleAccordionCard({
  rule,
  expanded,
  busy,
  onToggle,
  onApprove,
  onEdit,
  onReject,
}: RuleAccordionCardProps) {
  const isBusy = busy === rule.rule_id;

  return (
    <Card
      variant="outlined"
      sx={{
        borderLeft: "4px solid",
        borderLeftColor: "primary.main",
        borderRadius: 2,
      }}
    >
      {/* -- Row header (always visible) -- */}
      <CardContent sx={{ py: 1.2, "&:last-child": { pb: 1.2 } }}>
        <Stack
          direction="row"
          alignItems="flex-start"
          spacing={1}
          sx={{ cursor: "pointer" }}
          onClick={onToggle}
          role="button"
          aria-expanded={expanded}
          aria-label={`Toggle rule from ${rule.guideline_id}`}
        >
          {expanded ? (
            <ExpandMoreIcon sx={{ color: "primary.main", mt: 0.3, flexShrink: 0, fontSize: 18 }} />
          ) : (
            <ChevronRightIcon sx={{ color: "text.disabled", mt: 0.3, flexShrink: 0, fontSize: 18 }} />
          )}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap" sx={{ mb: 0.3 }}>
              <Chip label={rule.guideline_id} size="small" color="primary" />
              {rule.guideline_version && rule.guideline_version > 1 && (
                <Chip label={`v${rule.guideline_version}`} size="small" color="warning" variant="outlined" />
              )}
              {rule.strength && (
                <Chip label={rule.strength} size="small" variant="outlined" />
              )}
              {rule.has_predecessor && (
                <Chip icon={<CompareArrowsIcon />} label="Updated" size="small" color="warning" variant="outlined" />
              )}
              {rule.chapter_title && (
                <Typography variant="caption" color="text.secondary" noWrap sx={{ fontSize: "0.75rem" }}>
                  {rule.chapter_title}
                </Typography>
              )}
              {rule.updated_at && (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ fontSize: "0.75rem", fontStyle: "italic" }}
                  data-testid="rule-updated-relative"
                >
                  {formatRelativeUpdatedAt(rule.updated_at)}
                </Typography>
              )}
            </Stack>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                fontSize: "0.8rem",
                fontStyle: "italic",
                overflow: "hidden",
                display: "-webkit-box",
                WebkitLineClamp: expanded ? undefined : 2,
                WebkitBoxOrient: "vertical",
              }}
            >
              {rule.recommendation_text || rule.plain_english}
            </Typography>
          </Box>
        </Stack>

        {/* -- Expanded body -- */}
        <Collapse in={expanded}>
          <Box sx={{ mt: 1.5, ml: 3 }}>
            {/* Full NICE recommendation text */}
            {rule.recommendation_text && (
              <Box
                sx={{
                  p: 1.5,
                  bgcolor: "grey.50",
                  borderRadius: 1,
                  border: "1px solid",
                  borderColor: "grey.200",
                  mb: 0.5,
                }}
              >
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ fontWeight: 600, display: "block", mb: 0.5 }}
                >
                  NICE recommendation
                </Typography>
                <Typography variant="body2" sx={{ lineHeight: 1.7, fontStyle: "italic" }}>
                  &ldquo;{rule.recommendation_text}&rdquo;
                </Typography>
              </Box>
            )}

            {/* Structured criteria */}
            <RuleDetailPanel rule={rule} />

            {/* Version diff */}
            {rule.has_predecessor && (
              <Box sx={{ mt: 1.5 }}>
                <DiffPanel ruleId={rule.rule_id} />
              </Box>
            )}

            {/* Action buttons */}
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 2 }}>
              {onApprove && (
                <Button
                  variant="contained"
                  color="success"
                  size="small"
                  disabled={isBusy}
                  onClick={(e) => { e.stopPropagation(); onApprove(); }}
                  aria-label={`Approve rule ${rule.rule_id}`}
                >
                  Looks right
                </Button>
              )}
              <Button
                variant="outlined"
                size="small"
                disabled={isBusy}
                onClick={(e) => { e.stopPropagation(); onEdit(); }}
                aria-label={`Edit rule ${rule.rule_id}`}
              >
                Edit
              </Button>
              {onReject && (
                <Button
                  variant="outlined"
                  color="error"
                  size="small"
                  disabled={isBusy}
                  onClick={(e) => { e.stopPropagation(); onReject(); }}
                  aria-label={`Reject rule ${rule.rule_id}`}
                >
                  Reject
                </Button>
              )}
              {isBusy && <CircularProgress size={16} aria-label="Saving decision" />}
            </Stack>
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ---- Main section ------------------------------------------------------------

// ---- Active-list staleness helpers (DI-LEO-AI-528) --------------------------
//
// formatRelativeUpdatedAt renders an ISO 8601 timestamp (the BE returns
// rule.updated_at -- coalesced to created_at when the rule has never
// been edited) as a short, plain-English "Updated 5 minutes ago" hint.
// We deliberately keep the strings short and unambiguous (no "a few"
// or "about", no future tense) so reviewers reading dozens of cards
// can size relative staleness at a glance per .cursor/rules/
// health-literacy.mdc. The function is exported for static-source +
// unit tests and is pure (deterministic given an explicit `now`).
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
  if (minutes < 60)
    return `Updated ${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24)
    return `Updated ${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `Updated ${days} day${days === 1 ? "" : "s"} ago`;
  const months = Math.floor(days / 30);
  if (months < 12)
    return `Updated ${months} month${months === 1 ? "" : "s"} ago`;
  const years = Math.floor(days / 365);
  return `Updated ${years} year${years === 1 ? "" : "s"} ago`;
}

// sortRulesForStatus orders rules for display:
//  - "pending_review" + "superseded": preserve BE order (ORDER BY
//    rule.createdAt DESC -- newest first; the reviewer wants to see
//    the most recent generation / supersession at the top).
//  - "active": stalest first (longest since updated_at), so rules
//    most overdue for re-validation surface at the top of the page.
//    Ties break on rule_id for deterministic ordering across renders.
// Pure; exported for jest tests.
export function sortRulesForStatus<R extends { rule_id: string; updated_at?: string }>(
  rules: R[],
  statusFilter: RuleStatusFilter,
): R[] {
  if (statusFilter !== "active") return rules;
  const epoch = (iso: string | undefined): number => {
    if (!iso) return 0;
    const t = new Date(iso).getTime();
    return Number.isNaN(t) ? 0 : t;
  };
  // Copy first -- never mutate the caller's list, otherwise the React
  // state holding the fetched response would be silently re-ordered.
  return [...rules].sort((a, b) => {
    const da = epoch(a.updated_at);
    const db = epoch(b.updated_at);
    if (da !== db) return da - db;
    return a.rule_id.localeCompare(b.rule_id);
  });
}

// The status filter values mirror AppropriatenessRule.status in Neo4j and
// are forwarded verbatim as the ?status=... query param accepted by
// /api/guidance/rules/review (see services/api/app/routers/guidance_rules.py
// list_pending_rules). Adding a new status here also requires teaching
// the BE _FETCH_RULES query about it.
export type RuleStatusFilter = "pending_review" | "active" | "superseded";

const STATUS_FILTER_OPTIONS: ReadonlyArray<{
  value: RuleStatusFilter;
  label: string;
  helper: string;
}> = [
  {
    value: "pending_review",
    label: "Pending review",
    helper: "Rules waiting for a reviewer to approve, edit, or reject.",
  },
  {
    value: "active",
    label: "Active",
    helper:
      "Rules currently used by the live ruleset. Edit any to draft a new version (the active version stays live until the new edit is approved).",
  },
  {
    value: "superseded",
    label: "Superseded",
    helper:
      "Older versions of rules that have been replaced by an edit. Read-only history.",
  },
];

export default function RuleReviewSection({ refreshKey }: Props) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [internalKey, setInternalKey] = useState(0);
  const [approveAllOpen, setApproveAllOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [expandedRules, setExpandedRules] = useState<Record<string, boolean>>({});

  // Status filter for the rule list. Default = "pending_review" so the
  // section's first impression matches the existing review-first flow;
  // a reviewer who wants to revisit an already-live rule clicks Active.
  // The filter is local state (not URL) for now -- promoting it to a
  // URL-backed filter is a Tier 2 enhancement.
  const [statusFilter, setStatusFilter] = useState<RuleStatusFilter>(
    "pending_review",
  );

  // Edit dialog
  const [editRule, setEditRule] = useState<Rule | null>(null);
  const [editSaving, setEditSaving] = useState(false);

  // Promoted rules
  const [promoteConfirmRule, setPromoteConfirmRule] = useState<Rule | null>(null);
  const [promotedRules, setPromotedRules] = useState<Record<string, PromoteResult>>({});
  const [promoteBusy, setPromoteBusy] = useState<string | null>(null);
  const [promoteError, setPromoteError] = useState<string | null>(null);

  const [sessionApproved, setSessionApproved] = useState<Rule[]>([]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`/api/guidance/rules/review?status=${statusFilter}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setRules)
      .catch(() => setError("Could not load rules to review. Please try again."))
      .finally(() => setLoading(false));
  }, [refreshKey, internalKey, statusFilter]);

  const toggleExpanded = useCallback((ruleId: string) => {
    setExpandedRules((prev) => ({ ...prev, [ruleId]: !prev[ruleId] }));
  }, []);

  const decide = useCallback(
    async (rule: Rule, action: "approve" | "reject" | "edit", reason = "Admin review") => {
      setBusy(rule.rule_id);
      setActionError(null);
      try {
        const resp = await fetch(`/api/guidance/rules/review/${rule.rule_id}/decision`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, reviewer: "admin", reason }),
        });
        if (!resp.ok) throw new Error(await resp.text());
        if (action === "approve" || action === "edit") {
          setSessionApproved((prev) => [
            ...prev.filter((r) => r.rule_id !== rule.rule_id),
            { ...rule, status: "active" },
          ]);
        }
        setEditRule((prev) => (prev?.rule_id === rule.rule_id ? null : prev));
        setInternalKey((n) => n + 1);
      } catch {
        setActionError("Could not save your decision. Please try again.");
      } finally {
        setBusy(null);
      }
    },
    []
  );

  const handleSaveEdit = useCallback(
    async (payload: {
      name: string;
      strength: string;
      logic_tree: Record<string, unknown>;
      reason: string;
      action?: {
        snomed_concept_id: string;
        preferred_term: string;
        semantic_tag?: string;
        term?: string;
      };
    }) => {
      if (!editRule) return;
      setEditSaving(true);
      setActionError(null);
      try {
        const resp = await fetch(
          `/api/guidance/rules/review/${editRule.rule_id}/decision`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              action: "edit",
              reviewer: "admin",
              reason: payload.reason,
              updates: {
                name: payload.name,
                strength: payload.strength,
                logic_tree: payload.logic_tree,
                ...(payload.action ? { action: payload.action } : {}),
              },
            }),
          }
        );
        if (!resp.ok) {
          const detail = await resp
            .json()
            .catch(() => ({ detail: resp.statusText }));
          throw new Error(formatApiDetail(detail.detail) || resp.statusText);
        }
        const body = await resp.json().catch(() => ({}));
        const newRuleId = (body && body.rule_id) || editRule.rule_id;
        // Merge into the session cache via the shared helper; this keeps the
        // post-save snapshot in sync with what the BE just persisted (in
        // particular it forwards the new logic_tree, including any newly
        // added synonym seeds and exclusions).
        const previousRule = (editRule as unknown) as Rule;
        const mergedRule = mergeEditedRuleIntoCache(
          previousRule,
          newRuleId,
          payload,
        );
        setSessionApproved((prev) => [
          ...prev.filter((r) => r.rule_id !== editRule.rule_id),
          mergedRule,
        ]);
        setEditRule(null);
        setInternalKey((n) => n + 1);
      } catch (err) {
        setActionError(
          err instanceof Error ? err.message : "Could not save the edited rule."
        );
      } finally {
        setEditSaving(false);
      }
    },
    [editRule]
  );

  const handleApproveAll = useCallback(async () => {
    setApproveAllOpen(false);
    setActionError(null);
    setBusy("all");
    try {
      const resp = await fetch(
        "/api/guidance/rules/review/approve-all?reviewer=admin&reason=Bulk+approval",
        { method: "POST" }
      );
      if (!resp.ok) throw new Error(await resp.text());
      setSessionApproved((prev) => [
        ...prev,
        ...rules.map((r) => ({ ...r, status: "active" })),
      ]);
      setInternalKey((n) => n + 1);
    } catch {
      setActionError("Could not approve all rules. Please try again.");
    } finally {
      setBusy(null);
    }
  }, [rules]);

  const handlePromote = useCallback(async (rule: Rule) => {
    setPromoteConfirmRule(null);
    setPromoteBusy(rule.rule_id);
    setPromoteError(null);
    try {
      const resp = await fetch(
        `/api/guidance/rules/review/${rule.rule_id}/promote-to-domain?reviewer=admin`,
        { method: "POST" }
      );
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(detail.detail || resp.statusText);
      }
      const result: PromoteResult = await resp.json();
      setPromotedRules((prev) => ({ ...prev, [rule.rule_id]: result }));
    } catch (e) {
      setPromoteError(
        e instanceof Error ? e.message : "Could not add to domain. Please try again."
      );
    } finally {
      setPromoteBusy(null);
    }
  }, []);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress aria-label="Loading rules to review" />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  return (
    <Box>
      <EditRuleDialog
        rule={editRule ? ruleToEditable(editRule) : null}
        open={!!editRule}
        saving={editSaving}
        onClose={() => {
          if (editSaving) return;
          setEditRule(null);
        }}
        onSave={handleSaveEdit}
      />

      {/* ---- Alerts ---- */}
      {actionError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}
      {promoteError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setPromoteError(null)}>
          {promoteError}
        </Alert>
      )}

      {/* ---- Approved in this session ---- */}
      {sessionApproved.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1, color: "success.main" }}>
            Approved in this session
          </Typography>
          <Stack spacing={1}>
            {sessionApproved.map((rule) => (
              <Card
                key={rule.rule_id}
                variant="outlined"
                sx={{ borderLeft: "4px solid", borderLeftColor: "success.main", borderRadius: 2 }}
              >
                <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                    <CheckCircleOutlineIcon color="success" fontSize="small" />
                    <Chip label={rule.guideline_id} size="small" color="success" variant="outlined" />
                    <Chip label="Approved" size="small" color="success" />
                  </Stack>
                  <Typography variant="body2" sx={{ mb: 1, color: "text.secondary", fontSize: "0.82rem" }}>
                    {rule.recommendation_text || rule.name || rule.rule_id}
                  </Typography>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                    <Button
                      size="small"
                      variant="outlined"
                      color="primary"
                      startIcon={<EditOutlinedIcon fontSize="small" />}
                      onClick={() => setEditRule(rule)}
                      aria-label={`Edit approved rule ${rule.rule_id}`}
                    >
                      Edit
                    </Button>
                    {promotedRules[rule.rule_id] ? (
                      <Alert severity="success" sx={{ py: 0.5, flex: 1 }}>
                        Added {promotedRules[rule.rule_id].concepts_added} code
                        {promotedRules[rule.rule_id].concepts_added !== 1 ? "s" : ""} to{" "}
                        <Link href="/admin/knowledge?tab=domains" underline="hover">
                          {promotedRules[rule.rule_id].domain_name}
                        </Link>.
                      </Alert>
                    ) : (
                      <Button
                        size="small"
                        variant="outlined"
                        color="info"
                        disabled={promoteBusy === rule.rule_id}
                        onClick={() => setPromoteConfirmRule(rule)}
                        aria-label={`Add rule ${rule.rule_id} medical codes to domain`}
                      >
                        {promoteBusy === rule.rule_id ? "Adding..." : "Add to domain"}
                      </Button>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Stack>
        </Box>
      )}

      {/* ---- Status filter (Pending / Active / Superseded) ---- */}
      <Stack
        direction="row"
        spacing={1.5}
        alignItems="center"
        flexWrap="wrap"
        sx={{ mb: 1.5 }}
      >
        <ToggleButtonGroup
          value={statusFilter}
          exclusive
          size="small"
          color="primary"
          onChange={(_e, next) => {
            // exclusive ToggleButtonGroup emits null when the active
            // option is clicked again -- keep the current filter so
            // there is never a "no filter selected" empty state.
            if (next) setStatusFilter(next as RuleStatusFilter);
          }}
          aria-label="Filter rules by status"
        >
          {STATUS_FILTER_OPTIONS.map((opt) => (
            <Tooltip key={opt.value} title={opt.helper} arrow>
              <ToggleButton
                value={opt.value}
                aria-label={`Show ${opt.label} rules`}
              >
                {opt.label}
              </ToggleButton>
            </Tooltip>
          ))}
        </ToggleButtonGroup>
        <Typography variant="caption" color="text.secondary">
          {
            STATUS_FILTER_OPTIONS.find((o) => o.value === statusFilter)?.helper
          }
        </Typography>
      </Stack>

      {/* ---- Rules accordion list (filtered by status) ---- */}
      {rules.length === 0 ? (
        <Typography color="text.secondary">
          {statusFilter === "pending_review"
            ? "No rules waiting for review. Load a guideline first, then generate rules."
            : statusFilter === "active"
              ? "No active rules yet. Approve a pending rule to make it active."
              : "No superseded rules. Edits to active rules will appear here as a read-only history."}
        </Typography>
      ) : (
        <>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: 1.5 }}
          >
            <Typography variant="body2" color="text.secondary">
              {rules.length} {statusFilter === "pending_review" ? "rule" : statusFilter === "active" ? "active rule" : "superseded rule"}
              {rules.length !== 1 ? "s" : ""}
              {statusFilter === "pending_review" ? " to check" : ""}
              {" "}— click a row to read in full
            </Typography>
            {statusFilter === "pending_review" && (
              <Button
                variant="outlined"
                size="small"
                disabled={busy === "all"}
                onClick={() => setApproveAllOpen(true)}
                aria-label="Approve all rules"
              >
                Approve all
              </Button>
            )}
          </Stack>

          <Stack spacing={1}>
            {sortRulesForStatus(rules, statusFilter).map((rule) => (
              <RuleAccordionCard
                key={rule.rule_id}
                rule={rule}
                expanded={!!expandedRules[rule.rule_id]}
                busy={busy}
                onToggle={() => toggleExpanded(rule.rule_id)}
                onEdit={() => setEditRule(rule)}
                // Looks right is meaningful only for pending_review
                // (the rule has not been approved yet). For active
                // rules the affordance is Edit (creates a new draft);
                // for superseded rules everything except Edit is
                // hidden -- Tier 3 will add Restore to that surface.
                onApprove={
                  statusFilter === "pending_review"
                    ? () => decide(rule, "approve")
                    : undefined
                }
                onReject={
                  statusFilter === "pending_review"
                    ? () => decide(rule, "reject", "Rejected by reviewer")
                    : undefined
                }
              />
            ))}
          </Stack>
        </>
      )}

      {approveAllOpen && (
        <ConfirmDialog
          title="Approve all rules?"
          body={`This will approve all ${rules.length} rules and make them ready to compile. Only approve rules you have read and checked.`}
          confirmLabel="Yes, approve all"
          cancelLabel="Cancel"
          variant="primary"
          onConfirm={handleApproveAll}
          onCancel={() => setApproveAllOpen(false)}
        />
      )}

      {promoteConfirmRule && (
        <ConfirmDialog
          title="Add medical codes to this area?"
          body={`This will add the medical codes from rule "${promoteConfirmRule.name || promoteConfirmRule.rule_id}" to the NICE area linked to ${promoteConfirmRule.guideline_id}. Other parts of the system that use this area will see the new codes.`}
          confirmLabel="Yes, add to area"
          cancelLabel="Cancel"
          variant="primary"
          onConfirm={() => handlePromote(promoteConfirmRule)}
          onCancel={() => setPromoteConfirmRule(null)}
        />
      )}
    </Box>
  );
}
