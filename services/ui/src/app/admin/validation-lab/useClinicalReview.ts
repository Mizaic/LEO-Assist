/**
 * Open on Decide, rewind phases, and sync letter marks with the fact tree.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 */

import { useEffect, useRef, useState, type MutableRefObject } from "react";

import {
  defaultOpenStepId,
  phaseForStepId,
  phaseSnapshotStepId,
  type ClinicalPhaseId,
  type PhaseSpan,
} from "./clinicalPhases";
import { buildFactTree, type FactLeaf, type FactTreeGroup } from "./factTree";
import { workPreviewFromStage } from "./inspector/stageWorkItems";
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
  const lastPhase = useRef<ClinicalPhaseId | null>(null);
  const stepOrder = inspector.spans.map((span) => span.step_id);
  const selectedPhase =
    phaseForStepId(inspector.selectedStepId || "", stepOrder) || "decide";
  const highlights = stageLetterHighlights(
    inspector.selectedStepId,
    inspector.spans,
    inspector.stageDetail,
    focusTerm,
  );

  useOpenDecideStep(inspector);
  useRewindFocus(selectedPhase, lastPhase, highlights, setFocusTerm);

  return {
    selectedPhase,
    highlights,
    tree: treeFromInspector(inspector),
    focusTerm,
    openAssertion,
    openTag,
    onSelectPhase: (phase) => selectPhase(inspector, phase),
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

function treeFromInspector(inspector: InspectorSlice): FactTreeGroup[] {
  const preview = workPreviewFromStage(
    inspector.stageDetail?.step_id === inspector.selectedStepId
      ? inspector.stageDetail?.output
      : null,
    inspector.stageDetail?.input,
    inspector.spans.find((span) => span.step_id === inspector.selectedStepId)
      ?.work_preview,
  );
  return buildFactTree(preview.items || []);
}

function selectPhase(inspector: InspectorSlice, phase: ClinicalPhaseId): void {
  const stepId = phaseSnapshotStepId(inspector.spans, phase);
  if (stepId) inspector.setSelectedStepId(stepId);
}

function useOpenDecideStep(inspector: InspectorSlice): void {
  useEffect(() => {
    const openId = defaultOpenStepId(inspector.spans);
    if (!openId) return;
    const known = inspector.spans.some(
      (span) => span.step_id === inspector.selectedStepId,
    );
    if (!inspector.selectedStepId || !known) {
      inspector.setSelectedStepId(openId);
    }
  }, [inspector.spans, inspector.selectedStepId, inspector.setSelectedStepId]);
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
