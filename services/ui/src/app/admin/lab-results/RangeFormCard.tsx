/**
 * Atlas trace:
 *   DI: DI-3F771AFB
 */
"use client";

import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { ToolbarActions } from "@leo/design-system";

import { FormSection, formCardStyle, spanTwo } from "./labConfigForm";
import { RangeOwnerField } from "./RangeOwnerField";
import type { RangeDraft, RangeOrgOption } from "./rangeDraft";

export type { RangeOrgOption };

export function RangeFormCard({
  draft,
  orgs,
  onPatch,
  onSubmit,
  saving,
}: {
  draft: RangeDraft;
  orgs: RangeOrgOption[];
  onPatch: (patch: Partial<RangeDraft>) => void;
  onSubmit: () => void;
  saving: boolean;
}) {
  return (
    <fieldset data-testid="add-range-form" style={formCardStyle}>
      <legend style={{ padding: "0 6px" }}>Add reference range</legend>
      <Stack spacing={2} sx={{ mt: 0.5 }}>
        <WhoFields draft={draft} orgs={orgs} onPatch={onPatch} />
        <BandFields
          title="Normal band"
          low={{ label: "Low", value: draft.low, onChange: (low) => onPatch({ low }) }}
          high={{ label: "High", value: draft.high, onChange: (high) => onPatch({ high }) }}
        />
        <BandFields
          title="Critical band"
          low={{
            label: "Critical low",
            value: draft.critLow,
            onChange: (critLow) => onPatch({ critLow }),
          }}
          high={{
            label: "Critical high",
            value: draft.critHigh,
            onChange: (critHigh) => onPatch({ critHigh }),
          }}
        />
        <TextField
          label="Source"
          size="small"
          value={draft.source}
          onChange={(e) => onPatch({ source: e.target.value })}
          helperText="Who set this range (e.g. manual, NICE, local)"
          fullWidth
        />
        <ToolbarActions
          align="start"
          actions={[
            {
              id: "add-range",
              label: "Review range",
              variant: "primary",
              disabled: saving,
              onClick: onSubmit,
            },
          ]}
        />
      </Stack>
    </fieldset>
  );
}

function WhoFields({
  draft,
  orgs,
  onPatch,
}: {
  draft: RangeDraft;
  orgs: RangeOrgOption[];
  onPatch: (patch: Partial<RangeDraft>) => void;
}) {
  return (
    <FormSection title="Who it applies to">
      <RangeOwnerField
        orgId={draft.orgId}
        orgs={orgs}
        onChange={(orgId) => onPatch({ orgId })}
      />
      <FormControl size="small" fullWidth sx={spanTwo()}>
        <InputLabel id="sex-label">Sex</InputLabel>
        <Select
          labelId="sex-label"
          label="Sex"
          value={draft.sex}
          onChange={(e) => onPatch({ sex: e.target.value })}
        >
          <MenuItem value="all">All</MenuItem>
          <MenuItem value="male">Male</MenuItem>
          <MenuItem value="female">Female</MenuItem>
        </Select>
      </FormControl>
      <NumberField
        label="Min age"
        value={draft.ageMin}
        onChange={(ageMin) => onPatch({ ageMin })}
        helperText="Years"
      />
      <NumberField
        label="Max age"
        value={draft.ageMax}
        onChange={(ageMax) => onPatch({ ageMax })}
        helperText="Years"
      />
    </FormSection>
  );
}

function BandFields({
  title,
  low,
  high,
}: {
  title: string;
  low: { label: string; value: string; onChange: (next: string) => void };
  high: { label: string; value: string; onChange: (next: string) => void };
}) {
  return (
    <FormSection title={title}>
      <NumberField label={low.label} value={low.value} onChange={low.onChange} />
      <NumberField label={high.label} value={high.value} onChange={high.onChange} />
    </FormSection>
  );
}

function NumberField({
  label,
  value,
  onChange,
  helperText,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  helperText?: string;
}) {
  return (
    <TextField
      label={label}
      size="small"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      helperText={helperText}
      inputMode="decimal"
      fullWidth
    />
  );
}
