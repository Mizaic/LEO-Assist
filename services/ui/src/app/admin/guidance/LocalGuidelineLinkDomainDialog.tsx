/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

interface DomainOption {
  id: string;
  name: string;
}

interface Props {
  guidelineCode: string | null;
  onClose: () => void;
  onLinked: () => void;
}

export default function LocalGuidelineLinkDomainDialog({
  guidelineCode,
  onClose,
  onLinked,
}: Props) {
  const [domains, setDomains] = useState<DomainOption[]>([]);
  const [domainId, setDomainId] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDomains = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/proxy/analytics/domains");
      if (!r.ok) throw new Error(r.statusText);
      const data = await r.json();
      const list = Array.isArray(data) ? data : data.domains ?? [];
      setDomains(
        list.map((d: { id?: string; name?: string }) => ({
          id: String(d.id ?? ""),
          name: String(d.name ?? d.id ?? ""),
        })).filter((d: DomainOption) => d.id),
      );
    } catch {
      setError("Could not load audit domains.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!guidelineCode) return;
    setDomainId("");
    loadDomains();
  }, [guidelineCode, loadDomains]);

  async function handleLink() {
    if (!guidelineCode || !domainId) return;
    setSaving(true);
    setError(null);
    try {
      const r = await fetch(
        `/api/guidance/local/${encodeURIComponent(guidelineCode)}/link-domain`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ domain_id: domainId }),
        },
      );
      if (!r.ok) {
        const body = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(
          (body as { detail?: string }).detail || "Could not link domain.",
        );
      }
      onLinked();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not link domain.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={Boolean(guidelineCode)} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Link domain</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Choose the audit domain for {guidelineCode}. Approved rules can then
            be added to this domain.
          </Typography>
          {error && <Alert severity="error">{error}</Alert>}
          {loading ? (
            <CircularProgress size={24} />
          ) : (
            <FormControl fullWidth size="small">
              <InputLabel id="local-guideline-domain-label">Audit domain</InputLabel>
              <Select
                labelId="local-guideline-domain-label"
                label="Audit domain"
                value={domainId}
                onChange={(e) => setDomainId(String(e.target.value))}
              >
                {domains.map((d) => (
                  <MenuItem key={d.id} value={d.id}>
                    {d.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleLink}
          disabled={!domainId || saving || loading}
        >
          {saving ? "Linking..." : "Link domain"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
