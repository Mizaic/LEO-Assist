/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";

import { useMotion } from "@leo/design-system";

import ConfirmDialog from "@/components/ConfirmDialog";
import EditRuleDialog from "./EditRuleDialog";
import GuidelineChipFilter from "./GuidelineChipFilter";
import RuleReviewPool from "./RuleReviewPool";
import RuleReviewSessionPanels from "./RuleReviewSessionPanels";
import {
  fetchRules,
  filterRulesForReview,
  formatApiDetail,
  mergeEditedRuleIntoCache,
  ruleToEditable,
  upsertApprovedRule,
} from "./ruleReviewHelpers";
import type { PromoteResult, Rule } from "./ruleReviewTypes";

export {
  filterRulesForReview,
  formatApiDetail,
  mergeEditedRuleIntoCache,
  ruleReviewKey,
  sortRulesForStatus,
  upsertApprovedRule,
} from "./ruleReviewHelpers";
export type {
  ActionConcept,
  PromoteResult,
  Rule,
  RuleReviewIdentity,
  RuleStatusFilter,
} from "./ruleReviewTypes";
export { formatRelativeUpdatedAt } from "./RuleReviewCard";

interface Props {
  refreshKey?: number;
}

export default function RuleReviewSection({ refreshKey }: Props) {
  const { reducedMotion } = useMotion();
  const [pendingRules, setPendingRules] = useState<Rule[]>([]);
  const [approvedRules, setApprovedRules] = useState<Rule[]>([]);
  const [excludedRules, setExcludedRules] = useState<Rule[]>([]);
  const [supersededRules, setSupersededRules] = useState<Rule[]>([]);
  const [loadingPending, setLoadingPending] = useState(false);
  const [loadingApproved, setLoadingApproved] = useState(false);
  const [loadingExcluded, setLoadingExcluded] = useState(false);
  const [loadingSuperseded, setLoadingSuperseded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [internalKey, setInternalKey] = useState(0);
  const [approveAllOpen, setApproveAllOpen] = useState(false);
  const [excludeConfirmRule, setExcludeConfirmRule] = useState<Rule | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [expandedRules, setExpandedRules] = useState<Record<string, boolean>>({});
  const [showSuperseded, setShowSuperseded] = useState(false);
  const [editRule, setEditRule] = useState<Rule | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const [promoteConfirmRule, setPromoteConfirmRule] = useState<Rule | null>(null);
  const [promotedRules, setPromotedRules] = useState<Record<string, PromoteResult>>({});
  const [promoteBusy, setPromoteBusy] = useState<string | null>(null);
  const [promoteError, setPromoteError] = useState<string | null>(null);
  const [sessionApproved, setSessionApproved] = useState<Rule[]>([]);
  const [sessionExcluded, setSessionExcluded] = useState<Rule[]>([]);
  const [sessionApprovedOpen, setSessionApprovedOpen] = useState(false);
  const [sessionExcludedOpen, setSessionExcludedOpen] = useState(false);
  const [guidelineFilter, setGuidelineFilter] = useState<string | null>(null);
  const searchParams = useSearchParams();
  const prefillRuleId = searchParams.get("rule_id") || "";

  useEffect(() => {
    if (!prefillRuleId || editRule) return;
    const match = [
      ...pendingRules,
      ...approvedRules,
      ...excludedRules,
      ...supersededRules,
    ].find((row) => row.rule_id === prefillRuleId);
    if (match) setEditRule(match);
  }, [prefillRuleId, pendingRules, approvedRules, excludedRules, supersededRules, editRule]);

  const allGuidelineIds = useMemo(() => {
    const ids = new Set(
      [
        ...pendingRules.map((r) => r.guideline_id),
        ...approvedRules.map((r) => r.guideline_id),
        ...excludedRules.map((r) => r.guideline_id),
      ].filter(Boolean),
    );
    return [...ids].sort();
  }, [pendingRules, approvedRules, excludedRules]);

  const filterByGuideline = useCallback(
    (rules: Rule[]) =>
      guidelineFilter ? rules.filter((r) => r.guideline_id === guidelineFilter) : rules,
    [guidelineFilter],
  );

  const sessionResolved = useMemo(
    () => [...sessionApproved, ...sessionExcluded],
    [sessionApproved, sessionExcluded],
  );

  const pendingVisible = useMemo(
    () => filterRulesForReview(filterByGuideline(pendingRules), sessionResolved, "pending_review"),
    [pendingRules, sessionResolved, filterByGuideline],
  );

  const editableRule = useMemo(
    () => (editRule ? ruleToEditable(editRule) : null),
    [editRule],
  );

  const reloadPools = useCallback(async () => {
    setLoadingPending(true);
    setLoadingApproved(true);
    setLoadingExcluded(true);
    setError(null);
    try {
      const [pending, approved, excluded] = await Promise.all([
        fetchRules("pending_review"),
        fetchRules("active"),
        fetchRules("rejected"),
      ]);
      setPendingRules(pending);
      setApprovedRules(approved);
      setExcludedRules(excluded);
    } catch {
      setError("Could not load rules to review. Please try again.");
    } finally {
      setLoadingPending(false);
      setLoadingApproved(false);
      setLoadingExcluded(false);
    }
  }, []);

  useEffect(() => {
    void reloadPools();
  }, [refreshKey, internalKey, reloadPools]);

  useEffect(() => {
    if (!showSuperseded) return;
    setLoadingSuperseded(true);
    fetchRules("superseded")
      .then(setSupersededRules)
      .catch(() => setSupersededRules([]))
      .finally(() => setLoadingSuperseded(false));
  }, [showSuperseded, refreshKey, internalKey]);

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
          setSessionApproved((prev) => upsertApprovedRule(prev, { ...rule, status: "active" }));
          setSessionExcluded((prev) =>
            prev.filter((row) => row.rule_id !== rule.rule_id),
          );
        } else if (action === "reject") {
          setSessionApproved((prev) =>
            prev.filter((row) => row.rule_id !== rule.rule_id),
          );
          setSessionExcluded((prev) =>
            upsertApprovedRule(prev, { ...rule, status: "rejected" }),
          );
        }
        setEditRule((prev) => (prev?.rule_id === rule.rule_id ? null : prev));
        setInternalKey((n) => n + 1);
      } catch {
        setActionError("Could not save your decision. Please try again.");
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  const handleSaveEdit = useCallback(
    async (payload: {
      name: string;
      logic_tree: Record<string, unknown>;
      reason: string;
      actions?: Array<Record<string, unknown>>;
      priority?: "immediate" | "very_urgent" | "2ww" | "urgent" | "routine";
      due_days?: number | null;
    }) => {
      if (!editRule) return;
      setEditSaving(true);
      setActionError(null);
      try {
        const resp = await fetch(`/api/guidance/rules/review/${editRule.rule_id}/decision`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "edit",
            reviewer: "admin",
            reason: payload.reason,
            updates: {
              name: payload.name,
              logic_tree: payload.logic_tree,
              ...(payload.actions ? { actions: payload.actions } : {}),
              ...(payload.priority !== undefined
                ? {
                    priority: payload.priority,
                    due_days:
                      payload.priority === "routine"
                        ? null
                        : (payload.due_days ?? null),
                  }
                : {}),
            },
          }),
        });
        if (!resp.ok) {
          const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
          throw new Error(formatApiDetail(detail.detail) || resp.statusText);
        }
        const body = await resp.json().catch(() => ({}));
        const newRuleId = (body && body.rule_id) || editRule.rule_id;
        const mergedRule = mergeEditedRuleIntoCache(editRule, newRuleId, payload);
        setSessionApproved((prev) => upsertApprovedRule(prev, mergedRule));
        setEditRule(null);
        setInternalKey((n) => n + 1);
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "Could not save the edited rule.");
      } finally {
        setEditSaving(false);
      }
    },
    [editRule],
  );

  const handleApproveAll = useCallback(async () => {
    setApproveAllOpen(false);
    setActionError(null);
    setBusy("all");
    try {
      const resp = await fetch(
        "/api/guidance/rules/review/approve-all?reviewer=admin&reason=Bulk+approval",
        { method: "POST" },
      );
      if (!resp.ok) throw new Error(await resp.text());
      setSessionApproved((prev) =>
        pendingVisible.reduce(
          (acc, rule) => upsertApprovedRule(acc, { ...rule, status: "active" }),
          prev,
        ),
      );
      setInternalKey((n) => n + 1);
    } catch {
      setActionError("Could not approve all rules. Please try again.");
    } finally {
      setBusy(null);
    }
  }, [pendingVisible]);

  const handlePromote = useCallback(async (rule: Rule) => {
    setPromoteConfirmRule(null);
    setPromoteBusy(rule.rule_id);
    setPromoteError(null);
    try {
      const resp = await fetch(
        `/api/guidance/rules/review/${rule.rule_id}/promote-to-domain?reviewer=admin`,
        { method: "POST" },
      );
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(detail.detail || resp.statusText);
      }
      const result: PromoteResult = await resp.json();
      setPromotedRules((prev) => ({ ...prev, [rule.rule_id]: result }));
    } catch (e) {
      setPromoteError(e instanceof Error ? e.message : "Could not add to domain. Please try again.");
    } finally {
      setPromoteBusy(null);
    }
  }, []);

  if (error) return <Alert severity="error">{error}</Alert>;

  return (
    <Box>
      <EditRuleDialog
        rule={editableRule}
        open={!!editRule}
        saving={editSaving}
        saveError={editRule ? actionError : null}
        onClose={() => {
          if (editSaving) return;
          setEditRule(null);
          setActionError(null);
        }}
        onSave={handleSaveEdit}
      />
      {actionError && !editRule ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      ) : null}
      {promoteError ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setPromoteError(null)}>
          {promoteError}
        </Alert>
      ) : null}

      <RuleReviewSessionPanels
        reducedMotion={reducedMotion}
        sessionApproved={sessionApproved}
        sessionExcluded={sessionExcluded}
        sessionApprovedOpen={sessionApprovedOpen}
        sessionExcludedOpen={sessionExcludedOpen}
        promotedRules={promotedRules}
        promoteBusy={promoteBusy}
        onToggleApprovedOpen={() => setSessionApprovedOpen((v) => !v)}
        onToggleExcludedOpen={() => setSessionExcludedOpen((v) => !v)}
        onEdit={setEditRule}
        onPromoteConfirm={setPromoteConfirmRule}
      />

      <GuidelineChipFilter
        guidelineIds={allGuidelineIds}
        selected={guidelineFilter}
        onSelect={setGuidelineFilter}
      />

      <Stack spacing={2.5}>
        <RuleReviewPool
          poolId="pending"
          title="Awaiting review"
          helper="Rules the AI generated that still need a reviewer to approve, edit, or reject."
          statusFilter="pending_review"
          rules={pendingVisible}
          loading={loadingPending}
          expandedRules={expandedRules}
          busy={busy}
          showApproveAll
          onApproveAll={() => setApproveAllOpen(true)}
          onToggle={toggleExpanded}
          onEdit={setEditRule}
          onApprove={(rule) => decide(rule, "approve")}
          onReject={(rule) =>
            decide(
              rule,
              "reject",
              rule.generation_outcome === "no_rule_expected"
                ? "No coded rule needed"
                : "Rejected by reviewer",
            )
          }
        />

        <RuleReviewPool
          poolId="approved"
          title="Approved"
          helper="Rules already checked and used when you compile the live lookup index. Expand a row to edit or move it to Excluded."
          statusFilter="active"
          rules={filterByGuideline(approvedRules)}
          loading={loadingApproved}
          expandedRules={expandedRules}
          busy={busy}
          onToggle={toggleExpanded}
          onEdit={setEditRule}
          onReject={(rule) => setExcludeConfirmRule(rule)}
        />

        <RuleReviewPool
          poolId="excluded"
          title="Excluded"
          helper="No coded rule needed, rejected from review, or moved here from Approved. These are not compiled into the live lookup index."
          statusFilter="rejected"
          rules={filterByGuideline(excludedRules)}
          loading={loadingExcluded}
          expandedRules={expandedRules}
          busy={busy}
          onToggle={toggleExpanded}
          onEdit={setEditRule}
        />
      </Stack>

      <Box sx={{ mt: 2 }}>
        <Button
          size="small"
          variant="text"
          onClick={() => setShowSuperseded((open) => !open)}
          aria-expanded={showSuperseded}
          aria-controls="superseded-history-pool"
        >
          {showSuperseded ? "Hide superseded history" : "Show superseded history"}
        </Button>
        <Collapse in={showSuperseded}>
          <Box id="superseded-history-pool" sx={{ mt: 1.5 }}>
            <RuleReviewPool
              poolId="superseded"
              title="Superseded history"
              helper="Older rule versions replaced by an edit. Read-only history for audit."
              statusFilter="superseded"
              rules={supersededRules}
              loading={loadingSuperseded}
              expandedRules={expandedRules}
              busy={busy}
              onToggle={toggleExpanded}
              onEdit={setEditRule}
            />
          </Box>
        </Collapse>
      </Box>

      {approveAllOpen ? (
        <ConfirmDialog
          title="Approve all rules?"
          body={`This will approve all ${pendingVisible.length} pending rules and make them ready to compile. Only approve rules you have read and checked.`}
          confirmLabel="Yes, approve all"
          cancelLabel="Cancel"
          variant="primary"
          onConfirm={handleApproveAll}
          onCancel={() => setApproveAllOpen(false)}
        />
      ) : null}
      {excludeConfirmRule ? (
        <ConfirmDialog
          title="Exclude this approved rule?"
          body={`This moves "${excludeConfirmRule.name || excludeConfirmRule.recommendation_text || excludeConfirmRule.rule_id}" to Excluded. It will not be included the next time you compile the live lookup index.`}
          confirmLabel="Yes, exclude"
          cancelLabel="Cancel"
          variant="danger"
          onConfirm={() => {
            const rule = excludeConfirmRule;
            setExcludeConfirmRule(null);
            void decide(rule, "reject", "Excluded from approved list by reviewer");
          }}
          onCancel={() => setExcludeConfirmRule(null)}
        />
      ) : null}
      {promoteConfirmRule ? (
        <ConfirmDialog
          title="Add medical codes to this area?"
          body={`This will add the medical codes from rule "${promoteConfirmRule.name || promoteConfirmRule.rule_id}" to the NICE area linked to ${promoteConfirmRule.guideline_id}. Other parts of the system that use this area will see the new codes.`}
          confirmLabel="Yes, add to area"
          cancelLabel="Cancel"
          variant="primary"
          onConfirm={() => handlePromote(promoteConfirmRule)}
          onCancel={() => setPromoteConfirmRule(null)}
        />
      ) : null}
    </Box>
  );
}
