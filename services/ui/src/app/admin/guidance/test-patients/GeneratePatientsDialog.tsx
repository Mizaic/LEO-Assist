"use client";

/**
 * GeneratePatientsDialog -- propose synthetic patients from rule logic
 * trees, let the reviewer tick which to keep, then bulk-save (with
 * dedup-by-content-hash so re-runs are safe).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { generateProposals, savePatient } from "./api";
import type { GenerateResponse, ProposalRow } from "./types";

interface Props {
  open: boolean;
  onClose: () => void;
  guidelineId?: string;
  ruleId?: string;
  branchNodeId?: string;
  onSaved?: (savedCount: number) => void;
}

const KIND_LABEL: Record<ProposalRow["kind"], string> = {
  happy: "Should fire (happy path)",
  fail: "Should not fire (missing required)",
  branch: "Hits one OR branch",
  boundary: "Age boundary check",
};

const KIND_COLOR: Record<ProposalRow["kind"], "success" | "error" | "info" | "warning"> = {
  happy: "success",
  fail: "error",
  branch: "info",
  boundary: "warning",
};

export default function GeneratePatientsDialog({
  open,
  onClose,
  guidelineId,
  ruleId,
  branchNodeId,
  onSaved,
}: Props) {
  const [scopeType, setScopeType] = useState<"rule" | "branch" | "guideline" | "all">(
    ruleId ? "rule" : guidelineId ? "guideline" : "all"
  );
  const [depth, setDepth] = useState<"minimal_pair" | "boundary_plus_pairs">(
    "boundary_plus_pairs"
  );
  const [excludeExisting, setExcludeExisting] = useState(true);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<GenerateResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [savedSummary, setSavedSummary] = useState<string | null>(null);
  const autoCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearAutoClose = useCallback(() => {
    if (autoCloseTimer.current !== null) {
      clearTimeout(autoCloseTimer.current);
      autoCloseTimer.current = null;
    }
  }, []);

  useEffect(() => {
    if (!open) {
      setResponse(null);
      setSelected(new Set());
      setError(null);
      setSavedSummary(null);
      clearAutoClose();
    }
  }, [open, clearAutoClose]);

  useEffect(() => clearAutoClose, [clearAutoClose]);

  const runGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await generateProposals({
        scope_type: scopeType,
        guideline_id: guidelineId,
        rule_id: ruleId,
        branch_node_id: branchNodeId,
        depth,
        exclude_existing: excludeExisting,
      });
      setResponse(resp);
      setSelected(new Set(resp.proposals.map((_, i) => String(i))));
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "Could not generate patients."
      );
    } finally {
      setLoading(false);
    }
  }, [scopeType, guidelineId, ruleId, branchNodeId, depth, excludeExisting]);

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const saveAll = useCallback(async () => {
    if (!response) return;
    setSaving(true);
    setError(null);
    let savedCount = 0;
    try {
      for (const [idx, proposal] of response.proposals.entries()) {
        if (!selected.has(String(idx))) continue;
        const result = await savePatient({
          patient: proposal.patient,
          guideline_id: proposal.guideline_id,
          scope_type: "guideline",
          scope_id: proposal.guideline_id,
          expectations: [
            {
              rule_id: proposal.rule_id,
              fires: proposal.kind === "happy" || proposal.kind === "branch",
              matched_branch_node_ids: [],
            },
          ],
          skip_if_exists: true,
        });
        if (result.created) savedCount += 1;
      }
      setSavedSummary(
        `Saved ${savedCount} new patient${savedCount === 1 ? "" : "s"}. Closing...`
      );
      if (onSaved) onSaved(savedCount);
      clearAutoClose();
      autoCloseTimer.current = setTimeout(() => {
        autoCloseTimer.current = null;
        onClose();
      }, 1500);
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "Could not save patients."
      );
    } finally {
      setSaving(false);
    }
  }, [response, selected, onSaved, onClose, clearAutoClose]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Generate test patients</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            Build a happy and a fail patient for each rule, plus extra patients
            for any age cut-offs and OR branches. We skip any patient that
            already exists.
          </Typography>

          <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
            <TextField
              select
              size="small"
              label="Scope"
              value={scopeType}
              onChange={(e) => setScopeType(e.target.value as typeof scopeType)}
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="rule" disabled={!ruleId}>
                One rule
              </MenuItem>
              <MenuItem value="branch" disabled={!ruleId || !branchNodeId}>
                One branch
              </MenuItem>
              <MenuItem value="guideline" disabled={!guidelineId}>
                Whole guideline
              </MenuItem>
              <MenuItem value="all">All guidelines</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label="Depth"
              value={depth}
              onChange={(e) => setDepth(e.target.value as typeof depth)}
              sx={{ minWidth: 220 }}
            >
              <MenuItem value="minimal_pair">Minimal: 1 happy + 1 fail per rule</MenuItem>
              <MenuItem value="boundary_plus_pairs">
                Boundary + pairs (recommended)
              </MenuItem>
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={excludeExisting}
                  onChange={(e) => setExcludeExisting(e.target.checked)}
                />
              }
              label="Skip patients that already exist"
            />
          </Stack>

          <Box>
            <Button
              variant="contained"
              onClick={runGenerate}
              disabled={loading}
              startIcon={loading ? <CircularProgress size={16} /> : undefined}
            >
              {loading ? "Generating..." : "Generate proposals"}
            </Button>
          </Box>

          {error && <Alert severity="error">{error}</Alert>}
          {savedSummary && <Alert severity="success">{savedSummary}</Alert>}

          {response && (
            <Box>
              <Typography variant="body2">
                {response.proposals.length} proposal
                {response.proposals.length === 1 ? "" : "s"} from{" "}
                {response.rules_considered} rule
                {response.rules_considered === 1 ? "" : "s"}.
              </Typography>
              <Divider sx={{ my: 1 }} />
              <Stack spacing={0.75}>
                {response.proposals.map((prop, idx) => {
                  const key = String(idx);
                  return (
                    <Stack
                      key={key}
                      direction="row"
                      spacing={1}
                      alignItems="center"
                      sx={{ p: 1, bgcolor: "grey.50", borderRadius: 1 }}
                    >
                      <Checkbox
                        checked={selected.has(key)}
                        onChange={() => toggle(key)}
                        inputProps={{
                          "aria-label": `Keep proposal ${prop.patient.name}`,
                        }}
                      />
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography variant="body2" noWrap>
                          {prop.patient.name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {prop.rationale} -- rule: {prop.rule_name}
                        </Typography>
                      </Box>
                      <Chip
                        size="small"
                        label={KIND_LABEL[prop.kind]}
                        color={KIND_COLOR[prop.kind]}
                      />
                    </Stack>
                  );
                })}
              </Stack>
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button
          variant="contained"
          onClick={saveAll}
          disabled={saving || !response || selected.size === 0}
          startIcon={saving ? <CircularProgress size={16} /> : undefined}
        >
          {saving
            ? "Saving..."
            : `Save ${selected.size} selected`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
