/**
 * Tells the teacher when the proposed sections came from a simpler reader,
 * or from only part of a long letter.
 *
 * Atlas trace: DI-C1744ED5, DO-1C8E7598, R-98702FED
 */
"use client";

import Alert from "@mui/material/Alert";

export function FormSchemaDetectionNotice({ message }: { message: string }) {
  if (!message.trim()) return null;
  return (
    <Alert severity="warning" role="status" sx={{ mb: 1.5 }}>
      {message}
    </Alert>
  );
}
