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
 * Step 2 manual situation builder: lets a reviewer define two or more
 * situations from a single-sentence recommendation by picking each
 * situation's words (contiguous or non-contiguous) directly from the
 * full guideline text.
 */
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import HighlightableRecommendationText, {
  type TextSelectionResult,
} from "../SentenceEditor/HighlightableRecommendationText";
import type { PathwayTextBoundary } from "../SentenceEditor/pathwayTextSplit";
import { STEP_PATHWAY_SPLIT, WIZARD_TOOLTIPS } from "./copy";
import { pathwayLetter } from "./pathwayBoundaryEdits";

export interface ManualSituationBuilderProps {
  recommendationText: string;
  boundaries: PathwayTextBoundary[];
  onAddSelection: (selection: TextSelectionResult) => void;
  onRemoveAt: (index: number) => void;
  onLooksRight: () => void;
  onCancel: () => void;
}

export default function ManualSituationBuilder({
  recommendationText,
  boundaries,
  onAddSelection,
  onRemoveAt,
  onLooksRight,
  onCancel,
}: ManualSituationBuilderProps) {
  const nextLetter = pathwayLetter(boundaries.length);
  const canContinue = boundaries.length >= 2;

  return (
    <Stack spacing={1.5} data-tour="er-04-situations">
      {boundaries.length > 0 && (
        <Stack spacing={0.75}>
          {boundaries.map((boundary, index) => {
            const letter = pathwayLetter(index);
            return (
              <Stack
                key={`${letter}-${boundary.start}-${boundary.end}-${boundary.text}`}
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                spacing={1}
                data-testid={`pathway-boundary-row-${boundary.start}-${boundary.end}`}
                sx={{
                  px: 1.25,
                  py: 0.75,
                  borderRadius: 1.5,
                  border: "1px dashed",
                  borderColor: "divider",
                  bgcolor: "background.paper",
                }}
              >
                <Typography variant="body2" sx={{ lineHeight: 1.35 }}>
                  <strong>({letter})</strong> <span>{boundary.text}</span>
                </Typography>
                <Tooltip title={WIZARD_TOOLTIPS.removeSituation}>
                  <Button
                    size="small"
                    variant="text"
                    aria-label={STEP_PATHWAY_SPLIT.removeSituationAriaLabel(letter)}
                    onClick={() => onRemoveAt(index)}
                  >
                    Remove
                  </Button>
                </Tooltip>
              </Stack>
            );
          })}
        </Stack>
      )}

      <Box
        sx={{
          px: 1.25,
          py: 1,
          borderRadius: 1.5,
          border: "1px dashed",
          borderColor: "primary.main",
          bgcolor: "background.paper",
        }}
      >
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
          {STEP_PATHWAY_SPLIT.manualBuildInstruction(nextLetter)}
        </Typography>
        <HighlightableRecommendationText
          text={recommendationText}
          onConfirmSelection={onAddSelection}
        />
      </Box>

      {!canContinue && boundaries.length > 0 && (
        <Typography variant="caption" color="text.secondary" role="status">
          {STEP_PATHWAY_SPLIT.manualBuildNeedTwoHint}
        </Typography>
      )}

      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ rowGap: 1 }}>
        {canContinue && (
          <Tooltip title={WIZARD_TOOLTIPS.looksRight}>
            <Button variant="contained" size="small" onClick={onLooksRight}>
              {STEP_PATHWAY_SPLIT.looksRightLabel}
            </Button>
          </Tooltip>
        )}
        <Tooltip title={WIZARD_TOOLTIPS.cancelMergeSplit}>
          <Button variant="text" size="small" onClick={onCancel}>
            {STEP_PATHWAY_SPLIT.cancelLabel}
          </Button>
        </Tooltip>
      </Stack>
    </Stack>
  );
}
