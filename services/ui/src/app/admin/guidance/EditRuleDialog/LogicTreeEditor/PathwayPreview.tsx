"use client";
/**
 * Inline plain-English sentence preview box.
 * Shows "Preview: ..." at the bottom of each pathway card.
 * Hidden when the sentence is empty or the tree has no leaves.
 *
 * Atlas trace: DO-D6CE2AA5 / DI-A3107424
 */
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import { treeToSentence } from "../treeToSentence";
import type { EditableLogicNode } from "../types";

interface Props {
  node: EditableLogicNode;
}

export default function PathwayPreview({ node }: Props) {
  const summary = treeToSentence(node);
  const sentence = summary.lead;
  if (!sentence || !summary.isWellShaped) return null;

  return (
    <Box
      aria-label="Plain-English preview of this pathway"
      sx={{
        mt: 1.25,
        px: 1.25,
        py: 0.75,
        borderRadius: 1,
        bgcolor: "grey.50",
        border: "1px solid",
        borderColor: "grey.200",
      }}
    >
      <Typography
        variant="caption"
        sx={{ color: "text.secondary", fontStyle: "italic", lineHeight: 1.5 }}
      >
        <strong>Preview:</strong> {sentence}
      </Typography>
    </Box>
  );
}
