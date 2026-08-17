/**
 * PatientHeader -- sticky identity bar shown across all EPR tabs.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import type { PatientDetail } from "@/lib/patientEprApi";

interface Props {
  detail: PatientDetail | null;
  loading?: boolean;
}

function ageFromBirthDate(iso: string | null): string {
  if (!iso) return "";
  try {
    const birth = new Date(iso);
    const ageDiff = Date.now() - birth.getTime();
    const age = Math.abs(new Date(ageDiff).getUTCFullYear() - 1970);
    return `${age}y`;
  } catch {
    return "";
  }
}

function initials(patientId: string): string {
  const parts = patientId.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return patientId.slice(0, 2).toUpperCase();
}

export function PatientHeader({ detail, loading }: Props) {
  if (loading || !detail) {
    return (
      <Box
        sx={{
          px: { xs: 2, sm: 3 },
          py: 1.5,
          bgcolor: "#FFFFFF",
          borderBottom: "1px solid #E2E8F0",
        }}
      >
        <Stack direction="row" spacing={2} alignItems="center">
          <Skeleton variant="circular" width={44} height={44} />
          <Box sx={{ flex: 1 }}>
            <Skeleton width={220} height={22} />
            <Skeleton width={300} height={16} sx={{ mt: 0.5 }} />
          </Box>
        </Stack>
      </Box>
    );
  }

  const hasAlerts = detail.active_alert_count > 0;
  const avatarBg = hasAlerts ? "#B45309" : "#002178";
  const age = ageFromBirthDate(detail.birth_date);
  const genderAge = [detail.gender ?? "", age].filter(Boolean).join(" ");
  const displayName =
    (detail.display_name || "").trim() || detail.patient_id;

  return (
    <Box
      sx={{
        px: { xs: 2, sm: 3 },
        py: 1.5,
        bgcolor: "#FFFFFF",
        borderBottom: "1px solid #E2E8F0",
      }}
    >
      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" gap={1}>
        <Avatar
          sx={{
            bgcolor: avatarBg,
            width: 44,
            height: 44,
            fontSize: 15,
            fontWeight: 700,
            flexShrink: 0,
          }}
        >
          {initials(displayName)}
        </Avatar>

        <Box sx={{ flex: 1, minWidth: 160 }}>
          <Stack direction="row" spacing={1.5} alignItems="baseline" flexWrap="wrap">
            <Typography variant="subtitle1" fontWeight={700} lineHeight={1.2}>
              {displayName}
            </Typography>
            {detail.nhs_number && (
              <Typography variant="caption" color="text.secondary" fontFamily="monospace">
                NHS {detail.nhs_number.replace(/(\d{3})(\d{3})(\d{4})/, "$1 $2 $3")}
              </Typography>
            )}
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {genderAge && `${genderAge}  \u00B7  `}
            {detail.birth_date?.slice(0, 10) ?? "DOB unknown"}
            {detail.practice_name ? `  \u00B7  ${detail.practice_name}` : ""}
          </Typography>
        </Box>

        {hasAlerts && (
          <Chip
            icon={<WarningAmberIcon sx={{ fontSize: "16px !important", color: "#B45309 !important" }} />}
            label={`${detail.active_alert_count} alert${detail.active_alert_count !== 1 ? "s" : ""}`}
            size="small"
            sx={{ bgcolor: "#FEF3C7", color: "#B45309", fontWeight: 600, fontSize: 12 }}
          />
        )}
      </Stack>
    </Box>
  );
}
