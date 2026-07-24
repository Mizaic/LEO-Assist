"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Sentence-style ("Simple") rule logic canvas -- a fill-in-the-blank
 * prose alternative to LogicTreeEditor's boxed/indented tree, driven
 * by the exact same EditableLogicNode tree and NodeUpdate mutations.
 *
 * Detects a pathway split using the same findPathwaySplit() heuristic
 * as LogicTreeEditor/index.tsx and renders PathwaySentenceList (one
 * lettered card per pathway, prerequisites shown once above the
 * list); otherwise renders a single top-level GroupSentence, mirroring
 * the Advanced view's split-vs-single-group branching exactly so
 * switching views never changes what a reviewer sees.
 */
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { findPathwaySplit } from "../pathwayDetection";
import type { EditableLogicNode, NodeUpdate } from "../types";
import GroupSentence from "./GroupSentence";
import PathwaySentenceList from "./PathwaySentenceList";
import SentenceNodeDispatcher from "./SentenceNodeDispatcher";

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

export default function SentenceEditor({
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
    // role="group" (not "tree"): this is a labelled container of ordinary
    // interactive controls (chips, selects, buttons), not an ARIA tree
    // widget with treeitem children and roving tabindex. The ARIA "tree"
    // role has a strict aria-required-children rule that fails axe's
    // critical checks the moment real content (buttons, comboboxes) is a
    // direct child, so "group" is both the correct semantic and the one
    // that keeps the axe-core WCAG 2.1 AA pass clean once the canvas has
    // conditions in it (see LogicTreeEditor/index.tsx, which shares the
    // same fix for the Advanced view).
    <Box
      role="group"
      aria-label="Editable rule logic (plain-English sentence view)"
      data-testid="sentence-editor"
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
                  <SentenceNodeDispatcher
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
          <PathwaySentenceList
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
        <GroupSentence
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
