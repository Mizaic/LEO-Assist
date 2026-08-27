/**
 * Badge shown on a form section that was pre-filled from a known taught form.
 *
 * Atlas trace: DI-5C9CA57B
 */
"use client";

import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import CloseIcon from "@mui/icons-material/Close";

import { type BorrowedFrom } from "./formSchemaDetector";

const BADGE_STYLE: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 2,
  background: "#9338ff",
  color: "#fff",
  fontSize: 11,
  padding: "2px 6px",
  borderRadius: 4,
  whiteSpace: "nowrap",
  flexShrink: 0,
};

const MAX_SERVICE_LEN = 30;

function shortLabel(service: string): string {
  if (service.length <= MAX_SERVICE_LEN) return service;
  return service.slice(0, MAX_SERVICE_LEN - 2) + "..";
}

export function BorrowedFromBadge({
  borrowedFrom,
  onDismiss,
}: {
  borrowedFrom: BorrowedFrom;
  onDismiss: () => void;
}) {
  const pct = Math.round(borrowedFrom.confidence * 100);
  const badgeText = `From ${shortLabel(borrowedFrom.service)} - ${pct}%`;
  const tooltipText =
    `Pre-filled from ${borrowedFrom.org} ${borrowedFrom.service}.` +
    " Review and save to confirm.";

  return (
    <Tooltip title={tooltipText} arrow>
      <span data-testid="borrowed-from-badge" style={BADGE_STYLE}>
        {badgeText}
        <IconButton
          size="small"
          aria-label="Dismiss borrowed section badge"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss();
          }}
          sx={{ color: "#fff", p: 0, ml: 0.25, width: 14, height: 14 }}
        >
          <CloseIcon sx={{ fontSize: 10 }} />
        </IconButton>
      </span>
    </Tooltip>
  );
}
