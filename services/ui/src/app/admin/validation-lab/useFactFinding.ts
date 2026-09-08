/**
 * Save a Validation Lab finding for the selected fact.
 *
 * Atlas: DI-42EB69CA / DI-562F2C9E / DO-DD92B11E / VT-E8A064C9
 */

import { useState } from "react";

import { createFinding } from "./labFindingsApi";
import {
  stageFromStepId,
  type FindingCategory,
} from "./findingTypes";

export function useFactFinding(
  runId: string,
  stepId: string | null,
  readOnly?: boolean,
) {
  const [markTarget, setMarkTarget] = useState("");
  const [fixCategory, setFixCategory] = useState<FindingCategory | "">("");

  async function saveFinding(category: FindingCategory, note: string) {
    if (!runId || readOnly) return;
    await createFinding(runId, {
      stage_id: stageFromStepId(stepId || "extract"),
      category,
      target: markTarget,
      note,
    });
    setFixCategory(category);
  }

  return {
    markTarget,
    fixCategory,
    canMark: Boolean(runId) && !readOnly,
    openMarkWrong: (text: string) => setMarkTarget(text.trim()),
    closeMarkWrong: () => setMarkTarget(""),
    saveFinding,
  };
}
