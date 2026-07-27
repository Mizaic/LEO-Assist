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
  /** The TRAILING "any of the following" cluster's own grouping
   *  choice, keyed by `pathwayGroupingKey` (the pathway's own
   *  `pathway_key` -- see that helper's doc comment for why NOT the
   *  raw array index). */
  clusterGroupings: Record<string, ClusterGrouping>;
  /** A SEPARATE, marker-less lead-or cluster's own grouping choice
   *  (e.g. "nausea or vomiting" ahead of a trailing cluster), keyed
   *  the same way as `clusterGroupings` -- see
   *  `PathwayRows.leadCluster`'s doc comment. Kept as its own map
   *  rather than widening `clusterGroupings`'s value type so every
   *  existing single-cluster pathway's state shape is untouched. */
  leadClusterGroupings: Record<string, ClusterGrouping>;
  /** True right after Step 2 confirms 2+ boundaries but the tree
   *  mutation that creates the pathway groups has not landed in the
   *  `tree` prop yet -- see `materializePathways` in wizardMapping.ts. */
  materializing: boolean;
  /** Pathways whose "copy across" offer (see useCopyAcrossOffer) the
   *  reviewer has explicitly dismissed, keyed by `pathwayGroupingKey`.
   *  Lives in wizard state (not a local component useState) so
   *  re-rendering PathwayConditionsStage -- e.g. after an unrelated
   *  tree edit, or navigating Back then forward again to the same
   *  pathway -- does not resurface an offer the reviewer already said
   *  no to. */
  dismissedCopyAcrossOffers: Set<string>;
}

export const INITIAL_WIZARD_STATE: WizardState = {
  step: "prerequisites",
  pathwayIndex: 0,
  boundaries: null,
  clusterGroupings: {},
  leadClusterGroupings: {},
  materializing: false,
  dismissedCopyAcrossOffers: new Set(),
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
  | { type: "SET_CLUSTER_GROUPING"; pathwayKey: string; grouping: ClusterGrouping }
  | { type: "SET_LEAD_CLUSTER_GROUPING"; pathwayKey: string; grouping: ClusterGrouping }
  | { type: "DISMISS_COPY_ACROSS_OFFER"; pathwayKey: string }
  | { type: "CONFIRM_PATHWAY" }
  | { type: "GO_TO_REVIEW" }
  | { type: "BACK" }
  /** "Jump to issue" navigation -- see index.tsx's `findJumpTarget`.
   *  Only ever dispatched for a node the caller has already confirmed
   *  lives in prerequisites/this pathway; unlike every other action
   *  these do not follow the normal linear Confirm/Back sequence. */
  | { type: "JUMP_TO_PREREQUISITES" }
  | { type: "JUMP_TO_PATHWAY"; pathwayIndex: number };

function backOneStep(state: WizardState): WizardState {
  if (state.step === "pathway-split") {
    // Clearing `materializing` here (even if it was already false)
    // stops a race: CONFIRM_SPLIT set materializing=true and kicked
    // off a tree mutation, then the reviewer clicked Back to Step 1
    // BEFORE that mutation landed. Without this, the mutation's
    // eventual PATHWAYS_READY dispatch would still see
    // `state.materializing === true` and force step back to
    // "pathway-conditions", silently undoing the reviewer's Back
    // click -- see the wizard state-machine stability plan section.
    return { ...state, step: "prerequisites", materializing: false };
  }
  if (state.step === "pathway-conditions") {
    if (state.pathwayIndex > 0) {
      return { ...state, pathwayIndex: state.pathwayIndex - 1 };
    }
    // `boundaries` is DELIBERATELY kept (not nulled) -- StepPathwaySplit
    // reads it back as `initialBoundaries` so the reviewer's own prior
    // merge/split edits are still there instead of Step 2 silently
    // re-deriving a fresh guess from the raw text every time Back is
    // pressed. See the wizard confusion audit's merge/split section.
    return { ...state, step: "pathway-split" };
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
          [action.pathwayKey]: action.grouping,
        },
      };
    case "SET_LEAD_CLUSTER_GROUPING":
      return {
        ...state,
        leadClusterGroupings: {
          ...state.leadClusterGroupings,
          [action.pathwayKey]: action.grouping,
        },
      };
    case "DISMISS_COPY_ACROSS_OFFER":
      return {
        ...state,
        dismissedCopyAcrossOffers: new Set(state.dismissedCopyAcrossOffers).add(
          action.pathwayKey,
        ),
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
    case "JUMP_TO_PREREQUISITES":
      return { ...state, step: "prerequisites" };
    case "JUMP_TO_PATHWAY":
      // Only a node already confirmed to live inside a materialized
      // pathway ever reaches this action -- if boundaries somehow
      // isn't set yet, there is nothing to jump to, so no-op rather
      // than rendering Step 3 with a null boundary.
      return state.boundaries
        ? {
            ...state,
            step: "pathway-conditions",
            pathwayIndex: action.pathwayIndex,
            materializing: false,
          }
        : state;
    default:
      return state;
  }
}
