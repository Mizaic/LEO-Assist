/**
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 */
"use client";

import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { EmptyState, NudgeStrip } from "@leo/design-system";
import { RuleAccordionCard, SessionApprovedRow, type RuleCardCallbacks } from "./RuleReviewCard";
import type { Rule, PromoteResult, RuleStatusFilter } from "./RuleReviewSection";

interface SessionApprovedState {
  rules: Rule[];
  promotedRules: Record<string, PromoteResult>;
  promoteBusy: string | null;
}

interface RuleListState {
  rules: Rule[];
  expandedRules: Record<string, boolean>;
  busy: string | null;
}

interface RuleListActions {
  onToggle: (ruleId: string) => void;
  onEdit: (rule: Rule) => void;
  onApprove: (rule: Rule) => void;
  onReject: (rule: Rule) => void;
}

interface SessionApprovedActions {
  onEdit: (rule: Rule) => void;
  onPromote: (rule: Rule) => void;
}

interface Props {
  sessionApproved: SessionApprovedState;
  ruleList: RuleListState;
  statusFilter: RuleStatusFilter;
  listActions: RuleListActions;
  sessionActions: SessionApprovedActions;
}

const EMPTY_COPY: Record<RuleStatusFilter, string> = {
  pending_review: "No rules waiting for review. Load a guideline first, then generate rules.",
  active: "No active rules yet. Approve a pending rule to make it active.",
  superseded: "No superseded rules. Edits to active rules will appear here as a read-only history.",
};

export default function RuleReviewList({ sessionApproved, ruleList, statusFilter, listActions, sessionActions }: Props) {
  return (
    <Box>
      {sessionApproved.rules.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <NudgeStrip
            severity="info"
            icon={<CheckCircleOutlineIcon fontSize="small" />}
            message={`${sessionApproved.rules.length} rule${sessionApproved.rules.length !== 1 ? "s" : ""} approved in this session.`}
          />
          <Stack spacing={1}>
            {sessionApproved.rules.map((rule) => (
              <SessionApprovedRow
                key={rule.rule_id}
                rule={rule}
                promotedResult={sessionApproved.promotedRules[rule.rule_id]}
                promoteBusy={sessionApproved.promoteBusy === rule.rule_id}
                onEdit={() => sessionActions.onEdit(rule)}
                onPromote={() => sessionActions.onPromote(rule)}
              />
            ))}
          </Stack>
        </Box>
      )}

      {ruleList.rules.length === 0 ? (
        <EmptyState
          icon={<HistoryOutlinedIcon fontSize="large" />}
          title={statusFilter === "pending_review" ? "No rules pending" : statusFilter === "active" ? "No active rules" : "No superseded rules"}
          body={EMPTY_COPY[statusFilter]}
          data-testid="rule-list-empty"
        />
      ) : (
        <Stack spacing={0}>
          {ruleList.rules.map((rule, index) => {
            const callbacks: RuleCardCallbacks = {
              onToggle: () => listActions.onToggle(rule.rule_id),
              onEdit: () => listActions.onEdit(rule),
              onApprove: statusFilter === "pending_review" ? () => listActions.onApprove(rule) : undefined,
              onReject: statusFilter === "pending_review" ? () => listActions.onReject(rule) : undefined,
            };
            return (
              <RuleAccordionCard
                key={rule.rule_id}
                rule={rule}
                expanded={!!ruleList.expandedRules[rule.rule_id]}
                busy={ruleList.busy}
                index={index}
                statusFilter={statusFilter}
                callbacks={callbacks}
              />
            );
          })}
        </Stack>
      )}
    </Box>
  );
}
