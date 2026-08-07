/**
 * Open SBAR result control for a completed Validation Lab single run.
 * Atlas: DI-FE423B8D / DO-158BE606 / VT-8F7346F1
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import { loadSbarAssessmentId } from "./labApi";

interface Props {
  sheet: {
    caseId: string;
    title: string;
    runId?: string;
    status: string;
  };
}

export function RunSheetSbarActions({ sheet }: Props) {
  const [sbarId, setSbarId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (sheet.status !== "completed" || !sheet.runId) return null;

  async function onOpen() {
    if (!sheet.runId) return;
    setBusy(true);
    setError(null);
    try {
      const assessmentId = await loadSbarAssessmentId(sheet.caseId, sheet.runId);
      if (!assessmentId) {
        setError("No SBAR is available for this run yet.");
        setSbarId(null);
        return;
      }
      setSbarId(assessmentId);
    } catch {
      setError("Could not load the SBAR for this run.");
      setSbarId(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ flex: 1 }}>
        <Button
          variant="outlined"
          disabled={busy}
          onClick={() => void onOpen()}
          data-testid="validation-lab-run-sheet-open-sbar"
        >
          {busy ? "Opening SBAR..." : "Open SBAR result"}
        </Button>
        {error ? (
          <Alert severity="error" sx={{ py: 0, flex: 1 }}>
            {error}
          </Alert>
        ) : null}
      </Stack>
      <Drawer
        anchor="right"
        open={Boolean(sbarId)}
        onClose={() => setSbarId(null)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 480 } } }}
        data-testid="validation-lab-run-sheet-sbar-drawer"
      >
        <Box sx={{ p: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
            <Typography variant="h6" component="h2" sx={{ flex: 1 }}>
              SBAR -- {sheet.title || "Lab case"}
            </Typography>
            <IconButton
              aria-label="Close SBAR"
              onClick={() => setSbarId(null)}
              size="small"
            >
              <CloseIcon />
            </IconButton>
          </Stack>
          {sbarId ? <LeoSbarHost assessmentId={sbarId} /> : null}
        </Box>
      </Drawer>
    </>
  );
}
