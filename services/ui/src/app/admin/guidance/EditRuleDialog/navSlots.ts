/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Single flat navigation model for the rule editor.
 *
 * Replaces the nested "Who / Suggest / Save" + "Always true >
 * Situations > Conditions" pair with one slot list. After the
 * situations step confirms N pathways, N situation slots are
 * inserted so the bar grows with what the reviewer just found.
 */
import { pathwayLetter } from "./HighlightWizard/pathwayBoundaryEdits";
import type { WizardStepKind } from "./HighlightWizard/wizardState";
import type { StepId } from "./copy";

export type NavSlotId =
  | "who"
  | "always-true"
  | "situations"
  | `situation-${number}`
  | "check"
  | "suggest"
  | "save";

export interface NavSlot {
  id: NavSlotId;
  /** Chip label (letter for situations). */
  shortLabel: string;
  /** Full name for aria and wide layout. */
  title: string;
  /** Which left-pane surface to mount. */
  surface: StepId;
  /** Guided-wizard phase when surface is "who". */
  wizardStep?: WizardStepKind;
  /** 0-based situation index when wizardStep is pathway-conditions. */
  pathwayIndex?: number;
  /** Stepper click / footer Next may land here. */
  jumpable: boolean;
}

export interface NavSlotsInput {
  outerStep: StepId;
  /** Null when the guided wizard is not mounted. */
  wizardPhase: WizardStepKind | null;
  /** Confirmed situation count (0 until split is confirmed). */
  situationCount: number;
  /** Active situation while on pathway-conditions. */
  situationIndex: number;
  /** True once the reviewer has reached Check / Review. */
  reachedCheck: boolean;
}

export interface NavSlotsResult {
  slots: NavSlot[];
  currentId: NavSlotId;
  currentIndex: number;
}

function situationSlot(index: number, count: number, jumpable: boolean): NavSlot {
  const letter = pathwayLetter(index);
  return {
    id: `situation-${index}`,
    shortLabel: letter,
    title: `Situation ${letter} (${index + 1} of ${count})`,
    surface: "who",
    wizardStep: "pathway-conditions",
    pathwayIndex: index,
    jumpable,
  };
}

function guidedSlots(input: NavSlotsInput): NavSlot[] {
  const { wizardPhase, situationCount, reachedCheck, outerStep } = input;
  const onSuggestOrSave = outerStep === "suggest" || outerStep === "save";
  const showSituations =
    situationCount > 0 &&
    (wizardPhase === "pathway-conditions" ||
      wizardPhase === "review" ||
      reachedCheck ||
      onSuggestOrSave);

  const slots: NavSlot[] = [
    {
      id: "always-true",
      shortLabel: "Always",
      title: "Always true",
      surface: "who",
      wizardStep: "prerequisites",
      jumpable: true,
    },
    {
      id: "situations",
      shortLabel: "Situations",
      title: "Situations",
      surface: "who",
      wizardStep: "pathway-split",
      jumpable: true,
    },
  ];

  if (showSituations) {
    for (let i = 0; i < situationCount; i++) {
      slots.push(situationSlot(i, situationCount, true));
    }
    slots.push({
      id: "check",
      shortLabel: "Check",
      title: "Check the rule",
      surface: "who",
      wizardStep: "review",
      jumpable: true,
    });
  }

  slots.push(
    {
      id: "suggest",
      shortLabel: "Suggest",
      title: "What should the system suggest?",
      surface: "suggest",
      jumpable: true,
    },
    {
      id: "save",
      shortLabel: "Save",
      title: "Save your change",
      surface: "save",
      jumpable: true,
    },
  );
  return slots;
}

/** Past and current slots are open; future guided slots stay locked.
 *  Suggest / Save stay open so reviewers can still skip ahead. */
function applyJumpable(slots: NavSlot[], currentIndex: number): NavSlot[] {
  return slots.map((slot, index) => {
    if (slot.id === "suggest" || slot.id === "save") {
      return { ...slot, jumpable: true };
    }
    return { ...slot, jumpable: index <= currentIndex };
  });
}

function simpleSlots(): NavSlot[] {
  return [
    {
      id: "who",
      shortLabel: "Who",
      title: "Who is this rule about?",
      surface: "who",
      jumpable: true,
    },
    {
      id: "suggest",
      shortLabel: "Suggest",
      title: "What should the system suggest?",
      surface: "suggest",
      jumpable: true,
    },
    {
      id: "save",
      shortLabel: "Save",
      title: "Save your change",
      surface: "save",
      jumpable: true,
    },
  ];
}

export function resolveCurrentSlotId(input: NavSlotsInput): NavSlotId {
  if (input.outerStep === "suggest") return "suggest";
  if (input.outerStep === "save") return "save";
  if (!input.wizardPhase) return "who";
  if (input.wizardPhase === "prerequisites") return "always-true";
  if (input.wizardPhase === "pathway-split") return "situations";
  if (input.wizardPhase === "pathway-conditions") {
    return `situation-${input.situationIndex}`;
  }
  if (input.wizardPhase === "review") return "check";
  return "who";
}

/** Build the flat stepper slots for the current editor state. */
export function buildNavSlots(input: NavSlotsInput): NavSlotsResult {
  const raw = input.wizardPhase ? guidedSlots(input) : simpleSlots();
  const currentId = resolveCurrentSlotId(input);
  const currentIndex = Math.max(
    0,
    raw.findIndex((slot) => slot.id === currentId),
  );
  const slots = input.wizardPhase ? applyJumpable(raw, currentIndex) : raw;
  return { slots, currentId, currentIndex };
}

export type WizardNavTarget =
  | { step: "prerequisites" }
  | { step: "pathway-split" }
  | { step: "pathway-conditions"; pathwayIndex: number }
  | { step: "review" };

/** Map a who-surface slot to a wizard navigation target. */
export function slotToWizardTarget(slot: NavSlot): WizardNavTarget | null {
  if (slot.surface !== "who" || !slot.wizardStep) return null;
  if (slot.wizardStep === "pathway-conditions") {
    return {
      step: "pathway-conditions",
      pathwayIndex: slot.pathwayIndex ?? 0,
    };
  }
  return { step: slot.wizardStep };
}
