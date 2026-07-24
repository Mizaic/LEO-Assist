"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Routes an EditableLogicNode to the correct leaf or group component
 * for the Simple sentence canvas. Parallels
 * LogicTreeEditor/NodeDispatcher.tsx exactly: the four leaf kinds
 * reuse the exact same components as the Advanced tree (unmodified),
 * so a leaf edited in one view looks and behaves identically in the
 * other. Any group kind recurses into GroupSentence.
 */
import type { NodeProps } from "../LogicTreeEditor/shared";
import ConceptPill from "../LogicTreeEditor/ConceptPill";
import DemographicRow from "../LogicTreeEditor/DemographicRow";
import ObservationRow from "../LogicTreeEditor/ObservationRow";
import RuleFiredRow from "../LogicTreeEditor/RuleFiredRow";
import GroupSentence from "./GroupSentence";

export default function SentenceNodeDispatcher(props: NodeProps) {
  const {
    node,
    root,
    depth,
    selectedNodeId,
    onSelect,
    onUpdate,
    onRequestAdd,
    onRequestCoach,
    guidelineId,
    currentRuleId,
  } = props;

  if (node.kind === "CONCEPT") {
    return (
      <ConceptPill
        node={node}
        selectedNodeId={selectedNodeId}
        onSelect={onSelect}
        onUpdate={onUpdate}
        onRequestCoach={onRequestCoach}
      />
    );
  }

  if (node.kind === "DEMOGRAPHIC") {
    return <DemographicRow node={node} onUpdate={onUpdate} />;
  }

  if (node.kind === "OBSERVATION") {
    return <ObservationRow node={node} onUpdate={onUpdate} onSelect={onSelect} />;
  }

  if (node.kind === "RULE_FIRED") {
    return (
      <RuleFiredRow
        node={node}
        onUpdate={onUpdate}
        guidelineId={guidelineId}
        currentRuleId={currentRuleId}
      />
    );
  }

  return (
    <GroupSentence
      node={node}
      root={root}
      depth={depth}
      selectedNodeId={selectedNodeId}
      onSelect={onSelect}
      onUpdate={onUpdate}
      onRequestAdd={onRequestAdd}
      onRequestCoach={onRequestCoach}
      guidelineId={guidelineId}
      currentRuleId={currentRuleId}
    />
  );
}
