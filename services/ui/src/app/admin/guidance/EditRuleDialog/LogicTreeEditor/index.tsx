"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-D6CE2AA5
 *   DI: DI-A3107424
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
}

function isPathwayRoot(root: EditableLogicNode): boolean {
  return (
    root.kind === "OR" &&
    (root.children?.length ?? 0) >= 1
  );
}

export default function LogicTreeEditor({
  root,
  selectedNodeId,
  onSelect,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
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
        />
      )}
    </Box>
  );
}
