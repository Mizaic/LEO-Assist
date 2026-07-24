/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Pure phase state machine for the highlight-to-build wizard --
 * Step 1 (prerequisites) -> Step 2 (pathway split) -> Step 3 (per
 * pathway, repeated) -> Review. Kept free of React so the whole
 * navigation contract (what "Back", "Confirm", and a pending
 * materialization step do in every phase) is unit-testable without
 * mounting the orchestrator component.
 */
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import type { ClusterGrouping } from "./StepPathwayConditions";

export type WizardStepKind =
  | "prerequisites"
  | "pathway-split"
  | "pathway-conditions"
  | "review";

export interface WizardState {
  step: WizardStepKind;
  /** Meaningful only when `step === "pathway-conditions"`. */
  pathwayIndex: number;
  /** Set once Step 2 (or its "No, applies the same to everyone" exit)
   *  confirms a partition of the text -- null before that. */
  boundaries: PathwayTextBoundary[] | null;
  clusterGroupings: Record<number, ClusterGrouping>;
  /** True right after Step 2 confirms 2+ boundaries but the tree
   *  mutation that creates the pathway groups has not landed in the
   *  `tree` prop yet -- see `materializePathways` in wizardMapping.ts. */
  materializing: boolean;
}

export const INITIAL_WIZARD_STATE: WizardState = {
  step: "prerequisites",
  pathwayIndex: 0,
  boundaries: null,
  clusterGroupings: {},
  materializing: false,
};

export type WizardAction =
  | { type: "CONFIRM_PREREQUISITES" }
  | {
      type: "CONFIRM_SPLIT";
      boundaries: PathwayTextBoundary[];
      /** True when the tree already had a materialized pathway for
       *  every boundary, so Step 3 can start immediately. */
      readyImmediately: boolean;
    }
  | { type: "CONFIRM_NO_SPLIT"; boundary: PathwayTextBoundary }
  | { type: "PATHWAYS_READY" }
  | { type: "SET_CLUSTER_GROUPING"; pathwayIndex: number; grouping: ClusterGrouping }
  | { type: "CONFIRM_PATHWAY" }
  | { type: "GO_TO_REVIEW" }
  | { type: "BACK" };

function backOneStep(state: WizardState): WizardState {
  if (state.step === "pathway-split") {
    return { ...state, step: "prerequisites" };
  }
  if (state.step === "pathway-conditions") {
    if (state.pathwayIndex > 0) {
      return { ...state, pathwayIndex: state.pathwayIndex - 1 };
    }
    return { ...state, step: "pathway-split", boundaries: null };
  }
  if (state.step === "review") {
    const count = state.boundaries?.length ?? 0;
    return count > 0
      ? { ...state, step: "pathway-conditions", pathwayIndex: count - 1 }
      : { ...state, step: "pathway-split" };
  }
  // "prerequisites" is the first step -- nothing before it to go back to.
  return state;
}

export function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "CONFIRM_PREREQUISITES":
      return { ...state, step: "pathway-split" };
    case "CONFIRM_SPLIT":
      return action.readyImmediately
        ? {
            ...state,
            step: "pathway-conditions",
            pathwayIndex: 0,
            boundaries: action.boundaries,
            materializing: false,
          }
        : { ...state, boundaries: action.boundaries, materializing: true };
    case "CONFIRM_NO_SPLIT":
      return {
        ...state,
        step: "pathway-conditions",
        pathwayIndex: 0,
        boundaries: [action.boundary],
        materializing: false,
      };
    case "PATHWAYS_READY":
      return state.materializing
        ? { ...state, step: "pathway-conditions", pathwayIndex: 0, materializing: false }
        : state;
    case "SET_CLUSTER_GROUPING":
      return {
        ...state,
        clusterGroupings: {
          ...state.clusterGroupings,
          [action.pathwayIndex]: action.grouping,
        },
      };
    case "CONFIRM_PATHWAY": {
      const count = state.boundaries?.length ?? 0;
      return state.pathwayIndex + 1 < count
        ? { ...state, pathwayIndex: state.pathwayIndex + 1 }
        : { ...state, step: "review" };
    }
    case "GO_TO_REVIEW":
      return { ...state, step: "review" };
    case "BACK":
      return backOneStep(state);
    default:
      return state;
  }
}
