/**
 * Draft assessment host for the Decide phase.
 *
 * Atlas: DI-49BA8E04 / DI-A898556B / VT-592D30E9
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";
import { loadSbarAssessmentId } from "./labApi";

interface Props {
  caseId: string;
  runId: string;
}

export function DecideSbar({ caseId, runId }: Props) {
  const [assessmentId, setAssessmentId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!caseId || !runId) return;
    let alive = true;
    void loadSbarAssessmentId(caseId, runId)
      .then((id) => {
        if (!alive) return;
        setAssessmentId(id);
        setError(id ? "" : "The draft is not ready yet.");
      })
      .catch(() => {
        if (!alive) return;
        setAssessmentId(null);
        setError("We could not load the draft.");
      });
    return () => {
      alive = false;
    };
  }, [caseId, runId]);

  return (
    <Box
      sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 1.5 }}
      data-testid="validation-lab-decide-sbar"
    >
      {assessmentId ? <LeoSbarHost assessmentId={assessmentId} /> : null}
      {!assessmentId ? (
        <Typography variant="body2" color="text.secondary">
          {error || "Loading the draft..."}
        </Typography>
      ) : null}
    </Box>
  );
}
