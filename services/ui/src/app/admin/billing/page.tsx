"use client";

import React, { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import LocalOfferIcon from "@mui/icons-material/LocalOffer";
import MemoryIcon from "@mui/icons-material/Memory";
import PaidIcon from "@mui/icons-material/Paid";
import RefreshIcon from "@mui/icons-material/Refresh";
import SaveIcon from "@mui/icons-material/Save";
import SettingsIcon from "@mui/icons-material/Settings";
import StorageIcon from "@mui/icons-material/Storage";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import { compareStringsNatural } from "@/lib/sortNatural";

// =============================================================================
// Types
// =============================================================================

interface PricingConfig {
  targetMargin: number;
  updatedBy: string | null;
  updatedAt: string | null;
  isDefault: boolean;
}

interface ActiveDiscount {
  discountId: string;
  description: string;
  rate: number;
  type: string;
  validTo: string | null;
}

interface OrgSpend {
  orgId: string;
  orgName: string;
  runCount: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  rawCostUsd: number;
  listPriceUsd: number;
  discountRate: number;
  billableUsd: number;
  grossMargin: number;
  targetMargin: number;
  activeDiscounts: ActiveDiscount[];
}

interface OrgSpendResponse {
  orgs: OrgSpend[];
  targetMargin: number;
  totals: { rawCostUsd: number; billableUsd: number; orgCount: number };
}

interface Discount {
  discountId: string;
  orgId: string;
  description: string;
  rate: number;
  type: string;
  validFrom: string;
  validTo: string | null;
  isActive: boolean;
  createdBy: string;
  createdAt: string;
}

interface PlatformBreakdown {
  eventType: string;
  runCount: number;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  rawCostUsd: number;
}

interface PlatformSpendResponse {
  breakdown: PlatformBreakdown[];
  targetMargin: number;
  totals: { rawCostUsd: number; listPriceUsd: number; note: string };
}

// =============================================================================
// Helpers
// =============================================================================

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json" },
    ...opts,
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => r.statusText);
    throw new Error(`${r.status}: ${txt}`);
  }
  return r.json();
}

function fmt$(n: number, decimals = 4): string {
  if (n === 0) return "$0.00";
  return `$${n.toFixed(decimals)}`;
}

function fmtPct(n: number): string { return `${(n * 100).toFixed(1)}%`; }

function fmtTok(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}

/** Today first; rolling windows sorted by label with numeric-aware order (7 before 30). */
const PERIOD_OPTIONS = (() => {
  const rows = [
    { value: "today", label: "Today" },
    { value: "7d", label: "Last 7 days" },
    { value: "30d", label: "Last 30 days" },
    { value: "90d", label: "Last 90 days" },
  ] as const;
  const today = rows.find((r) => r.value === "today");
  const rolling = [...rows]
    .filter((r) => r.value !== "today")
    .sort((a, b) => compareStringsNatural(a.label, b.label));
  return [...(today ? [today] : []), ...rolling] as typeof rows;
})();

function periodDates(p: string): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now);
  if (p === "today") from.setHours(0, 0, 0, 0);
  else if (p === "7d") from.setDate(now.getDate() - 7);
  else if (p === "30d") from.setDate(now.getDate() - 30);
  else from.setDate(now.getDate() - 90);
  return { from: from.toISOString(), to: now.toISOString() };
}

// =============================================================================
// MarginCard — global margin config
// =============================================================================

function MarginCard({ onRefresh }: { onRefresh: () => void }) {
  const [config, setConfig]   = useState<PricingConfig | null>(null);
  const [draft, setDraft]     = useState<number>(0.75);
  const [saving, setSaving]   = useState(false);
  const [msg, setMsg]         = useState<string | null>(null);
  const [err, setErr]         = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<PricingConfig>("/api/pricing/config")
      .then((d) => { setConfig(d); setDraft(d.targetMargin); })
      .catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true); setMsg(null); setErr(null);
    try {
      await apiFetch("/api/pricing/config", {
        method: "PUT",
        body: JSON.stringify({ targetMargin: draft }),
      });
      setMsg(`Margin updated to ${fmtPct(draft)}. New invoices will use this rate.`);
      load(); onRefresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save");
    } finally { setSaving(false); }
  };

  const listMultiple = draft < 1 ? (1 / (1 - draft)).toFixed(2) : "∞";

  return (
    <Card variant="outlined" sx={{ borderRadius: 2 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
          <TrendingUpIcon color="primary" />
          <Typography variant="subtitle1" fontWeight={700}>Target gross margin</Typography>
          {config?.isDefault && <Chip size="small" label="default" variant="outlined" sx={{ height: 18, fontSize: "0.6rem" }} />}
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Applied globally to all tenants. List price = raw AI cost ÷ (1 − margin).
          At {fmtPct(draft)} margin, raw cost is multiplied by {listMultiple}×.
        </Typography>

        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 1 }}>
          <Slider
            value={Math.round(draft * 100)}
            onChange={(_, v) => setDraft((v as number) / 100)}
            min={0} max={95} step={1}
            marks={[{ value: 0, label: "0%" }, { value: 50, label: "50%" }, { value: 75, label: "75%" }, { value: 95, label: "95%" }]}
            sx={{ flex: 1 }}
          />
          <TextField
            size="small" type="number" value={Math.round(draft * 100)}
            onChange={(e) => { const v = Math.min(99, Math.max(0, Number(e.target.value))); setDraft(v / 100); }}
            inputProps={{ min: 0, max: 99, step: 1 }}
            InputProps={{ endAdornment: <InputAdornment position="end">%</InputAdornment> }}
            sx={{ width: 90 }}
          />
        </Stack>

        <Stack direction="row" spacing={2} sx={{ mb: 1.5 }}>
          {["25%", "50%", "67%", "75%", "80%"].map((p) => {
            const v = parseInt(p) / 100;
            return (
              <Chip key={p} size="small" label={p} variant={Math.abs(draft - v) < 0.005 ? "filled" : "outlined"}
                color={Math.abs(draft - v) < 0.005 ? "primary" : "default"}
                onClick={() => setDraft(v)} sx={{ cursor: "pointer" }} />
            );
          })}
        </Stack>

        <Stack direction="row" alignItems="center" spacing={1.5}>
          <Button size="small" variant="contained" startIcon={saving ? <CircularProgress size={14} /> : <SaveIcon />}
            disabled={saving || (config != null && Math.abs(draft - config.targetMargin) < 0.001)}
            onClick={save}>
            Save margin
          </Button>
          {config?.updatedBy && (
            <Typography variant="caption" color="text.disabled">
              Last set by {config.updatedBy} · {fmtDate(config.updatedAt)}
            </Typography>
          )}
        </Stack>
        {msg && <Alert severity="success" sx={{ mt: 1.5 }} onClose={() => setMsg(null)}>{msg}</Alert>}
        {err && <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setErr(null)}>{err}</Alert>}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// AddDiscountDialog
// =============================================================================

function AddDiscountDialog({
  open, orgId, orgName, onClose, onCreated,
}: {
  open: boolean; orgId: string; orgName: string;
  onClose: () => void; onCreated: () => void;
}) {
  const [description, setDescription] = useState("");
  const [rate, setRate]               = useState(10);
  const [type, setType]               = useState<"promo" | "contract">("promo");
  const [validFrom, setValidFrom]     = useState(new Date().toISOString().slice(0, 10));
  const [perpetual, setPerpetual]     = useState(false);
  const [validTo, setValidTo]         = useState("");
  const [saving, setSaving]           = useState(false);
  const [err, setErr]                 = useState<string | null>(null);

  useEffect(() => {
    if (open) { setDescription(""); setRate(10); setType("promo"); setPerpetual(false); setValidTo(""); setErr(null); }
  }, [open]);

  const submit = async () => {
    if (!description.trim()) { setErr("Description is required."); return; }
    setSaving(true); setErr(null);
    try {
      await apiFetch(`/api/pricing/orgs/${encodeURIComponent(orgId)}/discounts`, {
        method: "POST",
        body: JSON.stringify({
          description: description.trim(),
          rate: rate / 100,
          type,
          validFrom: new Date(validFrom).toISOString(),
          validTo: perpetual ? null : (validTo ? new Date(validTo).toISOString() : null),
        }),
      });
      onCreated(); onClose();
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not create discount"); }
    finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add discount — {orgName}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          {err && <Alert severity="error">{err}</Alert>}
          <TextField label="Description *" size="small" fullWidth value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Year 1 launch promo — 20% off" />
          <Stack direction="row" spacing={2}>
            <Box sx={{ flex: 1 }}>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                Discount rate
              </Typography>
              <Stack direction="row" spacing={1} alignItems="center">
                <Slider value={rate} onChange={(_, v) => setRate(v as number)} min={1} max={50} step={1} sx={{ flex: 1 }} />
                <TextField size="small" type="number" value={rate}
                  onChange={(e) => setRate(Math.min(50, Math.max(1, Number(e.target.value))))}
                  inputProps={{ min: 1, max: 50 }}
                  InputProps={{ endAdornment: <InputAdornment position="end">%</InputAdornment> }}
                  sx={{ width: 80 }} />
              </Stack>
            </Box>
            <Box sx={{ flex: 1 }}>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>Type</Typography>
              <Select size="small" fullWidth value={type} onChange={(e) => setType(e.target.value as typeof type)}>
                <MenuItem value="promo">Promo (time-limited)</MenuItem>
                <MenuItem value="contract">Contract (life of contract)</MenuItem>
              </Select>
            </Box>
          </Stack>
          <Stack direction="row" spacing={2}>
            <TextField label="Valid from" type="date" size="small" sx={{ flex: 1 }}
              value={validFrom} onChange={(e) => setValidFrom(e.target.value)}
              InputLabelProps={{ shrink: true }} />
            <Box sx={{ flex: 1 }}>
              <FormControlLabel
                control={<Switch size="small" checked={perpetual} onChange={(e) => setPerpetual(e.target.checked)} />}
                label={<Typography variant="body2">Perpetual (life of contract)</Typography>}
                sx={{ mb: 0.5 }}
              />
              {!perpetual && (
                <TextField label="Valid to" type="date" size="small" fullWidth
                  value={validTo} onChange={(e) => setValidTo(e.target.value)}
                  InputLabelProps={{ shrink: true }} />
              )}
            </Box>
          </Stack>
          <Paper variant="outlined" sx={{ p: 1.5, bgcolor: "info.50", borderColor: "info.light" }}>
            <Typography variant="caption" color="info.dark">
              <strong>Preview:</strong> {fmtPct(rate / 100)} off list price
              {perpetual ? " — applies for the life of the contract" : validTo ? ` until ${fmtDate(validTo)}` : ""}.
              If the tenant has multiple active discounts, rates are summed (capped at 100%).
            </Typography>
          </Paper>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>Cancel</Button>
        <Button variant="contained" onClick={submit} disabled={saving}
          startIcon={saving ? <CircularProgress size={14} /> : <LocalOfferIcon />}>
          Add discount
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// =============================================================================
// OrgRow — expandable tenant spend row with discount management
// =============================================================================

function OrgRow({ org, targetMargin, onRefresh }: { org: OrgSpend; targetMargin: number; onRefresh: () => void }) {
  const [open, setOpen]             = useState(false);
  const [discounts, setDiscounts]   = useState<Discount[]>([]);
  const [loadingDisc, setLoadingDisc] = useState(false);
  const [addOpen, setAddOpen]       = useState(false);
  const [deleting, setDeleting]     = useState<string | null>(null);

  const loadDiscounts = useCallback(async () => {
    setLoadingDisc(true);
    try {
      const d = await apiFetch<{ discounts: Discount[] }>(`/api/pricing/orgs/${encodeURIComponent(org.orgId)}/discounts`);
      setDiscounts(d.discounts);
    } finally { setLoadingDisc(false); }
  }, [org.orgId]);

  useEffect(() => { if (open) loadDiscounts(); }, [open, loadDiscounts]);

  const deleteDiscount = async (id: string, permanent: boolean) => {
    setDeleting(id);
    try {
      await apiFetch(`/api/pricing/discounts/${encodeURIComponent(id)}?permanent=${permanent}`, { method: "DELETE" });
      loadDiscounts(); onRefresh();
    } finally { setDeleting(null); }
  };

  const hasDiscount = org.discountRate > 0;
  const marginColor = org.grossMargin >= targetMargin - 0.02 ? "success.dark" : org.grossMargin >= targetMargin - 0.1 ? "warning.dark" : "error.main";

  return (
    <>
      <TableRow
        hover
        sx={{ cursor: "pointer", "& td": { borderBottom: open ? "none" : undefined } }}
        onClick={() => setOpen((o) => !o)}
      >
        <TableCell>
          <Stack direction="row" alignItems="center" spacing={0.75}>
            {open ? <ExpandLessIcon fontSize="small" sx={{ color: "text.secondary" }} /> : <ExpandMoreIcon fontSize="small" sx={{ color: "text.secondary" }} />}
            <Box>
              <Typography variant="body2" fontWeight={600}>{org.orgName || org.orgId}</Typography>
              <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace", fontSize: "0.62rem" }}>{org.orgId}</Typography>
            </Box>
          </Stack>
        </TableCell>
        <TableCell align="right">
          <Typography variant="body2">{org.runCount.toLocaleString()}</Typography>
          <Typography variant="caption" color="text.disabled">{fmtTok(org.inputTokens + org.outputTokens)} tok</Typography>
        </TableCell>
        <TableCell align="right">
          <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{fmt$(org.rawCostUsd, 4)}</Typography>
        </TableCell>
        <TableCell align="right">
          <Typography variant="body2" sx={{ fontFamily: "monospace" }}>{fmt$(org.listPriceUsd, 4)}</Typography>
        </TableCell>
        <TableCell align="right">
          {hasDiscount ? (
            <Chip size="small" label={`−${fmtPct(org.discountRate)}`} color="warning" variant="outlined"
              sx={{ height: 20, fontSize: "0.65rem", fontWeight: 700 }} />
          ) : (
            <Typography variant="caption" color="text.disabled">—</Typography>
          )}
        </TableCell>
        <TableCell align="right">
          <Typography variant="body2" fontWeight={700} sx={{ fontFamily: "monospace" }}>{fmt$(org.billableUsd, 4)}</Typography>
        </TableCell>
        <TableCell align="right">
          <Typography variant="body2" fontWeight={700} sx={{ color: marginColor }}>{fmtPct(org.grossMargin)}</Typography>
        </TableCell>
      </TableRow>

      {/* Expanded detail */}
      <TableRow>
        <TableCell colSpan={7} sx={{ p: 0 }}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ px: 3, py: 2, bgcolor: "grey.50", borderBottom: "1px solid", borderColor: "divider" }}>
              {/* Token breakdown */}
              <Stack direction="row" spacing={3} sx={{ mb: 2 }}>
                <Box>
                  <Typography variant="caption" color="text.secondary">Input tokens</Typography>
                  <Typography variant="body2" fontWeight={600}>{fmtTok(org.inputTokens)}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Output tokens</Typography>
                  <Typography variant="body2" fontWeight={600}>{fmtTok(org.outputTokens)}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Cached (discounted)</Typography>
                  <Typography variant="body2" fontWeight={600} color="success.dark">{fmtTok(org.cachedTokens)}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">Cache hit rate</Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {org.inputTokens > 0 ? fmtPct(org.cachedTokens / org.inputTokens) : "—"}
                  </Typography>
                </Box>
              </Stack>

              {/* Discounts */}
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: 0.5 }}>
                  Discounts
                </Typography>
                <Button size="small" startIcon={<AddIcon />} onClick={(e) => { e.stopPropagation(); setAddOpen(true); }}>
                  Add discount
                </Button>
              </Stack>
              {loadingDisc ? <CircularProgress size={16} /> : discounts.length === 0 ? (
                <Typography variant="caption" color="text.disabled">No discounts configured.</Typography>
              ) : (
                <Stack spacing={0.75}>
                  {discounts.map((d) => (
                    <Paper key={d.discountId} variant="outlined" sx={{ px: 1.5, py: 1, borderRadius: 1.5 }}>
                      <Stack direction="row" alignItems="center" spacing={1.5}>
                        <Chip size="small" label={d.type}
                          color={d.type === "contract" ? "primary" : "warning"}
                          variant={d.isActive ? "filled" : "outlined"}
                          sx={{ height: 18, fontSize: "0.58rem" }} />
                        <Chip size="small" label={`−${fmtPct(d.rate)}`}
                          color={d.isActive ? "success" : "default"} variant="outlined"
                          sx={{ height: 18, fontSize: "0.62rem", fontWeight: 700 }} />
                        {!d.isActive && <Chip size="small" label="inactive" sx={{ height: 18, fontSize: "0.58rem" }} />}
                        <Typography variant="caption" sx={{ flex: 1 }}>{d.description}</Typography>
                        <Typography variant="caption" color="text.disabled">
                          {fmtDate(d.validFrom)} → {d.validTo ? fmtDate(d.validTo) : "perpetual"}
                        </Typography>
                        <Tooltip title="Deactivate">
                          <span>
                            <IconButton size="small" color="warning" disabled={!!deleting || !d.isActive}
                              onClick={(e) => { e.stopPropagation(); deleteDiscount(d.discountId, false); }}>
                              {deleting === d.discountId ? <CircularProgress size={14} /> : <LocalOfferIcon fontSize="small" />}
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title="Delete permanently">
                          <span>
                            <IconButton size="small" color="error" disabled={!!deleting}
                              onClick={(e) => { e.stopPropagation(); deleteDiscount(d.discountId, true); }}>
                              {deleting === d.discountId ? <CircularProgress size={14} /> : <DeleteOutlineIcon fontSize="small" />}
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Stack>
                    </Paper>
                  ))}
                </Stack>
              )}
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>

      <AddDiscountDialog open={addOpen} orgId={org.orgId} orgName={org.orgName || org.orgId}
        onClose={() => setAddOpen(false)} onCreated={() => { loadDiscounts(); onRefresh(); }} />
    </>
  );
}

// =============================================================================
// PlatformSpendCard
// =============================================================================

function PlatformSpendCard({ period }: { period: string }) {
  const [data, setData]     = useState<PlatformSpendResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { from, to } = periodDates(period);
      const params = new URLSearchParams({ from, to });
      const d = await apiFetch<PlatformSpendResponse>(`/api/pricing/platform-spend?${params}`);
      setData(d);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  return (
    <Card variant="outlined" sx={{ borderRadius: 2 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
          <StorageIcon color="action" />
          <Typography variant="subtitle1" fontWeight={700}>Platform operating costs</Typography>
          <Chip size="small" label="not billed to tenants" variant="outlined" sx={{ height: 18, fontSize: "0.6rem" }} />
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          AI spend on training, verification and gold dataset runs — these are internal costs, not invoiced.
        </Typography>
        {loading ? <CircularProgress size={20} /> : !data || data.breakdown.length === 0 ? (
          <Typography variant="body2" color="text.disabled">No platform spend recorded in this period.</Typography>
        ) : (
          <>
            <Stack direction="row" spacing={2} sx={{ mb: 1.5 }}>
              <Paper variant="outlined" sx={{ p: 1, flex: 1, borderRadius: 1.5 }}>
                <Typography variant="caption" color="text.secondary">Total raw cost</Typography>
                <Typography variant="h6" fontWeight={700}>{fmt$(data.totals.rawCostUsd, 4)}</Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1, flex: 1, borderRadius: 1.5 }}>
                <Typography variant="caption" color="text.secondary">At target margin ({fmtPct(data.targetMargin)})</Typography>
                <Typography variant="h6" fontWeight={700} color="text.secondary">{fmt$(data.totals.listPriceUsd, 4)}</Typography>
              </Paper>
            </Stack>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Type</TableCell>
                    <TableCell align="right">Runs</TableCell>
                    <TableCell align="right">Tokens</TableCell>
                    <TableCell align="right">Cost</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.breakdown.map((row) => (
                    <TableRow key={row.eventType}>
                      <TableCell><Typography variant="caption" sx={{ fontFamily: "monospace" }}>{row.eventType}</Typography></TableCell>
                      <TableCell align="right"><Typography variant="caption">{row.runCount.toLocaleString()}</Typography></TableCell>
                      <TableCell align="right"><Typography variant="caption">{fmtTok(row.inputTokens + row.outputTokens)}</Typography></TableCell>
                      <TableCell align="right"><Typography variant="caption" fontFamily="monospace">{fmt$(row.rawCostUsd, 4)}</Typography></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Page
// =============================================================================

export default function BillingPage() {
  const [period, setPeriod]     = useState<"today" | "7d" | "30d" | "90d">("30d");
  const [data, setData]         = useState<OrgSpendResponse | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const { from, to } = periodDates(period);
      const params = new URLSearchParams({ from, to });
      const d = await apiFetch<OrgSpendResponse>(`/api/pricing/orgs?${params}`);
      setData(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load billing data — admin access required.");
    } finally { setLoading(false); }
  }, [period, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);
  const onRefresh = () => setRefreshKey((k) => k + 1);

  const totals = data?.totals;
  const orgs   = data?.orgs ?? [];
  const targetMargin = data?.targetMargin ?? 0.75;

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: "auto" }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <PaidIcon color="primary" />
          <Typography variant="h5" fontWeight={700}>Billing & pricing</Typography>
          <Chip size="small" label="Admin only" color="warning" sx={{ height: 20, fontSize: "0.65rem", fontWeight: 700 }} />
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <Select size="small" value={period} onChange={(e) => setPeriod(e.target.value as typeof period)}
            sx={{ fontSize: "0.8rem", height: 30 }}>
            {PERIOD_OPTIONS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </Select>
          <Tooltip title="Refresh">
            <IconButton size="small" onClick={onRefresh} disabled={loading}>
              {loading ? <CircularProgress size={18} /> : <RefreshIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
        </Stack>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Per-tenant AI spend with margin and discounts applied. Visible to platform admins only.
      </Typography>

      {/* Margin config */}
      <Box sx={{ mb: 3 }}>
        <MarginCard onRefresh={onRefresh} />
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* Summary tiles */}
      {totals && (
        <Stack direction="row" spacing={2} sx={{ mb: 3 }}>
          <Paper variant="outlined" sx={{ p: 2, flex: 1, borderRadius: 2 }}>
            <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.5 }}>
              <MemoryIcon sx={{ fontSize: 16, color: "text.secondary" }} />
              <Typography variant="caption" color="text.secondary" fontWeight={600} textTransform="uppercase" letterSpacing={0.5}>
                Total AI cost
              </Typography>
            </Stack>
            <Typography variant="h5" fontWeight={700}>{fmt$(totals.rawCostUsd, 4)}</Typography>
            <Typography variant="caption" color="text.disabled">raw spend across {totals.orgCount} tenants</Typography>
          </Paper>
          <Paper variant="outlined" sx={{ p: 2, flex: 1, borderRadius: 2, borderColor: "success.main", borderWidth: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.5 }}>
              <TrendingUpIcon sx={{ fontSize: 16, color: "success.main" }} />
              <Typography variant="caption" color="success.dark" fontWeight={600} textTransform="uppercase" letterSpacing={0.5}>
                Total billable
              </Typography>
            </Stack>
            <Typography variant="h5" fontWeight={700} color="success.dark">{fmt$(totals.billableUsd, 4)}</Typography>
            <Typography variant="caption" color="text.disabled">after discounts · target {fmtPct(targetMargin)} margin</Typography>
          </Paper>
          <Paper variant="outlined" sx={{ p: 2, flex: 1, borderRadius: 2 }}>
            <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.5 }}>
              <SettingsIcon sx={{ fontSize: 16, color: "text.secondary" }} />
              <Typography variant="caption" color="text.secondary" fontWeight={600} textTransform="uppercase" letterSpacing={0.5}>
                Gross profit
              </Typography>
            </Stack>
            <Typography variant="h5" fontWeight={700}>{fmt$(totals.billableUsd - totals.rawCostUsd, 4)}</Typography>
            <Typography variant="caption" color="text.disabled">billable minus AI cost</Typography>
          </Paper>
        </Stack>
      )}

      {/* Per-tenant table */}
      {!loading && orgs.length === 0 && !error ? (
        <Alert severity="info" sx={{ mb: 3 }}>No tenant spend data for this period.</Alert>
      ) : (
        <Card variant="outlined" sx={{ mb: 3, borderRadius: 2 }}>
          <Box sx={{ px: 2, pt: 2, pb: 1 }}>
            <Typography variant="subtitle2" fontWeight={700}>Spend by tenant</Typography>
            <Typography variant="caption" color="text.secondary">Click a row to expand discounts and token detail.</Typography>
          </Box>
          <Divider />
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ "& th": { fontWeight: 700, fontSize: "0.72rem", color: "text.secondary" } }}>
                  <TableCell>Tenant</TableCell>
                  <TableCell align="right">Runs</TableCell>
                  <TableCell align="right">Raw cost</TableCell>
                  <TableCell align="right">List price</TableCell>
                  <TableCell align="right">Discount</TableCell>
                  <TableCell align="right">Billable</TableCell>
                  <TableCell align="right">Margin</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading
                  ? Array.from({ length: 3 }).map((_, i) => (
                      <TableRow key={i}>
                        {Array.from({ length: 7 }).map((_, j) => (
                          <TableCell key={j}><Box sx={{ height: 16, bgcolor: "grey.100", borderRadius: 1 }} /></TableCell>
                        ))}
                      </TableRow>
                    ))
                  : orgs.map((org) => (
                      <OrgRow key={org.orgId} org={org} targetMargin={targetMargin} onRefresh={onRefresh} />
                    ))
                }
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      )}

      {/* Platform spend */}
      <PlatformSpendCard period={period} />
    </Box>
  );
}
