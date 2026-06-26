/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E647765A")
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";

import ConfirmDialog from "@/components/ConfirmDialog";
import EditRuleDialog, { type EditableRule } from "./EditRuleDialog";
import { STRENGTH_LABELS } from "./EditRuleDialog/copy";
import type { LogicCriterion } from "./EditRuleDialog/types";
import {
  RuleDetailPanel,
  type CriterionResult,
  type LogicTreeNode,
  type RuleCriterion as Criterion,
} from "./RuleLogicView";
import { RuleAccordionCard, SessionApprovedRow, formatRelativeUpdatedAt } from "./RuleReviewCard";
import { EmptyState, NudgeStrip } from "@leo/design-system";

// Re-export for test backward-compat
export { formatRelativeUpdatedAt } from "./RuleReviewCard";

// -- Types -------------------------------------------------------------------

export interface ActionConcept {
  snomed_concept_id: string | null;
  preferred_term: string;
  semantic_tag?: string;
  term?: string;
}

export interface Rule {
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
  created_at?: string;
  updated_at?: string;
  reviewed_at?: string;
  reviewed_by?: string;
  generation_outcome?: string | null;
  needs_human_review?: boolean;
  generation_errors?: string[];
}

export interface PromoteResult {
  domain_id: string;
  domain_name: string;
  concepts_added: number;
}

export interface RuleReviewIdentity {
  rule_id: string;
  guideline_id?: string;
  recommendation_text?: string;
}

export type RuleStatusFilter = "pending_review" | "active" | "superseded";

// RuleAccordionCard action props -- onApprove/onReject are optional so the
// same card component serves all three status lists.
interface RuleCardActions {
  onApprove?: () => void;
  onReject?: () => void;
  onEdit: () => void;
}

export const STATUS_FILTER_OPTIONS: ReadonlyArray<{
  value: RuleStatusFilter;
  label: string;
  helper: string;
}> = [
  { value: "pending_review", label: "Pending review", helper: "Rules waiting for a reviewer to approve, edit, or reject." },
  { value: "active", label: "Active", helper: "Rules currently used by the live ruleset. Edit any to draft a new version." },
  { value: "superseded", label: "Superseded", helper: "Older versions of rules that have been replaced by an edit. Read-only history." },
];

// -- Utility functions -------------------------------------------------------

export function formatApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      if (typeof d === "string") return d;
      if (d && typeof d === "object") {
        const obj = d as Record<string, unknown>;
        const loc = Array.isArray(obj.loc) ? (obj.loc as unknown[]).filter((x) => x !== "body" && x !== "updates").join(".") : "";
        const msg = typeof obj.msg === "string" ? obj.msg : "";
        if (loc && msg) return `${loc}: ${msg}`;
        if (msg) return msg;
      }
      try { return JSON.stringify(d); } catch { return String(d); }
    }).filter((s) => s.length > 0);
    return parts.join("; ");
  }
  if (detail && typeof detail === "object") {
    try { return JSON.stringify(detail); } catch { return String(detail); }
  }
  return "";
}

export function mergeEditedRuleIntoCache(
  previous: Rule,
  newRuleId: string,
  payload: { name: string; strength: string; logic_tree: Record<string, unknown>; action?: ActionConcept; },
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

function normaliseRecommendationText(value: string | undefined): string {
  return (value || "").toLowerCase().replace(/\s+/g, " ").replace(/[^\w. ]+/g, "").trim();
}

export function ruleReviewKey(rule: RuleReviewIdentity): string {
  const text = normaliseRecommendationText(rule.recommendation_text);
  const recommendationNumber = text.match(/^(\d+(?:\.\d+)+)\b/)?.[1];
  if (recommendationNumber) return `${rule.guideline_id || ""}:${recommendationNumber}`;
  return `${rule.guideline_id || ""}:${text || rule.rule_id}`;
}

export function upsertApprovedRule<T extends RuleReviewIdentity>(current: T[], next: T): T[] {
  const nextKey = ruleReviewKey(next);
  return [...current.filter((rule) => rule.rule_id !== next.rule_id && ruleReviewKey(rule) !== nextKey), next];
}

export function filterRulesForReview<T extends RuleReviewIdentity>(
  rules: T[],
  sessionApproved: RuleReviewIdentity[],
  statusFilter: RuleStatusFilter,
): T[] {
  const approvedKeys = new Set(sessionApproved.map(ruleReviewKey));
  const seen = new Set<string>();
  const out: T[] = [];
  for (const rule of rules) {
    const key = ruleReviewKey(rule);
    if (statusFilter === "pending_review" && approvedKeys.has(key)) continue;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(rule);
  }
  return out;
}

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
  return [...rules].sort((a, b) => {
    const da = epoch(a.updated_at);
    const db = epoch(b.updated_at);
    if (da !== db) return da - db;
    return a.rule_id.localeCompare(b.rule_id);
  });
}

function ruleToEditable(rule: Rule): EditableRule {
  let action: LogicCriterion | null = null;
  if (rule.action && rule.action.snomed_concept_id) {
    action = { snomed_concept_id: rule.action.snomed_concept_id, preferred_term: rule.action.preferred_term, semantic_tag: rule.action.semantic_tag, term: rule.action.term };
  }
  return { rule_id: rule.rule_id, name: rule.name, strength: rule.strength, guideline_id: rule.guideline_id, chapter_title: rule.chapter_title, recommendation_text: rule.recommendation_text, logic_tree: rule.logic_tree, action };
}

// -- Props -------------------------------------------------------------------

interface Props { refreshKey?: number; }

// -- Main component ----------------------------------------------------------
// LONG FUNCTION: React state machine with 4 async handlers + orchestration JSX.

export default function RuleReviewSection({ refreshKey }: Props) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [internalKey, setInternalKey] = useState(0);
  const [approveAllOpen, setApproveAllOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [expandedRules, setExpandedRules] = useState<Record<string, boolean>>({});
  const [statusFilter, setStatusFilter] = useState<RuleStatusFilter>("pending_review");
  const [editRule, setEditRule] = useState<Rule | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const [promoteConfirmRule, setPromoteConfirmRule] = useState<Rule | null>(null);
  const [promotedRules, setPromotedRules] = useState<Record<string, PromoteResult>>({});
  const [promoteBusy, setPromoteBusy] = useState<string | null>(null);
  const [promoteError, setPromoteError] = useState<string | null>(null);
  const [sessionApproved, setSessionApproved] = useState<Rule[]>([]);

  const visibleRules = useMemo(
    () => filterRulesForReview(rules, sessionApproved, statusFilter),
    [rules, sessionApproved, statusFilter],
  );

  const editableRule = useMemo(() => (editRule ? ruleToEditable(editRule) : null), [editRule]);

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

  const decide = useCallback(async (rule: Rule, action: "approve" | "reject" | "edit", reason = "Admin review") => {
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
        setSessionApproved((prev) => upsertApprovedRule(prev, { ...rule, status: "active" }));
      }
      setEditRule((prev) => (prev?.rule_id === rule.rule_id ? null : prev));
      setInternalKey((n) => n + 1);
    } catch { setActionError("Could not save your decision. Please try again."); }
    finally { setBusy(null); }
  }, []);

  const handleSaveEdit = useCallback(async (payload: {
    name: string; strength: string; logic_tree: Record<string, unknown>; reason: string;
    action?: { snomed_concept_id: string; preferred_term: string; semantic_tag?: string; term?: string; };
  }) => {
    if (!editRule) return;
    setEditSaving(true);
    setActionError(null);
    try {
      const resp = await fetch(`/api/guidance/rules/review/${editRule.rule_id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "edit", reviewer: "admin", reason: payload.reason, updates: { name: payload.name, strength: payload.strength, logic_tree: payload.logic_tree, ...(payload.action ? { action: payload.action } : {}) } }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(formatApiDetail(detail.detail) || resp.statusText);
      }
      const body = await resp.json().catch(() => ({}));
      const newRuleId = (body && body.rule_id) || editRule.rule_id;
      const mergedRule = mergeEditedRuleIntoCache(editRule as unknown as Rule, newRuleId, payload);
      setSessionApproved((prev) => upsertApprovedRule(prev, mergedRule));
      setEditRule(null);
      setInternalKey((n) => n + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not save the edited rule.");
    } finally { setEditSaving(false); }
  }, [editRule]);

  const handleApproveAll = useCallback(async () => {
    setApproveAllOpen(false);
    setActionError(null);
    setBusy("all");
    try {
      const resp = await fetch("/api/guidance/rules/review/approve-all?reviewer=admin&reason=Bulk+approval", { method: "POST" });
      if (!resp.ok) throw new Error(await resp.text());
      setSessionApproved((prev) => visibleRules.reduce((acc, rule) => upsertApprovedRule(acc, { ...rule, status: "active" }), prev));
      setInternalKey((n) => n + 1);
    } catch { setActionError("Could not approve all rules. Please try again."); }
    finally { setBusy(null); }
  }, [visibleRules]);

  const handlePromote = useCallback(async (rule: Rule) => {
    setPromoteConfirmRule(null);
    setPromoteBusy(rule.rule_id);
    setPromoteError(null);
    try {
      const resp = await fetch(`/api/guidance/rules/review/${rule.rule_id}/promote-to-domain?reviewer=admin`, { method: "POST" });
      if (!resp.ok) { const detail = await resp.json().catch(() => ({ detail: resp.statusText })); throw new Error(detail.detail || resp.statusText); }
      const result: PromoteResult = await resp.json();
      setPromotedRules((prev) => ({ ...prev, [rule.rule_id]: result }));
    } catch (e) { setPromoteError(e instanceof Error ? e.message : "Could not add to domain. Please try again."); }
    finally { setPromoteBusy(null); }
  }, []);

  if (loading) {
    return <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}><span aria-label="Loading rules to review" style={{ display: "block", height: 40 }} /></Box>;
  }

  if (error) return <Alert severity="error">{error}</Alert>;

  return (
    <Box>
      <EditRuleDialog rule={editableRule} open={!!editRule} saving={editSaving} onClose={() => { if (editSaving) return; setEditRule(null); }} onSave={handleSaveEdit} />
      {actionError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>{actionError}</Alert>}
      {promoteError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setPromoteError(null)}>{promoteError}</Alert>}

      {/* -- Status filter toolbar ---------------------------------------- */}
      <Stack spacing={1} sx={{ mb: 1.5 }}>
        <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap">
          <ToggleButtonGroup
            exclusive
            value={statusFilter}
            onChange={(_, next) => {
              if (next) setStatusFilter(next as RuleStatusFilter);
            }}
            size="small"
            aria-label="Filter rules by status"
          >
            {STATUS_FILTER_OPTIONS.map((opt) => (
              <ToggleButton
                key={opt.value}
                value={opt.value}
                aria-label={`Show ${opt.label} rules`}
              >
                {opt.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          <Typography variant="caption" color="text.secondary">
            {STATUS_FILTER_OPTIONS.find((t) => t.value === statusFilter)?.helper ?? ""}
          </Typography>
        </Stack>
        {visibleRules.length > 0 && (
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="body2" color="text.secondary">
              {visibleRules.length} rule{visibleRules.length !== 1 ? "s" : ""}
            </Typography>
            {statusFilter === "pending_review" && (
              <Tooltip title="Approve every pending rule in one click.">
                <span>
                  <Button
                    variant="outlined"
                    size="small"
                    disabled={busy === "all"}
                    onClick={() => setApproveAllOpen(true)}
                    aria-label="Approve all rules"
                  >
                    Approve all
                  </Button>
                </span>
              </Tooltip>
            )}
          </Stack>
        )}
      </Stack>

      {/* -- Session-approved -------------------------------------------- */}
      {sessionApproved.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography
            variant="overline"
            sx={{ fontWeight: 700, letterSpacing: 0.6, display: "block", mb: 1 }}
          >
            Approved in this session
          </Typography>
          <Stack spacing={1}>
            {sessionApproved.map((rule) => (
              <Box
                key={rule.rule_id}
                sx={{ p: 1.5, border: "1px solid", borderColor: "success.light", borderRadius: 1.5, bgcolor: "#F0FDF4" }}
              >
                <Typography variant="body2" sx={{ mb: 1, fontWeight: 500 }}>
                  {rule.name || rule.rule_id}
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
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
                    <Alert severity="success" sx={{ py: 0, px: 1, fontSize: "0.75rem", flex: 1 }}>
                      Added to {promotedRules[rule.rule_id].domain_name}
                    </Alert>
                  ) : (
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={promoteBusy === rule.rule_id}
                      onClick={() => setPromoteConfirmRule(rule)}
                    >
                      Add to domain
                    </Button>
                  )}
                </Stack>
              </Box>
            ))}
          </Stack>
        </Box>
      )}

      {/* -- Rule list --------------------------------------------------- */}
      {visibleRules.length === 0 ? (
        <EmptyState
          icon={<HistoryOutlinedIcon fontSize="large" />}
          title={
            statusFilter === "pending_review"
              ? "No rules pending"
              : statusFilter === "active"
              ? "No active rules"
              : "No superseded rules"
          }
          body={
            statusFilter === "pending_review"
              ? "No rules waiting for review. Load a guideline first, then generate rules."
              : statusFilter === "active"
              ? "No active rules yet. Approve a pending rule to make it active."
              : "No superseded rules. Edits to active rules will appear here as a read-only history."
          }
        />
      ) : (
        <Stack spacing={0}>
          {sortRulesForStatus(visibleRules, statusFilter).map((rule) => (
            <Box key={rule.rule_id}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "none" }}
                data-testid="rule-updated-relative"
              >
                {formatRelativeUpdatedAt(rule.updated_at)}
              </Typography>
              <RuleAccordionCard
                rule={rule}
                expanded={!!expandedRules[rule.rule_id]}
                busy={busy}
                index={0}
                statusFilter={statusFilter}
                onToggle={() => toggleExpanded(rule.rule_id)}
                onEdit={() => setEditRule(rule)}
                onApprove={statusFilter === "pending_review" ? () => decide(rule, "approve") : undefined}
                onReject={statusFilter === "pending_review" ? () => decide(rule, "reject", "Rejected by reviewer") : undefined}
              />
            </Box>
          ))}
        </Stack>
      )}

      {approveAllOpen && (
        <ConfirmDialog
          title="Approve all rules?"
          body={`This will approve all ${visibleRules.length} rules and make them ready to compile. Only approve rules you have read and checked.`}
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
