"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Sentence-canvas equivalent of LogicTreeEditor/PathwayCard.tsx: same
 * card chrome (accent stripe, letter badge, editable name, remove
 * button, AI-draft badge that clears on first edit), but the body is a
 * top-level GroupSentence instead of a boxed GroupBody. Keeps the same
 * inline PathwayPreview sentence at the bottom, reused unchanged --
 * it is already prose, so it reinforces (rather than duplicates) what
 * the editable sentence above it already reads like.
 */
import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { GROUP_KINDS, type EditableLogicNode, type NodeUpdate } from "../types";
import { CARD_ACCENTS, PathwayNameInput } from "../LogicTreeEditor/PathwayCard";
import PathwayPreview from "../LogicTreeEditor/PathwayPreview";
import GroupSentence from "./GroupSentence";

interface Props {
  node: EditableLogicNode;
  root: EditableLogicNode;
  index: number;
  selectedNodeId: string | null;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  guidelineId?: string;
  currentRuleId?: string;
}

export default function PathwaySentenceCard({
  node, root, index,
  selectedNodeId, onSelect, onUpdate, onRequestAdd, onRequestCoach,
  guidelineId, currentRuleId,
}: Props) {
  const letter = String.fromCharCode(65 + index);
  const positional = `Pathway ${letter}`;
  const accent = CARD_ACCENTS[index % CARD_ACCENTS.length];

  const [aiSuggested, setAiSuggested] = useState(
    (node as EditableLogicNode & { _aiSuggested?: boolean })._aiSuggested === true,
  );

  // Guard: only handles group nodes, matching PathwayCard's own guard.
  // Leaf kinds (CONCEPT etc.) should never reach here.
  if (!GROUP_KINDS.includes(node.kind as typeof GROUP_KINDS[number])) {
    return null;
  }

  function wrappedOnUpdate(u: NodeUpdate) {
    setAiSuggested(false);
    onUpdate(u);
  }

  return (
    <Box
      data-testid={`pathway-card-${letter}`}
      sx={{
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        boxShadow: "0 1px 2px rgba(15,23,42,0.04), 0 4px 12px rgba(15,23,42,0.04)",
        overflow: "hidden",
        transition: "box-shadow 150ms ease, border-color 150ms ease",
        "&:hover": {
          boxShadow: "0 1px 2px rgba(15,23,42,0.06), 0 6px 18px rgba(15,23,42,0.08)",
        },
      }}
    >
      <Box aria-hidden sx={{ height: 4, width: "100%", bgcolor: accent }} />

      <Box sx={{ p: 1.75 }}>
        <Stack direction="row" alignItems="flex-start" spacing={0.75} sx={{ mb: 1 }}>
          <Box
            sx={{
              display: "inline-flex", alignItems: "center",
              px: 0.85, py: 0.3, borderRadius: 1,
              bgcolor: `${accent}22`, color: accent,
              fontSize: "0.68rem", fontWeight: 700, letterSpacing: 0.4,
              textTransform: "uppercase", flexShrink: 0, mt: 0.5,
            }}
          >
            {letter}
          </Box>
          <PathwayNameInput node={node} positional={positional} onUpdate={wrappedOnUpdate} />
          <Stack direction="row" spacing={0.25} alignItems="center">
            {aiSuggested && (
              <Chip
                icon={<AutoAwesomeIcon sx={{ fontSize: 12 }} />}
                label="AI draft - please check"
                size="small"
                color="info"
                variant="outlined"
                sx={{ height: 22, fontSize: "0.7rem", borderRadius: 1 }}
              />
            )}
            <Tooltip title={`Remove ${positional}`}>
              <IconButton
                size="small"
                aria-label={`Remove ${positional}`}
                onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
                sx={{ color: "text.secondary", "&:hover": { color: "error.main" } }}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>
        </Stack>

        <GroupSentence
          node={node}
          root={root}
          depth={1}
          isTopLevel
          selectedNodeId={selectedNodeId}
          onSelect={onSelect}
          onUpdate={wrappedOnUpdate}
          onRequestAdd={onRequestAdd}
          onRequestCoach={onRequestCoach}
          guidelineId={guidelineId}
          currentRuleId={currentRuleId}
        />

        <PathwayPreview node={node} />
      </Box>
    </Box>
  );
}
