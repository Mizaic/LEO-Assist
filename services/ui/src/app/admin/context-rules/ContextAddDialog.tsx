/**
 * Add a custom context rule.
 *
 * Atlas trace:
 *   DO: DO-7E9AD55B
 *   DI: DI-DA60AC55
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7E9AD55B")
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import CloseIcon from "@mui/icons-material/Close";

import { CATEGORY_OPTIONS, DIRECTION_OPTIONS } from "./categoryCopy";

export interface NewContextRuleValues {
  literal: string;
  category: string;
  direction: string;
  max_scope: number;
  description: string;
  example: string;
}

interface ContextAddDialogProps {
  open: boolean;
  saving: boolean;
  error: string;
  onClose: () => void;
  onSave: (values: NewContextRuleValues) => Promise<void>;
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <FormControl size="small" fullWidth>
      <InputLabel>{label}</InputLabel>
      <Select
        label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((opt) => (
          <MenuItem key={opt.value} value={opt.value}>
            {opt.label}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

interface AddFormState {
  literal: string;
  category: string;
  direction: string;
  maxScope: number;
  description: string;
  example: string;
}

function emptyForm(): AddFormState {
  return {
    literal: "",
    category: "NEGATED_EXISTENCE",
    direction: "FORWARD",
    maxScope: 6,
    description: "",
    example: "",
  };
}

function ContextAddFields({
  state,
  onChange,
}: {
  state: AddFormState;
  onChange: (patch: Partial<AddFormState>) => void;
}) {
  return (
    <>
      <TextField
        label="Phrase"
        size="small"
        value={state.literal}
        onChange={(e) => onChange({ literal: e.target.value })}
        placeholder='e.g. "would not consider"'
        helperText="The exact phrase LEO will look for. Saved as lower-case."
        fullWidth
      />
      <SelectField
        label="What does it mean?"
        value={state.category}
        onChange={(value) => onChange({ category: value })}
        options={CATEGORY_OPTIONS}
      />
      <SelectField
        label="Where does it apply?"
        value={state.direction}
        onChange={(value) => onChange({ direction: value })}
        options={DIRECTION_OPTIONS}
      />
      <TextField
        label="How many words nearby"
        type="number"
        size="small"
        value={state.maxScope}
        onChange={(e) => onChange({ maxScope: Number(e.target.value) })}
        inputProps={{ min: 1, max: 20 }}
      />
      <TextField
        label="Why this rule exists"
        size="small"
        value={state.description}
        onChange={(e) => onChange({ description: e.target.value })}
        multiline
        minRows={2}
        fullWidth
      />
      <TextField
        label="Example note"
        size="small"
        value={state.example}
        onChange={(e) => onChange({ example: e.target.value })}
        placeholder='e.g. "nil chest pain -> no chest pain"'
        fullWidth
      />
    </>
  );
}

function ContextAddForm({
  saving,
  error,
  onSave,
}: {
  saving: boolean;
  error: string;
  onSave: (values: NewContextRuleValues) => Promise<void>;
}) {
  const [form, setForm] = useState<AddFormState>(emptyForm);
  function onChange(patch: Partial<AddFormState>) {
    setForm((prev) => ({ ...prev, ...patch }));
  }

  async function handleSave() {
    if (!form.literal.trim()) return;
    await onSave({
      literal: form.literal.trim(),
      category: form.category,
      direction: form.direction,
      max_scope: form.maxScope,
      description: form.description.trim(),
      example: form.example.trim(),
    });
    setForm((prev) => ({
      ...emptyForm(),
      category: prev.category,
      direction: prev.direction,
    }));
  }

  return (
    <Stack spacing={2} data-testid="context-rules-add-form">
      <ContextAddFields state={form} onChange={onChange} />
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Button
        variant="contained"
        onClick={handleSave}
        disabled={saving || !form.literal.trim()}
        sx={{ textTransform: "none", alignSelf: "flex-start" }}
      >
        {saving ? "Saving..." : "Save rule"}
      </Button>
    </Stack>
  );
}

export default function ContextAddDialog({
  open,
  saving,
  error,
  onClose,
  onSave,
}: ContextAddDialogProps) {
  if (!open) return null;
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>
        Add context rule
        <IconButton
          aria-label="Close"
          onClick={onClose}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <ContextAddForm saving={saving} error={error} onSave={onSave} />
      </DialogContent>
    </Dialog>
  );
}
