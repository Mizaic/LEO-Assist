/**
 * Unit tests for the highlight-to-build wizard's pure phase state
 * machine -- Step 1 -> Step 2 -> Step 3 (repeated per pathway) ->
 * Review, plus Back navigation and the "materializing" hold state
 * for when Step 2's confirm needs a tree mutation to land first.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import {
  INITIAL_WIZARD_STATE,
  wizardReducer,
  type WizardState,
} from "../HighlightWizard/wizardState";
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";

function boundary(text: string): PathwayTextBoundary {
  return { text, start: 0, end: text.length, source: "heuristic" };
}

const TWO_BOUNDARIES = [boundary("pathway A"), boundary("pathway B")];

describe("wizardReducer: forward navigation", () => {
  it("starts on prerequisites", () => {
    expect(INITIAL_WIZARD_STATE.step).toBe("prerequisites");
  });

  it("CONFIRM_PREREQUISITES moves to pathway-split", () => {
    const next = wizardReducer(INITIAL_WIZARD_STATE, { type: "CONFIRM_PREREQUISITES" });
    expect(next.step).toBe("pathway-split");
  });

  it("CONFIRM_SPLIT with readyImmediately jumps straight to pathway-conditions[0]", () => {
    const state: WizardState = { ...INITIAL_WIZARD_STATE, step: "pathway-split" };
    const next = wizardReducer(state, {
      type: "CONFIRM_SPLIT",
      boundaries: TWO_BOUNDARIES,
      readyImmediately: true,
    });
    expect(next.step).toBe("pathway-conditions");
    expect(next.pathwayIndex).toBe(0);
    expect(next.boundaries).toBe(TWO_BOUNDARIES);
  });

  it("CONFIRM_SPLIT without readyImmediately sets materializing and stays put", () => {
    const state: WizardState = { ...INITIAL_WIZARD_STATE, step: "pathway-split" };
    const next = wizardReducer(state, {
      type: "CONFIRM_SPLIT",
      boundaries: TWO_BOUNDARIES,
      readyImmediately: false,
    });
    expect(next.step).toBe("pathway-split");
    expect(next.materializing).toBe(true);
    expect(next.boundaries).toBe(TWO_BOUNDARIES);
  });

  it("PATHWAYS_READY advances to pathway-conditions[0] only while materializing", () => {
    const materializing: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "pathway-split",
      boundaries: TWO_BOUNDARIES,
      materializing: true,
    };
    const ready = wizardReducer(materializing, { type: "PATHWAYS_READY" });
    expect(ready.step).toBe("pathway-conditions");
    expect(ready.materializing).toBe(false);

    const notMaterializing: WizardState = { ...INITIAL_WIZARD_STATE, step: "pathway-split" };
    expect(wizardReducer(notMaterializing, { type: "PATHWAYS_READY" })).toBe(notMaterializing);
  });

  it("CONFIRM_NO_SPLIT sets a single synthetic boundary and jumps to pathway-conditions[0]", () => {
    const state: WizardState = { ...INITIAL_WIZARD_STATE, step: "pathway-split" };
    const whole = boundary("the whole recommendation");
    const next = wizardReducer(state, { type: "CONFIRM_NO_SPLIT", boundary: whole });
    expect(next.step).toBe("pathway-conditions");
    expect(next.pathwayIndex).toBe(0);
    expect(next.boundaries).toEqual([whole]);
  });

  it("SET_CLUSTER_GROUPING records a choice keyed by the pathway's own pathway_key", () => {
    const next = wizardReducer(INITIAL_WIZARD_STATE, {
      type: "SET_CLUSTER_GROUPING",
      pathwayKey: "pw_b",
      grouping: "AT_LEAST",
    });
    expect(next.clusterGroupings).toEqual({ pw_b: "AT_LEAST" });
  });

  it("SET_LEAD_CLUSTER_GROUPING records a choice keyed by pathway_key, independently of clusterGroupings", () => {
    const next = wizardReducer(INITIAL_WIZARD_STATE, {
      type: "SET_LEAD_CLUSTER_GROUPING",
      pathwayKey: "pw_d",
      grouping: "AT_LEAST",
    });
    expect(next.leadClusterGroupings).toEqual({ pw_d: "AT_LEAST" });
    expect(next.clusterGroupings).toEqual({});
  });

  it("CONFIRM_PATHWAY advances to the next pathway index", () => {
    const state: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "pathway-conditions",
      pathwayIndex: 0,
      boundaries: TWO_BOUNDARIES,
    };
    const next = wizardReducer(state, { type: "CONFIRM_PATHWAY" });
    expect(next.step).toBe("pathway-conditions");
    expect(next.pathwayIndex).toBe(1);
  });

  it("CONFIRM_PATHWAY on the last pathway moves to review", () => {
    const state: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "pathway-conditions",
      pathwayIndex: 1,
      boundaries: TWO_BOUNDARIES,
    };
    const next = wizardReducer(state, { type: "CONFIRM_PATHWAY" });
    expect(next.step).toBe("review");
  });

  it("GO_TO_REVIEW jumps straight to review from any step", () => {
    const next = wizardReducer(INITIAL_WIZARD_STATE, { type: "GO_TO_REVIEW" });
    expect(next.step).toBe("review");
  });
});

describe("wizardReducer: BACK navigation", () => {
  it("does nothing from the first step", () => {
    const next = wizardReducer(INITIAL_WIZARD_STATE, { type: "BACK" });
    expect(next).toEqual(INITIAL_WIZARD_STATE);
  });

  it("pathway-split goes back to prerequisites", () => {
    const state: WizardState = { ...INITIAL_WIZARD_STATE, step: "pathway-split" };
    expect(wizardReducer(state, { type: "BACK" }).step).toBe("prerequisites");
  });

  it("pathway-conditions[i>0] steps back one pathway without leaving step 3", () => {
    const state: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "pathway-conditions",
      pathwayIndex: 2,
      boundaries: [boundary("a"), boundary("b"), boundary("c")],
    };
    const next = wizardReducer(state, { type: "BACK" });
    expect(next.step).toBe("pathway-conditions");
    expect(next.pathwayIndex).toBe(1);
  });

  it("pathway-conditions[0] goes back to pathway-split and KEEPS boundaries (Step 2 re-reads them as its own prior edits)", () => {
    const state: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "pathway-conditions",
      pathwayIndex: 0,
      boundaries: TWO_BOUNDARIES,
    };
    const next = wizardReducer(state, { type: "BACK" });
    expect(next.step).toBe("pathway-split");
    // Nulling this here would force StepPathwaySplit to re-derive
    // fresh boundaries from the raw text on remount, silently
    // discarding any merge/split the reviewer already did in Step 2
    // before confirming -- see the merge/split confusion audit.
    expect(next.boundaries).toEqual(TWO_BOUNDARIES);
  });

  it("review goes back to the last pathway when there were pathways", () => {
    const state: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "review",
      boundaries: TWO_BOUNDARIES,
    };
    const next = wizardReducer(state, { type: "BACK" });
    expect(next.step).toBe("pathway-conditions");
    expect(next.pathwayIndex).toBe(1);
  });

  it("review goes back to pathway-split when there were no boundaries", () => {
    const state: WizardState = { ...INITIAL_WIZARD_STATE, step: "review", boundaries: null };
    expect(wizardReducer(state, { type: "BACK" }).step).toBe("pathway-split");
  });

  it("pathway-split clears a pending materialize flag so a race with PATHWAYS_READY cannot undo the Back click", () => {
    // Mirrors CONFIRM_SPLIT's non-ready branch: materializing=true,
    // still on "pathway-split" while the tree mutation is in flight.
    const state: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "pathway-split",
      boundaries: TWO_BOUNDARIES,
      materializing: true,
    };
    const backed = wizardReducer(state, { type: "BACK" });
    expect(backed.step).toBe("prerequisites");
    expect(backed.materializing).toBe(false);

    // The tree mutation lands afterwards and useMaterializationEffect
    // fires PATHWAYS_READY regardless of what step the UI is now on --
    // it must be a no-op since materializing was already cleared.
    const afterLateReady = wizardReducer(backed, { type: "PATHWAYS_READY" });
    expect(afterLateReady).toEqual(backed);
    expect(afterLateReady.step).toBe("prerequisites");
  });
});

describe("wizardReducer: copy-across offer dismissal", () => {
  it("DISMISS_COPY_ACROSS_OFFER records the pathway_key without touching other pathways", () => {
    const withOneDismissed = wizardReducer(INITIAL_WIZARD_STATE, {
      type: "DISMISS_COPY_ACROSS_OFFER",
      pathwayKey: "pw_b",
    });
    expect(withOneDismissed.dismissedCopyAcrossOffers.has("pw_b")).toBe(true);
    expect(withOneDismissed.dismissedCopyAcrossOffers.has("pw_c")).toBe(false);

    const withTwoDismissed = wizardReducer(withOneDismissed, {
      type: "DISMISS_COPY_ACROSS_OFFER",
      pathwayKey: "pw_c",
    });
    expect(withTwoDismissed.dismissedCopyAcrossOffers.has("pw_b")).toBe(true);
    expect(withTwoDismissed.dismissedCopyAcrossOffers.has("pw_c")).toBe(true);
    // The original state's set is untouched -- reducers never mutate.
    expect(INITIAL_WIZARD_STATE.dismissedCopyAcrossOffers.size).toBe(0);
  });
});

describe("wizardReducer: jump-to-issue navigation", () => {
  it("JUMP_TO_PREREQUISITES moves straight there from any step", () => {
    const fromReview: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "review",
      boundaries: TWO_BOUNDARIES,
      pathwayIndex: 1,
    };
    const next = wizardReducer(fromReview, { type: "JUMP_TO_PREREQUISITES" });
    expect(next.step).toBe("prerequisites");
    // Nothing else about the in-progress work is lost by jumping.
    expect(next.boundaries).toBe(TWO_BOUNDARIES);
    expect(next.pathwayIndex).toBe(1);
  });

  it("JUMP_TO_PATHWAY jumps straight to the given pathway from Review", () => {
    const fromReview: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "review",
      boundaries: TWO_BOUNDARIES,
    };
    const next = wizardReducer(fromReview, { type: "JUMP_TO_PATHWAY", pathwayIndex: 1 });
    expect(next.step).toBe("pathway-conditions");
    expect(next.pathwayIndex).toBe(1);
  });

  it("JUMP_TO_PATHWAY jumps between pathways directly, skipping the ones between", () => {
    const state: WizardState = {
      ...INITIAL_WIZARD_STATE,
      step: "pathway-conditions",
      pathwayIndex: 0,
      boundaries: [boundary("a"), boundary("b"), boundary("c")],
    };
    const next = wizardReducer(state, { type: "JUMP_TO_PATHWAY", pathwayIndex: 2 });
    expect(next.step).toBe("pathway-conditions");
    expect(next.pathwayIndex).toBe(2);
  });

  it("JUMP_TO_PATHWAY is a no-op when boundaries are not set yet", () => {
    const state: WizardState = { ...INITIAL_WIZARD_STATE, step: "prerequisites" };
    expect(wizardReducer(state, { type: "JUMP_TO_PATHWAY", pathwayIndex: 0 })).toBe(state);
  });
});
