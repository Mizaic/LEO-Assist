/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

/**
 * Presentational chrome for StepPathwayConditions: copy-across banner,
 * confirmed-pathway summary, and the AT_LEAST / AND grouping card.
 */
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { STEP_PATHWAY_CONDITIONS, WIZARD_TOOLTIPS } from "./copy";
import type { ClusterGrouping } from "./wizardMapping";

export function CopyAcrossBanner({
  offer,
  onAccept,
  onDismiss,
}: {
  offer: { sourceLetter: string; count: number };
  onAccept?: () => void;
  onDismiss?: () => void;
}) {
  return (
    <Alert
      severity="info"
      icon={<ContentCopyRoundedIcon fontSize="small" />}
      aria-label={STEP_PATHWAY_CONDITIONS.copyAcrossAriaLabel}
      action={
        <Stack direction="row" spacing={1} sx={{ pt: 0.25 }}>
          <Tooltip title={WIZARD_TOOLTIPS.copyAcross}>
            <Button
              size="small"
              variant="contained"
              aria-label={STEP_PATHWAY_CONDITIONS.copyAcrossAcceptLabel}
              onClick={onAccept}
            >
              {STEP_PATHWAY_CONDITIONS.copyAcrossAcceptLabel}
            </Button>
          </Tooltip>
          <Tooltip title={WIZARD_TOOLTIPS.dismissCopy}>
            <Button
              size="small"
              aria-label={STEP_PATHWAY_CONDITIONS.copyAcrossDismissLabel}
              onClick={onDismiss}
            >
              {STEP_PATHWAY_CONDITIONS.copyAcrossDismissLabel}
            </Button>
          </Tooltip>
        </Stack>
      }
    >
      {STEP_PATHWAY_CONDITIONS.copyAcrossOffer(offer.sourceLetter, offer.count)}
    </Alert>
  );
}

export function ConfirmedSoFar({
  summaries,
}: {
  summaries: Array<{ letter: string; summary: string }>;
}) {
  return (
    <Stack spacing={0.5}>
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          color: "text.secondary",
        }}
      >
        {STEP_PATHWAY_CONDITIONS.confirmedHeading}
      </Typography>
      {summaries.map((s) => (
        <Stack
          key={s.letter}
          direction="row"
          spacing={0.75}
          alignItems="center"
          data-testid={`confirmed-pathway-${s.letter}`}
        >
          <CheckCircleIcon fontSize="small" sx={{ color: "#16A34A" }} />
          <Typography variant="body2">
            {s.letter}: {s.summary}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}

export function ClusterGroupingChoice({
  prompt,
  grouping,
  onChoose,
  suggestedMin = 1,
  clusterMin = 1,
  termCount = 0,
  confirmedTerms = [],
  onSetClusterMin,
}: {
  prompt: string;
  grouping?: ClusterGrouping;
  onChoose?: (grouping: ClusterGrouping, min?: number) => void;
  suggestedMin?: number;
  clusterMin?: number;
  termCount?: number;
  confirmedTerms?: string[];
  onSetClusterMin?: (min: number) => void;
}) {
  const recommendN = suggestedMin > 1;
  const maxMin = Math.max(termCount, suggestedMin, 1);

  if (grouping) {
    const confirmedLabel =
      grouping === "AT_LEAST"
        ? STEP_PATHWAY_CONDITIONS.groupingConfirmedAtLeastN(
            clusterMin,
            confirmedTerms,
          )
        : confirmedTerms.length > 0
          ? STEP_PATHWAY_CONDITIONS.groupingConfirmedAllWithTerms(confirmedTerms)
          : STEP_PATHWAY_CONDITIONS.groupingConfirmedAll;
    return (
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        flexWrap="wrap"
        role="group"
        aria-label={prompt}
        sx={{ rowGap: 1 }}
      >
        <Typography variant="body2" color="text.secondary">
          {confirmedLabel}
        </Typography>
        {grouping === "AT_LEAST" && onSetClusterMin && maxMin > 1 && (
          <Stack direction="row" spacing={0.5} alignItems="center">
            <TextField
              size="small"
              type="number"
              value={clusterMin}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (!Number.isFinite(n)) return;
                onSetClusterMin(Math.max(1, Math.min(Math.floor(n), maxMin)));
              }}
              inputProps={{
                min: 1,
                max: maxMin,
                "aria-label": STEP_PATHWAY_CONDITIONS.clusterMinLabel,
              }}
              sx={{ width: 64 }}
            />
            <Typography variant="caption" color="text.secondary">
              {STEP_PATHWAY_CONDITIONS.clusterMinOf(maxMin)}
            </Typography>
          </Stack>
        )}
        <Tooltip title={WIZARD_TOOLTIPS.changeGrouping}>
          <Button
            size="small"
            onClick={() => {
              if (grouping === "AT_LEAST") onChoose?.("AND");
              else onChoose?.("AT_LEAST", suggestedMin);
            }}
          >
            {STEP_PATHWAY_CONDITIONS.changeLabel}
          </Button>
        </Tooltip>
      </Stack>
    );
  }
  const onlyOneText = STEP_PATHWAY_CONDITIONS.onlyOneLabel(!recommendN);
  const atLeastText = STEP_PATHWAY_CONDITIONS.atLeastNLabel(suggestedMin, true);
  return (
    <Box
      role="group"
      aria-label={prompt}
      sx={{ p: 1.5, borderRadius: 1.5, bgcolor: "grey.50" }}
    >
      <Typography variant="body2" sx={{ mb: 1 }}>
        {prompt}
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ rowGap: 1 }}>
        {recommendN && (
          <Tooltip title={WIZARD_TOOLTIPS.atLeastN}>
            <Button
              variant="contained"
              size="small"
              aria-label={atLeastText}
              onClick={() => onChoose?.("AT_LEAST", suggestedMin)}
            >
              {atLeastText}
            </Button>
          </Tooltip>
        )}
        <Tooltip title={WIZARD_TOOLTIPS.onlyOne}>
          <Button
            variant={recommendN ? "outlined" : "contained"}
            size="small"
            aria-label={onlyOneText}
            onClick={() => onChoose?.("AT_LEAST", 1)}
          >
            {onlyOneText}
          </Button>
        </Tooltip>
        <Tooltip title={WIZARD_TOOLTIPS.allMustMatch}>
          <Button
            variant="outlined"
            size="small"
            aria-label={STEP_PATHWAY_CONDITIONS.allMustMatchLabel}
            onClick={() => onChoose?.("AND")}
          >
            {STEP_PATHWAY_CONDITIONS.allMustMatchLabel}
          </Button>
        </Tooltip>
      </Stack>
    </Box>
  );
}
