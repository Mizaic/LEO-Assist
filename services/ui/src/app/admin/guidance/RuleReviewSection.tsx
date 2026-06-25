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
import RuleReviewList from "./RuleReviewList";
import RuleReviewToolbar from "./RuleReviewToolbar";

// Re-export for test backward-compat (defined in RuleReviewCard to avoid
// circular runtime imports; re-exported here so the test import path is stable).
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
    () => sortRulesForStatus(filterRulesForReview(rules, sessionApproved, statusFilter), statusFilter),
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

      <RuleReviewToolbar
        statusFilter={statusFilter}
        onFilterChange={setStatusFilter}
        visibleCount={visibleRules.length}
        busy={busy}
        onApproveAll={() => setApproveAllOpen(true)}
      />

      <RuleReviewList
        sessionApproved={{ rules: sessionApproved, promotedRules, promoteBusy }}
        ruleList={{ rules: visibleRules, expandedRules, busy }}
        statusFilter={statusFilter}
        listActions={{ onToggle: toggleExpanded, onEdit: setEditRule, onApprove: (rule) => decide(rule, "approve"), onReject: (rule) => decide(rule, "reject", "Rejected by reviewer") }}
        sessionActions={{ onEdit: setEditRule, onPromote: (rule) => setPromoteConfirmRule(rule) }}
      />

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
