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

import { useState, type CSSProperties, type KeyboardEvent } from "react";
import { motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DownloadingIcon from "@mui/icons-material/Downloading";
import SyncIcon from "@mui/icons-material/Sync";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { springOrInstant, springs, tapScale, useMotion } from "@leo/design-system";
import { color, elevation, typography } from "@leo/design-system/tokens";

export interface PackageStatus {
  label: string;
  local_version: string | null;
  trud_version: string | null;
  trud_date: string | null;
  trud_size_mb: number | null;
  up_to_date: boolean;
}

type Tone = "positive" | "warning" | "neutral";

function packageTone(pkg: PackageStatus): Tone {
  if (pkg.up_to_date) return "positive";
  if (!pkg.local_version) return "neutral";
  return "warning";
}

function packageStatusLabel(pkg: PackageStatus): string {
  if (pkg.up_to_date) return "Up to date";
  if (!pkg.local_version) return "Not on disk";
  return "Update available";
}

function toneAccent(tone: Tone): string {
  if (tone === "positive") return color.status.success;
  if (tone === "warning") return color.status.warning;
  return color.text.disabled;
}

interface Props {
  pkg: PackageStatus;
  selected: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function PackageCard({ pkg, selected, onToggle, disabled = false }: Props) {
  const { reducedMotion } = useMotion();
  const [hovered, setHovered] = useState(false);
  const tone = packageTone(pkg);
  const accent = toneAccent(tone);
  const enter = springOrInstant(reducedMotion, springs.ui);

  return (
    <fm.div
      data-testid={`terminology-package-${pkg.label.toLowerCase().replace(/\s+/g, "-")}`}
      whileTap={tapScale(reducedMotion)}
      transition={enter}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={disabled ? undefined : onToggle}
      style={cardStyle(selected, disabled)}
      tabIndex={disabled ? -1 : 0}
      role="checkbox"
      aria-checked={selected}
      aria-label={`${pkg.label} -- ${packageStatusLabel(pkg)}. Click to ${selected ? "deselect" : "select"} for sync.`}
      onKeyDown={(e) => onCardKey(e, disabled, onToggle)}
    >
      <AccentStrip accent={accent} />
      <PackageHeader pkg={pkg} tone={tone} accent={accent} />
      <PackageMeta pkg={pkg} />
      <HoverSync hovered={hovered} disabled={disabled} selected={selected} onToggle={onToggle} />
    </fm.div>
  );
}

function onCardKey(e: KeyboardEvent, disabled: boolean, onToggle: () => void) {
  if (disabled || (e.key !== "Enter" && e.key !== " ")) return;
  e.preventDefault();
  onToggle();
}

function AccentStrip({ accent }: { accent: string }) {
  return (
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
  );
}

function PackageHeader({
  pkg,
  tone,
  accent,
}: {
  pkg: PackageStatus;
  tone: Tone;
  accent: string;
}) {
  const Icon =
    tone === "positive"
      ? CheckCircleOutlineIcon
      : tone === "warning"
        ? WarningAmberIcon
        : DownloadingIcon;
  return (
    <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Icon sx={{ color: accent, fontSize: 22 }} />
        <Typography
          sx={{
            fontFamily: typography.fontFamily.heading,
            fontWeight: 700,
            fontSize: "1rem",
            lineHeight: 1.25,
            letterSpacing: typography.letterSpacing.display,
            color: color.text.primary,
          }}
        >
          {pkg.label}
        </Typography>
      </Stack>
      <StatusChip tone={tone} label={packageStatusLabel(pkg)} />
    </Stack>
  );
}

function StatusChip({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span
      style={{
        height: 22,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: "22px",
        padding: "0 8px",
        borderRadius: 999,
        flexShrink: 0,
        background: color.surface.alt,
        color: toneAccent(tone),
        border: "1px solid " + color.surface.divider,
      }}
    >
      {label}
    </span>
  );
}

function PackageMeta({ pkg }: { pkg: PackageStatus }) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "auto 1fr",
        rowGap: 0.5,
        columnGap: 1,
        flex: 1,
      }}
    >
      <MetaRow label="On disk" value={pkg.local_version ?? "not downloaded"} muted={!pkg.local_version} />
      <MetaRow
        label="TRUD latest"
        value={
          pkg.trud_version
            ? `${pkg.trud_version}${pkg.trud_date ? ` - ${pkg.trud_date}` : ""}`
            : "--"
        }
      />
      {pkg.trud_size_mb != null ? (
        <MetaRow label="Download" value={`${pkg.trud_size_mb} MB`} />
      ) : null}
    </Box>
  );
}

function MetaRow({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <>
      <Typography variant="caption" sx={{ color: color.text.secondary }}>
        {label}
      </Typography>
      <Typography
        variant="caption"
        sx={{
          fontWeight: 500,
          color: muted ? color.text.caption : color.text.primary,
          fontStyle: muted ? "italic" : "normal",
        }}
      >
        {value}
      </Typography>
    </>
  );
}

function HoverSync({
  hovered,
  disabled,
  selected,
  onToggle,
}: {
  hovered: boolean;
  disabled: boolean;
  selected: boolean;
  onToggle: () => void;
}) {
  if (!hovered || disabled) return null;
  return (
    <Tooltip
      title={selected ? "Deselect this package from sync" : "Add this package to sync queue"}
      placement="top"
    >
      <Button
        size="small"
        variant="text"
        startIcon={<SyncIcon fontSize="small" />}
        onClick={(e) => {
          e.stopPropagation();
          onToggle();
        }}
        sx={{
          mt: "auto",
          color: selected ? color.text.secondary : color.brand.primary,
          fontSize: "0.75rem",
          textTransform: "none",
          alignSelf: "flex-start",
        }}
      >
        {selected ? "Remove from sync" : "Sync this package"}
      </Button>
    </Tooltip>
  );
}

function cardStyle(selected: boolean, disabled: boolean): CSSProperties {
  return {
    position: "relative",
    background: color.surface.raised,
    border: selected
      ? `2px solid ${color.brand.primary}`
      : `1px solid ${color.surface.divider}`,
    borderRadius: 12,
    padding: 18,
    flex: 1,
    minWidth: 0,
    minHeight: 168,
    display: "flex",
    flexDirection: "column",
    gap: 10,
    cursor: disabled ? "default" : "pointer",
    boxShadow: selected
      ? `${elevation.card}, 0 0 0 3px ${color.focus.ringAlpha}`
      : elevation.card,
    outline: "none",
    fontFamily: typography.fontFamily.body,
  };
}
