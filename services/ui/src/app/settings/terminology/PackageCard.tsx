/**
 * PackageCard -- tone-accented status card for a single terminology package.
 *
 * Wave E: framer-motion hover lift, click-to-select for sync queue,
 * hover-reveal "Sync this package" ghost action.
 *
 * Design Controls: DI-340279C1, DO-CFA1ED55.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
"use client";

import { useState } from "react";
import { motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DownloadingIcon from "@mui/icons-material/Downloading";
import SyncIcon from "@mui/icons-material/Sync";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

export interface PackageStatus {
  label: string;
  local_version: string | null;
  trud_version: string | null;
  trud_date: string | null;
  trud_size_mb: number | null;
  up_to_date: boolean;
}

function packageTone(pkg: PackageStatus): "positive" | "warning" | "neutral" {
  if (pkg.up_to_date) return "positive";
  if (!pkg.local_version) return "neutral";
  return "warning";
}

function packageStatusLabel(pkg: PackageStatus): string {
  if (pkg.up_to_date) return "Up to date";
  if (!pkg.local_version) return "Not on disk";
  return "Update available";
}

interface Props {
  pkg: PackageStatus;
  selected: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function PackageCard({ pkg, selected, onToggle, disabled = false }: Props) {
  const [hovered, setHovered] = useState(false);
  const tone = packageTone(pkg);
  const accent =
    tone === "positive" ? "#16A34A" : tone === "warning" ? "#D97706" : "#94A3B8";
  const Icon =
    tone === "positive"
      ? CheckCircleOutlineIcon
      : tone === "warning"
        ? WarningAmberIcon
        : DownloadingIcon;

  return (
    <fm.div
      data-testid={`terminology-package-${pkg.label.toLowerCase().replace(/\s+/g, "-")}`}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.12 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={disabled ? undefined : onToggle}
      style={{
        position: "relative",
        background: "#FFFFFF",
        border: selected ? `2px solid #1E40AF` : "1px solid #E2E8F0",
        borderRadius: 12,
        padding: 18,
        flex: 1,
        minWidth: 0,
        minHeight: 168,
        display: "flex",
        flexDirection: "column",
        gap: 10,
        cursor: disabled ? "default" : "pointer",
        boxShadow: selected ? "0 0 0 3px rgba(30,64,175,0.15)" : undefined,
        transition: "border-color 120ms ease-out, box-shadow 120ms ease-out",
        outline: "none",
      }}
      tabIndex={disabled ? -1 : 0}
      role="checkbox"
      aria-checked={selected}
      aria-label={`${pkg.label} -- ${packageStatusLabel(pkg)}. Click to ${selected ? "deselect" : "select"} for sync.`}
      onKeyDown={(e) => {
        if (!disabled && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onToggle();
        }
      }}
    >
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 1,
          bgcolor: accent,
        }}
      />
      <Stack
        direction="row"
        alignItems="flex-start"
        justifyContent="space-between"
        spacing={1}
      >
        <Stack direction="row" spacing={1} alignItems="center">
          <Icon sx={{ color: accent, fontSize: 22 }} />
          <Typography sx={{ fontWeight: 600, fontSize: "1rem", lineHeight: 1.25 }}>
            {pkg.label}
          </Typography>
        </Stack>
        <Chip
          label={packageStatusLabel(pkg)}
          size="small"
          sx={{
            height: 22,
            fontSize: "0.7rem",
            bgcolor:
              tone === "positive" ? "#ECFDF5"
              : tone === "warning" ? "#FEF3C7"
              : "#F1F5F9",
            color:
              tone === "positive" ? "#047857"
              : tone === "warning" ? "#92400E"
              : "#475569",
            border: "1px solid",
            borderColor:
              tone === "positive" ? "#A7F3D0"
              : tone === "warning" ? "#FDE68A"
              : "#E2E8F0",
            flexShrink: 0,
          }}
        />
      </Stack>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          rowGap: 0.5,
          columnGap: 1,
          flex: 1,
        }}
      >
        <Typography variant="caption" color="text.secondary">On disk</Typography>
        <Typography variant="caption" sx={{ fontWeight: 500 }}>
          {pkg.local_version ?? <em style={{ opacity: 0.5 }}>not downloaded</em>}
        </Typography>
        <Typography variant="caption" color="text.secondary">TRUD latest</Typography>
        <Typography variant="caption" sx={{ fontWeight: 500 }}>
          {pkg.trud_version
            ? `${pkg.trud_version}${pkg.trud_date ? ` - ${pkg.trud_date}` : ""}`
            : "--"}
        </Typography>
        {pkg.trud_size_mb != null ? (
          <>
            <Typography variant="caption" color="text.secondary">Download</Typography>
            <Typography variant="caption" sx={{ fontWeight: 500 }}>
              {pkg.trud_size_mb} MB
            </Typography>
          </>
        ) : null}
      </Box>
      {/* Hover-reveal ghost action */}
      {hovered && !disabled ? (
        <Tooltip
          title={selected ? "Deselect this package from sync" : "Add this package to sync queue"}
          placement="top"
        >
          <Button
            size="small"
            variant="text"
            startIcon={<SyncIcon fontSize="small" />}
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            sx={{
              mt: "auto",
              color: selected ? "text.secondary" : "primary.main",
              fontSize: "0.75rem",
              textTransform: "none",
              alignSelf: "flex-start",
            }}
          >
            {selected ? "Remove from sync" : "Sync this package"}
          </Button>
        </Tooltip>
      ) : null}
    </fm.div>
  );
}
