"use client";
/**
 * Single CONCEPT leaf row: pill chip + synonym indicator +
 * vague-phrase badge + remove button.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { motion as fm } from "framer-motion";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import CloseIcon from "@mui/icons-material/Close";
import LightbulbIcon from "@mui/icons-material/Lightbulb";

import { useMotion } from "@leo/design-system";

import { friendlyTerm } from "../copy";
import { detectVaguePhrase } from "../vaguePhrases";
import SynonymChipEditor from "../SynonymChipEditor";
import type { EditableLogicNode, NodeUpdate } from "../types";
import { popVariants } from "../../motionPresets";

interface Props {
  node: EditableLogicNode;
  selectedNodeId: string | null;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}

export default function ConceptPill({
  node,
  selectedNodeId,
  onSelect,
  onUpdate,
  onRequestCoach,
}: Props) {
  const isSelected = selectedNodeId === node.node_id;
  const rawLabel = node.criterion?.preferred_term || node.criterion?.snomed_concept_id || "";
  const friendly = friendlyTerm(rawLabel);
  const label = friendly || "Click to pick a symptom, procedure, or situation";
  const vague = detectVaguePhrase(node.criterion?.preferred_term);
  const tooltip = node.criterion?.snomed_concept_id
    ? `${friendly} (code ${node.criterion.snomed_concept_id}). Click to swap.`
    : "No code yet. Click to search and pick one.";
  const { reducedMotion } = useMotion();

  return (
    <fm.div
      variants={popVariants(reducedMotion)}
      initial="initial"
      animate="animate"
      style={{ display: "inline-flex" }}
    >
      <Stack direction="row" spacing={0} alignItems="center" sx={{ display: "inline-flex" }}>
        <Tooltip title={tooltip} arrow>
          <Chip
            label={label}
            color={
              isSelected ? "primary"
                : vague.isVague ? "warning"
                : node.criterion?.snomed_concept_id ? "success"
                : "warning"
            }
            variant={isSelected ? "filled" : "outlined"}
            size="small"
            onClick={(e) => onSelect(node.node_id, e.currentTarget)}
            onDelete={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
            deleteIcon={<CloseIcon sx={{ fontSize: 13 }} />}
            sx={{
              height: 28,
              fontSize: "0.8rem",
              fontWeight: 500,
              borderRadius: 1.5,
              bgcolor: !isSelected && node.criterion?.snomed_concept_id
                ? "background.paper" : undefined,
            }}
            aria-label={`${label}. Click to swap, X to remove.`}
          />
        </Tooltip>
        {vague.isVague && onRequestCoach && (
          <Tooltip title={`"${label}" is vague. Click for specific suggestions.`} arrow>
            <IconButton
              size="small"
              aria-label={`Get specific suggestions for "${label}"`}
              onClick={(e) => onRequestCoach(node.node_id, e.currentTarget)}
              sx={{
                p: 0.25, ml: 0.25,
                color: "warning.dark", bgcolor: "warning.50",
                "&:hover": { bgcolor: "warning.100" },
              }}
            >
              <LightbulbIcon sx={{ fontSize: 13 }} />
            </IconButton>
          </Tooltip>
        )}
        {node.criterion?.snomed_concept_id && (
          <SynonymChipEditor node={node} onUpdate={onUpdate} />
        )}
      </Stack>
    </fm.div>
  );
}
