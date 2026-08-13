/**
 * Facts and codes that arrived for a Validation Lab pipeline stage.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-257D6883
 *   VT: VT-825F42CC
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import type { LabWorkPreview } from "../inspectorTypes";
import { formatEvidenceTooltip } from "./stageWorkItems";

interface Props {
  preview: LabWorkPreview | null;
  loading: boolean;
  onMarkWrong?: (text: string) => void;
}

export function StageWorkPreview({ preview, loading, onMarkWrong }: Props) {
  if (loading) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Loading what this step found...
      </Typography>
    );
  }
  const items = preview?.items || [];
  const headline = preview?.headline || "";
  if (!headline && !items.length) return null;
  return (
    <Box
      data-testid="validation-lab-stage-work"
      sx={{
        mb: 1.5,
        p: 1.25,
        bgcolor: "#F0FDF4",
        border: "1px solid #BBF7D0",
        borderRadius: "8px",
      }}
    >
      {headline ? (
        <Typography
          variant="caption"
          sx={{
            display: "block",
            fontWeight: 700,
            color: "#166534",
            mb: items.length ? 0.75 : 0,
          }}
        >
          {headline}
        </Typography>
      ) : null}
      {items.length ? (
        <Stack direction="row" flexWrap="wrap" gap={0.75}>
          {items.map((item, index) => (
            <Tooltip
              key={`${item.text}-${index}`}
              title={
                <Typography
                  component="pre"
                  variant="caption"
                  sx={{ m: 0, whiteSpace: "pre-wrap", fontFamily: "inherit" }}
                >
                  {formatEvidenceTooltip(item)}
                </Typography>
              }
            >
              <Chip
                size="small"
                label={item.code ? `${item.text} -- ${item.code}` : item.text}
                onClick={onMarkWrong ? () => onMarkWrong(item.text) : undefined}
                sx={{ height: 22, fontSize: "0.7rem", maxWidth: "100%" }}
              />
            </Tooltip>
          ))}
        </Stack>
      ) : null}
    </Box>
  );
}
