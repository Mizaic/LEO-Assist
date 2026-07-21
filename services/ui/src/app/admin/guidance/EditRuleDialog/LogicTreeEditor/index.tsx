"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Consumer-grade rule logic tree editor.
 *
 * When the root node is OR with >= 1 child, renders PathwayList
 * (vertical stacked cards, one per pathway). Otherwise renders
 * GroupBody directly for non-pathway-split trees (e.g. a single AND
 * root for simple rules).
 *
 * Replaces the 1,497-line monolithic LogicTreeEditor.tsx with a
 * directory of focused sub-components.
 */
import Box from "@mui/material/Box";

import type { EditableLogicNode, NodeUpdate } from "../types";
import GroupBody from "./GroupBody";
import PathwayList from "./PathwayList";

interface Props {
  root: EditableLogicNode;
  selectedNodeId: string | null;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  guidelineId?: string;
  currentRuleId?: string;
}

function isPathwayRoot(root: EditableLogicNode): boolean {
  const children = root.children ?? [];
  return (
    root.kind === "OR" &&
    children.length >= 1 &&
    children.every(
      (c) =>
        c.kind === "AND" ||
        c.kind === "OR" ||
        c.kind === "NOT" ||
        c.kind === "AT_LEAST",
    )
  );
}

export default function LogicTreeEditor({
  root,
  selectedNodeId,
  onSelect,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
  guidelineId,
  currentRuleId,
}: Props) {
  return (
    <Box
      role="tree"
      aria-label="Editable rule logic"
      data-testid="logic-tree-editor"
    >
      {isPathwayRoot(root) ? (
        <PathwayList
          root={root}
          selectedNodeId={selectedNodeId}
          onSelect={onSelect}
          onUpdate={onUpdate}
          onRequestAdd={onRequestAdd}
          onRequestCoach={onRequestCoach}
          guidelineId={guidelineId}
          currentRuleId={currentRuleId}
        />
      ) : (
        <GroupBody
          node={root}
          root={root}
          depth={0}
          isTopLevel
          selectedNodeId={selectedNodeId}
          onSelect={onSelect}
          onUpdate={onUpdate}
          onRequestAdd={onRequestAdd}
          onRequestCoach={onRequestCoach}
          guidelineId={guidelineId}
          currentRuleId={currentRuleId}
        />
      )}
    </Box>
  );
}
