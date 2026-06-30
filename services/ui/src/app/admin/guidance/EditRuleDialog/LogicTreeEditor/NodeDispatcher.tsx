"use client";
/**
 * Routes an EditableLogicNode to the correct leaf or group component.
 *
 * Atlas trace: DO-D6CE2AA5 / DI-A3107424
 */
import type { NodeProps } from "./shared";
import ConceptPill from "./ConceptPill";
import DemographicRow from "./DemographicRow";
import ObservationRow from "./ObservationRow";
import RuleFiredRow from "./RuleFiredRow";
import GroupBody from "./GroupBody";

export default function NodeDispatcher(props: NodeProps) {
  const { node, root, depth, selectedNodeId, onSelect, onUpdate, onRequestAdd, onRequestCoach, guidelineId, currentRuleId } = props;

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
    <GroupBody
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
