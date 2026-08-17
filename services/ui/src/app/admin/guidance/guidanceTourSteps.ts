/**
 * Single source of truth for Clinical Guidelines IFU tour steps.
 *
 * Drives CoachTour content, data-tour anchors, and Playwright
 * screenshot basenames. Keep ids stable -- screenshots and e2e
 * selectors depend on them.
 *
 * Atlas trace: DI-LEO-AI-121 / DI-42246DA7 (cosmetic coach / editor chrome).
 */

import type { TourStep } from "@/components/ui/CoachTour";

export type { TourStep };

/** Act A -- page shell (Load -> Compile). */
export const PAGE_TOUR_STEPS: TourStep[] = [
  {
    id: "cg-01-jump",
    title: "Four steps on this page",
    body: "This bar switches the page. Pick Load, Inspect, Review, or Compile. You see one step at a time.",
    anchorSelector: '[data-tour="cg-01-jump"]',
  },
  {
    id: "cg-02-load",
    title: "Bring a guideline in",
    body: "Search by condition or guideline code, then wait until loading finishes.",
    anchorSelector: '[data-tour="cg-02-load"]',
  },
  {
    id: "cg-03-inspect",
    title: "Check what loaded",
    body: "Confirm the chapters. Generate rules when you are ready.",
    anchorSelector: '[data-tour="cg-03-inspect"]',
  },
  {
    id: "cg-04-review-pool",
    title: "Rules waiting for you",
    body: "Open Review to accept, edit, or reject each draft before it can go live.",
    anchorSelector: '[data-tour="cg-04-review-pool"]',
  },
  {
    id: "cg-05-card",
    title: "Check the wording",
    body: "Open one draft to read the plain English next to the guideline text, then decide.",
    anchorSelector: '[data-tour="cg-05-card"]',
  },
  {
    id: "cg-06-compile",
    title: "Save is not live yet",
    body: "Come back here and compile so patients see the change.",
    anchorSelector: '[data-tour="cg-06-compile"]',
  },
];

/** Act B -- edit dialog (Who -> Save). */
export const EDIT_RULE_TOUR_STEPS: TourStep[] = [
  {
    id: "er-01-stepper",
    title: "Who, Suggest, Save",
    body: "This bar is your map through the rule.",
    anchorSelector: '[data-tour="er-01-stepper"]',
  },
  {
    id: "er-02-quote",
    title: "Keep the guideline in view",
    body: "Look at the NICE text on the right -- those are the words you are turning into a rule.",
    anchorSelector: '[data-tour="er-02-quote"]',
  },
  {
    id: "er-03-always",
    title: "Always-true checks",
    body: "Add something here only if it applies no matter which situation matches.",
    anchorSelector: '[data-tour="er-03-always"]',
  },
  {
    id: "er-04-situations",
    title: "Confirm the split",
    body: "Check the situations LEO found. Only merge or split if it got it wrong.",
    anchorSelector: '[data-tour="er-04-situations"]',
  },
  {
    id: "er-05-conditions",
    title: "Match every line",
    body: "Every row needs a code. A row with no match blocks you moving on.",
    anchorSelector: '[data-tour="er-05-conditions"]',
  },
  {
    id: "er-06-review",
    title: "Check the meaning",
    body: "Read the live preview on the right -- that is what the rule will do.",
    anchorSelector: '[data-tour="er-06-preview"]',
  },
  {
    id: "er-07-save",
    title: "Say why, then approve",
    body: "Write a short reason, then approve and save. Patients still will not see it until you compile.",
    anchorSelector: '[data-tour="er-07-save"]',
  },
];

/** Page jump targets for Act A prepareStep. */
export type PageTourJumpId = "load" | "inspect" | "review" | "compile";

export function pageTourJumpForStep(stepId: string): PageTourJumpId | null {
  switch (stepId) {
    case "cg-02-load":
      return "load";
    case "cg-03-inspect":
      return "inspect";
    case "cg-04-review-pool":
    case "cg-05-card":
      return "review";
    case "cg-06-compile":
      return "compile";
    default:
      return null;
  }
}

/** Wizard / editor phase the Act B tour needs before measuring. */
export type EditTourPhase =
  | "prerequisites"
  | "pathway-split"
  | "pathway-conditions"
  | "review"
  | "save";

export function editTourPhaseForStep(stepId: string): EditTourPhase | null {
  switch (stepId) {
    case "er-01-stepper":
    case "er-02-quote":
    case "er-03-always":
      return "prerequisites";
    case "er-04-situations":
      return "pathway-split";
    case "er-05-conditions":
      return "pathway-conditions";
    case "er-06-review":
      return "review";
    case "er-07-save":
      return "save";
    default:
      return null;
  }
}
