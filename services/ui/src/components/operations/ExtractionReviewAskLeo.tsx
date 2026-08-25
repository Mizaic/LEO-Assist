/**
 * Ask LEO on a selected extraction-review fact.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { AskLeoBusyMark } from "@/components/AskLeoBusyMark";
import { askLeoSmart, searchTerms } from "@/lib/api/legacy";
import type { AskLeoSmartResult } from "@/lib/types";

import { applyAskLeoPatch, type AskLeoFactPatch } from "./askLeoFactPatch";

type LeoStep = "idle" | "loading" | "done" | "error";

export default function ExtractionReviewAskLeo({
  entityText,
  letterText,
  assertion,
  onApply,
}: {
  entityText: string;
  letterText: string;
  assertion: string;
  onApply: (patch: AskLeoFactPatch) => void;
}) {
  const [step, setStep] = useState<LeoStep>("idle");
  const [result, setResult] = useState<AskLeoSmartResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setStep("idle");
    setResult(null);
    setError("");
  }, [entityText]);

  async function ask() {
    setStep("loading");
    setResult(null);
    setError("");
    try {
      const candidates = await searchTerms(entityText, 10);
      const next = await askLeoSmart(
        entityText,
        letterText,
        candidates as unknown as Array<Record<string, unknown>>,
        [],
        "small",
        assertion || "present",
      );
      setResult(next);
      setStep("done");
    } catch {
      setError("Ask LEO is not available right now.");
      setStep("error");
    }
  }

  const patch = result ? applyAskLeoPatch(result) : null;

  return (
    <Stack spacing={0.75} sx={{ mt: 0.75, mb: 1 }} data-testid="extraction-review-ask-leo">
      <AskButton step={step} onAsk={() => void ask()} />
      {step === "error" ? <Alert severity="warning">{error}</Alert> : null}
      {step === "done" && result ? (
        <AskResult result={result} patch={patch} onApply={onApply} onDismiss={() => setStep("idle")} />
      ) : null}
    </Stack>
  );
}

function AskButton({ step, onAsk }: { step: LeoStep; onAsk: () => void }) {
  const loading = step === "loading";
  return (
    <Button
      size="small"
      variant="outlined"
      color="secondary"
      onClick={onAsk}
      disabled={loading}
      startIcon={loading ? <AskLeoBusyMark /> : undefined}
      aria-busy={loading}
      aria-label={loading ? "Asking LEO" : "Ask LEO"}
    >
      {loading ? "" : "Ask LEO"}
    </Button>
  );
}

function AskResult({
  result,
  patch,
  onApply,
  onDismiss,
}: {
  result: AskLeoSmartResult;
  patch: AskLeoFactPatch | null;
  onApply: (patch: AskLeoFactPatch) => void;
  onDismiss: () => void;
}) {
  const match = result.matched_candidate;
  const warning = result.assertion_warning;
  const copy =
    result.reason ||
    (result.is_ambiguous
      ? "LEO could not pick one tag from this letter. Choose a tag yourself."
      : "LEO could not suggest a tag for this fact.");
  return (
    <Stack
      spacing={0.75}
      sx={{
        p: 1,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        bgcolor: "background.paper",
      }}
    >
      {warning ? <Alert severity="warning">{warning}</Alert> : null}
      <Typography variant="caption" color="text.secondary">
        {copy}
      </Typography>
      {match ? (
        <Typography variant="body2" fontWeight={600}>
          {match.term}
          {patch?.semantic_tag ? ` -- ${patch.semantic_tag.replace(/_/g, " ")}` : ""}
        </Typography>
      ) : null}
      <Stack direction="row" spacing={1}>
        {patch ? (
          <Button size="small" variant="contained" onClick={() => onApply(patch)}>
            Use this tag
          </Button>
        ) : null}
        <Button size="small" onClick={onDismiss}>
          Dismiss
        </Button>
      </Stack>
    </Stack>
  );
}
