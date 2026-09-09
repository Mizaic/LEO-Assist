/**
 * Open on Decide, rewind phases, and sync letter marks with the fact tree.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 *
 * Atlas trace:
 *   DO: DO-7B63A6BE
 *   DI: DI-49BA8E04
 *   Risks: R-823853D7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7B63A6BE")
 */

import { useEffect, useRef, useState, type MutableRefObject } from "react";

import {
  applyPhaseClick,
  defaultOpenStepId,
  phaseForStepId,
  phaseSnapshotStepId,
  type ClinicalPhaseId,
  type PhaseSpan,
} from "./clinicalPhases";
import { buildFactTree, type FactLeaf, type FactTreeGroup } from "./factTree";
import { clinicalFactItems } from "./inspector/stageWorkItems";
import type { LabStageDetail, LabWorkPreview } from "./inspectorTypes";
import type { LetterMark } from "./letterHighlight";
import { firstChangedTerm, stageLetterHighlights } from "./letterHighlight";
import type { LetterMarkPick } from "./LetterPane";
import { assertionKey, semanticTagKey } from "./letterMarkStyle";

interface InspectorSlice {
  spans: Array<PhaseSpan & { work_preview?: LabWorkPreview }>;
  selectedStepId: string | null;
  setSelectedStepId: (id: string | null) => void;
  stageDetail: LabStageDetail | null;
}

export interface ClinicalReviewState {
  selectedPhase: ClinicalPhaseId;
  phaseReached: boolean;
  highlights: LetterMark[];
  tree: FactTreeGroup[];
  focusTerm: string;
  openAssertion: string | null;
  openTag: string | null;
  onSelectPhase: (phase: ClinicalPhaseId) => void;
  onMarkClick: (mark: LetterMarkPick) => void;
  onSelectLeaf: (leaf: FactLeaf, assertion: string, tag: string) => void;
  onToggleAssertion: (key: string) => void;
  onToggleTag: (assertion: string, tag: string) => void;
}

export function useClinicalReview(inspector: InspectorSlice): ClinicalReviewState {
  const [focusTerm, setFocusTerm] = useState("");
  const [openAssertion, setOpenAssertion] = useState<string | null>(null);
  const [openTag, setOpenTag] = useState<string | null>(null);
  const [selectedPhase, setSelectedPhase] = useState<ClinicalPhaseId>("decide");
  const userPicked = useRef(false);
  const lastPhase = useRef<ClinicalPhaseId | null>(null);
  const phaseStepId = phaseSnapshotStepId(inspector.spans, selectedPhase);
  const highlights = stageLetterHighlights(
    phaseStepId || inspector.selectedStepId,
    inspector.spans,
    inspector.stageDetail,
    focusTerm,
  );

  useOpenDecideStep(inspector, userPicked, setSelectedPhase);
  useRewindFocus(selectedPhase, lastPhase, highlights, setFocusTerm);

  return {
    selectedPhase,
    phaseReached: Boolean(phaseStepId),
    highlights,
    tree: treeFromInspector(inspector, phaseStepId),
    focusTerm,
    openAssertion,
    openTag,
    onSelectPhase: (phase) => {
      userPicked.current = true;
      const next = applyPhaseClick(inspector.spans, phase);
      setSelectedPhase(next.selectedPhase);
      if (next.selectedStepId) {
        inspector.setSelectedStepId(next.selectedStepId);
      }
    },
    onMarkClick: (mark) => {
      setFocusTerm(mark.term);
      setOpenAssertion(assertionKey(mark.assertion));
      setOpenTag(semanticTagKey(mark.semanticTag) || null);
    },
    onSelectLeaf: (leaf, assertion, tag) => {
      setFocusTerm(leaf.text);
      setOpenAssertion(assertion);
      setOpenTag(tag);
    },
    onToggleAssertion: (key) =>
      setOpenAssertion((cur) => (cur === key ? null : key)),
    onToggleTag: (assertion, tag) => {
      setOpenAssertion(assertion);
      setOpenTag((cur) => (cur === tag ? null : tag));
    },
  };
}

function treeFromInspector(
  inspector: InspectorSlice,
  phaseStepId: string | null,
): FactTreeGroup[] {
  if (!phaseStepId) return buildFactTree([]);
  const items = clinicalFactItems(
    inspector.stageDetail?.step_id === phaseStepId
      ? inspector.stageDetail?.output
      : null,
    inspector.stageDetail?.input,
    inspector.spans.find((span) => span.step_id === phaseStepId)
      ?.work_preview,
  );
  return buildFactTree(items);
}

function useOpenDecideStep(
  inspector: InspectorSlice,
  userPicked: MutableRefObject<boolean>,
  setSelectedPhase: (phase: ClinicalPhaseId) => void,
): void {
  useEffect(() => {
    if (userPicked.current) return;
    const openId = defaultOpenStepId(inspector.spans);
    if (!openId) return;
    const order = inspector.spans.map((span) => span.step_id);
    const phase = phaseForStepId(openId, order) || "read";
    setSelectedPhase(phase);
    if (inspector.selectedStepId !== openId) {
      inspector.setSelectedStepId(openId);
    }
  }, [inspector.spans, inspector.selectedStepId, inspector.setSelectedStepId, setSelectedPhase, userPicked]);
}

function useRewindFocus(
  selectedPhase: ClinicalPhaseId,
  lastPhase: MutableRefObject<ClinicalPhaseId | null>,
  highlights: LetterMark[],
  setFocusTerm: (term: string) => void,
): void {
  useEffect(() => {
    if (lastPhase.current && lastPhase.current !== selectedPhase) {
      const changed = firstChangedTerm(highlights);
      if (changed) setFocusTerm(changed);
    }
    lastPhase.current = selectedPhase;
  }, [selectedPhase, highlights, lastPhase, setFocusTerm]);
}
