/**
 * Single-run review lightbox or multi-run progress sheet.
 *
 * Atlas: DI-C953EF73 / DI-FE423B8D / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import RunReviewLightbox from "./RunReviewLightbox";
import RunSheetDialog, { type RunSheetState } from "./RunSheetDialog";
import type { LabCase } from "./labApi";

interface Props {
  sheet: RunSheetState | null;
  detail: LabCase | null;
  onClose: () => void;
  onRetest: (caseId: string) => void;
  onSavedGold: () => void;
}

export default function LabRunSheetHost({
  sheet,
  detail,
  onClose,
  onRetest,
  onSavedGold,
}: Props) {
  if (sheet?.mode === "single") {
    return (
      <RunReviewLightbox
        target={{
          title: sheet.title,
          caseId: sheet.caseId,
          labRunId: sheet.runId,
          referralText: detail?.referral_text || "",
          status: sheet.status,
          terminal: sheet.terminal,
          assessmentCaseId: sheet.caseId,
        }}
        onClose={onClose}
        onRetest={() => onRetest(sheet.caseId)}
        onSavedGold={onSavedGold}
      />
    );
  }
  return <RunSheetDialog sheet={sheet} onClose={onClose} />;
}
