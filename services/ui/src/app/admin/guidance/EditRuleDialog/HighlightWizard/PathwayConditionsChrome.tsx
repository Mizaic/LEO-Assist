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
 * confirmed-pathway summary, and the AND / OR / AT_LEAST grouping card.
 */
import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import type { EditableLogicNode } from "../types";
import { STEP_PATHWAY_CONDITIONS, WIZARD_TOOLTIPS } from "./copy";
import { leafDisplayTerm, type ClusterGrouping } from "./wizardMapping";

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

/**
 * THIS pathway's own already-captured non-demographic leaves, shown as
 * plain reviewable/removable rows -- see `pathwayConfirmedLeaves`'s doc
 * comment for why this exists (tree-rehydrated situations have no
 * guideline quote to derive `ListRecommendationView` rows from, so
 * without this a saved CONCEPT/OBSERVATION leaf is invisible in Step 3
 * even though the Review step's plain-English summary shows it fine).
 * Deliberately its own component rather than reusing `ListRecommendationView`
 * -- there is no guideline text offset to key rows by here, only node
 * identity, and no "unresolved" state is possible (every leaf here is
 * already a real tree node with a code).
 */
export function ConfirmedPathwayConditions({
  leaves,
  onEditLeaf,
  onRemoveLeaf,
}: {
  leaves: EditableLogicNode[];
  onEditLeaf: (node: EditableLogicNode) => void;
  onRemoveLeaf?: (node: EditableLogicNode) => void;
}) {
  if (leaves.length === 0) return null;
  return (
    <Stack spacing={0.75} data-testid="pathway-confirmed-conditions">
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          color: "text.secondary",
        }}
      >
        {STEP_PATHWAY_CONDITIONS.confirmedConditionsHeading}
      </Typography>
      {leaves.map((node) => {
        const text = leafDisplayTerm(node);
        return (
          <Stack
            key={node.node_id}
            direction="row"
            alignItems="center"
            spacing={0.75}
            data-testid={`pathway-confirmed-condition-${node.node_id}`}
            sx={{
              p: 1,
              borderRadius: 1,
              border: "1px solid",
              borderColor: "divider",
            }}
          >
            <CheckCircleIcon fontSize="small" sx={{ color: "#16A34A" }} />
            <Box
              component="button"
              type="button"
              onClick={() => onEditLeaf(node)}
              sx={{
                flexGrow: 1,
                textAlign: "left",
                background: "none",
                border: "none",
                cursor: "pointer",
                p: 0,
                font: "inherit",
                color: "inherit",
              }}
            >
              <Typography variant="body2">{text}</Typography>
            </Box>
            {onRemoveLeaf && (
              <Tooltip title={WIZARD_TOOLTIPS.removeConfirmedCondition}>
                <IconButton
                  size="small"
                  onClick={() => onRemoveLeaf(node)}
                  aria-label={STEP_PATHWAY_CONDITIONS.removeConditionAriaLabel(text)}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
          </Stack>
        );
      })}
    </Stack>
  );
}

function confirmedGroupingLabel(
  grouping: ClusterGrouping,
  clusterMin: number,
  confirmedTerms: string[],
): string {
  if (grouping === "OR") {
    return confirmedTerms.length > 0
      ? STEP_PATHWAY_CONDITIONS.groupingConfirmedOnlyOneWithTerms(confirmedTerms)
      : STEP_PATHWAY_CONDITIONS.groupingConfirmedOnlyOne;
  }
  if (grouping === "AT_LEAST") {
    return STEP_PATHWAY_CONDITIONS.groupingConfirmedAtLeastN(
      clusterMin,
      confirmedTerms,
    );
  }
  return confirmedTerms.length > 0
    ? STEP_PATHWAY_CONDITIONS.groupingConfirmedAllWithTerms(confirmedTerms)
    : STEP_PATHWAY_CONDITIONS.groupingConfirmedAll;
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
  const [editing, setEditing] = useState(false);
  const recommendN = suggestedMin > 1;
  const maxMin = Math.max(termCount, suggestedMin, 1);
  const showChoices = !grouping || editing;

  if (!showChoices && grouping) {
    const confirmedLabel = confirmedGroupingLabel(
      grouping,
      clusterMin,
      confirmedTerms,
    );
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
          <Button size="small" onClick={() => setEditing(true)}>
            {STEP_PATHWAY_CONDITIONS.changeLabel}
          </Button>
        </Tooltip>
      </Stack>
    );
  }

  function pick(next: ClusterGrouping, min?: number) {
    setEditing(false);
    if (min === undefined) onChoose?.(next);
    else onChoose?.(next, min);
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
              onClick={() => pick("AT_LEAST", suggestedMin)}
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
            onClick={() => pick("OR")}
          >
            {onlyOneText}
          </Button>
        </Tooltip>
        <Tooltip title={WIZARD_TOOLTIPS.allMustMatch}>
          <Button
            variant="outlined"
            size="small"
            aria-label={STEP_PATHWAY_CONDITIONS.allMustMatchLabel}
            onClick={() => pick("AND")}
          >
            {STEP_PATHWAY_CONDITIONS.allMustMatchLabel}
          </Button>
        </Tooltip>
      </Stack>
    </Box>
  );
}
