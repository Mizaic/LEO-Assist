/**
 * Soft guideline-word checks on a CONCEPT chip.
 *
 * Atlas trace:
 *   DI: DI-C136E4B7, DI-0C904503
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";

import { RECENCY_LABELS, SOFT_QUALIFIER_LABELS } from "./copy";
import type {
  NodeUpdate,
  SoftEnforcement,
  SoftQualifierKind,
  SoftQualifierSpec,
} from "./types";

interface Props {
  nodeId: string;
  qualifiers: SoftQualifierSpec[];
  onUpdate: (u: NodeUpdate) => void;
}

export default function SoftChecksPanel({
  nodeId,
  qualifiers,
  onUpdate,
}: Props) {
  function commit(next: SoftQualifierSpec[]) {
    onUpdate({ kind: "set_soft_qualifiers", nodeId, soft_qualifiers: next });
  }

  function addCheck() {
    const used = new Set(qualifiers.map((q) => q.kind));
    const nextKind = SOFT_QUALIFIER_LABELS.find((k) => !used.has(k.kind as SoftQualifierKind));
    if (!nextKind) return;
    commit([
      ...qualifiers,
      { kind: nextKind.kind as SoftQualifierKind, enforcement: "soft" },
    ]);
  }

  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="caption" sx={{ fontWeight: 700, color: "text.primary" }}>
        Soft checks
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mb: 0.75, lineHeight: 1.45 }}
      >
        Default is Soft: we will still offer the test if we cannot check this.
        Hard means the word must be proved before this chip can fire.
      </Typography>
      <Stack spacing={1}>
        {qualifiers.map((q, index) => (
          <Stack
            key={`${q.kind}-${index}`}
            direction={{ xs: "column", sm: "row" }}
            spacing={1}
            alignItems={{ xs: "stretch", sm: "center" }}
          >
            <Select
              size="small"
              value={q.kind}
              onChange={(e) => {
                const next = qualifiers.slice();
                next[index] = {
                  ...q,
                  kind: e.target.value as SoftQualifierKind,
                };
                commit(next);
              }}
              inputProps={{ "aria-label": `Soft check ${index + 1}` }}
              sx={{ minWidth: 200 }}
            >
              {SOFT_QUALIFIER_LABELS.map((opt) => (
                <MenuItem key={opt.kind} value={opt.kind}>
                  {opt.label}
                </MenuItem>
              ))}
            </Select>
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={q.enforcement === "hard"}
                  onChange={(e) => {
                    const next = qualifiers.slice();
                    const enforcement: SoftEnforcement = e.target.checked
                      ? "hard"
                      : "soft";
                    next[index] = { ...q, enforcement };
                    commit(next);
                  }}
                  inputProps={{ "aria-label": `Hard enforcement for ${q.kind}` }}
                />
              }
              label="Hard"
            />
            <Select
              size="small"
              displayEmpty
              value={q.within_days == null ? "" : String(q.within_days)}
              onChange={(e) => {
                const raw = String(e.target.value);
                const next = qualifiers.slice();
                next[index] = {
                  ...q,
                  within_days: raw === "" ? null : Number(raw),
                  max_occurrences: raw === "" ? null : q.max_occurrences ?? 1,
                };
                commit(next);
              }}
              inputProps={{ "aria-label": `Count window for ${q.kind}` }}
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="">No count window</MenuItem>
              {RECENCY_LABELS.map((opt) => (
                <MenuItem key={opt.days} value={String(opt.days)}>
                  {opt.label}
                </MenuItem>
              ))}
            </Select>
            <Button
              size="small"
              onClick={() => commit(qualifiers.filter((_, i) => i !== index))}
              sx={{ textTransform: "none" }}
            >
              Remove
            </Button>
          </Stack>
        ))}
      </Stack>
      <Button
        size="small"
        onClick={addCheck}
        disabled={qualifiers.length >= SOFT_QUALIFIER_LABELS.length}
        sx={{ mt: 0.75, textTransform: "none", fontWeight: 600 }}
      >
        Add a soft check
      </Button>
    </Box>
  );
}
