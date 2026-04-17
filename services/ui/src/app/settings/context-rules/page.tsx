"use client";

/**
 * Context Rules -- Wave E Phase 3a redesign
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes:
 *   - StatHero: total / built-in / custom / active counts at a glance.
 *   - SegmentedTabs: source filter (All / Built-in / Custom).
 *   - ToolbarActions: Export PDF + Add rule.
 *   - ReviewListCard: one row per rule with progressive disclosure of
 *     the plain-English description and example.
 *
 * Design Controls: DI-LEO-AI-147, DO-LEO-AI-143, VT-LEO-AI-145.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { FilterView as PdfFilterView } from "@/lib/exportContextRulesPdf";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DownloadIcon from "@mui/icons-material/Download";
import {
  ProgressiveReveal,
  ReviewListCard,
  SegmentedTabs,
  StatHero,
  ToolbarActions,
  type ReviewListItem,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

// -- Constants ---------------------------------------------------------------

const CATEGORIES = [
  "NEGATED_EXISTENCE",
  "POSSIBLE_EXISTENCE",
  "HISTORICAL",
  "HYPOTHETICAL",
  "FAMILY",
  "DECLINED",
];

const DIRECTIONS = ["FORWARD", "BACKWARD", "BIDIRECTIONAL"];

const CATEGORY_COLOR: Record<string, "error" | "warning" | "info" | "default" | "success"> = {
  NEGATED_EXISTENCE: "error",
  DECLINED: "error",
  POSSIBLE_EXISTENCE: "warning",
  HISTORICAL: "info",
  HYPOTHETICAL: "primary" as never,
  FAMILY: "default",
  CANCELLED: "default",
};

const CATEGORY_LABEL: Record<string, string> = {
  NEGATED_EXISTENCE: "Not present",
  POSSIBLE_EXISTENCE: "Possibly present",
  HISTORICAL: "Historical",
  HYPOTHETICAL: "Planned / pending",
  FAMILY: "Family member",
  DECLINED: "Patient declined",
  CANCELLED: "Appointment missed",
};

// -- Types -------------------------------------------------------------------

type RuleSource = "builtin" | "custom";
type FilterView = "all" | "builtin" | "custom";

interface ContextRule {
  rule_id: string | null;
  literal: string;
  category: string;
  direction: string;
  max_scope: number;
  description: string;
  example: string;
  created_by: string;
  active: boolean;
  created_at: string | null;
  source: RuleSource;
  org_id: string | null;
}

// -- Fetch helpers -----------------------------------------------------------

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// -- Stats -------------------------------------------------------------------

function computeStats(rules: ContextRule[]): StatTile[] {
  const total = rules.length;
  const builtin = rules.filter((r) => r.source === "builtin").length;
  const custom = rules.filter((r) => r.source === "custom").length;
  const active = rules.filter((r) => r.active || r.source === "builtin").length;
  return [
    {
      id: "total",
      label: "Rules in use",
      value: total,
      hint: "All context rules LEO can apply",
    },
    {
      id: "builtin",
      label: "Built-in",
      value: builtin,
      hint: "Shipped with LEO; read-only",
    },
    {
      id: "custom",
      label: "Custom",
      value: custom,
      hint: "Added by your organisation",
      tone: custom > 0 ? "positive" : "neutral",
    },
    {
      id: "active",
      label: "Active",
      value: active,
      hint: total > 0 ? `${Math.round((active / total) * 100)}% applied at runtime` : "--",
      tone: "positive",
    },
  ];
}

// -- Per-rule renderers ------------------------------------------------------

function ruleTitle(rule: ContextRule) {
  const hasDetail = !!(rule.description || rule.example);
  return (
    <Stack spacing={0.5}>
      <code
        style={{
          fontFamily:
            "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "0.95rem",
          fontWeight: 600,
          color: "#0f172a",
        }}
      >
        {rule.literal}
      </code>
      {hasDetail ? (
        <ProgressiveReveal summary="Why this rule exists">
          {rule.description ? (
            <Typography variant="body2" sx={{ mb: rule.example ? 0.75 : 0 }}>
              {rule.description}
            </Typography>
          ) : null}
          {rule.example ? (
            <Box
              component="code"
              sx={{
                display: "block",
                fontFamily:
                  "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: "0.78rem",
                px: 1.25,
                py: 0.6,
                borderRadius: 1,
                bgcolor: "#F1F5F9",
                color: "text.secondary",
                whiteSpace: "pre-wrap",
              }}
            >
              e.g. {rule.example}
            </Box>
          ) : null}
        </ProgressiveReveal>
      ) : null}
    </Stack>
  );
}

function ruleMeta(rule: ContextRule) {
  return (
    <>
      <span>{CATEGORY_LABEL[rule.category] ?? rule.category}</span>
      <span>{rule.direction}</span>
      <span>scope {rule.max_scope}</span>
      {rule.created_by ? <span>by {rule.created_by}</span> : null}
    </>
  );
}

function ruleChips(rule: ContextRule) {
  const isBuiltin = rule.source === "builtin";
  const statusActive = rule.active || isBuiltin;
  return (
    <>
      <Chip
        label={rule.category}
        size="small"
        color={CATEGORY_COLOR[rule.category] ?? "default"}
        sx={{ fontSize: "0.65rem", height: 20 }}
      />
      <Chip
        label={isBuiltin ? "Built-in" : "Custom"}
        size="small"
        variant="outlined"
        color={isBuiltin ? "default" : "primary"}
        sx={{ fontSize: "0.65rem", height: 20 }}
      />
      <Chip
        label={statusActive ? "Active" : "Inactive"}
        size="small"
        variant="outlined"
        color={statusActive ? "success" : "default"}
        sx={{ fontSize: "0.65rem", height: 20 }}
      />
    </>
  );
}

function ruleActions(
  rule: ContextRule,
  onDeactivate: (id: string) => void,
) {
  if (rule.source !== "custom" || !rule.active || !rule.rule_id) return null;
  const id = rule.rule_id;
  return (
    <Button
      size="small"
      color="warning"
      variant="text"
      onClick={() => onDeactivate(id)}
      sx={{ textTransform: "none", fontSize: "0.78rem" }}
    >
      Deactivate
    </Button>
  );
}

// -- Page --------------------------------------------------------------------

export default function ContextRulesPage() {
  const [rules, setRules] = useState<ContextRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<FilterView>("all");

  const [addOpen, setAddOpen] = useState(false);
  const [literal, setLiteral] = useState("");
  const [category, setCategory] = useState("NEGATED_EXISTENCE");
  const [direction, setDirection] = useState("FORWARD");
  const [maxScope, setMaxScope] = useState(6);
  const [description, setDescription] = useState("");
  const [example, setExample] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  const loadRules = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await jsonFetch<{ rules: ContextRule[] }>(
        "/api/training/context-rules?active_only=false&include_builtin=true",
      );
      setRules(data.rules ?? []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRules();
  }, [loadRules]);

  const handleAdd = useCallback(async () => {
    if (!literal.trim()) return;
    setSaving(true);
    setSaveError("");
    try {
      await jsonFetch("/api/training/context-rules", {
        method: "POST",
        body: JSON.stringify({
          literal: literal.trim(),
          category,
          direction,
          max_scope: maxScope,
          description: description.trim(),
          example: example.trim(),
        }),
      });
      setLiteral("");
      setDescription("");
      setExample("");
      setAddOpen(false);
      await loadRules();
    } catch (e) {
      setSaveError(String(e));
    } finally {
      setSaving(false);
    }
  }, [literal, category, direction, maxScope, description, example, loadRules]);

  const handleDeactivate = useCallback(async (ruleId: string) => {
    try {
      await jsonFetch(`/api/training/context-rules/${ruleId}/deactivate`, {
        method: "PATCH",
      });
      setRules((prev) =>
        prev.map((r) => (r.rule_id === ruleId ? { ...r, active: false } : r)),
      );
    } catch {
      setError("Could not deactivate rule. Please try again.");
    }
  }, []);

  const visibleRules = useMemo(
    () => rules.filter((r) => filter === "all" || r.source === filter),
    [rules, filter],
  );
  const builtinCount = useMemo(
    () => rules.filter((r) => r.source === "builtin").length,
    [rules],
  );
  const customCount = useMemo(
    () => rules.filter((r) => r.source === "custom").length,
    [rules],
  );

  const handleExportPdf = useCallback(async () => {
    setExporting(true);
    setExportError("");
    try {
      const { exportContextRulesPdf } = await import(
        "@/lib/exportContextRulesPdf"
      );
      exportContextRulesPdf(visibleRules, filter as PdfFilterView);
    } catch (e) {
      setExportError(`PDF export failed: ${String(e)}`);
    } finally {
      setExporting(false);
    }
  }, [visibleRules, filter]);

  const stats = useMemo(() => computeStats(rules), [rules]);

  const toolbarActions: ToolbarAction[] = [
    {
      id: "export-pdf",
      label: exporting ? "Exporting" : "Export PDF",
      icon: <DownloadIcon fontSize="small" />,
      variant: "secondary",
      onClick: handleExportPdf,
      disabled: exporting || loading || visibleRules.length === 0,
      loading: exporting,
    },
    {
      id: "add-rule",
      label: addOpen ? "Cancel" : "Add rule",
      icon: addOpen ? undefined : <AddIcon fontSize="small" />,
      variant: "primary",
      onClick: () => setAddOpen((v) => !v),
    },
  ];

  const items: ReviewListItem[] = visibleRules.map((rule, i) => ({
    id: rule.rule_id ?? `builtin-${i}`,
    title: ruleTitle(rule),
    meta: ruleMeta(rule),
    chips: ruleChips(rule),
    actions: ruleActions(rule, handleDeactivate),
    tone: rule.active || rule.source === "builtin" ? "neutral" : "warning",
  }));

  return (
    <Box>
      <StatHero stats={stats} />

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}
      {exportError ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setExportError("")}>
          {exportError}
        </Alert>
      ) : null}

      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 2,
          flexWrap: "wrap",
          mb: 2,
        }}
      >
        <SegmentedTabs
          tabs={[
            { id: "all", label: "All", count: builtinCount + customCount },
            { id: "builtin", label: "Built-in", count: builtinCount },
            { id: "custom", label: "Custom", count: customCount },
          ]}
          value={filter}
          onChange={(id) => setFilter(id as FilterView)}
          aria-label="Filter context rules by source"
        />
        <ToolbarActions actions={toolbarActions} />
      </Box>

      {filter !== "all" ? (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mb: 2 }}
        >
          {filter === "builtin"
            ? "Shipped with LEO. Read-only and shared across all organisations."
            : "Added by your organisation's admins. Applied on next worker restart."}
        </Typography>
      ) : null}

      {addOpen ? (
        <Paper
          variant="outlined"
          sx={{
            p: 2.25,
            mb: 3,
            borderRadius: 2,
            bgcolor: "#F8FAFC",
          }}
          data-testid="context-rules-add-form"
        >
          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
            New custom context rule
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 1.5 }}
          >
            Adding a plain-English description helps colleagues understand why
            the rule exists.
          </Typography>
          <Stack spacing={2}>
            <TextField
              label="Phrase"
              size="small"
              value={literal}
              onChange={(e) => setLiteral(e.target.value)}
              placeholder='e.g. "would not consider"'
              helperText="The exact phrase the system will look for. Saved as lower-case."
              fullWidth
            />
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <InputLabel>What does it mean?</InputLabel>
                <Select
                  label="What does it mean?"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {CATEGORIES.map((c) => (
                    <MenuItem key={c} value={c}>
                      <Stack>
                        <Typography variant="body2">
                          {CATEGORY_LABEL[c] ?? c}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {c}
                        </Typography>
                      </Stack>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 160 }}>
                <InputLabel>Direction</InputLabel>
                <Select
                  label="Direction"
                  value={direction}
                  onChange={(e) => setDirection(e.target.value)}
                >
                  {DIRECTIONS.map((d) => (
                    <MenuItem key={d} value={d}>
                      {d}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                label="Max scope (words)"
                type="number"
                size="small"
                value={maxScope}
                onChange={(e) => setMaxScope(Number(e.target.value))}
                inputProps={{ min: 1, max: 20 }}
                sx={{ width: 160 }}
              />
            </Stack>
            <TextField
              label="Plain-English description (optional but helpful)"
              size="small"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Explain what this phrase means and why the rule is needed."
              multiline
              minRows={2}
              fullWidth
            />
            <TextField
              label="Example (optional)"
              size="small"
              value={example}
              onChange={(e) => setExample(e.target.value)}
              placeholder='e.g. "would not consider surgery -> patient declined"'
              fullWidth
            />
            {saveError ? (
              <Alert severity="error" sx={{ py: 0.5 }}>
                {saveError}
              </Alert>
            ) : null}
            <Box>
              <Button
                variant="contained"
                size="small"
                onClick={handleAdd}
                disabled={saving || !literal.trim()}
                startIcon={
                  saving ? (
                    <CircularProgress size={14} color="inherit" />
                  ) : undefined
                }
                sx={{ textTransform: "none" }}
              >
                {saving ? "Saving..." : "Save rule"}
              </Button>
            </Box>
          </Stack>
        </Paper>
      ) : null}

      {loading ? (
        <Stack alignItems="center" sx={{ py: 6 }}>
          <CircularProgress aria-label="Loading" size={28} />
        </Stack>
      ) : (
        <ReviewListCard
          items={items}
          emptyState={
            filter === "custom"
              ? 'No custom rules yet. Click "Add rule" to teach the system a new pattern.'
              : "No rules match the current filter."
          }
        />
      )}
    </Box>
  );
}
