/**
 * Product NCR lookup and minimum create form.
 *
 * Atlas: DI-287FFFD0
 */
"use client";

import type { CSSProperties } from "react";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { color, elevation, typography } from "@leo/design-system/tokens";

import { useClinicalNcr } from "./useClinicalNcr";
import { NCR_SEVERITIES, type ProductNcr } from "./ncrDraft";
import { pressable } from "./clinicalDoorChrome";

export function ClinicalNcrPanel({
  runId = "",
  why = "",
  onLinked,
}: {
  runId?: string;
  why?: string;
  onLinked?: (row: ProductNcr) => void;
}) {
  const ncr = useClinicalNcr(runId, why, onLinked);
  const pick = (row: ProductNcr) => {
    ncr.setSelected(row);
    onLinked?.(row);
  };
  return (
    <Stack
      spacing={1.5}
      data-testid="validation-lab-ncr-panel"
      style={panelStyle()}
    >
      <Typography sx={headlineSx()}>Product non-conformances</Typography>
      <Typography sx={bodySx()}>
        Look up an open record in Atlas, or submit a new one. Closed and
        cancelled records stay in Atlas. The product is set for you.
      </Typography>
      {ncr.selected ? (
        <Typography data-testid="validation-lab-ncr-selected" sx={bodySx()}>
          Linked: {ncr.selected.title}
        </Typography>
      ) : null}
      {ncr.error ? (
        <Typography color="error" sx={{ fontSize: 13 }}>
          {ncr.error}
        </Typography>
      ) : null}
      <Stack direction="row" spacing={1}>
        <TextField
          size="small"
          fullWidth
          value={ncr.query}
          onChange={(e) => ncr.setQuery(e.target.value)}
          placeholder="Search title or status"
          inputProps={{ "aria-label": "Search product NCRs" }}
        />
        <Button
          onClick={ncr.onSearch}
          disabled={ncr.busy}
          sx={pressable}
          data-testid="validation-lab-ncr-search"
        >
          Search
        </Button>
      </Stack>
      <NcrList rows={ncr.rows} onPick={pick} />
      {ncr.creating ? (
        <NcrCreateForm
          draft={ncr.draft}
          onDraft={ncr.setDraft}
          busy={ncr.busy}
          onSave={ncr.onCreate}
          onCancel={() => ncr.setCreating(false)}
        />
      ) : (
        <Button
          variant="contained"
          onClick={() => ncr.setCreating(true)}
          sx={pressable}
          data-testid="validation-lab-ncr-open-new"
        >
          Open a new NCR
        </Button>
      )}
    </Stack>
  );
}

function NcrList({
  rows,
  onPick,
}: {
  rows: ProductNcr[];
  onPick: (row: ProductNcr) => void;
}) {
  if (rows.length === 0) {
    return (
      <Typography sx={bodySx()}>No open product records match yet.</Typography>
    );
  }
  return (
    <Stack spacing={0.75} data-testid="validation-lab-ncr-list">
      {rows.slice(0, 8).map((row) => (
        <button
          key={row.id}
          type="button"
          onClick={() => onPick(row)}
          style={rowStyle()}
        >
          <span style={{ fontWeight: 600 }}>{row.title}</span>
          <span style={{ color: color.text.secondary }}>
            {" "}
            -- {row.severity || "severity n/a"} / {row.status || "open"}
          </span>
        </button>
      ))}
    </Stack>
  );
}

function NcrCreateForm({
  draft,
  onDraft,
  busy,
  onSave,
  onCancel,
}: {
  draft: ReturnType<typeof useClinicalNcr>["draft"];
  onDraft: ReturnType<typeof useClinicalNcr>["setDraft"];
  busy: boolean;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <Stack spacing={1.25} data-testid="validation-lab-ncr-form">
      <Typography sx={bodySx()}>
        Minimum needed: title, what went wrong, and how serious it is.
        Do not put an NHS number or referral number (UBRN) here. Add
        cases after you save. Those stay in LEO.
      </Typography>
      <TextField
        size="small"
        label="Title"
        value={draft.title}
        onChange={(e) => onDraft({ ...draft, title: e.target.value })}
        inputProps={{ "aria-label": "NCR title" }}
      />
      <TextField
        size="small"
        label="What went wrong"
        value={draft.description}
        onChange={(e) => onDraft({ ...draft, description: e.target.value })}
        multiline
        minRows={3}
        inputProps={{ "aria-label": "What went wrong" }}
      />
      <TextField
        size="small"
        select
        label="How serious"
        value={draft.severity}
        onChange={(e) =>
          onDraft({ ...draft, severity: e.target.value as typeof draft.severity })
        }
        inputProps={{ "aria-label": "How serious" }}
      >
        {NCR_SEVERITIES.map((value) => (
          <MenuItem key={value} value={value}>
            {value}
          </MenuItem>
        ))}
      </TextField>
      <Typography sx={bodySx()}>
        Product is locked to LEO Clinical Decision Support.
      </Typography>
      <Stack direction="row" spacing={1}>
        <Button
          variant="contained"
          onClick={onSave}
          disabled={busy}
          sx={pressable}
          data-testid="validation-lab-ncr-save"
        >
          Save NCR
        </Button>
        <Button onClick={onCancel} sx={pressable}>
          Cancel
        </Button>
      </Stack>
    </Stack>
  );
}

function panelStyle(): CSSProperties {
  return {
    background: color.surface.raised,
    borderRadius: 12,
    padding: 18,
    boxShadow: elevation.card,
    fontFamily: typography.fontFamily.body,
  };
}

function headlineSx() {
  return {
    fontFamily: typography.fontFamily.heading,
    fontWeight: 700,
    fontSize: 16,
    color: color.text.primary,
  };
}

function bodySx() {
  return { fontSize: 13, color: color.text.secondary, lineHeight: 1.45 };
}

function rowStyle(): CSSProperties {
  return {
    textAlign: "left",
    border: 0,
    background: color.surface.alt,
    borderRadius: 8,
    padding: "10px 12px",
    cursor: "pointer",
    fontFamily: typography.fontFamily.body,
    fontSize: 13,
    color: color.text.primary,
  };
}
