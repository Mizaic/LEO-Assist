/**
 * Emergency override reason field for a platform admin who is the author.
 *
 * Atlas trace:
 *   DI: DI-B00BD595
 */
"use client";

import Alert from "@mui/material/Alert";
import TextField from "@mui/material/TextField";

export const REASON_MIN = 10;
export const REASON_MAX = 500;

export function reasonIsValid(reason: string): boolean {
  const n = reason.trim().length;
  return n >= REASON_MIN && n <= REASON_MAX;
}

export function BreakGlassReason({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
}) {
  return (
    <>
      <Alert severity="warning">
        You drafted this change. A different person should publish it. Use this
        emergency path only when no second person is available.
      </Alert>
      <TextField
        label="Why do you need this emergency override"
        value={value}
        onChange={(event) => onChange(event.target.value.slice(0, REASON_MAX))}
        disabled={disabled}
        required
        multiline
        minRows={2}
        fullWidth
        inputProps={{ maxLength: REASON_MAX, minLength: REASON_MIN }}
        helperText="Write 10 to 500 characters. This is saved in the audit record."
      />
    </>
  );
}
