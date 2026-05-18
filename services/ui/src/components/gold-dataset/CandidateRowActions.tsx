/**
 * CandidateRowActions -- the right-edge action cluster on a
 * CandidateReviewList row: a primary "Mark gold" button plus an
 * overflow kebab menu holding Edit and Delete. Progressive disclosure
 * keeps the quiet common case (mark gold) dominant.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import { useState } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Tooltip from "@mui/material/Tooltip";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditNoteIcon from "@mui/icons-material/EditNote";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";

export function MarkGoldButton({
  candidateId,
  busy,
  disabled,
  onClick,
}: {
  candidateId: string;
  busy: boolean;
  disabled: boolean;
  onClick: (candidateId: string) => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled || busy}
      data-testid={`mark-gold-${candidateId}`}
      onClick={(event) => {
        event.stopPropagation();
        onClick(candidateId);
      }}
      style={{
        minWidth: 96,
        height: 32,
        padding: "0 14px",
        borderRadius: 6,
        border: "1px solid #047857",
        background: busy ? "#065F46" : "#047857",
        color: "#FFFFFF",
        fontSize: "0.78rem",
        fontWeight: 600,
        cursor: disabled || busy ? "not-allowed" : "pointer",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
      }}
    >
      {busy ? <CircularProgress size={12} sx={{ color: "#FFFFFF" }} /> : null}
      Mark gold
    </button>
  );
}

export function RowMenu({
  candidateId,
  disabled,
  deleting,
  onOpen,
  onDelete,
}: {
  candidateId: string;
  disabled: boolean;
  deleting: boolean;
  onOpen: (candidateId: string) => void;
  onDelete: (candidateId: string) => void;
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const close = () => setAnchor(null);
  return (
    <>
      <Tooltip title="More actions">
        <span>
          <IconButton
            size="small"
            disabled={disabled}
            aria-label="More actions"
            data-testid={`row-menu-${candidateId}`}
            onClick={(event) => {
              event.stopPropagation();
              setAnchor(event.currentTarget);
            }}
          >
            <MoreHorizIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </span>
      </Tooltip>
      <Menu
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={close}
        MenuListProps={{ dense: true }}
      >
        <MenuItem
          onClick={(event) => {
            event.stopPropagation();
            close();
            onOpen(candidateId);
          }}
        >
          <ListItemIcon>
            <EditNoteIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Edit codes and terms</ListItemText>
        </MenuItem>
        <MenuItem
          onClick={(event) => {
            event.stopPropagation();
            close();
            onDelete(candidateId);
          }}
          sx={{ color: "error.main" }}
        >
          <ListItemIcon>
            {deleting ? (
              <CircularProgress size={14} />
            ) : (
              <DeleteOutlineIcon fontSize="small" color="error" />
            )}
          </ListItemIcon>
          <ListItemText>Remove item</ListItemText>
        </MenuItem>
      </Menu>
    </>
  );
}
