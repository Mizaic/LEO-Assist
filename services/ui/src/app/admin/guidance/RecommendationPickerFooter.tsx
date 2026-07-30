/**
 * Footer actions for RecommendationPickerDialog.
 *
 * Atlas: DI-EB716E68
 */
"use client";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import BuildIcon from "@mui/icons-material/Build";

export interface DialogFooterProps {
  aiCount: number;
  handCount: number;
  generating: boolean;
  creatingStub: boolean;
  generationDone: boolean;
  generationError: string | null;
  onGenerate: () => void;
  onBuildHand: () => void;
  onClose: () => void;
  attachMode?: boolean;
  attachCount?: number;
  onAttach?: () => void;
}

export function DialogFooter({
  aiCount,
  handCount,
  generating,
  creatingStub,
  generationDone,
  generationError,
  onGenerate,
  onBuildHand,
  onClose,
  attachMode = false,
  attachCount = 0,
  onAttach,
}: DialogFooterProps) {
  const totalSelected = attachMode ? attachCount : aiCount + handCount;
  return (
    <Box
      sx={{
        px: 2.5,
        py: 1.5,
        borderTop: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        position: "sticky",
        bottom: 0,
        zIndex: 1,
      }}
    >
      {generationError && (
        <Alert severity="error" sx={{ mb: 1, py: 0.3, fontSize: "0.78rem" }}>
          {generationError}
        </Alert>
      )}
      {generationDone && !attachMode && (
        <Alert severity="success" sx={{ mb: 1, py: 0.3, fontSize: "0.78rem" }}>
          AI drafts generated. Rules are in the review queue.
        </Alert>
      )}
      {generating && <LinearProgress sx={{ mb: 1, borderRadius: 1 }} />}
      <Stack
        direction="row"
        spacing={1.5}
        alignItems="center"
        justifyContent="space-between"
      >
        <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.8rem" }}>
          {totalSelected === 0
            ? "No recommendations selected"
            : `${totalSelected} selected`}
          {!attachMode && aiCount > 0 && ` · ${aiCount} AI draft`}
          {!attachMode && handCount > 0 && ` · ${handCount} by hand`}
        </Typography>

        <Stack direction="row" spacing={1}>
          <Button variant="outlined" size="small" onClick={onClose}>
            {generationDone ? "Close" : "Cancel"}
          </Button>
          {attachMode ? (
            <Button
              variant="contained"
              size="small"
              color="primary"
              onClick={onAttach}
              disabled={attachCount === 0}
            >
              Attach selected ({attachCount})
            </Button>
          ) : null}
          {!attachMode && handCount > 0 && (
            <Tooltip title="Open the rule editor for each selected recommendation so you can write the logic yourself.">
              <span>
                <Button
                  variant="outlined"
                  size="small"
                  color="primary"
                  startIcon={
                    creatingStub ? (
                      <CircularProgress size={13} color="inherit" />
                    ) : (
                      <BuildIcon sx={{ fontSize: 14 }} />
                    )
                  }
                  onClick={onBuildHand}
                  disabled={creatingStub || generating}
                >
                  Build by hand ({handCount})
                </Button>
              </span>
            </Tooltip>
          )}
          {!attachMode && aiCount > 0 && (
            <Tooltip title="Ask AI to draft rules for the selected recommendations. You will still check each one.">
              <span>
                <Button
                  variant="contained"
                  size="small"
                  color="primary"
                  startIcon={
                    generating ? (
                      <CircularProgress size={13} color="inherit" />
                    ) : (
                      <AutoAwesomeIcon sx={{ fontSize: 14 }} />
                    )
                  }
                  onClick={onGenerate}
                  disabled={generating || creatingStub}
                >
                  {generating ? "Generating..." : `Generate AI drafts (${aiCount})`}
                </Button>
              </span>
            </Tooltip>
          )}
        </Stack>
      </Stack>
    </Box>
  );
}
