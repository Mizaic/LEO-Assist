/**
 * Validation Lab home path order and copy.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
export type LabDoor = "rule" | "clinical" | "saved";

export interface HomeDoor {
  id: LabDoor;
  testId: string;
  tone: "danger" | "success" | "brand";
  headline: string;
  description: string;
  steps: string[];
}

export const HOME_DOORS: HomeDoor[] = [
  {
    id: "clinical",
    testId: "validation-lab-mode-clinical",
    tone: "danger",
    headline: "Investigate a non-conformance",
    description:
      "Start with the product non-conformance. Then find the patient. Mark what went wrong. Do not start a new job.",
    steps: [
      "1. Look up or open the product NCR",
      "2. Find the patient or letter",
      "3. Say why you opened it",
      "4. Mark what is wrong",
    ],
  },
  {
    id: "saved",
    testId: "validation-lab-mode-saved",
    tone: "success",
    headline: "Run baseline tests",
    description:
      "Replay gold cases. Check LEO still reads them the same way.",
    steps: [
      "1. Open saved gold cases",
      "2. Run the baseline set",
      "3. Review any drift",
      "4. Fix, then retest if needed",
    ],
  },
  {
    id: "rule",
    testId: "validation-lab-mode-rule",
    tone: "brand",
    headline: "Build new tests",
    description:
      "Test a guideline rule. Pick a care rule. Check the letter. Run the same path a real referral uses.",
    steps: [
      "1. Pick a guideline rule",
      "2. Check the letter",
      "3. Review each step",
      "4. Fix, retest, save gold",
    ],
  },
];
