/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Full-size "Ask LEO for ideas" dialog.
 *
 * Stage 1 -- call POST /api/guidance/concepts/expand-topic, tick terms.
 * Stage 2 -- bulk /api/terminology/search per ticked term, review matches.
 * Confirm -- bulk-add LogicCriterion rows via onConfirm (same path Coach uses).
 */
import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import {
  buildResolvedTermRow,
  criteriaFromResolvedRows,
  type ResolvedTermRow,
} from "./conceptExpandResolve";
import { AskLeoBusyMark } from "@/components/AskLeoBusyMark";
import { CONCEPT_EXPAND } from "./copy";
import type { ConceptSearchHit, LogicCriterion } from "./types";

type Stage = "tick" | "resolve";

interface Props {
  open: boolean;
  phrase: string;
  onClose: () => void;
  onConfirm: (criteria: LogicCriterion[]) => void;
}

async function fetchExpandTerms(phrase: string): Promise<string[]> {
  const res = await fetch("/api/guidance/concepts/expand-topic", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify({ phrase }),
  });
  if (!res.ok) throw new Error("expand failed");
  const body = (await res.json()) as { terms?: string[] };
  return Array.isArray(body.terms) ? body.terms : [];
}

async function searchTerm(term: string): Promise<ConceptSearchHit[]> {
  const url = `/api/terminology/search?q=${encodeURIComponent(term)}&limit=5`;
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) return [];
  const rows = (await res.json()) as ConceptSearchHit[];
  return Array.isArray(rows) ? rows : [];
}

export default function ConceptExpandDialog({
  open,
  phrase,
  onClose,
  onConfirm,
}: Props) {
  const [stage, setStage] = useState<Stage>("tick");
  const [terms, setTerms] = useState<string[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [rows, setRows] = useState<ResolvedTermRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setStage("tick");
    setTerms([]);
    setPicked(new Set());
    setRows([]);
    setError(null);
    setLoading(true);
    let cancelled = false;
    fetchExpandTerms(phrase)
      .then((next) => {
        if (cancelled) return;
        setTerms(next);
        setPicked(new Set(next));
      })
      .catch(() => {
        if (!cancelled) setError(CONCEPT_EXPAND.loadError);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, phrase]);

  function toggleTerm(term: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(term)) next.delete(term);
      else next.add(term);
      return next;
    });
  }

  async function handleContinue() {
    const chosen = terms.filter((t) => picked.has(t));
    if (chosen.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const resolved = await Promise.all(
        chosen.map(async (term) => buildResolvedTermRow(term, await searchTerm(term))),
      );
      setRows(resolved);
      setStage("resolve");
    } catch {
      setError(CONCEPT_EXPAND.loadError);
    } finally {
      setLoading(false);
    }
  }

  function handleSelectHit(term: string, snomedId: string) {
    setRows((prev) =>
      prev.map((row) =>
        row.term === term
          ? { ...row, selectedId: snomedId, status: "matched" as const }
          : row,
      ),
    );
  }

  function handleAdd() {
    const criteria = criteriaFromResolvedRows(rows);
    if (criteria.length === 0) return;
    onConfirm(criteria);
    onClose();
  }

  const matchedCount = criteriaFromResolvedRows(rows).length;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      aria-labelledby="concept-expand-dialog-title"
    >
      <DialogTitle id="concept-expand-dialog-title">
        {CONCEPT_EXPAND.title}
      </DialogTitle>
      <DialogContent dividers>
        {error && (
          <Alert severity="warning" sx={{ mb: 1.5 }}>
            {error}
          </Alert>
        )}
        {loading && (
          <Stack alignItems="center" spacing={1} sx={{ py: 4 }}>
            {stage === "tick" ? (
              <AskLeoBusyMark height={28} title={CONCEPT_EXPAND.loadingIdeas} />
            ) : (
              <CircularProgress
                size={28}
                aria-label={CONCEPT_EXPAND.loadingResolve}
              />
            )}
            <Typography variant="body2" color="text.secondary">
              {stage === "tick"
                ? CONCEPT_EXPAND.loadingIdeas
                : CONCEPT_EXPAND.loadingResolve}
            </Typography>
          </Stack>
        )}
        {!loading && stage === "tick" && (
          <TickStage
            phrase={phrase}
            terms={terms}
            picked={picked}
            onToggle={toggleTerm}
            onTickAll={() => setPicked(new Set(terms))}
          />
        )}
        {!loading && stage === "resolve" && (
          <ResolveStage rows={rows} onSelectHit={handleSelectHit} />
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 1.5, gap: 1 }}>
        <Button onClick={onClose}>{CONCEPT_EXPAND.cancelLabel}</Button>
        <Box sx={{ flex: 1 }} />
        {stage === "resolve" && (
          <Button onClick={() => setStage("tick")} disabled={loading}>
            {CONCEPT_EXPAND.backLabel}
          </Button>
        )}
        {stage === "tick" && (
          <Button
            variant="contained"
            onClick={handleContinue}
            disabled={loading || picked.size === 0 || terms.length === 0}
          >
            {CONCEPT_EXPAND.continueLabel}
          </Button>
        )}
        {stage === "resolve" && (
          <Button
            variant="contained"
            onClick={handleAdd}
            disabled={matchedCount === 0}
            aria-label={CONCEPT_EXPAND.addAriaLabel}
          >
            {CONCEPT_EXPAND.addLabel}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

function TickStage({
  phrase,
  terms,
  picked,
  onToggle,
  onTickAll,
}: {
  phrase: string;
  terms: string[];
  picked: Set<string>;
  onToggle: (term: string) => void;
  onTickAll: () => void;
}) {
  if (terms.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {CONCEPT_EXPAND.emptyIdeas}
      </Typography>
    );
  }
  return (
    <Stack spacing={1}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
          {CONCEPT_EXPAND.tickStageLead(phrase)}
        </Typography>
        <Button size="small" onClick={onTickAll} sx={{ textTransform: "none" }}>
          {CONCEPT_EXPAND.tickAllLabel}
        </Button>
      </Stack>
      <Box role="list" aria-label="Suggested terms">
        {terms.map((term) => (
          <FormControlLabel
            key={term}
            control={
              <Checkbox
                size="small"
                checked={picked.has(term)}
                onChange={() => onToggle(term)}
                inputProps={{ "aria-label": `Tick ${term}` }}
              />
            }
            label={<Typography variant="body2">{term}</Typography>}
            sx={{ display: "flex", m: 0, py: 0.25 }}
          />
        ))}
      </Box>
    </Stack>
  );
}

function ResolveStage({
  rows,
  onSelectHit,
}: {
  rows: ResolvedTermRow[];
  onSelectHit: (term: string, snomedId: string) => void;
}) {
  if (rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        {CONCEPT_EXPAND.noMatchedYet}
      </Typography>
    );
  }
  return (
    <Stack spacing={1.5}>
      <Typography variant="body2" color="text.secondary">
        {CONCEPT_EXPAND.resolveStageLead}
      </Typography>
      {rows.map((row) => (
        <ResolveRow key={row.term} row={row} onSelectHit={onSelectHit} />
      ))}
    </Stack>
  );
}

function ResolveRow({
  row,
  onSelectHit,
}: {
  row: ResolvedTermRow;
  onSelectHit: (term: string, snomedId: string) => void;
}) {
  const statusLabel =
    row.status === "unmatched"
      ? CONCEPT_EXPAND.unmatchedLabel
      : row.status === "needs_pick"
        ? CONCEPT_EXPAND.needsPickLabel
        : CONCEPT_EXPAND.matchedLabel;
  return (
    <Box
      sx={{
        p: 1.25,
        borderRadius: 1,
        border: "1px solid",
        borderColor: row.status === "unmatched" ? "warning.light" : "divider",
      }}
    >
      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
        {row.term}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block">
        {statusLabel}
      </Typography>
      {row.hits.length > 0 && (
        <TextField
          select
          size="small"
          fullWidth
          sx={{ mt: 1 }}
          label="Clinical term"
          value={row.selectedId ?? ""}
          onChange={(e) => onSelectHit(row.term, e.target.value)}
          inputProps={{ "aria-label": `Match for ${row.term}` }}
        >
          {row.hits.map((hit) => (
            <MenuItem key={hit.snomed_concept_id} value={hit.snomed_concept_id}>
              {hit.term}
            </MenuItem>
          ))}
        </TextField>
      )}
    </Box>
  );
}
