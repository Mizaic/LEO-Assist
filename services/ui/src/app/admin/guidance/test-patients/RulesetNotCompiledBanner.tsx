"use client";

/**
 * Loud banner shown whenever the production bitmap has not been
 * compiled for the requested scope. Without this banner the UI used
 * to silently report "no rules fired", which looked identical to a
 * legitimate empty result and hid the fact that the entire evaluator
 * had nothing loaded.
 *
 * The banner offers a one-click compile so the reviewer can fix the
 * problem without leaving the dialog.
 *
 * Design control: DI-LEO-AI-181 / R-LEO-AI-176 (silent zero-match).
 */

import { useState } from "react";
import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { compileProductionBitmap } from "./api";

interface Props {
  /**
   * Scope the missing ruleset belongs to. ``global``/``default`` is
   * the production scope; other values mean a guideline- or
   * domain-scoped ruleset is missing for that subset of rules.
   */
  scopeType?: string;
  scopeId?: string;
  /** Optional message returned by the backend (e.g. recompile_hint). */
  detail?: string | null;
  /**
   * Optional callback fired AFTER compile is requested -- typically
   * the parent re-runs whatever query just returned ``not_compiled``
   * (replay, diagnose, evaluate) so the new banner state reflects
   * reality.
   */
  onCompileRequested?: (job: { job_id: string; version: string }) => void;
  /**
   * When ``true`` the banner explains we are in a draft sandbox flow
   * (so the user understands that compiling production won't fix the
   * sandbox). Defaults to ``false``.
   */
  sandbox?: boolean;
}

export default function RulesetNotCompiledBanner({
  scopeType = "global",
  scopeId = "default",
  detail,
  onCompileRequested,
  sandbox = false,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<{ job_id: string; version: string } | null>(
    null,
  );

  async function handleCompile() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const summary = await compileProductionBitmap(scopeType, scopeId);
      setJob(summary);
      onCompileRequested?.(summary);
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "Could not start the compile. Try the Bitmap lifecycle panel.",
      );
    } finally {
      setBusy(false);
    }
  }

  const scopeLabel =
    scopeType === "global" && scopeId === "default"
      ? "the production ruleset"
      : `${scopeType} / ${scopeId}`;

  return (
    <Alert
      severity="warning"
      role="status"
      aria-label="No active bitmap ruleset"
      sx={{ mt: 1 }}
      action={
        sandbox ? null : (
          <Button
            color="inherit"
            size="small"
            onClick={handleCompile}
            disabled={busy}
            startIcon={busy ? <CircularProgress size={14} /> : undefined}
          >
            {busy ? "Compiling..." : "Compile now"}
          </Button>
        )
      }
    >
      <AlertTitle>
        {sandbox
          ? "Draft sandbox could not be compiled"
          : "No bitmap ruleset is loaded"}
      </AlertTitle>
      {sandbox ? (
        <Typography variant="body2">
          The draft rule could not be compiled into a sandbox bitmap, so
          there is nothing to test the saved patients against. Check the
          rule has at least one SNOMED-coded leaf.
          {detail ? ` ${detail}` : ""}
        </Typography>
      ) : (
        <Stack spacing={0.5}>
          <Typography variant="body2">
            Patient evaluations against {scopeLabel} are returning zero
            matches because the bitmap has not been compiled. Click
            <strong> Compile now </strong> to build it from the active
            rules in Neo4j.
          </Typography>
          {detail && (
            <Typography variant="caption" color="text.secondary">
              {detail}
            </Typography>
          )}
        </Stack>
      )}
      {job && (
        <Box sx={{ mt: 0.5 }}>
          <Typography variant="caption" color="text.secondary">
            Compile started (job {job.job_id}, version {job.version}).
            Re-run the test once it finishes; check the Bitmap
            lifecycle panel for live progress.
          </Typography>
        </Box>
      )}
      {error && (
        <Typography variant="caption" color="error.main" sx={{ display: "block", mt: 0.5 }}>
          {error}
        </Typography>
      )}
    </Alert>
  );
}
