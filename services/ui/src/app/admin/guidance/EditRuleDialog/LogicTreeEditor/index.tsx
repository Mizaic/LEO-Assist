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
 * Detects a pathway split -- an OR at depth 0 or 1 with 2+ children --
 * using the same isPathwaySplit() heuristic as the read-only Check &
 * approve view (RuleLogicView.tsx) and the Simple sentence canvas
 * (SentenceEditor/index.tsx), and renders it as PathwayList (vertical
 * stacked cards, one per pathway). When the OR sits one level down
 * inside a wrapping AND (e.g. a demographic prerequisite alongside the
 * pathway split, as in NG12 1.2.9), any sibling nodes render once
 * above the pathway list instead of disappearing into pathway card A.
 * Otherwise renders GroupBody directly (e.g. a single AND root for
 * simple rules).
 *
 * Replaces the 1,497-line monolithic LogicTreeEditor.tsx with a
 * directory of focused sub-components.
 */
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { findPathwaySplit } from "../pathwayDetection";
import type { EditableLogicNode, NodeUpdate } from "../types";
import GroupBody from "./GroupBody";
import NodeDispatcher from "./NodeDispatcher";
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
  const split = findPathwaySplit(root);
  return (
    // role="group" (not "tree"): a labelled container of ordinary
    // interactive controls (chips, selects, buttons), not an ARIA tree
    // widget with treeitem children and roving tabindex. "tree" has a
    // strict aria-required-children rule that axe flags as a critical
    // violation the moment real content is a direct child -- see the
    // matching fix + rationale in SentenceEditor/index.tsx.
    <Box
      role="group"
      aria-label="Editable rule logic"
      data-testid="logic-tree-editor"
    >
      {split ? (
        <Stack spacing={1.25}>
          {split.prerequisites.length > 0 && (
            <Box role="group" aria-label="Applies to every pathway below">
              <Typography
                variant="caption"
                sx={{
                  fontWeight: 700,
                  color: "text.secondary",
                  display: "block",
                  mb: 0.5,
                  textTransform: "uppercase",
                  letterSpacing: 0.4,
                  fontSize: "0.68rem",
                }}
              >
                Applies to every pathway below
              </Typography>
              <Stack direction="row" flexWrap="wrap" sx={{ rowGap: 0.5 }}>
                {split.prerequisites.map((node) => (
                  <NodeDispatcher
                    key={node.node_id}
                    node={node}
                    root={root}
                    depth={0}
                    selectedNodeId={selectedNodeId}
                    onSelect={onSelect}
                    onUpdate={onUpdate}
                    onRequestAdd={onRequestAdd}
                    onRequestCoach={onRequestCoach}
                    guidelineId={guidelineId}
                    currentRuleId={currentRuleId}
                  />
                ))}
              </Stack>
            </Box>
          )}
          <PathwayList
            root={split.orNode}
            selectedNodeId={selectedNodeId}
            onSelect={onSelect}
            onUpdate={onUpdate}
            onRequestAdd={onRequestAdd}
            onRequestCoach={onRequestCoach}
            guidelineId={guidelineId}
            currentRuleId={currentRuleId}
          />
        </Stack>
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
