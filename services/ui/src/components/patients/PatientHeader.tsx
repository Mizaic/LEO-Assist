/**
 * PatientHeader -- identity chrome for the EPR record.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import type { ReactNode } from "react";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { motion as fm } from "framer-motion";
import {
  color,
  frostStyle,
  radius,
  spacing,
  springOrInstant,
  springs,
  tapScale,
  typography,
  useMotion,
  useReducedTransparency,
} from "@leo/design-system";
import type { PatientDetail } from "@/lib/patientEprApi";
import {
  ageFromBirthDate,
  formatBornDate,
  formatNhsNumber,
  genderLabel,
  initials,
} from "./patientIdentity";

interface Props {
  detail: PatientDetail | null;
  loading?: boolean;
  onBack?: () => void;
  backLabel?: string;
  onOpenAlerts?: () => void;
  children?: ReactNode;
}

function metaLine(detail: PatientDetail): string {
  const bits = [
    [genderLabel(detail.gender), ageFromBirthDate(detail.birth_date)]
      .filter(Boolean)
      .join(", "),
    formatBornDate(detail.birth_date),
    detail.practice_name ?? "",
  ].filter(Boolean);
  return bits.join("  --  ");
}

function QuietButton({
  onClick,
  ariaLabel,
  children,
}: {
  onClick: () => void;
  ariaLabel: string;
  children: ReactNode;
}) {
  const { reducedMotion } = useMotion();
  return (
    <fm.button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      whileTap={tapScale(reducedMotion)}
      transition={springOrInstant(reducedMotion, springs.press)}
      data-chrome="press"
      style={{
        appearance: "none",
        border: "none",
        background: "transparent",
        color: color.brand.primary,
        fontFamily: typography.fontFamily.body,
        fontSize: 13,
        fontWeight: 600,
        padding: "6px 8px",
        margin: "0 0 0 -8px",
        borderRadius: radius.sm,
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        minHeight: 32,
      }}
    >
      {children}
    </fm.button>
  );
}

function AlertCta({
  count,
  onOpenAlerts,
}: {
  count: number;
  onOpenAlerts: () => void;
}) {
  const { reducedMotion } = useMotion();
  const label = `Review ${count} alert${count !== 1 ? "s" : ""}`;
  return (
    <fm.button
      type="button"
      onClick={onOpenAlerts}
      aria-label={label}
      data-testid="epr-review-alerts"
      data-chrome="press"
      whileTap={tapScale(reducedMotion)}
      transition={springOrInstant(reducedMotion, springs.press)}
      style={{
        appearance: "none",
        border: "none",
        background: color.status.warning,
        color: color.brand.onBrand,
        fontFamily: typography.fontFamily.body,
        fontSize: 13,
        fontWeight: 700,
        padding: "8px 14px",
        borderRadius: radius.pill,
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        minHeight: 36,
        flexShrink: 0,
      }}
    >
      <WarningAmberIcon sx={{ fontSize: 16 }} />
      {label}
    </fm.button>
  );
}

function HeaderSkeleton() {
  return (
    <Stack direction="row" spacing={2} alignItems="center" sx={{ py: 0.5 }}>
      <Skeleton variant="circular" width={48} height={48} />
      <Box sx={{ flex: 1 }}>
        <Skeleton width={220} height={24} />
        <Skeleton width={320} height={16} sx={{ mt: 0.5 }} />
      </Box>
    </Stack>
  );
}

function IdentityRow({
  detail,
  onOpenAlerts,
}: {
  detail: PatientDetail;
  onOpenAlerts?: () => void;
}) {
  const hasAlerts = detail.active_alert_count > 0;
  const displayName = (detail.display_name || "").trim() || detail.patient_id;
  const avatarBg = hasAlerts ? color.status.warning : color.brand.primaryHover;
  return (
    <Stack
      direction="row"
      spacing={2}
      alignItems="center"
      flexWrap="wrap"
      useFlexGap
      sx={{ gap: `${spacing.sm}px` }}
    >
      <Avatar
        sx={{
          bgcolor: avatarBg,
          width: 48,
          height: 48,
          fontSize: 15,
          fontWeight: 700,
          flexShrink: 0,
        }}
      >
        {initials(displayName)}
      </Avatar>
      <Box sx={{ flex: 1, minWidth: 180 }}>
        <Typography
          variant="h5"
          component="h1"
          sx={{
            fontFamily: typography.fontFamily.heading,
            fontWeight: 700,
            letterSpacing: typography.letterSpacing.display,
            lineHeight: 1.2,
            fontSize: { xs: 20, sm: 24 },
            color: color.text.primary,
          }}
        >
          {displayName}
        </Typography>
        {detail.nhs_number && (
          <Typography
            variant="caption"
            sx={{
              display: "block",
              mt: 0.25,
              fontFamily: typography.fontFamily.mono,
              color: color.text.caption,
              letterSpacing: "0.04em",
            }}
          >
            NHS {formatNhsNumber(detail.nhs_number)}
          </Typography>
        )}
        <Typography
          variant="caption"
          sx={{ display: "block", mt: 0.25, color: color.text.caption }}
        >
          {metaLine(detail)}
        </Typography>
      </Box>
      {hasAlerts && onOpenAlerts && (
        <AlertCta count={detail.active_alert_count} onOpenAlerts={onOpenAlerts} />
      )}
    </Stack>
  );
}

export function PatientHeader({
  detail,
  loading,
  onBack,
  backLabel = "Back to patients",
  onOpenAlerts,
  children,
}: Props) {
  const reducedTransparency = useReducedTransparency();
  const frost = frostStyle(reducedTransparency, "pane");
  return (
    <Box
      data-testid="epr-patient-header"
      sx={{
        flexShrink: 0,
        px: { xs: 2, sm: 3 },
        pt: 1.5,
        pb: 1.5,
        ...frost,
        borderBottom: "1px solid",
        borderColor: "divider",
        "@media (hover: hover) and (pointer: fine)": {
          "& [data-chrome='press']:hover": { opacity: 0.92 },
        },
      }}
    >
      {onBack && (
        <QuietButton onClick={onBack} ariaLabel={backLabel}>
          <ArrowBackIcon sx={{ fontSize: 18 }} />
          {backLabel}
        </QuietButton>
      )}
      <Box sx={{ mt: onBack ? 0.5 : 0 }}>
        {loading || !detail ? (
          <HeaderSkeleton />
        ) : (
          <IdentityRow detail={detail} onOpenAlerts={onOpenAlerts} />
        )}
      </Box>
      {children && <Box sx={{ mt: 1.5 }}>{children}</Box>}
    </Box>
  );
}
