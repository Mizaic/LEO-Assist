"use client";

import { useCallback, useEffect, useState } from "react";
import type { FilterView as PdfFilterView } from "@/lib/exportContextRulesPdf";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DownloadIcon from "@mui/icons-material/Download";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";

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
  NEGATED_EXISTENCE:  "error",
  DECLINED:           "error",
  POSSIBLE_EXISTENCE: "warning",
  HISTORICAL:         "info",
  HYPOTHETICAL:       "primary" as never,
  FAMILY:             "default",
  CANCELLED:          "default",
};

const CATEGORY_LABEL: Record<string, string> = {
  NEGATED_EXISTENCE:  "Not present",
  POSSIBLE_EXISTENCE: "Possibly present",
  HISTORICAL:         "Historical",
  HYPOTHETICAL:       "Planned / pending",
  FAMILY:             "Family member",
  DECLINED:           "Patient declined",
  CANCELLED:          "Appointment missed",
};

// -- Types -------------------------------------------------------------------

type RuleSource = "builtin" | "custom";
type FilterView  = "all" | "builtin" | "custom";

interface ContextRule {
  rule_id:     string | null;
  literal:     string;
  category:    string;
  direction:   string;
  max_scope:   number;
  description: string;
  example:     string;
  created_by:  string;
  active:      boolean;
  created_at:  string | null;
  source:      RuleSource;
  org_id:      string | null;
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

// -- Column header with tooltip ----------------------------------------------

const COL_TIPS: Record<string, string> = {
  Phrase:
    "The exact word or phrase LEO looks for in the clinical note. Not case-sensitive. " +
    "When this phrase is found near a condition, the rule changes how that condition is coded.",
  Category:
    "What the phrase signals about the nearby condition. For example, 'Patient declined' means " +
    "the patient said no, so the condition or procedure should not be coded as having happened.",
  Direction:
    "Which direction from the phrase the rule applies to. " +
    "FORWARD: the phrase comes first — e.g. 'declined colonoscopy' (declined → then the condition). " +
    "BACKWARD: the condition comes first — e.g. 'colonoscopy was declined' (condition → then declined). " +
    "BIDIRECTIONAL: works either way — e.g. 'mum had diabetes' or 'diabetes (mum)'.",
  Scope:
    "How many words either side of the phrase are checked. A scope of 6 means up to 6 words " +
    "before or after the phrase. Wider scope catches more cases but can affect unrelated conditions.",
  Source:
    "Built-in rules come with LEO and apply to all organisations. " +
    "Custom rules were added by your organisation's admin and apply to your organisation only.",
  "Added by": "The email address of the person who added this rule (custom rules only).",
  Status:
    "Active rules are applied every time the coding pipeline runs. " +
    "Inactive rules are kept for reference but have no effect.",
};

function ColHeader({ label, align }: { label: string; align?: "right" }) {
  const tip = COL_TIPS[label];
  return (
    <TableCell align={align}>
      <Stack direction="row" alignItems="center" spacing={0.5} justifyContent={align === "right" ? "flex-end" : "flex-start"}>
        <span>{label}</span>
        {tip && (
          <Tooltip title={tip} arrow placement="top">
            <InfoOutlinedIcon sx={{ fontSize: "0.85rem", color: "text.disabled", cursor: "help", flexShrink: 0 }} />
          </Tooltip>
        )}
      </Stack>
    </TableCell>
  );
}

// -- Expandable rule row -----------------------------------------------------

function RuleRow({
  rule,
  onDeactivate,
}: {
  rule: ContextRule;
  onDeactivate: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const hasDetail = !!(rule.description || rule.example);

  return (
    <>
      <TableRow
        sx={{
          opacity: rule.active ? 1 : 0.45,
          bgcolor: rule.source === "builtin" ? "action.hover" : undefined,
          cursor: hasDetail ? "pointer" : "default",
          "& > td": { borderBottom: open ? "none" : undefined },
        }}
        onClick={() => hasDetail && setOpen((v) => !v)}
      >
        {/* Expand chevron */}
        <TableCell sx={{ width: 32, pr: 0, pl: 1 }}>
          {hasDetail ? (
            <IconButton size="small" tabIndex={-1} aria-label={open ? "Collapse" : "Expand"}>
              {open ? <KeyboardArrowDownIcon fontSize="small" /> : <KeyboardArrowRightIcon fontSize="small" />}
            </IconButton>
          ) : null}
        </TableCell>

        {/* Phrase */}
        <TableCell>
          <Typography variant="body2" sx={{ fontFamily: "monospace", fontWeight: 500 }}>
            {rule.literal}
          </Typography>
        </TableCell>

        {/* Category — friendly label on top, technical chip below */}
        <TableCell>
          <Stack spacing={0.25}>
            <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.2 }}>
              {CATEGORY_LABEL[rule.category] ?? rule.category}
            </Typography>
            <Chip
              label={rule.category}
              size="small"
              color={CATEGORY_COLOR[rule.category] ?? "default"}
              sx={{ maxWidth: 180, fontSize: "0.68rem" }}
            />
          </Stack>
        </TableCell>

        <TableCell>
          <Typography variant="caption">{rule.direction}</Typography>
        </TableCell>
        <TableCell align="right">
          <Typography variant="caption">{rule.max_scope}</Typography>
        </TableCell>

        {/* Source chip */}
        <TableCell>
          <Chip
            label={rule.source === "builtin" ? "Built-in" : "Custom"}
            size="small"
            variant="outlined"
            color={rule.source === "builtin" ? "default" : "primary"}
          />
        </TableCell>

        <TableCell>
          <Typography variant="caption" color="text.secondary">{rule.created_by}</Typography>
        </TableCell>

        {/* Status */}
        <TableCell>
          {rule.source === "builtin" ? (
            <Chip label="Active" size="small" color="success" variant="outlined" />
          ) : (
            <Chip
              label={rule.active ? "Active" : "Inactive"}
              size="small"
              color={rule.active ? "success" : "default"}
              variant="outlined"
            />
          )}
        </TableCell>

        {/* Actions */}
        <TableCell align="right" onClick={(e) => e.stopPropagation()}>
          {rule.source === "custom" && rule.active && rule.rule_id && (
            <Tooltip title="Deactivate this rule">
              <Button
                size="small"
                color="warning"
                variant="text"
                onClick={() => onDeactivate(rule.rule_id!)}
              >
                Deactivate
              </Button>
            </Tooltip>
          )}
        </TableCell>
      </TableRow>

      {/* Expanded detail row */}
      {hasDetail && (
        <TableRow sx={{ bgcolor: rule.source === "builtin" ? "action.hover" : undefined }}>
          <TableCell colSpan={9} sx={{ py: 0, borderTop: "none" }}>
            <Collapse in={open} timeout="auto" unmountOnExit>
              <Box sx={{ py: 1.5, px: 2, borderLeft: 3, borderColor: "primary.light", ml: 4, my: 1 }}>
                {rule.description && (
                  <Typography variant="body2" sx={{ mb: rule.example ? 0.75 : 0 }}>
                    {rule.description}
                  </Typography>
                )}
                {rule.example && (
                  <Typography
                    variant="caption"
                    sx={{
                      display: "block",
                      fontFamily: "monospace",
                      bgcolor: "action.selected",
                      px: 1.25,
                      py: 0.5,
                      borderRadius: 1,
                      color: "text.secondary",
                    }}
                  >
                    e.g. {rule.example}
                  </Typography>
                )}
              </Box>
            </Collapse>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

// -- Page --------------------------------------------------------------------

export default function ContextRulesPage() {
  const [rules, setRules]     = useState<ContextRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const [filter, setFilter]   = useState<FilterView>("all");

  // Add-rule form state.
  const [addOpen, setAddOpen]       = useState(false);
  const [literal, setLiteral]       = useState("");
  const [category, setCategory]     = useState("NEGATED_EXISTENCE");
  const [direction, setDirection]   = useState("FORWARD");
  const [maxScope, setMaxScope]     = useState(6);
  const [description, setDescription] = useState("");
  const [example, setExample]       = useState("");
  const [saving, setSaving]         = useState(false);
  const [saveError, setSaveError]   = useState("");
  const [exporting, setExporting]   = useState(false);
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

  useEffect(() => { loadRules(); }, [loadRules]);

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
      setLiteral(""); setDescription(""); setExample("");
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
      await jsonFetch(`/api/training/context-rules/${ruleId}/deactivate`, { method: "PATCH" });
      setRules((prev) => prev.map((r) => r.rule_id === ruleId ? { ...r, active: false } : r));
    } catch {
      setError("Could not deactivate rule. Please try again.");
    }
  }, []);

  const visibleRules  = rules.filter((r) => filter === "all" || r.source === filter);
  const builtinCount  = rules.filter((r) => r.source === "builtin").length;
  const customCount   = rules.filter((r) => r.source === "custom").length;

  const handleExportPdf = useCallback(async () => {
    setExporting(true);
    setExportError("");
    try {
      const { exportContextRulesPdf } = await import("@/lib/exportContextRulesPdf");
      exportContextRulesPdf(visibleRules, filter as PdfFilterView);
    } catch (e) {
      setExportError(`PDF export failed: ${String(e)}`);
    } finally {
      setExporting(false);
    }
  }, [visibleRules, filter]);

  return (
    <Box sx={{ maxWidth: 1000, mx: "auto", p: 3 }}>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link href="/settings" underline="hover" color="inherit">Settings</Link>
        <Typography color="text.primary">Context rules</Typography>
      </Breadcrumbs>

      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h5" gutterBottom>Context rules</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 640 }}>
            Context rules are a key part of how LEO reads clinical notes. Doctors often write things
            like <em>&quot;patient declined colonoscopy&quot;</em> or{" "}
            <em>&quot;awaiting CT scan&quot;</em>. Without these rules, the system might think the
            procedure actually happened when it did not. Context rules make sure that planned,
            declined, or historical events are recorded correctly — so the data matches what really
            took place. Click any row to see a simple explanation and an example.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} sx={{ ml: 2, flexShrink: 0 }}>
          <Tooltip title={`Export the currently visible rules as a PDF transparency report`}>
            <span>
              <Button
                variant="outlined"
                size="small"
                startIcon={exporting
                  ? <CircularProgress size={14} color="inherit" aria-label="Exporting" />
                  : <DownloadIcon fontSize="small" />
                }
                onClick={handleExportPdf}
                disabled={exporting || loading || visibleRules.length === 0}
              >
                {exporting ? "Exporting…" : "Export PDF"}
              </Button>
            </span>
          </Tooltip>
          <Button variant="contained" size="small" onClick={() => setAddOpen((v) => !v)}>
            {addOpen ? "Cancel" : "Add rule"}
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {exportError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setExportError("")}>{exportError}</Alert>}

      {/* Add rule form */}
      {addOpen && (
        <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>New custom context rule</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
            Adding a plain-English description helps colleagues understand why the rule exists.
          </Typography>
          <Stack spacing={2}>
            <TextField
              label="Phrase"
              size="small"
              value={literal}
              onChange={(e) => setLiteral(e.target.value)}
              placeholder='e.g. "would not consider"'
              helperText="The exact phrase the system will look for in the encounter note. Saved as lower-case."
              fullWidth
            />
            <Stack direction="row" spacing={2} flexWrap="wrap">
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <InputLabel>What does it mean?</InputLabel>
                <Select label="What does it mean?" value={category} onChange={(e) => setCategory(e.target.value)}>
                  {CATEGORIES.map((c) => (
                    <MenuItem key={c} value={c}>
                      <Stack>
                        <Typography variant="body2">{CATEGORY_LABEL[c] ?? c}</Typography>
                        <Typography variant="caption" color="text.secondary">{c}</Typography>
                      </Stack>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 160 }}>
                <InputLabel>Direction</InputLabel>
                <Select label="Direction" value={direction} onChange={(e) => setDirection(e.target.value)}>
                  {DIRECTIONS.map((d) => <MenuItem key={d} value={d}>{d}</MenuItem>)}
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
                helperText="How many words either side to check"
              />
            </Stack>
            <TextField
              label="Plain-English description (optional but helpful)"
              size="small"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Explain what this phrase means in plain English and why the rule is needed."
              multiline
              minRows={2}
              fullWidth
            />
            <TextField
              label="Example (optional)"
              size="small"
              value={example}
              onChange={(e) => setExample(e.target.value)}
              placeholder='e.g. "would not consider surgery → patient declined; not coded as a procedure"'
              fullWidth
            />
            {saveError && <Alert severity="error" sx={{ py: 0.5 }}>{saveError}</Alert>}
            <Box>
              <Button
                variant="contained"
                size="small"
                onClick={handleAdd}
                disabled={saving || !literal.trim()}
                startIcon={saving ? <CircularProgress aria-label="Loading" size={14} color="inherit" /> : undefined}
              >
                {saving ? "Saving..." : "Save rule"}
              </Button>
            </Box>
          </Stack>
        </Paper>
      )}

      <Divider sx={{ mb: 2 }} />

      {/* Filter toggle */}
      <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
        <ToggleButtonGroup
          value={filter}
          exclusive
          size="small"
          onChange={(_, v) => { if (v) setFilter(v); }}
        >
          <ToggleButton value="all">All ({builtinCount + customCount})</ToggleButton>
          <ToggleButton value="builtin">Built-in ({builtinCount})</ToggleButton>
          <ToggleButton value="custom">Custom ({customCount})</ToggleButton>
        </ToggleButtonGroup>
        <Typography variant="caption" color="text.secondary">
          {filter === "builtin" && "Shipped with LEO · read-only · shared across all organisations"}
          {filter === "custom"  && "Added by your organisation's admins · applied on next worker restart"}
        </Typography>
      </Stack>

      {loading ? (
        <Stack alignItems="center" sx={{ py: 4 }}>
          <CircularProgress aria-label="Loading" size={28} />
        </Stack>
      ) : visibleRules.length === 0 ? (
        <Alert severity="info">
          {filter === "custom"
            ? 'No custom rules yet. Click "Add rule" to teach the system a new pattern.'
            : "No rules match the current filter."}
        </Alert>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 32 }} />
                <ColHeader label="Phrase" />
                <ColHeader label="Category" />
                <ColHeader label="Direction" />
                <ColHeader label="Scope" align="right" />
                <ColHeader label="Source" />
                <ColHeader label="Added by" />
                <ColHeader label="Status" />
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleRules.map((r, i) => (
                <RuleRow
                  key={r.rule_id ?? `builtin-${i}`}
                  rule={r}
                  onDeactivate={handleDeactivate}
                />
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
