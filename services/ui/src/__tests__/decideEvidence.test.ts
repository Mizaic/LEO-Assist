/**
 * VT-592D30E9 -- Decide shows guideline, completeness, and the draft.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 */

import {
  decideOutcomeStepIds,
  sbarIdFromStage,
  sbarMarkdownFromStage,
} from "../app/admin/validation-lab/decideEvidence";

describe("decideEvidence", () => {
  test("finds guideline, completeness, and SBAR step ids", () => {
    expect(
      decideOutcomeStepIds([
        { step_id: "act-ref-compliance", status: "completed" },
        { step_id: "act-ref-quality-check", status: "completed" },
        { step_id: "act-ref-sbar", status: "completed" },
      ]),
    ).toEqual({
      guideline: "act-ref-compliance",
      completeness: "act-ref-quality-check",
      sbar: "act-ref-sbar",
    });
  });

  test("reads an assessment id and markdown from the SBAR stage", () => {
    const output = {
      sbar_assessment_id: "ass-1",
      sbar_report: {
        situation: "New jaundice",
        background: "Liver clinic letter",
        assessment: "Urgent scan",
        recommendation: "Two week wait",
      },
    };
    expect(sbarIdFromStage(output)).toBe("ass-1");
    expect(sbarMarkdownFromStage(output)).toContain("## Situation");
    expect(sbarMarkdownFromStage(output)).toContain("New jaundice");
  });
});
