/**
 * Dialog opened from My work when a phrase is waiting to be published.
 *
 * Shows what will change in plain English, who drafted it, and the sample
 * sentence. Two actions: Publish (disabled for the author) and Send back.
 *
 * Atlas trace:
 *   DI: DI-6BD7B681, DI-B00BD595
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { WorkTask } from "@leo/design-system";
import { useAuth } from "@/lib/authContext";
import {
  fetchPhraseItem,
  publishPhrase,
  sendBackPhrase,
  type UncodedPhrase,
} from "@/app/settings/surface-forms/phraseMappingsApi";
import { BreakGlassReason, reasonIsValid } from "./BreakGlassReason";
import { workTaskSourceId } from "./workTaskSourceId";

interface Props {
  task: WorkTask;
  onClose: () => void;
  onResolved: () => void;
}

function actionSummary(phrase: UncodedPhrase): string {
  if (phrase.draft_action === "map" && phrase.draft_concept_term) {
    return (
      "Map \u2018" +
      phrase.normalized +
      "\u2019 to " +
      phrase.draft_concept_term +
      "."
    );
  }
  if (phrase.draft_action === "exclude") {
    return (
      "Do not code \u2018" +
      phrase.normalized +
      "\u2019. Reason: " +
      (phrase.draft_reason || "none given") +
      "."
    );
  }
  return "Publish the change for \u2018" + phrase.normalized + "\u2019.";
}

export default function PhrasePublishDialog({
  task,
  onClose,
  onResolved,
}: Props) {
  const { session } = useAuth();
  const phraseKey = workTaskSourceId(task.task_id);

  const [phrase, setPhrase] = useState<UncodedPhrase | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    setLoading(true);
    fetchPhraseItem(phraseKey)
      .then(setPhrase)
      .catch(() => setError("Could not load this change. Please try again."))
      .finally(() => setLoading(false));
  }, [phraseKey]);

  const currentEmail = (session?.user.email ?? "").toLowerCase();
  const draftAuthor = (phrase?.draft_author ?? task.draft_author ?? "").toLowerCase();
  const isAuthor = Boolean(currentEmail && currentEmail === draftAuthor);
  const canBreakGlass = isAuthor && Boolean(session?.isPlatformAdmin);
  const publishBlocked =
    busy || !phrase || (isAuthor && !canBreakGlass) ||
    (canBreakGlass && !reasonIsValid(reason));

  const handlePublish = useCallback(async () => {
    if (!phrase) return;
    setBusy(true);
    setError(null);
    try {
      await publishPhrase(phrase.phrase_key, canBreakGlass ? reason.trim() : "");
      setNotice("Published. The pipeline will use this from the next run.");
      onResolved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not publish. Try again.");
    } finally {
      setBusy(false);
    }
  }, [phrase, onResolved, canBreakGlass, reason]);

  const handleSendBack = useCallback(async () => {
    if (!phrase) return;
    setBusy(true);
    setError(null);
    try {
      await sendBackPhrase(phrase.phrase_key);
      setNotice("Sent back. The engineer can revise and resubmit.");
      onResolved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send back. Try again.");
    } finally {
      setBusy(false);
    }
  }, [phrase, onResolved]);

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Change to publish</DialogTitle>
      <DialogContent>
        {loading ? (
          <CircularProgress size={24} />
        ) : (
          <Stack spacing={1.5}>
            {phrase ? (
              <>
                <Typography variant="body1">{actionSummary(phrase)}</Typography>
                {phrase.sample_sentence ? (
                  <Typography variant="caption" color="text.secondary">
                    Sample: {phrase.sample_sentence}
                  </Typography>
                ) : null}
                <Typography variant="caption" color="text.secondary">
                  Drafted by {phrase.draft_author || "unknown"}
                </Typography>
                {isAuthor && !canBreakGlass ? (
                  <Alert severity="info">
                    You drafted this change. A different person must publish it.
                  </Alert>
                ) : null}
                {canBreakGlass ? (
                  <BreakGlassReason
                    value={reason}
                    onChange={setReason}
                    disabled={busy}
                  />
                ) : null}
              </>
            ) : null}
            {error ? <Alert severity="error">{error}</Alert> : null}
            {notice ? <Alert severity="success">{notice}</Alert> : null}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Close
        </Button>
        <Button onClick={() => void handleSendBack()} disabled={busy || !phrase}>
          Send back
        </Button>
        <Button
          variant="contained"
          onClick={() => void handlePublish()}
          disabled={publishBlocked}
          aria-disabled={publishBlocked}
        >
          {busy ? "Publishing..." : "Publish to live"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
