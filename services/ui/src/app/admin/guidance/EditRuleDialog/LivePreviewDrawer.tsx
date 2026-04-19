"use client";

/**
 * Inline slide-in preview panel that lives INSIDE the editor dialog.
 *
 * When the reviewer clicks "See full preview" in the LivePreviewBanner,
 * this panel slides in from the right of the dialog's content area,
 * sharing space with the canvas. When closed, the canvas reclaims the
 * full width.
 *
 * Important: this is *not* a MUI Drawer / Modal. A page-level Drawer
 * would render in its own portal beside / behind the dialog backdrop,
 * which is visually confusing. By rendering inline we keep the
 * preview scoped to the dialog and avoid stacking two modal surfaces.
 *
 * Closes on:
 *   - X button in the header
 *   - ESC key (consumed locally so it doesn't bubble up and close the
 *     parent Dialog)
 *
 * Width: 380px on md+, full available width on xs (the dialog itself
 * already collapses to fullScreen on small viewports).
 *
 * Design Controls: UN-LEO-AI-094 (v2), DI-LEO-AI-512 (v2),
 *                  R-LEO-AI-509 (v2), VT-LEO-AI-511 (v2).
 */

import { useEffect } from "react";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import LivePreviewPane from "./LivePreviewPane";
import type { RuleSummary } from "./treeToSentence";
import type { LogicCriterion } from "./types";

interface Props {
  open: boolean;
  onClose: () => void;
  summary: RuleSummary;
  strength: string;
  action: LogicCriterion | null;
  showBeforeAfter: boolean;
  beforeSummary?: RuleSummary;
  beforeStrength?: string;
  beforeAction?: LogicCriterion | null;
}

const PANEL_WIDTH = 380;

export default function LivePreviewDrawer({
  open,
  onClose,
  summary,
  strength,
  action,
  showBeforeAfter,
  beforeSummary,
  beforeStrength,
  beforeAction,
}: Props) {
  // Local ESC handler so the user can dismiss the inline preview
  // without also dismissing the parent Dialog. We attach the listener
  // only while the panel is open.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  return (
    <Collapse
      in={open}
      orientation="horizontal"
      timeout={220}
      unmountOnExit
      sx={{
        flexShrink: 0,
        height: "100%",
        "& .MuiCollapse-wrapperInner": {
          width: { xs: "100%", md: PANEL_WIDTH },
          height: "100%",
        },
      }}
    >
      <Box
        role="region"
        aria-label={
          showBeforeAfter
            ? "Before and after preview panel"
            : "Live preview panel"
        }
        sx={{
          width: { xs: "100%", md: PANEL_WIDTH },
          height: "100%",
          display: "flex",
          flexDirection: "column",
          borderLeft: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
        }}
      >
        <Stack
          direction="row"
          alignItems="center"
          spacing={1}
          sx={{
            px: 2,
            py: 1.25,
            borderBottom: "1px solid",
            borderColor: "divider",
            bgcolor: "background.paper",
            position: "sticky",
            top: 0,
            zIndex: 1,
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography
              variant="subtitle2"
              sx={{ fontWeight: 700, lineHeight: 1.2 }}
            >
              {showBeforeAfter ? "Before and after" : "Live preview"}
            </Typography>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 0.25 }}
            >
              {showBeforeAfter
                ? "Compare the rule as it is now with your edits."
                : "Plain-English mirror of the rule you are editing."}
            </Typography>
          </Box>
          <Tooltip title="Close preview (ESC)">
            <IconButton
              onClick={onClose}
              size="small"
              aria-label="Close preview"
              sx={{ color: "text.secondary" }}
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
        <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "grey.50" }}>
          <LivePreviewPane
            summary={summary}
            strength={strength}
            action={action}
            showBeforeAfter={showBeforeAfter}
            beforeSummary={beforeSummary}
            beforeStrength={beforeStrength}
            beforeAction={beforeAction}
          />
        </Box>
      </Box>
    </Collapse>
  );
}
