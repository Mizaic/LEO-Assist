/**
 * HITL buttons on the Operations review card.
 *
 * Atlas: DI-4A012A59
 */
"use client";

import { useState } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import ConfirmDialog from "@/components/ConfirmDialog";
import type { ReviewItem } from "./ReviewCard";

interface Props {
  item: ReviewItem;
  busy: boolean;
  onResolve: (item: ReviewItem, status: "resolved" | "dismissed") => void;
  onSkip: () => void;
  onOpenLetter?: (item: ReviewItem) => void;
}

export default function HitlActions({
  item,
  busy,
  onResolve,
  onSkip,
  onOpenLetter,
}: Props) {
  const [confirmDismiss, setConfirmDismiss] = useState(false);
  if (item.taskType === "extraction_quality_review") {
    return (
      <Stack direction="row" gap={1}>
        <Button
          variant="contained"
          onClick={() => onOpenLetter?.(item)}
          disabled={busy}
          fullWidth
        >
          Open letter
        </Button>
        <Button variant="outlined" onClick={onSkip} disabled={busy}>
          Skip
        </Button>
      </Stack>
    );
  }
  return (
    <>
      <Stack direction="row" gap={1}>
        <Button
          variant="contained"
          color="success"
          onClick={() => onResolve(item, "resolved")}
          disabled={busy}
          fullWidth
        >
          Approve
        </Button>
        <Button
          variant="outlined"
          color="error"
          onClick={() => setConfirmDismiss(true)}
          disabled={busy}
          fullWidth
        >
          Dismiss
        </Button>
        <Button variant="outlined" onClick={onSkip} disabled={busy}>
          Skip
        </Button>
      </Stack>
      {confirmDismiss && (
        <ConfirmDialog
          title="Dismiss this review item?"
          body={`"${item.entityText}" will be removed from the review queue. This cannot be undone.`}
          confirmLabel="Dismiss"
          variant="danger"
          onConfirm={() => {
            onResolve(item, "dismissed");
            setConfirmDismiss(false);
          }}
          onCancel={() => setConfirmDismiss(false)}
        />
      )}
    </>
  );
}
