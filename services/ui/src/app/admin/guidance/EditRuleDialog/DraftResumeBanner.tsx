/**
 * Resume / discard banner for a Neo4j RuleEditDraft (DI-D52E923B).
 */
"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { DRAFT_PROGRESS_COPY } from "./copy";

interface Props {
  updatedAt: string;
  saving: boolean;
  onResume: () => void;
  onDiscard: () => void;
}

function formatUpdatedAt(raw: string): string {
  if (!raw) return "";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}

export default function DraftResumeBanner({
  updatedAt,
  saving,
  onResume,
  onDiscard,
}: Props) {
  const when = formatUpdatedAt(updatedAt);
  return (
    <Alert
      severity="info"
      role="status"
      aria-label={DRAFT_PROGRESS_COPY.resumeAria}
      sx={{ mb: 2 }}
      action={
        <Stack direction="row" spacing={1}>
          <Button
            color="inherit"
            size="small"
            disabled={saving}
            onClick={onResume}
          >
            {DRAFT_PROGRESS_COPY.resumeLabel}
          </Button>
          <Button
            color="inherit"
            size="small"
            disabled={saving}
            onClick={onDiscard}
          >
            {DRAFT_PROGRESS_COPY.discardLabel}
          </Button>
        </Stack>
      }
    >
      <Typography variant="body2">
        {DRAFT_PROGRESS_COPY.resumeLead}
        {when ? ` ${DRAFT_PROGRESS_COPY.resumeWhenPrefix} ${when}.` : ""}
      </Typography>
    </Alert>
  );
}
