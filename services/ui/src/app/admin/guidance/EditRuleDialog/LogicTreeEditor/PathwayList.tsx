"use client";
/**
 * Vertical stacked list of pathway cards.
 * One PathwayCard per child of the OR root node.
 * Full-width dashed "+ Add pathway" button at the bottom.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { AnimatePresence, motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import AddIcon from "@mui/icons-material/Add";

import { useMotion } from "@leo/design-system";

import type { EditableLogicNode, NodeUpdate } from "../types";
import PathwayCard from "./PathwayCard";
import { bounceInteraction, popVariants } from "../../motionPresets";

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

export default function PathwayList({
  root, selectedNodeId, onSelect, onUpdate, onRequestAdd, onRequestCoach,
  guidelineId, currentRuleId,
}: Props) {
  const children = root.children ?? [];
  const { reducedMotion } = useMotion();

  return (
    <Stack spacing={2}>
      <AnimatePresence initial={false}>
        {children.map((child, i) => (
          <fm.div
            key={child.node_id}
            layout
            variants={popVariants(reducedMotion)}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            <PathwayCard
              node={child}
              root={root}
              index={i}
              selectedNodeId={selectedNodeId}
              onSelect={onSelect}
              onUpdate={onUpdate}
              onRequestAdd={onRequestAdd}
              onRequestCoach={onRequestCoach}
              guidelineId={guidelineId}
              currentRuleId={currentRuleId}
            />
          </fm.div>
        ))}
      </AnimatePresence>

      <Box>
        <fm.div style={{ display: "block" }} {...bounceInteraction(reducedMotion)}>
          <Button
            fullWidth
            startIcon={<AddIcon />}
            onClick={() =>
              onUpdate({
                kind: "add_group",
                parentNodeId: root.node_id,
                groupKind: "AND",
              })
            }
            aria-label="Add another pathway"
            sx={{
              border: "1.5px dashed",
              borderColor: "divider",
              borderRadius: 2,
              color: "text.secondary",
              textTransform: "none",
              fontSize: "0.85rem",
              fontWeight: 500,
              py: 1,
              bgcolor: "transparent",
              "&:hover": {
                borderColor: "primary.main",
                color: "primary.main",
                bgcolor: "primary.50",
              },
            }}
          >
            Add pathway
          </Button>
        </fm.div>
      </Box>
    </Stack>
  );
}
