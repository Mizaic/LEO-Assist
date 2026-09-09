/**
 * Load Decide-phase guideline, completeness, and draft evidence.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 */

import { useEffect, useState } from "react";

import { getRunInspectorStage, loadSbarAssessmentId } from "./labApi";
import { getPipelineRunInspectorStage } from "./labFindingsApi";
import type { PhaseSpan } from "./clinicalPhases";
import {
  decideOutcomeStepIds,
  sbarIdFromStage,
  sbarMarkdownFromStage,
} from "./decideEvidence";
import { stageStory, type StageStory } from "./inspector/stageEvidence";
import type { LabStageDetail } from "./inspectorTypes";

export interface DecideEvidence {
  guideline: StageStory | null;
  completeness: StageStory | null;
  assessmentId: string | null;
  markdown: string;
  error: string;
  loading: boolean;
}

const EMPTY: DecideEvidence = {
  guideline: null,
  completeness: null,
  assessmentId: null,
  markdown: "",
  error: "",
  loading: true,
};

export function useDecideEvidence(
  caseId: string,
  runId: string,
  pipelineRunId: string,
  spans: PhaseSpan[],
): DecideEvidence {
  const [view, setView] = useState<DecideEvidence>(EMPTY);
  const spanKey = spans.map((span) => `${span.step_id}:${span.status}`).join("|");

  useEffect(() => {
    let alive = true;
    void loadDecideEvidence(caseId, runId, pipelineRunId, spans).then(
      (next) => {
        if (alive) setView(next);
      },
    );
    return () => {
      alive = false;
    };
  }, [caseId, runId, pipelineRunId, spanKey, spans]);

  return view;
}

async function loadDecideEvidence(
  caseId: string,
  runId: string,
  pipelineRunId: string,
  spans: PhaseSpan[],
): Promise<DecideEvidence> {
  const ids = decideOutcomeStepIds(spans);
  const [guide, gaps, sbar] = await Promise.all([
    loadStage(caseId, runId, pipelineRunId, ids.guideline),
    loadStage(caseId, runId, pipelineRunId, ids.completeness),
    loadStage(caseId, runId, pipelineRunId, ids.sbar),
  ]);
  const fromLab =
    caseId && runId ? await loadSbarAssessmentId(caseId, runId).catch(() => null) : null;
  const assessmentId = fromLab || sbarIdFromStage(sbar?.output);
  const markdown = sbarMarkdownFromStage(sbar?.output);
  return {
    guideline: ids.guideline ? stageStory(ids.guideline, guide?.output) : null,
    completeness: ids.completeness
      ? stageStory(ids.completeness, gaps?.output)
      : null,
    assessmentId,
    markdown,
    error: decideError(assessmentId, markdown),
    loading: false,
  };
}

async function loadStage(
  caseId: string,
  runId: string,
  pipelineRunId: string,
  stepId: string | null,
): Promise<LabStageDetail | null> {
  if (!stepId) return null;
  try {
    if (caseId && runId) return await getRunInspectorStage(caseId, runId, stepId);
    if (pipelineRunId) {
      return await getPipelineRunInspectorStage(pipelineRunId, stepId);
    }
  } catch {
    return null;
  }
  return null;
}

function decideError(
  assessmentId: string | null,
  markdown: string,
): string {
  if (assessmentId || markdown) return "";
  return "The draft is not ready yet.";
}
