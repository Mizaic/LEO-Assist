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
import { AnimatePresence, motion as fm } from "framer-motion";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";

import { useMotion } from "@leo/design-system";

import ConfirmDialog from "@/components/ConfirmDialog";
import EditRuleDialog from "./EditRuleDialog";
import { formatRelativeUpdatedAt } from "./RuleReviewCard";
import RuleReviewPool from "./RuleReviewPool";
import { popVariants } from "./motionPresets";
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

interface GuidelineChipFilterProps {
  guidelineIds: string[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}

function GuidelineChipFilter({ guidelineIds, selected, onSelect }: GuidelineChipFilterProps) {
  if (guidelineIds.length < 2) return null;
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.6, display: "block", mb: 0.75 }}>
        Filter by guideline
      </Typography>
      <Stack direction="row" spacing={0.75} flexWrap="wrap">
        <Chip
          label="All"
          size="small"
          variant={selected === null ? "filled" : "outlined"}
          color={selected === null ? "primary" : "default"}
          onClick={() => onSelect(null)}
          sx={{ cursor: "pointer" }}
        />
        {guidelineIds.map((id) => (
          <Chip
            key={id}
            label={id}
            size="small"
            variant={selected === id ? "filled" : "outlined"}
            color={selected === id ? "primary" : "default"}
            onClick={() => onSelect(id)}
            sx={{ cursor: "pointer", fontWeight: selected === id ? 700 : 400 }}
          />
        ))}
      </Stack>
    </Box>
  );
}

interface Props {
  refreshKey?: number;
}

export default function RuleReviewSection({ refreshKey }: Props) {
  const { reducedMotion } = useMotion();
  const [pendingRules, setPendingRules] = useState<Rule[]>([]);
  const [approvedRules, setApprovedRules] = useState<Rule[]>([]);
  const [supersededRules, setSupersededRules] = useState<Rule[]>([]);
  const [loadingPending, setLoadingPending] = useState(false);
  const [loadingApproved, setLoadingApproved] = useState(false);
  const [loadingSuperseded, setLoadingSuperseded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [internalKey, setInternalKey] = useState(0);
  const [approveAllOpen, setApproveAllOpen] = useState(false);
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
  const [guidelineFilter, setGuidelineFilter] = useState<string | null>(null);

  const allGuidelineIds = useMemo(() => {
    const ids = new Set([
      ...pendingRules.map((r) => r.guideline_id),
      ...approvedRules.map((r) => r.guideline_id),
    ].filter(Boolean));
    return [...ids].sort();
  }, [pendingRules, approvedRules]);

  const filterByGuideline = useCallback(
    (rules: Rule[]) =>
      guidelineFilter ? rules.filter((r) => r.guideline_id === guidelineFilter) : rules,
    [guidelineFilter],
  );

  const pendingVisible = useMemo(
    () => filterRulesForReview(filterByGuideline(pendingRules), sessionApproved, "pending_review"),
    [pendingRules, sessionApproved, filterByGuideline],
  );

  const editableRule = useMemo(() => (editRule ? ruleToEditable(editRule) : null), [editRule]);

  const reloadPools = useCallback(async () => {
    setLoadingPending(true);
    setLoadingApproved(true);
    setError(null);
    try {
      const [pending, approved] = await Promise.all([
        fetchRules("pending_review"),
        fetchRules("active"),
      ]);
      setPendingRules(pending);
      setApprovedRules(approved);
    } catch {
      setError("Could not load rules to review. Please try again.");
    } finally {
      setLoadingPending(false);
      setLoadingApproved(false);
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
        onClose={() => {
          if (editSaving) return;
          setEditRule(null);
        }}
        onSave={handleSaveEdit}
      />
      {actionError ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      ) : null}
      {promoteError ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setPromoteError(null)}>
          {promoteError}
        </Alert>
      ) : null}

      {sessionApproved.length > 0 ? (
        <Box sx={{ mb: 3 }}>
          <Typography variant="overline" sx={{ fontWeight: 700, letterSpacing: 0.6, display: "block", mb: 1 }}>
            Approved in this session
          </Typography>
          <Stack spacing={1}>
            <AnimatePresence initial={false}>
              {sessionApproved.map((rule) => (
                <fm.div
                  key={rule.rule_id}
                  layout
                  variants={popVariants(reducedMotion)}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                >
                  <Box
                    sx={{
                      p: 1.5,
                      border: "1px solid",
                      borderColor: "success.light",
                      borderRadius: 1.5,
                      bgcolor: "#F0FDF4",
                    }}
                  >
                    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 1 }}>
                      <fm.div
                        initial={reducedMotion ? undefined : { scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: "spring", stiffness: 420, damping: 18, delay: reducedMotion ? 0 : 0.1 }}
                        style={{ display: "flex" }}
                      >
                        <CheckCircleRoundedIcon fontSize="small" color="success" />
                      </fm.div>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {rule.name || rule.rule_id}
                      </Typography>
                    </Stack>
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
                </fm.div>
              ))}
            </AnimatePresence>
          </Stack>
        </Box>
      ) : null}

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
          onReject={(rule) => decide(rule, "reject", "Rejected by reviewer")}
        />

        <RuleReviewPool
          poolId="approved"
          title="Approved"
          helper="Rules already checked and used when you compile the live lookup index."
          statusFilter="active"
          rules={filterByGuideline(approvedRules)}
          loading={loadingApproved}
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
