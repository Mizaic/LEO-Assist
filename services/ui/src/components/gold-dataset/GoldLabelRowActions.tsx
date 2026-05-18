/**
 * GoldLabelRowActions -- the right-edge action cluster on a
 * verified-gold or synthetic-gold review row.
 *
 * Mirrors the candidate-side CandidateRowActions in shape but with the
 * verified-gold semantics:
 *   - QualityChip: a quiet quality-score pill (only goes loud for low
 *     scores so high-quality items stay calm).
 *   - GoldRowMenu: an overflow kebab holding "Reset to candidate"
 *     (destructive). Open is achieved by clicking the row body.
 *
 * Keeps the destructive Reset action behind progressive disclosure so
 * the common case (reading the verified text) dominates the visual
 * weight of the row.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Tooltip from "@mui/material/Tooltip";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import VerifiedIcon from "@mui/icons-material/Verified";

type Tone = "neutral" | "positive" | "warning" | "danger";

function toneFor(score: number | null): Tone {
  if (score === null) return "neutral";
  if (score >= 0.8) return "positive";
  if (score >= 0.5) return "warning";
  return "danger";
}

const TONE_STYLE: Record<
  Tone,
  { bg: string; fg: string; border: string }
> = {
  neutral: { bg: "#F1F5F9", fg: "#475569", border: "#E2E8F0" },
  positive: { bg: "#ECFDF5", fg: "#047857", border: "#A7F3D0" },
  warning: { bg: "#FEF3C7", fg: "#92400E", border: "#FDE68A" },
  danger: { bg: "#FEE2E2", fg: "#B91C1C", border: "#FECACA" },
};

export function QualityChip({
  score,
}: {
  score: number | null;
}) {
  const tone = toneFor(score);
  const style = TONE_STYLE[tone];
  const label = score !== null ? `${Math.round(score * 100)}%` : "verified";
  return (
    <Tooltip title={score !== null ? `Quality score: ${label}` : "Verified"}>
      <Box
        component="span"
        data-testid="gold-quality-chip"
        data-tone={tone}
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: "4px",
          height: 24,
          px: 0.85,
          borderRadius: 1,
          fontSize: "0.72rem",
          fontWeight: 600,
          color: style.fg,
          background: style.bg,
          border: `1px solid ${style.border}`,
          letterSpacing: 0.2,
        }}
      >
        <VerifiedIcon sx={{ fontSize: 14, color: style.fg }} />
        {label}
      </Box>
    </Tooltip>
  );
}

export function GoldRowMenu({
  labelId,
  resetting,
  disabled,
  onReset,
}: {
  labelId: string;
  resetting: boolean;
  disabled: boolean;
  onReset: () => void;
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
            data-testid={`gold-row-menu-${labelId}`}
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
            onReset();
          }}
          sx={{ color: "error.main" }}
        >
          <ListItemIcon>
            {resetting ? (
              <CircularProgress size={14} />
            ) : (
              <DeleteOutlineIcon fontSize="small" color="error" />
            )}
          </ListItemIcon>
          <ListItemText>Reset to candidate</ListItemText>
        </MenuItem>
      </Menu>
    </>
  );
}
