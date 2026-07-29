/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Visible label for the in-wizard back control. Kept distinct from the
 * dialog footer's "Previous step" so reviewers do not confuse "previous
 * situation / question" with jumping Who -> Suggest -> Save.
 *
 * Lives outside copy.ts so it can import WizardStepKind without a
 * copy <-> wizardState cycle.
 */
import { WIZARD_CHROME } from "./copy";
import type { WizardStepKind } from "./wizardState";

export function wizardBackLabel(
  step: WizardStepKind,
  pathwayIndex = 0,
): string {
  if (step === "pathway-split") return WIZARD_CHROME.backToAlwaysTrue;
  if (step === "pathway-conditions") {
    return pathwayIndex > 0
      ? WIZARD_CHROME.previousSituation
      : WIZARD_CHROME.backToSituations;
  }
  if (step === "review") return WIZARD_CHROME.reviewBackLabel;
  return WIZARD_CHROME.backLabel;
}
