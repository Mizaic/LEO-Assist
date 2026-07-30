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
 * One proposed situation row in Step 2 (StepPathwaySplit) -- either a
 * plain lettered summary, or (while it's the active split target) its
 * own scoped word-selection editor. Split out of StepPathwaySplit.tsx
 * to keep that file under the repo's 500-LOC file-length limit; this
 * component has no state of its own, only the parent's.
 */
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import HighlightableRecommendationText, {
  type TextSelectionResult,
} from "../SentenceEditor/HighlightableRecommendationText";
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import { STEP_PATHWAY_SPLIT } from "./copy";

export default function PathwayBoundaryRow({
  boundary,
  letter,
  selectable,
  selected,
  isSplitTarget,
  onClick,
  onConfirmSplitSelection,
}: {
  boundary: PathwayTextBoundary;
  letter: string;
  selectable: boolean;
  selected: boolean;
  isSplitTarget: boolean;
  onClick: () => void;
  onConfirmSplitSelection: (selection: TextSelectionResult) => void;
}) {
  const nestedItems = boundary.structureChildren ?? [];
  // Once this row IS the active split target it hosts genuinely
  // interactive descendants of its own (word chunks, Confirm/Cancel)
  // -- nesting those inside a role="button" wrapper is both an ARIA
  // violation and, concretely, makes this row's own accessible name
  // swallow "Confirm selection" as a text-content substring, which
  // breaks any query for that button. Only wrap non-target rows.
  const isSelectableButton = selectable && !isSplitTarget;
  return (
    <Box
      data-testid={`pathway-boundary-row-${boundary.start}-${boundary.end}`}
      data-selected={selected || undefined}
      data-source={boundary.source}
      role={isSelectableButton ? "button" : undefined}
      tabIndex={isSelectableButton ? 0 : undefined}
      onClick={isSelectableButton ? onClick : undefined}
      onKeyDown={
        isSelectableButton
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      sx={{
        px: 1.25,
        py: nestedItems.length > 0 || isSplitTarget ? 1 : 0.75,
        borderRadius: 1.5,
        border: boundary.source === "structure" ? "1px solid" : "1px dashed",
        borderColor: selected ? "primary.main" : "divider",
        bgcolor: selected ? "primary.50" : "background.paper",
        cursor: isSelectableButton ? "pointer" : "default",
      }}
    >
      {isSplitTarget ? (
        <Box>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
            {STEP_PATHWAY_SPLIT.splitInstruction}
          </Typography>
          <HighlightableRecommendationText
            text={boundary.text}
            onConfirmSelection={onConfirmSplitSelection}
          />
        </Box>
      ) : (
        <Typography variant="body2" sx={{ lineHeight: 1.35 }}>
          <strong>({letter})</strong> {boundary.text}
        </Typography>
      )}
      {!isSplitTarget && nestedItems.length > 0 && (
        <Box component="ul" sx={{ mt: 0.5, mb: 0, pl: 2.5 }}>
          {nestedItems.map((child) => (
            <Box component="li" key={`${child.start}-${child.end}`} sx={{ py: 0.125 }}>
              <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.35 }}>
                {child.text}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
