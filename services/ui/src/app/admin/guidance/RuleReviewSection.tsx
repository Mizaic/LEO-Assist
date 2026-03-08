"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
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
  recommendation_text: string;
  plain_english: string;
  present_criteria: Criterion[];
  absent_criteria: Criterion[];
}

interface Props {
  refreshKey?: number;
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

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch("/api/guidance/rules/review?status=pending_review")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then(setRules)
      .catch(() => setError("Could not load rules to review. Please try again."))
      .finally(() => setLoading(false));
  }, [refreshKey, internalKey]);

  const decide = useCallback(
    async (ruleId: string, action: "approve" | "reject" | "edit", reason = "Admin review") => {
      setBusy(ruleId);
      setActionError(null);
      try {
        const resp = await fetch(`/api/guidance/rules/review/${ruleId}/decision`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, reviewer: "admin", reason }),
        });
        if (!resp.ok) throw new Error(await resp.text());
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
      setInternalKey((n) => n + 1);
    } catch {
      setActionError("Could not approve all rules. Please try again.");
    } finally {
      setBusy(null);
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
      {actionError && <Alert severity="error" sx={{ mb: 2 }}>{actionError}</Alert>}

      {rules.length === 0 ? (
        <Typography color="text.secondary">
          No rules waiting for review. Load a guideline first, then generate rules.
        </Typography>
      ) : (
        <>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
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
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                    <Chip label={rule.guideline_id} size="small" color="primary" variant="outlined" />
                    {rule.strength && (
                      <Chip label={rule.strength} size="small" variant="outlined" />
                    )}
                  </Stack>

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

                  <Typography variant="body2" sx={{ mb: 2, fontWeight: 500 }}>
                    {rule.plain_english}
                  </Typography>

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
                          onClick={() => decide(rule.rule_id, "edit", editReason)}
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
                        onClick={() => decide(rule.rule_id, "approve")}
                        aria-label={`Approve rule ${rule.rule_id}`}
                      >
                        Looks right
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={busy === rule.rule_id}
                        onClick={() => { setEditingRule(rule.rule_id); setEditReason(""); }}
                        aria-label={`Edit rule ${rule.rule_id}`}
                      >
                        Edit
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        color="error"
                        disabled={busy === rule.rule_id}
                        onClick={() => decide(rule.rule_id, "reject", "Rejected by reviewer")}
                        aria-label={`Reject rule ${rule.rule_id}`}
                      >
                        Reject
                      </Button>
                    </Stack>
                  )}
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
    </Box>
  );
}
