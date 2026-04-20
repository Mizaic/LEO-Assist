/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import GlossaryTerm from "@/components/ui/GlossaryTerm";
import PageIntro from "@/components/ui/PageIntro";
import { ENTITY_LABEL_OPTIONS } from "./codingReviewUtils";
import { CODING_REVIEW_INTRO } from "./codingReviewCopy";

interface Props {
  entityText: string;
  caseCount: number;
  labelOverride: string;
  rawLabel: string;
  savingLabel: boolean;
  labelMenuAnchor: HTMLElement | null;
  onOpenLabelMenu: (anchor: HTMLElement) => void;
  onCloseLabelMenu: () => void;
  onCorrectLabel: (newLabel: string) => void;
  confidentCount: number;
  warningCount: number;
  safetyCount: number;
  showPrefilledSummary: boolean;
  isAcceptAllBusy: boolean;
  isBatchBusy: boolean;
  loading: boolean;
  onAcceptAll: () => void;
  onBatchOpen: () => void;
}

export default function CodingReviewCasesModalTitle({
  entityText,
  caseCount,
  labelOverride,
  rawLabel,
  savingLabel,
  labelMenuAnchor,
  onOpenLabelMenu,
  onCloseLabelMenu,
  onCorrectLabel,
  confidentCount,
  warningCount,
  safetyCount,
  showPrefilledSummary,
  isAcceptAllBusy,
  isBatchBusy,
  loading,
  onAcceptAll,
  onBatchOpen,
}: Props) {
  return (
    <>
      <PageIntro
        screenId="coding-review-cases"
        why={CODING_REVIEW_INTRO.why}
        how={CODING_REVIEW_INTRO.how}
        what={CODING_REVIEW_INTRO.what}
        headingLevel={2}
      />
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        flexWrap="wrap"
        gap={1}
      >
        <Box>
          <Typography variant="h6" component="span">
            Cases for &apos;{entityText}&apos;
          </Typography>
          {caseCount > 0 && (
            <Chip
              label={`${caseCount} remaining`}
              size="small"
              sx={{ ml: 1.5 }}
            />
          )}
          {labelOverride && (
            <Tooltip title="The kind of thing this code is (e.g. finding, procedure). Click to correct if wrong.">
              <Chip
                label={savingLabel ? "Saving..." : labelOverride}
                size="small"
                color={labelOverride !== rawLabel ? "warning" : "default"}
                variant="outlined"
                onClick={(e) => onOpenLabelMenu(e.currentTarget)}
                sx={{ ml: 1, cursor: "pointer" }}
              />
            </Tooltip>
          )}
          <Menu
            open={Boolean(labelMenuAnchor)}
            anchorEl={labelMenuAnchor}
            onClose={onCloseLabelMenu}
          >
            <MenuItem disabled>
              <Typography variant="caption" color="text.secondary">
                Correct entity type
              </Typography>
            </MenuItem>
            {ENTITY_LABEL_OPTIONS.map((opt) => (
              <MenuItem
                key={opt}
                selected={opt === labelOverride}
                onClick={() => onCorrectLabel(opt)}
                dense
              >
                {opt}
              </MenuItem>
            ))}
          </Menu>
        </Box>
        <Stack direction="row" gap={1} flexWrap="wrap">
          {confidentCount > 0 && (
            <Button
              variant="contained"
              color="success"
              size="small"
              disabled={isAcceptAllBusy || isBatchBusy}
              onClick={onAcceptAll}
              startIcon={
                isAcceptAllBusy ? (
                  <CircularProgress
                    aria-label="Loading"
                    size={14}
                    color="inherit"
                  />
                ) : undefined
              }
            >
              {isAcceptAllBusy
                ? "Accepting..."
                : `Accept ${confidentCount} LEO suggestion${confidentCount !== 1 ? "s" : ""}`}
            </Button>
          )}
          <Button
            variant="outlined"
            size="small"
            disabled={isBatchBusy || isAcceptAllBusy || loading || caseCount === 0}
            onClick={onBatchOpen}
            startIcon={
              isBatchBusy ? (
                <CircularProgress
                  aria-label="Loading"
                  size={14}
                  color="inherit"
                />
              ) : undefined
            }
          >
            {isBatchBusy ? "Coding all..." : `Code all ${caseCount} at once`}
          </Button>
        </Stack>
      </Stack>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ mt: 0.5 }}
      >
        {showPrefilledSummary ? (
          <PrefilledSummary
            confidentCount={confidentCount}
            safetyCount={safetyCount}
            warningCount={warningCount}
          />
        ) : (
          <>
            Review each encounter below. Each case has an{" "}
            <GlossaryTerm termId="assertion">assertion</GlossaryTerm> chip
            showing how the record treats it. Code individually, or use
            &quot;Code all at once&quot; if the same code fits every case.
          </>
        )}
      </Typography>
    </>
  );
}

function PrefilledSummary({
  confidentCount,
  safetyCount,
  warningCount,
}: {
  confidentCount: number;
  safetyCount: number;
  warningCount: number;
}) {
  const nonSafety = warningCount - safetyCount;
  return (
    <>
      LEO has analysed each encounter. Accept individual suggestions, accept
      all {confidentCount} confident ones, or override any.{" "}
      {safetyCount > 0 && (
        <>
          {safetyCount} clinical safety alert{safetyCount !== 1 ? "s" : ""}{" "}
          detected (red glow below).{" "}
        </>
      )}
      {nonSafety > 0 && (
        <>
          {nonSafety} case{nonSafety !== 1 ? "s" : ""} flagged as not
          suitable for coding.
        </>
      )}
    </>
  );
}
