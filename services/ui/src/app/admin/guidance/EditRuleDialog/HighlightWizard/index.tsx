/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * The highlight-to-build rule wizard: a one-question-at-a-time flow
 * anchored to the live NICE guideline sentence, unified for both
 * building from scratch and reviewing an AI-drafted tree. See the
 * plan's wireframes for the exact per-step layout.
 *
 * Step 1 (StepPrerequisites) -- "What must ALWAYS be true?"
 * Step 2 (StepPathwaySplit) -- "Does this split into situations?"
 * Step 3 (PathwayConditionsStage, repeated once per pathway) --
 *   "Within this situation, what must ALL be true?"
 * Review -- short confirmation that points at the right-column live
 *   preview (no second Simple editor). Power edits use Advanced.
 *
 * Every step mutates the SAME EditableLogicNode tree and NodeUpdate
 * contract every other surface (LogicTreeEditor, SentenceEditor) uses
 * -- this component only ever adds a thin, reversible layer of
 * "which question to ask next" on top, never a second data model.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type Dispatch,
} from "react";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ConfirmDialog from "@/components/ConfirmDialog";
import { findPathwaySplit } from "../pathwayDetection";
import {
  buildNoSplitBoundary,
  splitPathways,
  type PathwayTextBoundary,
  type RecommendationStructure,
} from "../SentenceEditor/pathwayTextSplit";
import {
  buildWeightedChecklistState,
  resolveCompanionPanels,
  type CompanionPanel,
} from "./weightedChecklist";
import type { EditableLogicNode, NodeUpdate } from "../types";
import PathwayConditionsStage, { resolvePathwayNodes } from "./PathwayConditionsStage";
import StepPathwaySplit from "./StepPathwaySplit";
import StepPrerequisites from "./StepPrerequisites";
import { SPLIT_COUNT_CHANGE_WARNING, WIZARD_CHROME } from "./copy";
import {
  findNodeById,
  materializePathways,
  readMaterializedPathways,
  splitWouldDiscardPathwayLeaves,
} from "./wizardMapping";
import { buildInitialWizardState } from "./initialWizardState";
import {
  INITIAL_WIZARD_STATE,
  wizardReducer,
  type WizardAction,
  type WizardState,
  type WizardStepKind,
} from "./wizardState";
import type { WizardNavTarget } from "../navSlots";

/** A one-shot "go show me this node" request from outside the wizard
 *  (see EditRuleDialog/index.tsx's issue banner). `requestId` only
 *  needs to change between clicks -- Date.now() is enough -- so
 *  clicking "Take me there" twice on the SAME node still re-triggers
 *  the jump (and the scroll+flash that follows it). */
export interface WizardJumpRequest {
  nodeId: string;
  requestId: number;
}

type JumpTarget =
  | { step: "prerequisites" }
  | { step: "pathway-conditions"; pathwayIndex: number };

/** Where does `nodeId` actually live -- Step 1's always-true list, or
 *  one of Step 3's confirmed pathways? Mirrors exactly the same
 *  pathway resolution `PathwayConditionsStage` itself uses
 *  (`resolvePathwayNodes`) so a jump can never land on the wrong
 *  situation. Returns null when the node isn't found at all (e.g. it
 *  was removed by an edit that raced the jump). */
function findJumpTarget(
  tree: EditableLogicNode,
  boundaries: PathwayTextBoundary[] | null,
  recommendationText: string | null | undefined,
  prerequisiteNodes: EditableLogicNode[],
  nodeId: string,
): JumpTarget | null {
  for (const node of prerequisiteNodes) {
    if (findNodeById(node, nodeId)) return { step: "prerequisites" };
  }
  if (!boundaries) return null;
  const pathwayNodes = resolvePathwayNodes(tree, boundaries, recommendationText);
  for (let i = 0; i < pathwayNodes.length; i++) {
    if (findNodeById(pathwayNodes[i], nodeId)) {
      return { step: "pathway-conditions", pathwayIndex: i };
    }
  }
  return null;
}

export interface HighlightWizardProps {
  tree: EditableLogicNode;
  recommendationText?: string | null;
  recommendationStructure?: RecommendationStructure | null;
  /** Sibling NICE panel boxes (e.g. weighted 7-point checklist). */
  companionPanels?: CompanionPanel[] | null;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (
    parentNodeId: string,
    anchor?: HTMLElement | null,
    initialQuery?: string,
    multiPick?: boolean,
  ) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  /**
   * Opens the add/remove/depth synonym editor for a CONCEPT leaf that
   * already has a matched code -- see `PathwayConditionsStage`'s doc
   * comment on the same prop. Used by both Step 1 (editing an
   * existing prerequisite) and Step 3 (editing an existing pathway
   * condition) row clicks.
   */
  onEditConcept: (nodeId: string) => void;
  guidelineId?: string;
  currentRuleId?: string;
  /** Reports the wizard's own current step so the host can, for
   *  example, pin the guideline quote in the side panel until the
   *  reviewer reaches Review -- the only step where "what this rule
   *  means" is actually built up enough to be worth previewing. */
  onStepChange?: (step: WizardStepKind) => void;
  /**
   * `auto` (default) opens Review when every pathway already has
   * leaves -- so reopening a saved rule does not force Step 1 again.
   * `fresh` always starts at prerequisites (tests / rebuild).
   */
  startMode?: "auto" | "fresh";
  /**
   * Reports the situations the quote panel should colour:
   *  - Step 2: proposed boundaries + null active index (colour-per-
   *    situation overview of what the text detector found)
   *  - Step 3: confirmed boundaries + the active pathway index
   *    (scoped capture view)
   *  - otherwise: `(null, null)` -- plain / tree-leaf highlighting
   */
  onActiveSituationChange?: (
    boundaries: PathwayTextBoundary[] | null,
    activePathwayIndex: number | null,
  ) => void;
  /** See `WizardJumpRequest`'s doc comment -- "jump to issue"
   *  navigation into whichever phase/pathway actually owns the
   *  problem node, driven from outside the wizard (the issue banner
   *  lives at the EditRuleDialog level, above both this component and
   *  the tree itself). */
  jumpRequest?: WizardJumpRequest | null;
  /**
   * IFU CoachTour: one-shot request to show a wizard phase so the
   * matching `data-tour` anchor exists before the bubble measures.
   */
  tourGotoRequest?: { requestId: number; phase: WizardStepKind } | null;
  /**
   * Flat stepper / footer: one-shot jump into a guided phase so the
   * editor has a single navigation surface (no nested Back control).
   */
  navGotoRequest?: { requestId: number; target: WizardNavTarget } | null;
}

function usePrerequisiteNodes(tree: EditableLogicNode): EditableLogicNode[] {
  return useMemo(() => {
    const split = findPathwaySplit(tree);
    if (split) return split.prerequisites;
    return tree.kind === "AND" ? tree.children ?? [] : [tree];
  }, [tree]);
}

/** Promotes CONFIRM_SPLIT to "ready immediately" only when every
 *  boundary already has a live pathway node -- otherwise the reducer
 *  parks in `materializing` until the effect below observes the
 *  tree mutation land. */
function useMaterializationEffect(
  tree: EditableLogicNode,
  state: WizardState,
  dispatch: Dispatch<WizardAction>,
) {
  useEffect(() => {
    if (!state.materializing || !state.boundaries) return;
    const nodes = readMaterializedPathways(tree, state.boundaries.length);
    if (nodes.length > 0) dispatch({ type: "PATHWAYS_READY" });
  }, [tree, state.materializing, state.boundaries, dispatch]);
}

/**
 * Consumes a `WizardJumpRequest` exactly once per `requestId` and
 * dispatches whichever JUMP_TO_* action gets the reviewer there.
 * Reads the latest tree/boundaries/prerequisites off refs rather than
 * listing them as effect deps -- the jump must fire ONLY when a new
 * request actually arrives, not on every tree edit the reviewer makes
 * while an old request object is still the current prop value.
 */
function useJumpRequest(
  jumpRequest: WizardJumpRequest | null | undefined,
  tree: EditableLogicNode,
  boundaries: PathwayTextBoundary[] | null,
  recommendationText: string | null | undefined,
  prerequisiteNodes: EditableLogicNode[],
  dispatch: Dispatch<WizardAction>,
): void {
  const latest = useRef({ tree, boundaries, recommendationText, prerequisiteNodes });
  latest.current = { tree, boundaries, recommendationText, prerequisiteNodes };

  useEffect(() => {
    if (!jumpRequest) return;
    const { tree: t, boundaries: b, recommendationText: r, prerequisiteNodes: p } = latest.current;
    const target = findJumpTarget(t, b, r, p, jumpRequest.nodeId);
    if (!target) return;
    if (target.step === "prerequisites") {
      dispatch({ type: "JUMP_TO_PREREQUISITES" });
    } else {
      dispatch({ type: "JUMP_TO_PATHWAY", pathwayIndex: target.pathwayIndex });
    }
    // Only `requestId` (via the `jumpRequest` object identity) should
    // re-trigger this -- see the doc comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpRequest]);
}

const JUMP_FLASH_MAX_ATTEMPTS = 30;

/**
 * Once `useJumpRequest` has switched to the right phase/pathway, the
 * jumped-to row still needs to actually be found and shown -- this
 * polls with requestAnimationFrame (materialization and the
 * subsequent re-render both take a frame or two) for the element
 * carrying `data-wizard-jump-target="true"` + a matching
 * `data-node-id`, scrolls it into view, and flashes it via the
 * `wizard-jump-flash` CSS animation (globals.css) so the reviewer's
 * eye lands on the right row instead of just the right screen.
 */
function useJumpScrollAndFlash(
  jumpRequest: WizardJumpRequest | null | undefined,
  containerRef: { current: HTMLElement | null },
  step: WizardStepKind,
  pathwayIndex: number,
): void {
  useEffect(() => {
    if (!jumpRequest) return;
    let attempts = 0;
    let rafId = 0;
    const tryFlash = () => {
      const el = containerRef.current?.querySelector<HTMLElement>(
        `[data-wizard-jump-target="true"][data-node-id="${jumpRequest.nodeId}"]`,
      );
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("wizard-jump-flash");
        el.addEventListener(
          "animationend",
          () => el.classList.remove("wizard-jump-flash"),
          { once: true },
        );
        return;
      }
      attempts += 1;
      if (attempts < JUMP_FLASH_MAX_ATTEMPTS) rafId = requestAnimationFrame(tryFlash);
    };
    rafId = requestAnimationFrame(tryFlash);
    return () => cancelAnimationFrame(rafId);
    // `step`/`pathwayIndex` are included so a jump that changes phase
    // re-polls once the new phase has actually mounted its rows.
  }, [jumpRequest, containerRef, step, pathwayIndex]);
}

export default function HighlightWizard({
  tree,
  recommendationText,
  recommendationStructure,
  companionPanels,
  onSelectNode,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
  onEditConcept,
  guidelineId,
  currentRuleId,
  onStepChange,
  startMode = "auto",
  onActiveSituationChange,
  jumpRequest,
  tourGotoRequest,
  navGotoRequest,
}: HighlightWizardProps) {
  const [state, dispatch] = useReducer(wizardReducer, undefined, () =>
    startMode === "fresh"
      ? INITIAL_WIZARD_STATE
      : buildInitialWizardState(tree, recommendationText, recommendationStructure),
  );
  const [proposedBoundaries, setProposedBoundaries] = useState<
    PathwayTextBoundary[] | null
  >(null);
  const prerequisiteNodes = usePrerequisiteNodes(tree);
  const containerRef = useRef<HTMLDivElement>(null);
  useMaterializationEffect(tree, state, dispatch);
  useJumpRequest(jumpRequest, tree, state.boundaries, recommendationText, prerequisiteNodes, dispatch);
  useJumpScrollAndFlash(jumpRequest, containerRef, state.step, state.pathwayIndex);

  useEffect(() => {
    if (!tourGotoRequest) return;
    const phase = tourGotoRequest.phase;
    const derived =
      state.boundaries?.length
        ? state.boundaries
        : proposedBoundaries?.length
          ? proposedBoundaries
          : splitPathways(recommendationText, recommendationStructure);
    if (phase === "prerequisites") {
      dispatch({ type: "TOUR_GOTO", step: "prerequisites" });
      return;
    }
    if (phase === "pathway-split") {
      dispatch({
        type: "TOUR_GOTO",
        step: "pathway-split",
        boundaries: derived,
      });
      return;
    }
    if (phase === "pathway-conditions") {
      if (!derived?.length) return;
      const nodes = materializePathways(tree, derived.length, onUpdate);
      dispatch({
        type: "CONFIRM_SPLIT",
        boundaries: derived,
        readyImmediately: nodes.length > 0,
      });
      return;
    }
    if (phase === "review") {
      dispatch({
        type: "TOUR_GOTO",
        step: "review",
        boundaries: derived,
      });
    }
    // Only fire when the tour asks for a new phase.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tourGotoRequest]);

  useEffect(() => {
    if (!navGotoRequest) return;
    const { target } = navGotoRequest;
    if (target.step === "prerequisites") {
      dispatch({ type: "JUMP_TO_PREREQUISITES" });
      return;
    }
    if (target.step === "pathway-split") {
      dispatch({
        type: "TOUR_GOTO",
        step: "pathway-split",
        boundaries: state.boundaries,
      });
      return;
    }
    if (target.step === "pathway-conditions") {
      dispatch({
        type: "JUMP_TO_PATHWAY",
        pathwayIndex: target.pathwayIndex,
      });
      return;
    }
    if (target.step === "review") {
      dispatch({ type: "GO_TO_REVIEW" });
    }
    // Only fire when the flat stepper asks for a new target.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navGotoRequest]);

  useEffect(() => {
    onStepChange?.(state.step);
  }, [state.step, onStepChange]);

  useEffect(() => {
    if (state.step === "pathway-conditions" && state.boundaries) {
      onActiveSituationChange?.(state.boundaries, state.pathwayIndex);
    } else if (state.step === "pathway-split" && proposedBoundaries) {
      // Null active index = Step 2 overview: paint every situation
      // its own colour so the detector's full wording is visible.
      onActiveSituationChange?.(proposedBoundaries, null);
    } else if (state.step === "review" && state.boundaries) {
      // Rehydrating straight into Review (reopening an already-built
      // rule -- see buildInitialWizardState) never passes through
      // "pathway-conditions", so this is the ONLY chance to report
      // the confirmed boundaries. Without it the host's
      // `situationCount` stays 0 forever, `navSlots.showSituations`
      // never turns on, and the flat stepper permanently mis-renders
      // "Always true" as current with Situations/Next locked even
      // though the wizard itself is already on Review.
      onActiveSituationChange?.(state.boundaries, null);
    } else {
      onActiveSituationChange?.(null, null);
    }
  }, [
    state.step,
    state.boundaries,
    state.pathwayIndex,
    proposedBoundaries,
    onActiveSituationChange,
  ]);

  const [pendingCountChange, setPendingCountChange] = useState<
    PathwayTextBoundary[] | null
  >(null);

  const applySplit = useCallback(
    (boundaries: PathwayTextBoundary[]) => {
      const nodes = materializePathways(tree, boundaries.length, onUpdate);
      dispatch({ type: "CONFIRM_SPLIT", boundaries, readyImmediately: nodes.length > 0 });
    },
    [tree, onUpdate],
  );

  const handleConfirmSplit = useCallback(
    (boundaries: PathwayTextBoundary[]) => {
      if (splitWouldDiscardPathwayLeaves(tree, boundaries.length)) {
        setPendingCountChange(boundaries);
        return;
      }
      applySplit(boundaries);
    },
    [tree, applySplit],
  );

  const handleNoSplit = useCallback(() => {
    const text = recommendationText ?? "";
    const panels = resolveCompanionPanels(guidelineId, text, companionPanels);
    const weighted = buildWeightedChecklistState(text, panels, false);
    dispatch({
      type: "CONFIRM_NO_SPLIT",
      boundary: buildNoSplitBoundary(text, recommendationStructure, weighted),
    });
  }, [recommendationText, recommendationStructure, companionPanels, guidelineId]);

  const handleBack = useCallback(() => dispatch({ type: "BACK" }), []);

  return (
    <Stack ref={containerRef} spacing={2} data-testid="highlight-wizard">
      {/* Isolated unit tests drive BACK without the dialog footer. */}
      {process.env.NODE_ENV === "test" && state.step !== "prerequisites" ? (
        <button
          type="button"
          data-testid="wizard-back"
          onClick={handleBack}
          style={{ position: "absolute", width: 1, height: 1, overflow: "hidden" }}
        >
          Previous question
        </button>
      ) : null}

      {state.step === "prerequisites" && (
        <StepPrerequisites
          recommendationText={recommendationText}
          prerequisites={prerequisiteNodes}
          onEdit={onSelectNode}
          onEditConcept={onEditConcept}
          onUpdate={onUpdate}
          onRemove={(nodeId) => onUpdate({ kind: "remove", nodeId })}
          onAddFromSelection={(selection, anchor) =>
            onRequestAdd(tree.node_id, anchor, selection.text, true)
          }
          onAddDemographic={(field) =>
            onUpdate({ kind: "add_demographic", parentNodeId: tree.node_id, field })
          }
          onAddObservation={() =>
            onUpdate({ kind: "add_observation", parentNodeId: tree.node_id })
          }
          onConfirmNoMore={() => dispatch({ type: "CONFIRM_PREREQUISITES" })}
        />
      )}

      {state.step === "pathway-split" &&
        (state.materializing ? (
          <Typography variant="body2" color="text.secondary" role="status">
            {WIZARD_CHROME.materializingStatus}
          </Typography>
        ) : (
          <StepPathwaySplit
            recommendationText={recommendationText}
            recommendationStructure={recommendationStructure}
            initialBoundaries={state.boundaries}
            onConfirm={handleConfirmSplit}
            onNoSplit={handleNoSplit}
            onProposedBoundariesChange={setProposedBoundaries}
          />
        ))}

      {pendingCountChange && (
        <ConfirmDialog
          title={SPLIT_COUNT_CHANGE_WARNING.title}
          body={SPLIT_COUNT_CHANGE_WARNING.body}
          confirmLabel={SPLIT_COUNT_CHANGE_WARNING.confirmLabel}
          cancelLabel={SPLIT_COUNT_CHANGE_WARNING.cancelLabel}
          variant="danger"
          onConfirm={() => {
            applySplit(pendingCountChange);
            setPendingCountChange(null);
          }}
          onCancel={() => setPendingCountChange(null)}
        />
      )}

      {state.step === "pathway-conditions" && state.boundaries && (
        <PathwayConditionsStage
          tree={tree}
          recommendationText={recommendationText}
          boundaries={state.boundaries}
          pathwayIndex={state.pathwayIndex}
          onExpandWeightedChecklist={() =>
            dispatch({
              type: "EXPAND_WEIGHTED_CHECKLIST",
              pathwayIndex: state.pathwayIndex,
            })
          }
          clusterGroupings={state.clusterGroupings}
          onSetClusterGrouping={(pathwayKey, grouping) =>
            dispatch({ type: "SET_CLUSTER_GROUPING", pathwayKey, grouping })
          }
          leadClusterGroupings={state.leadClusterGroupings}
          onSetLeadClusterGrouping={(pathwayKey, grouping) =>
            dispatch({ type: "SET_LEAD_CLUSTER_GROUPING", pathwayKey, grouping })
          }
          dismissedCopyAcrossOffers={state.dismissedCopyAcrossOffers}
          onDismissCopyAcrossOffer={(pathwayKey) =>
            dispatch({ type: "DISMISS_COPY_ACROSS_OFFER", pathwayKey })
          }
          onSelectNode={onSelectNode}
          onUpdate={onUpdate}
          onRequestAdd={onRequestAdd}
          onEditConcept={onEditConcept}
          onConfirmPathway={() => dispatch({ type: "CONFIRM_PATHWAY" })}
        />
      )}

      {state.step === "review" && (
        <Stack spacing={1} data-testid="wizard-review">
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            {WIZARD_CHROME.reviewTitle}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {WIZARD_CHROME.reviewHelper}
          </Typography>
        </Stack>
      )}
    </Stack>
  );
}
