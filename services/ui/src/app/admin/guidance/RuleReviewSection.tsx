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
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CompareArrowsIcon from "@mui/icons-material/CompareArrows";
import RemoveCircleOutlineIcon from "@mui/icons-material/RemoveCircleOutline";
import ConfirmDialog from "@/components/ConfirmDialog";

interface Criterion {
  predicate: string;
  concept_id: string;
  preferred_term: string;
}

interface Rule {
  rule_id: string;
  name: string;
  status: string;
  strength: string;
  guideline_id: string;
  guideline_version?: number;
  chapter_title?: string;
  recommendation_text: string;
  plain_english: string;
  present_criteria: Criterion[];
  absent_criteria: Criterion[];
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
                      {data.predecessor!.decisions.map((d, i) => (
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

export default function RuleReviewSection({ refreshKey }: Props) {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [internalKey, setInternalKey] = useState(0);
  const [approveAllOpen, setApproveAllOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<string | null>(null);
  const [editReason, setEditReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const [promoteConfirmRule, setPromoteConfirmRule] = useState<Rule | null>(null);
  const [promotedRules, setPromotedRules] = useState<Record<string, PromoteResult>>({});
  const [promoteBusy, setPromoteBusy] = useState<string | null>(null);
  const [promoteError, setPromoteError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch("/api/guidance/rules/review?status=pending_review")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setRules)
      .catch(() => setError("Could not load rules to review. Please try again."))
      .finally(() => setLoading(false));
  }, [refreshKey, internalKey]);

  const [sessionApproved, setSessionApproved] = useState<Rule[]>([]);

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
        setInternalKey((n) => n + 1);
        setEditingRule(null);
      } catch {
        setActionError("Could not save your decision. Please try again.");
      } finally {
        setBusy(null);
      }
    },
    []
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

      {/* Approved rules from this session */}
      {sessionApproved.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1, color: "success.main" }}>
            Approved in this session
          </Typography>
          <Stack spacing={2}>
            {sessionApproved.map((rule) => (
              <Card key={rule.rule_id} variant="outlined" sx={{ borderColor: "success.light" }}>
                <CardContent>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                    <CheckCircleOutlineIcon color="success" fontSize="small" />
                    <Chip label={rule.guideline_id} size="small" color="success" variant="outlined" />
                    <Chip label="Approved" size="small" color="success" />
                  </Stack>
                  <Typography variant="body2" sx={{ mb: 1.5, fontWeight: 500 }}>
                    {rule.plain_english}
                  </Typography>
                  {promotedRules[rule.rule_id] ? (
                    <Alert severity="success" sx={{ py: 0.5 }}>
                      Added {promotedRules[rule.rule_id].concepts_added} code
                      {promotedRules[rule.rule_id].concepts_added !== 1 ? "s" : ""} to{" "}
                      <Link href={`/admin/domains`} underline="hover">
                        {promotedRules[rule.rule_id].domain_name}
                      </Link>
                      .
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
                      {promoteBusy === rule.rule_id ? "Adding\u2026" : "Add to domain"}
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </Stack>
        </Box>
      )}

      {/* Pending rules */}
      {rules.length === 0 ? (
        <Typography color="text.secondary">
          No rules waiting for review. Load a guideline first, then generate rules.
        </Typography>
      ) : (
        <>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: 2 }}
          >
            <Typography variant="body2" color="text.secondary">
              {rules.length} rule{rules.length !== 1 ? "s" : ""} to check
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

          <Stack spacing={2}>
            {rules.map((rule) => (
              <Card key={rule.rule_id} variant="outlined">
                <CardContent>
                  {/* Header chips */}
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" sx={{ mb: 1 }}>
                    <Chip label={rule.guideline_id} size="small" color="primary" variant="outlined" />
                    {rule.guideline_version && rule.guideline_version > 1 && (
                      <Chip
                        label={`v${rule.guideline_version}`}
                        size="small"
                        color="warning"
                        variant="outlined"
                        title={`This is version ${rule.guideline_version} of the guideline`}
                      />
                    )}
                    {rule.chapter_title && (
                      <Typography variant="caption" color="text.secondary">
                        {rule.chapter_title}
                      </Typography>
                    )}
                    {rule.strength && (
                      <Chip label={rule.strength} size="small" variant="outlined" />
                    )}
                    {rule.has_predecessor && (
                      <Chip
                        icon={<CompareArrowsIcon />}
                        label="Updated rule"
                        size="small"
                        color="warning"
                        variant="outlined"
                        title="This recommendation had a previous approved version"
                      />
                    )}
                  </Stack>

                  {/* Source recommendation text */}
                  {rule.recommendation_text && (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ mb: 1, fontStyle: "italic", fontSize: "0.8rem" }}
                    >
                      &ldquo;{rule.recommendation_text.slice(0, 200)}
                      {rule.recommendation_text.length > 200 ? "..." : ""}&rdquo;
                    </Typography>
                  )}

                  {/* AI-generated plain-English rule */}
                  <Typography variant="body2" sx={{ mb: 1.5, fontWeight: 500 }}>
                    {rule.plain_english}
                  </Typography>

                  {/* Version diff panel — only shown when a predecessor exists */}
                  {rule.has_predecessor && <DiffPanel ruleId={rule.rule_id} />}

                  <Box sx={{ mt: 2 }}>
                    {editingRule === rule.rule_id ? (
                      <Box>
                        <TextField
                          fullWidth
                          size="small"
                          label="Reason for edit"
                          value={editReason}
                          onChange={(e) => setEditReason(e.target.value)}
                          sx={{ mb: 1 }}
                          inputProps={{ "aria-label": "Reason for editing this rule" }}
                        />
                        <Stack direction="row" spacing={1}>
                          <Button
                            size="small"
                            variant="contained"
                            disabled={busy === rule.rule_id || !editReason.trim()}
                            onClick={() => decide(rule, "edit", editReason)}
                          >
                            Save edit
                          </Button>
                          <Button size="small" onClick={() => setEditingRule(null)}>
                            Cancel
                          </Button>
                        </Stack>
                      </Box>
                    ) : (
                      <Stack direction="row" spacing={1}>
                        <Button
                          size="small"
                          variant="contained"
                          color="success"
                          disabled={busy === rule.rule_id}
                          onClick={() => decide(rule, "approve")}
                          aria-label={`Approve rule ${rule.rule_id}`}
                        >
                          Looks right
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={busy === rule.rule_id}
                          onClick={() => {
                            setEditingRule(rule.rule_id);
                            setEditReason("");
                          }}
                          aria-label={`Edit rule ${rule.rule_id}`}
                        >
                          Edit
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          color="error"
                          disabled={busy === rule.rule_id}
                          onClick={() => decide(rule, "reject", "Rejected by reviewer")}
                          aria-label={`Reject rule ${rule.rule_id}`}
                        >
                          Reject
                        </Button>
                      </Stack>
                    )}
                  </Box>
                </CardContent>
              </Card>
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
