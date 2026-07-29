/**
 * Click a flat-stepper slot by outer surface (Who / Suggest / Save).
 * Slot indexes vary once situations are inserted, so tests must not
 * hard-code "Step N of 3".
 */
import { fireEvent, screen } from "@testing-library/react";

const STEP_PATTERNS = [
  /Step \d+ of \d+: (Who is this rule about|Always true)/i,
  /Step \d+ of \d+: What should the system suggest/i,
  /Step \d+ of \d+: Save your change/i,
] as const;

export function goToEditorStep(stepNumber: 1 | 2 | 3): void {
  fireEvent.click(
    screen.getByRole("button", { name: STEP_PATTERNS[stepNumber - 1] }),
  );
}
