/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4FD76836
 *   DI: DI-238DA59A, DI-C953EF73, DI-562F2C9E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4FD76836")
 */
"use client";

/**
 * Three-path Validation Lab home, then one run review.
 *
 * Atlas: UN-4DCE95C8 / DI-238DA59A / DI-C953EF73 / DI-562F2C9E
 * DO: DO-4FD76836
 */

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";

import AccuracyLoopHome, { type LabDoor } from "./AccuracyLoopHome";
import ClinicalDoor from "./ClinicalDoor";
import LabCasesPanel from "./LabCasesPanel";
import RuleDoor from "./RuleDoor";
import RunReviewLightbox, { type RunReviewTarget } from "./RunReviewLightbox";
import type { LabWorkPreview } from "./inspectorTypes";
import { getCase, listCases, type LabCase } from "./labApi";
import { listOpenFindings } from "./labFindingsApi";
import { pollCasePipeline, queueCasePipeline } from "./labRun";
import type { ValidationFinding } from "./findingTypes";

type View = "home" | LabDoor;

export default function ValidationLabPage() {
  const [view, setView] = useState<View>("home");
  const [review, setReview] = useState<RunReviewTarget | null>(null);
  const [goldCases, setGoldCases] = useState<LabCase[]>([]);
  const [findings, setFindings] = useState<ValidationFinding[]>([]);
  const [twinPhrases, setTwinPhrases] = useState<string[]>([]);

  const reloadStrip = useCallback(async () => {
    const [cases, open] = await Promise.all([
      listCases(),
      listOpenFindings().catch(() => [] as ValidationFinding[]),
    ]);
    setGoldCases(cases.filter((row) => row.has_gold));
    setFindings(open);
  }, []);

  useEffect(() => {
    void reloadStrip().catch(() => undefined);
  }, [reloadStrip]);

  async function openGold(caseId: string) {
    const labCase = await getCase(caseId);
    const latest = labCase.runs?.[0];
    setReview({
      title: labCase.title,
      caseId: labCase.id,
      labRunId: latest?.id,
      referralText: labCase.referral_text || "",
      status: latest?.status || "idle",
      terminal: Boolean(latest),
      assessmentCaseId: labCase.id,
    });
  }

  async function retest(previews: Record<string, LabWorkPreview>) {
    if (!review?.caseId) return;
    const started = await queueCasePipeline(review.caseId);
    setReview({
      ...review,
      labRunId: started.id,
      status: started.status,
      terminal: false,
      readOnly: false,
      previousPreviews: previews,
    });
    const finalRun = await pollCasePipeline(review.caseId, started.id);
    setReview((prev) =>
      prev
        ? {
            ...prev,
            status: finalRun.status,
            terminal: true,
          }
        : prev,
    );
  }

  return (
    <Box data-testid="validation-lab-page">
      {view === "home" ? (
        <AccuracyLoopHome
          goldCases={goldCases}
          openFindings={findings}
          onOpenDoor={setView}
          onOpenGold={(id) => void openGold(id)}
          onOpenFinding={(runId) =>
            setReview({
              title: "Finding",
              pipelineRunId: runId,
              labRunId: runId,
              status: "completed",
              terminal: true,
              readOnly: true,
            })
          }
        />
      ) : null}
      {view === "rule" ? (
        <RuleDoor
          seedPhrases={twinPhrases}
          onBack={() => {
            setView("home");
            setTwinPhrases([]);
          }}
          onReview={setReview}
        />
      ) : null}
      {view === "clinical" ? (
        <ClinicalDoor onBack={() => setView("home")} onReview={setReview} />
      ) : null}
      {view === "saved" ? (
        <LabCasesPanel initialMode="case" onBack={() => setView("home")} />
      ) : null}
      <RunReviewLightbox
        target={review}
        onClose={() => {
          setReview(null);
          void reloadStrip();
        }}
        onRetest={(previews) => void retest(previews)}
        onSavedGold={() => void reloadStrip()}
        onBuildTwin={(phrases) => {
          setTwinPhrases(phrases);
          setReview(null);
          setView("rule");
        }}
      />
    </Box>
  );
}
