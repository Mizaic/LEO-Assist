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
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CompareArrowsIcon from "@mui/icons-material/CompareArrows";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import ConfirmDialog from "@/components/ConfirmDialog";
import EditRuleDialog from "./EditRuleDialog";
import { compareIsoDateTimeAsc } from "@/lib/dateSort";

interface Criterion {
  predicate: string;
  concept_id: string;
  preferred_term: string;
}

interface CriterionResult {
  term: string;
  snomed_concept_id: string | null;
  preferred_term: string;
  semantic_tag: string;
  verification_status?: string;
}

interface LogicTreeNode {
  kind: string;
  node_id?: string;
  children?: LogicTreeNode[];
  min?: number;
  criterion?: CriterionResult;
  field?: string;
  operator?: string;
  value?: number | string | null;
  unit?: string | null;
}

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

// ---- Rule detail panel (rendered inline when a row is expanded) ---------------

function SnomedChip({ item }: { item: CriterionResult }) {
  const resolved = !!item.snomed_concept_id;
  return (
    <Tooltip
      title={resolved ? `SNOMED: ${item.snomed_concept_id} | ${item.semantic_tag}` : "No SNOMED match found"}
      arrow
    >
      <Chip
        label={resolved ? item.preferred_term : `? ${item.term}`}
        size="small"
        color={resolved ? "success" : "warning"}
        variant={resolved ? "filled" : "outlined"}
        sx={{ height: 20, fontSize: "0.68rem", mr: 0.4, mb: 0.4 }}
      />
    </Tooltip>
  );
}

function LogicNodePanel({ node, depth = 0 }: { node: LogicTreeNode; depth?: number }) {
  const kind = String(node.kind || "").toUpperCase();

  if (kind === "CONCEPT") {
    if (node.criterion) return <SnomedChip item={node.criterion} />;
    return (
      <Chip
        label="unknown concept"
        size="small"
        variant="outlined"
        color="default"
        sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
      />
    );
  }

  if (kind === "DEMOGRAPHIC") {
    const label = `${node.field ?? "?"} ${node.operator ?? "="} ${node.value ?? "?"}${node.unit ? ` ${node.unit}` : ""}`;
    return (
      <Chip
        label={label}
        size="small"
        variant="filled"
        color="secondary"
        sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
      />
    );
  }

  const title =
    kind === "AND" ? "ALL of these"
    : kind === "OR" ? "ANY of these"
    : kind === "NOT" ? "NOT"
    : `AT LEAST ${node.min ?? 1}`;

  return (
    <Box sx={{ ml: depth ? 1.5 : 0, mt: 0.5, pl: 1, borderLeft: "2px solid", borderColor: "divider" }}>
      <Typography variant="caption" sx={{ fontWeight: 700, color: "text.secondary", display: "block", mb: 0.4 }}>
        {title}
      </Typography>
      <Box>
        {(node.children ?? []).map((child, idx) => (
          <LogicNodePanel key={child.node_id ?? `${kind}-${idx}`} node={child} depth={depth + 1} />
        ))}
      </Box>
    </Box>
  );
}

function V1CriteriaFallback({ present, absent }: { present: Criterion[]; absent: Criterion[] }) {
  if (present.length === 0 && absent.length === 0) {
    return (
      <Typography variant="body2" color="text.disabled" sx={{ fontSize: "0.78rem", fontStyle: "italic" }}>
        No criteria stored for this rule.
      </Typography>
    );
  }
  return (
    <>
      {present.length > 0 && (
        <Box sx={{ mt: 0.5, pl: 1, borderLeft: "2px solid", borderColor: "divider" }}>
          <Typography variant="caption" sx={{ fontWeight: 700, color: "text.secondary", display: "block", mb: 0.4 }}>
            ANY of these
          </Typography>
          <Box>
            {present.map((c) => (
              <Tooltip key={c.concept_id} title={`${c.predicate} | ${c.concept_id}`} arrow>
                <Chip label={c.preferred_term || c.concept_id} size="small" color="success" variant="outlined"
                  sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }} />
              </Tooltip>
            ))}
          </Box>
        </Box>
      )}
      {absent.length > 0 && (
        <Box sx={{ mt: 0.5, pl: 1, borderLeft: "2px solid", borderColor: "error.light" }}>
          <Typography variant="caption" sx={{ fontWeight: 700, color: "text.secondary", display: "block", mb: 0.4 }}>
            NOT any of these
          </Typography>
          <Box>
            {absent.map((c) => (
              <Tooltip key={c.concept_id} title={`${c.predicate} | ${c.concept_id}`} arrow>
                <Chip label={c.preferred_term || c.concept_id} size="small" color="error" variant="outlined"
                  sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }} />
              </Tooltip>
            ))}
          </Box>
        </Box>
      )}
    </>
  );
}

function RuleDetailPanel({ rule }: { rule: Rule }) {
  const hasLogicTree = !!rule.logic_tree;

  return (
    <Box
      sx={{
        mt: 1.5,
        p: 1.5,
        bgcolor: "primary.50",
        border: "1px solid",
        borderColor: "primary.200",
        borderRadius: 1,
      }}
    >
      <Typography variant="caption" sx={{ fontWeight: 700, color: "primary.dark", display: "block", mb: 1 }}>
        Exact rule logic
      </Typography>

      {hasLogicTree ? (
        <LogicNodePanel node={rule.logic_tree!} />
      ) : (
        <V1CriteriaFallback present={rule.present_criteria} absent={rule.absent_criteria} />
      )}

      {rule.strength && rule.strength !== "unspecified" && (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="info.dark" sx={{ fontWeight: 600, display: "block", mb: 0.3 }}>
            Recommended action
          </Typography>
          <Chip
            label={rule.strength}
            size="small"
            variant="outlined"
            color="info"
            sx={{ fontSize: "0.68rem", height: 20 }}
          />
        </Box>
      )}
    </Box>
  );
}

// ---- Accordion rule card -----------------------------------------------------

interface RuleAccordionCardProps {
  rule: Rule;
  expanded: boolean;
  busy: string | null;
  onToggle: () => void;
  onApprove: () => void;
  onEdit: () => void;
  onReject: () => void;
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
              <Button
                variant="outlined"
                size="small"
                disabled={isBusy}
                onClick={(e) => { e.stopPropagation(); onEdit(); }}
                aria-label={`Edit rule ${rule.rule_id}`}
              >
                Edit
              </Button>
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
              {isBusy && <CircularProgress size={16} aria-label="Saving decision" />}
            </Stack>
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ---- Main section ------------------------------------------------------------

export default function RuleReviewSection({ refreshKey }: Props) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [internalKey, setInternalKey] = useState(0);
  const [approveAllOpen, setApproveAllOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [expandedRules, setExpandedRules] = useState<Record<string, boolean>>({});

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
    fetch("/api/guidance/rules/review?status=pending_review")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setRules)
      .catch(() => setError("Could not load rules to review. Please try again."))
      .finally(() => setLoading(false));
  }, [refreshKey, internalKey]);

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
          const detail = await resp.json().catch(() => ({ detail: resp.statusText }));
          throw new Error(detail.detail || resp.statusText);
        }
        const body = await resp.json().catch(() => ({}));
        const newRuleId = (body && body.rule_id) || editRule.rule_id;
        setSessionApproved((prev) => [
          ...prev.filter((r) => r.rule_id !== editRule.rule_id),
          {
            ...editRule,
            rule_id: newRuleId,
            status: "active",
            name: payload.name || editRule.name,
            strength: payload.strength || editRule.strength,
          },
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
        rule={editRule}
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
                  {promotedRules[rule.rule_id] ? (
                    <Alert severity="success" sx={{ py: 0.5 }}>
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
                </CardContent>
              </Card>
            ))}
          </Stack>
        </Box>
      )}

      {/* ---- Pending rules accordion list ---- */}
      {rules.length === 0 ? (
        <Typography color="text.secondary">
          No rules waiting for review. Load a guideline first, then generate rules.
        </Typography>
      ) : (
        <>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              {rules.length} rule{rules.length !== 1 ? "s" : ""} to check — click a row to read in full
            </Typography>
            <Button
              variant="outlined"
              size="small"
              disabled={busy === "all"}
              onClick={() => setApproveAllOpen(true)}
              aria-label="Approve all rules"
            >
              Approve all
            </Button>
          </Stack>

          <Stack spacing={1}>
            {rules.map((rule) => (
              <RuleAccordionCard
                key={rule.rule_id}
                rule={rule}
                expanded={!!expandedRules[rule.rule_id]}
                busy={busy}
                onToggle={() => toggleExpanded(rule.rule_id)}
                onApprove={() => decide(rule, "approve")}
                onEdit={() => setEditRule(rule)}
                onReject={() => decide(rule, "reject", "Rejected by reviewer")}
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
