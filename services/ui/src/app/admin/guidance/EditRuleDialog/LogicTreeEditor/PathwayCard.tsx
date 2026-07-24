"use client";
/**
 * Full pathway card with:
 *   - Header: letter badge + editable name + operator label + delete
 *   - Section label (UPPERCASE) + thin divider
 *   - GroupBody with left-border color by kind
 *   - Inline PathwayPreview sentence
 *   - Optional _aiSuggested badge (cleared on first edit inside the card)
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { GROUP_KIND_LABELS, PATHWAY_NAME } from "../copy";
import { GROUP_KINDS, type EditableLogicNode, type LogicNodeKind, type NodeUpdate } from "../types";
import GroupBody from "./GroupBody";
import PathwayPreview from "./PathwayPreview";
import { KIND_COLORS } from "./shared";

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

/**
 * Exported so PathwaySentenceCard (Simple canvas) cycles through the
 * exact same per-pathway accent colors as this boxed card.
 */
export const CARD_ACCENTS = [
  "#2563EB", "#0891b2", "#7C3AED", "#059669", "#D97706",
] as const;

export default function PathwayCard({
  node, root, index,
  selectedNodeId, onSelect, onUpdate, onRequestAdd, onRequestCoach,
  guidelineId, currentRuleId,
}: Props) {
  const letter = String.fromCharCode(65 + index);
  const positional = `Pathway ${letter}`;
  const accent = CARD_ACCENTS[index % CARD_ACCENTS.length];
  const borderColor = KIND_COLORS[node.kind] ?? accent;

  // Guard: PathwayCard only handles group nodes. Leaf kinds (CONCEPT etc.)
  // should never reach here; if they do, render nothing so MUI Select
  // does not warn about an out-of-range value.
  if (!GROUP_KINDS.includes(node.kind as typeof GROUP_KINDS[number])) {
    return null;
  }

  const [aiSuggested, setAiSuggested] = useState(
    (node as EditableLogicNode & { _aiSuggested?: boolean })._aiSuggested === true,
  );

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
      {/* Top accent stripe */}
      <Box aria-hidden sx={{ height: 4, width: "100%", bgcolor: accent }} />

      <Box sx={{ p: 1.75 }}>
        {/* Card header row */}
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

        {/* Inline operator selector (replaces static section label) */}
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
          <Select
            size="small"
            value={node.kind}
            onChange={(e) =>
              wrappedOnUpdate({
                kind: "change_kind",
                nodeId: node.node_id,
                newKind: e.target.value as LogicNodeKind,
              })
            }
            inputProps={{ "aria-label": `Match mode for ${positional}` }}
            sx={{
              fontSize: "0.72rem", fontWeight: 700,
              "& .MuiSelect-select": { py: 0.3, pr: "26px !important", color: "text.secondary", fontWeight: 700, letterSpacing: 0.4 },
              "& .MuiOutlinedInput-notchedOutline": { borderColor: "divider" },
              "& .MuiSvgIcon-root": { fontSize: "1rem" },
            }}
          >
            {GROUP_KINDS.map((k) => (
              <MenuItem key={k} value={k} sx={{ fontSize: "0.78rem" }}>{GROUP_KIND_LABELS[k]}</MenuItem>
            ))}
          </Select>
        </Stack>
        <Divider
          sx={{ mb: 1, borderColor: borderColor, opacity: 0.4 }}
        />

        {/* Conditions */}
        <GroupBody
          node={node}
          root={root}
          depth={1}
          isTopLevel
          showKindSelect={false}
          selectedNodeId={selectedNodeId}
          onSelect={onSelect}
          onUpdate={wrappedOnUpdate}
          onRequestAdd={onRequestAdd}
          onRequestCoach={onRequestCoach}
          guidelineId={guidelineId}
          currentRuleId={currentRuleId}
        />

        {/* Inline sentence preview */}
        <PathwayPreview node={node} />
      </Box>
    </Box>
  );
}

// -- Editable pathway name ---------------------------------------------------

/**
 * Exported so PathwaySentenceCard (Simple canvas) reuses the exact same
 * debounced-draft/commit-on-blur name editor as this boxed card,
 * instead of duplicating the focus-preserving logic.
 */
export function PathwayNameInput({
  node,
  positional,
  onUpdate,
}: {
  node: EditableLogicNode;
  positional: string;
  onUpdate: (u: NodeUpdate) => void;
}) {
  const initial = typeof node.name === "string" ? node.name : "";
  const [draft, setDraft] = useState(initial);
  const inputId = `pathway-name-${node.node_id}`;

  useEffect(() => {
    if (
      typeof document !== "undefined" &&
      document.activeElement?.id === inputId
    ) return;
    setDraft(initial);
  }, [initial, inputId]);

  const commit = (next: string) => {
    const trimmed = next.trim();
    if (trimmed === (node.name ?? "").trim()) return;
    onUpdate({ kind: "set_name", nodeId: node.node_id, name: trimmed });
  };

  return (
    <TextField
      id={inputId}
      size="small"
      variant="standard"
      value={draft}
      onChange={(e) => setDraft(e.target.value.slice(0, PATHWAY_NAME.helperMaxChars))}
      onBlur={(e) => commit(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
        }
      }}
      placeholder={PATHWAY_NAME.inputPlaceholder}
      inputProps={{
        "aria-label": PATHWAY_NAME.inputAriaTemplate(positional),
        maxLength: PATHWAY_NAME.helperMaxChars,
      }}
      sx={{
        flex: 1,
        "& .MuiInput-input": { fontSize: "0.85rem", fontWeight: 600, py: 0.3 },
        "& .MuiInput-underline:before": {
          borderBottomStyle: "dashed", borderBottomColor: "divider",
        },
      }}
    />
  );
}
