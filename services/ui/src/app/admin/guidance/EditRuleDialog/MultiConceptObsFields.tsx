/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-C21AE387
 *   DO: DO-AA74E9A6
 *   VT: VT-5632FA0D
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-C21AE387")
 */
"use client";

/**
 * Operator / value / unit row for a ticked observable hit in
 * MultiConceptPicker. Depth stays on the parent row. Unit is a
 * dropdown from the lab unit converter (LabResultConfig).
 */
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { MULTI_CONCEPT_PICKER, OPERATOR_LABELS } from "./copy";
import type { ObservableThresholdDraft } from "./multiConceptSeed";
import ObservableUnitSelect from "./ObservableUnitSelect";
import type { ObservationOperator } from "./types";

const OPERATORS: ObservationOperator[] = [
  ">=",
  "<=",
  ">",
  "<",
  "=",
  "between",
];

interface Props {
  term: string;
  observableId: string;
  draft: ObservableThresholdDraft;
  onChange: (next: ObservableThresholdDraft) => void;
}

export default function MultiConceptObsFields({
  term,
  observableId,
  draft,
  onChange,
}: Props) {
  const isBetween = draft.operator === "between";
  return (
    <Stack spacing={0.75} sx={{ mt: 0.5 }}>
      <Typography variant="caption" color="text.secondary">
        {MULTI_CONCEPT_PICKER.observationHint}
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Select
          size="small"
          value={draft.operator}
          onChange={(e) =>
            onChange({
              ...draft,
              operator: String(e.target.value) as ObservationOperator,
            })
          }
          inputProps={{
            "aria-label": MULTI_CONCEPT_PICKER.operatorAriaLabel(term),
          }}
          sx={{ minWidth: 140 }}
        >
          {OPERATORS.map((op) => (
            <MenuItem key={op} value={op}>
              {OPERATOR_LABELS[op] ?? op}
            </MenuItem>
          ))}
        </Select>
        <TextField
          size="small"
          type="number"
          label={MULTI_CONCEPT_PICKER.valueLabel}
          value={draft.value}
          onChange={(e) => onChange({ ...draft, value: e.target.value })}
          inputProps={{
            "aria-label": MULTI_CONCEPT_PICKER.valueAriaLabel(term),
            style: { width: 72 },
          }}
        />
        {isBetween && (
          <TextField
            size="small"
            type="number"
            label={MULTI_CONCEPT_PICKER.value2Label}
            value={draft.value2}
            onChange={(e) => onChange({ ...draft, value2: e.target.value })}
            inputProps={{
              "aria-label": MULTI_CONCEPT_PICKER.value2AriaLabel(term),
              style: { width: 72 },
            }}
          />
        )}
        <ObservableUnitSelect
          observableId={observableId}
          value={draft.unit}
          onChange={(unit) => onChange({ ...draft, unit })}
          ariaLabel={MULTI_CONCEPT_PICKER.unitAriaLabel(term)}
        />
      </Stack>
    </Stack>
  );
}
