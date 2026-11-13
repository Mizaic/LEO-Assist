/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Lets a reviewer view or re-pick the guideline words (`source_row_text`)
 * linked to an existing CONCEPT or OBSERVATION leaf inside
 * ConceptSynonymDialog -- including disconnected words across a list
 * (e.g. "unexplained" + "vulval" + "bleeding." on NG12 1.5.17).
 */
import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { leafTextMatches } from "./HighlightWizard/leafTextMatch";
import HighlightableRecommendationText, {
  type HighlightSpan,
} from "./SentenceEditor/HighlightableRecommendationText";
import type { EditableLogicNode, NodeUpdate } from "./types";

interface Props {
  node: EditableLogicNode;
  recommendationText: string;
  onUpdate: (update: NodeUpdate) => void;
}

export default function SourceWordingPanel({
  node,
  recommendationText,
  onUpdate,
}: Props) {
  const [editing, setEditing] = useState(false);
  const currentText = node.source_row_text?.trim() || "";

  const currentHighlights: HighlightSpan[] = useMemo(
    () =>
      leafTextMatches(recommendationText, node).map((m) => ({
        start: m.start,
        end: m.end,
        kind: "confirmed" as const,
      })),
    [recommendationText, node],
  );

  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="caption" sx={{ fontWeight: 700, color: "text.primary" }}>
        Guideline wording
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mb: 0.75, lineHeight: 1.45 }}
      >
        Shows the exact words from the guideline linked to this condition.
      </Typography>

      {!editing ? (
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          flexWrap="wrap"
          sx={{ rowGap: 0.75 }}
        >
          <Box
            sx={{
              px: 1,
              py: 0.5,
              borderRadius: 1,
              bgcolor: "grey.50",
              border: "1px solid",
              borderColor: "divider",
              flex: "1 1 auto",
              minWidth: 0,
            }}
          >
            <Typography
              variant="body2"
              color={currentText ? "text.primary" : "text.secondary"}
              sx={{ fontStyle: currentText ? "normal" : "italic" }}
            >
              {currentText || "Not linked to custom wording (uses the code name)."}
            </Typography>
          </Box>
          <Button
            size="small"
            variant="outlined"
            onClick={() => setEditing(true)}
            sx={{ textTransform: "none", fontWeight: 600 }}
          >
            {currentText ? "Change wording" : "Link guideline words"}
          </Button>
          {currentText && (
            <Button
              size="small"
              variant="text"
              onClick={() =>
                onUpdate({
                  kind: "set_source_row_text",
                  nodeId: node.node_id,
                  sourceRowText: null,
                })
              }
              sx={{ textTransform: "none" }}
            >
              Reset to code name
            </Button>
          )}
        </Stack>
      ) : (
        <Box
          sx={{
            p: 1.25,
            borderRadius: 1.5,
            bgcolor: "grey.50",
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <HighlightableRecommendationText
            text={recommendationText}
            highlights={currentHighlights}
            onConfirmSelection={(selection) => {
              onUpdate({
                kind: "set_source_row_text",
                nodeId: node.node_id,
                sourceRowText: selection.text,
              });
              setEditing(false);
            }}
            onCancelSelection={() => setEditing(false)}
          />
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mt: 1 }}
          >
            <Typography variant="caption" color="text.secondary">
              Click words to turn them on or off -- even when they are separated by other words.
            </Typography>
            <Button
              size="small"
              variant="text"
              onClick={() => setEditing(false)}
              sx={{ textTransform: "none" }}
            >
              Close
            </Button>
          </Stack>
        </Box>
      )}
    </Box>
  );
}
