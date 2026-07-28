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
    title: "Four stages",
    body: "Find, then check, then approve, then go live. Jump here anytime.",
    anchorSelector: '[data-tour="cg-01-jump"]',
  },
  {
    id: "cg-02-load",
    title: "Load a guideline",
    body: "Search NICE or enter a code. Wait for it to finish loading.",
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
    title: "Your review queue",
    body: "New drafts wait here. You decide on each one.",
    anchorSelector: '[data-tour="cg-04-review-pool"]',
  },
  {
    id: "cg-05-card",
    title: "Read before you decide",
    body: "Open a rule to see the plain-English logic and the NICE text side by side.",
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
    body: "The right side shows the exact words you are turning into a rule.",
    anchorSelector: '[data-tour="er-02-quote"]',
  },
  {
    id: "er-03-always",
    title: "Global checks only",
    body: "Add something here only if it applies no matter which symptoms match.",
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
    body: "This is what the rule will actually do. Read it like a clinician would.",
    anchorSelector: '[data-tour="er-06-review"]',
  },
  {
    id: "er-07-save",
    title: "Say why, then approve",
    body: "Write a short reason. Approve and save.",
    anchorSelector: '[data-tour="er-07-save"]',
  },
];
