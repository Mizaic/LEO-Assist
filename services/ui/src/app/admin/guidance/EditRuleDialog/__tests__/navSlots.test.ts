/**
 * Flat stepper slots grow with confirmed situations.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { buildNavSlots, resolveCurrentSlotId } from "../navSlots";

describe("buildNavSlots", () => {
  it("uses the simple Who / Suggest / Save bar when the wizard is off", () => {
    const { slots, currentId } = buildNavSlots({
      outerStep: "who",
      wizardPhase: null,
      situationCount: 0,
      situationIndex: 0,
      reachedCheck: false,
    });
    expect(slots.map((s) => s.id)).toEqual(["who", "suggest", "save"]);
    expect(currentId).toBe("who");
  });

  it("starts guided flow without situation pills", () => {
    const { slots, currentId } = buildNavSlots({
      outerStep: "who",
      wizardPhase: "prerequisites",
      situationCount: 0,
      situationIndex: 0,
      reachedCheck: false,
    });
    expect(slots.map((s) => s.id)).toEqual([
      "always-true",
      "situations",
      "suggest",
      "save",
    ]);
    expect(currentId).toBe("always-true");
    expect(slots.find((s) => s.id === "situations")?.jumpable).toBe(false);
  });

  it("inserts one slot per confirmed situation plus Check", () => {
    const { slots, currentId } = buildNavSlots({
      outerStep: "who",
      wizardPhase: "pathway-conditions",
      situationCount: 3,
      situationIndex: 1,
      reachedCheck: false,
    });
    expect(slots.map((s) => s.id)).toEqual([
      "always-true",
      "situations",
      "situation-0",
      "situation-1",
      "situation-2",
      "check",
      "suggest",
      "save",
    ]);
    expect(currentId).toBe("situation-1");
    expect(slots.find((s) => s.id === "situation-0")?.jumpable).toBe(true);
    expect(slots.find((s) => s.id === "situation-1")?.jumpable).toBe(true);
    expect(slots.find((s) => s.id === "situation-2")?.jumpable).toBe(false);
    expect(slots.find((s) => s.id === "check")?.jumpable).toBe(false);
    expect(slots.find((s) => s.id === "situation-1")?.title).toMatch(
      /Situation B \(2 of 3\)/,
    );
  });

  it("keeps situation slots after Check is reached", () => {
    const { currentId } = buildNavSlots({
      outerStep: "who",
      wizardPhase: "review",
      situationCount: 2,
      situationIndex: 0,
      reachedCheck: true,
    });
    expect(currentId).toBe("check");
    expect(resolveCurrentSlotId({
      outerStep: "suggest",
      wizardPhase: "review",
      situationCount: 2,
      situationIndex: 0,
      reachedCheck: true,
    })).toBe("suggest");
  });
});
