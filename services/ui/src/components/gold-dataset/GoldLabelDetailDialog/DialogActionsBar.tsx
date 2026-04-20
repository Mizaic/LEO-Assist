/**
 * DialogActionsBar -- Wave E Phase 2a-iv
 *
 * Single-primary-action footer for the gold-label review dialog.
 *
 * Replaces the legacy 5-button stripe (Close, Delete, Skip,
 * Accept-all-and-mark, Mark-as-gold) which had two green buttons
 * competing for attention. The new design follows the
 * "one primary, one secondary, everything else hidden" rule:
 *
 *   - One primary: "Mark as gold". When suggestions are pending the
 *     label morphs to "Accept {n} + mark as gold" so the reviewer
 *     never has to choose between two green buttons.
 *   - One secondary: "Skip" (next candidate).
 *   - Destructive (Delete): hidden behind a kebab to keep the rest
 *     interaction calm. Only revealed when the reviewer actually
 *     wants it. Implements the standard progressive-disclosure
 *     pattern used elsewhere in Knowledge.
 *
 * "Close" was removed -- the X in the title strip is the natural
 * dismiss control.
 *
 * Atlas trace:
 *   DO: DO-1E9BCC70
 *   DI: DI-3035F221
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-1E9BCC70")
 */
"use client";

import { useState } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Tooltip from "@mui/material/Tooltip";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import VerifiedIcon from "@mui/icons-material/Verified";

interface DialogActionsBarProps {
  saving: boolean;
  markingGold: boolean;
  pendingSuggestionCount: number;
  canMarkGold: boolean;
  canDelete: boolean;
  canSkip: boolean;
  onMarkGold: () => void;
  onAcceptAllAndMark: () => void;
  onSkipNext: () => void;
  onRequestDelete: () => void;
}

export default function DialogActionsBar(props: DialogActionsBarProps) {
  const {
    saving,
    markingGold,
    pendingSuggestionCount,
    canMarkGold,
    canDelete,
    canSkip,
    onMarkGold,
    onAcceptAllAndMark,
    onSkipNext,
    onRequestDelete,
  } = props;
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const closeMenu = () => setAnchor(null);

  const morph = pendingSuggestionCount > 0;
  const primaryLabel = markingGold
    ? "Saving..."
    : morph
      ? `Accept ${pendingSuggestionCount} + mark as gold`
      : "Mark as gold";
  const handlePrimary = markingGold || saving
    ? undefined
    : morph
      ? onAcceptAllAndMark
      : onMarkGold;

  return (
    <Box
      data-testid="dialog-actions-bar"
      sx={{
        px: 2.25,
        py: 1.5,
        borderTop: "1px solid",
        borderColor: "divider",
        bgcolor: "background.default",
        display: "flex",
        alignItems: "center",
        gap: 1,
      }}
    >
      {canSkip && (
        <Button
          variant="text"
          size="small"
          onClick={onSkipNext}
          disabled={saving || markingGold}
          data-testid="dialog-skip-button"
          sx={{ color: "text.secondary", textTransform: "none" }}
        >
          Skip to next
        </Button>
      )}
      {canDelete && (
        <>
          <Tooltip title="More actions">
            <span>
              <IconButton
                size="small"
                disabled={saving || markingGold}
                aria-label="More actions"
                data-testid="dialog-more-actions"
                onClick={(event) => setAnchor(event.currentTarget)}
                sx={{ color: "text.secondary" }}
              >
                <MoreHorizIcon sx={{ fontSize: 18 }} />
              </IconButton>
            </span>
          </Tooltip>
          <Menu
            anchorEl={anchor}
            open={Boolean(anchor)}
            onClose={closeMenu}
            MenuListProps={{ dense: true }}
          >
            <MenuItem
              onClick={() => {
                closeMenu();
                onRequestDelete();
              }}
              data-testid="dialog-delete-menu-item"
              sx={{ color: "error.main" }}
            >
              <ListItemIcon>
                <DeleteOutlineIcon fontSize="small" color="error" />
              </ListItemIcon>
              <ListItemText>Delete this sentence</ListItemText>
            </MenuItem>
          </Menu>
        </>
      )}
      <Box sx={{ flex: 1 }} />
      {canMarkGold && (
        <Button
          variant="contained"
          color="success"
          size="small"
          startIcon={
            markingGold ? (
              <CircularProgress size={14} color="inherit" />
            ) : (
              <VerifiedIcon sx={{ fontSize: 18 }} />
            )
          }
          disabled={markingGold || saving || handlePrimary === undefined}
          onClick={handlePrimary}
          data-testid="dialog-primary-action"
          data-morph={morph ? "accept-and-mark" : "mark"}
          sx={{
            px: 2.25,
            fontWeight: 600,
            fontSize: "0.85rem",
            textTransform: "none",
            boxShadow: "0 1px 2px rgba(4, 120, 87, 0.18)",
            "&:hover": {
              boxShadow: "0 2px 6px rgba(4, 120, 87, 0.28)",
            },
          }}
        >
          {primaryLabel}
        </Button>
      )}
    </Box>
  );
}
