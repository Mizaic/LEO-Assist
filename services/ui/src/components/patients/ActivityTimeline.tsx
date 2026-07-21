/**
 * ActivityTimeline: renders all clinical events for a patient in date order.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5D3EA371")
 *
 * Shows encounters, episode starts, and safety netting alerts together in a
 * single descending-date list. No event type is filtered out.
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import HealingOutlinedIcon from "@mui/icons-material/HealingOutlined";
import type { TimelineItem } from "@/lib/patientEprApi";

interface Props {
  items: TimelineItem[];
  loading?: boolean;
  error?: string | null;
  /** Optional handler -- typically used for encounter rows. */
  onItemClick?: (item: TimelineItem) => void;
}

const ITEM_TYPE_CONFIG: Record<
  string,
  { label: string; color: string; icon: React.ReactElement }
> = {
  encounter: {
    label: "Encounter",
    color: "#1E40AF",
    icon: <MedicalServicesOutlinedIcon fontSize="small" />,
  },
  episode: {
    label: "Episode",
    color: "#047857",
    icon: <HealingOutlinedIcon fontSize="small" />,
  },
  alert: {
    label: "Alert",
    color: "#B45309",
    icon: <WarningAmberOutlinedIcon fontSize="small" />,
  },
};

function getConfig(type: string) {
  return (
    ITEM_TYPE_CONFIG[type] ?? {
      label: type,
      color: "#475569",
      icon: <AssignmentOutlinedIcon fontSize="small" />,
    }
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export function ActivityTimeline({
  items,
  loading,
  error,
  onItemClick,
}: Props) {
  if (loading) {
    return (
      <Stack spacing={1.5}>
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} variant="rounded" height={56} />
        ))}
      </Stack>
    );
  }

  if (error) {
    return (
      <Alert severity="warning">
        Unable to load activity timeline. Please retry.
      </Alert>
    );
  }

  if (!items.length) {
    return (
      <Alert severity="info">
        No activity recorded for this patient yet.
      </Alert>
    );
  }

  return (
    <Stack spacing={0} sx={{ position: "relative" }}>
      {/* Vertical guide line */}
      <Box
        aria-hidden="true"
        sx={{
          position: "absolute",
          left: 15,
          top: 12,
          bottom: 12,
          width: 2,
          bgcolor: "#E2E8F0",
          borderRadius: 1,
        }}
      />
      {items.map((item, idx) => {
        const cfg = getConfig(item.item_type);
        const clickable = Boolean(onItemClick) && item.item_type === "encounter";
        return (
          <Box
            key={`${item.item_type}-${item.item_id}-${idx}`}
            sx={{ display: "flex", gap: 2, alignItems: "flex-start", pb: 1.5 }}
          >
            {/* Dot */}
            <Box
              aria-hidden="true"
              sx={{
                flexShrink: 0,
                width: 32,
                height: 32,
                borderRadius: "50%",
                bgcolor: `${cfg.color}18`,
                border: `2px solid ${cfg.color}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: cfg.color,
                zIndex: 1,
              }}
            >
              {cfg.icon}
            </Box>
            {/* Content */}
            <Box
              component={clickable ? "button" : "div"}
              type={clickable ? "button" : undefined}
              onClick={clickable ? () => onItemClick?.(item) : undefined}
              sx={{
                flex: 1,
                border: "1px solid #E2E8F0",
                borderRadius: "8px",
                p: "10px 14px",
                bgcolor: "#FAFAFA",
                textAlign: "left",
                font: "inherit",
                cursor: clickable ? "pointer" : "default",
                "&:hover": clickable
                  ? { borderColor: "#94A3B8", bgcolor: "#F8FAFC" }
                  : undefined,
              }}
            >
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Chip
                  label={cfg.label}
                  size="small"
                  sx={{
                    bgcolor: `${cfg.color}18`,
                    color: cfg.color,
                    fontWeight: 600,
                    fontSize: 11,
                    height: 20,
                  }}
                />
                <Typography variant="body2" color="text.secondary" fontSize={12}>
                  {formatDate(item.item_date)}
                </Typography>
              </Stack>
              <Typography variant="body2" sx={{ mt: 0.5, fontWeight: 500 }}>
                {item.label}
              </Typography>
              {item.extra && (
                <Typography variant="caption" color="text.secondary">
                  {item.extra}
                </Typography>
              )}
            </Box>
          </Box>
        );
      })}
    </Stack>
  );
}
