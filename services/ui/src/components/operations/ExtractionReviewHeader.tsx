/**
 * Header for paused extraction review, including copyable identity chips.
 *
 * Atlas trace: DI-4A012A59
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import { QUALITY_SCORE_HINT, pauseReasonLabels } from "./extractionReviewCopy";
import { formatNhsNumber, formatUbrn } from "./extractionReviewIds";

interface Props {
  reason: string;
  qualityReasons: string[];
  score: number;
  loaded: boolean;
  nhsNumber: string;
  ubrn: string;
  onClose: () => void;
  onRemoveTask: () => void;
}

export default function ExtractionReviewHeader({
  reason,
  qualityReasons,
  score,
  loaded,
  nhsNumber,
  ubrn,
  onClose,
  onRemoveTask,
}: Props) {
  const scorePercent = Math.round(score * 100);
  const scoreColor = score > 0.7 ? "#16A34A" : score > 0.4 ? "#D97706" : "#DC2626";
  const reasons = pauseReasonLabels(reason, qualityReasons);
  const nhs = formatNhsNumber(nhsNumber);
  const referral = formatUbrn(ubrn);

  return (
    <Stack
      direction="row"
      alignItems="flex-start"
      sx={{
        px: 2,
        py: 1.5,
        borderBottom: "1px solid",
        borderColor: "divider",
        bgcolor: "#FAFAFA",
        flexShrink: 0,
      }}
    >
      <WarningAmberIcon sx={{ color: "#D97706", mr: 1.5, fontSize: 22, mt: 0.25 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="subtitle1" fontWeight={700}>
          Check paused extraction
        </Typography>
        {(nhs || referral) ? (
          <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 0.5 }}>
            {nhs ? <CopyChip label="NHS" value={nhs} /> : null}
            {referral ? <CopyChip label="UBRN" value={referral} /> : null}
          </Stack>
        ) : null}
        {reasons.length ? (
          <Stack direction="row" flexWrap="wrap" gap={0.75} sx={{ mt: 0.5 }}>
            {reasons.map((label) => (
              <Typography
                key={label}
                variant="caption"
                sx={{
                  px: 1,
                  py: 0.25,
                  color: "warning.dark",
                  bgcolor: "background.paper",
                  border: "1px solid",
                  borderColor: "warning.dark",
                  borderRadius: "4px",
                  fontWeight: 600,
                }}
              >
                {label}
              </Typography>
            ))}
          </Stack>
        ) : null}
      </Box>
      {loaded && scorePercent > 0 ? (
        <Tooltip title={QUALITY_SCORE_HINT}>
          <Box
            sx={{
              mr: 2,
              mt: 0.25,
              px: 1.5,
              py: 0.5,
              bgcolor: `${scoreColor}18`,
              border: `1px solid ${scoreColor}`,
              borderRadius: "6px",
              flexShrink: 0,
            }}
          >
            <Typography variant="caption" fontWeight={700} sx={{ color: scoreColor }}>
              Letter score {scorePercent}%
            </Typography>
          </Box>
        </Tooltip>
      ) : null}
      <Button
        onClick={onRemoveTask}
        size="small"
        color="inherit"
        sx={{ mr: 1, flexShrink: 0 }}
      >
        Remove this task
      </Button>
      <IconButton onClick={onClose} size="small" aria-label="Close review">
        <CloseIcon fontSize="small" />
      </IconButton>
    </Stack>
  );
}

function CopyChip({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Tooltip title={copied ? "Copied" : `Copy ${label}`}>
      <Chip
        size="small"
        clickable
        icon={<ContentCopyIcon sx={{ fontSize: "14px !important" }} />}
        label={`${label} ${value}`}
        onClick={() => void copy()}
        data-testid={`review-id-chip-${label.toLowerCase()}`}
        sx={{
          fontWeight: 700,
          bgcolor: "background.paper",
          border: "1px solid",
          borderColor: "primary.main",
          color: "primary.main",
        }}
      />
    </Tooltip>
  );
}
