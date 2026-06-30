"use client";
/**
 * Vertical stacked list of pathway cards.
 * One PathwayCard per child of the OR root node.
 * Full-width dashed "+ Add pathway" button at the bottom.
 *
 * Atlas trace: DO-D6CE2AA5 / DI-A3107424
 */
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import AddIcon from "@mui/icons-material/Add";

import type { EditableLogicNode, NodeUpdate } from "../types";
import PathwayCard from "./PathwayCard";

interface Props {
  root: EditableLogicNode;
  selectedNodeId: string | null;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}

export default function PathwayList({
  root, selectedNodeId, onSelect, onUpdate, onRequestAdd, onRequestCoach,
}: Props) {
  const children = root.children ?? [];

  return (
    <Stack spacing={2}>
      {children.map((child, i) => (
        <PathwayCard
          key={child.node_id}
          node={child}
          root={root}
          index={i}
          selectedNodeId={selectedNodeId}
          onSelect={onSelect}
          onUpdate={onUpdate}
          onRequestAdd={onRequestAdd}
          onRequestCoach={onRequestCoach}
        />
      ))}

      <Box>
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
      </Box>
    </Stack>
  );
}
