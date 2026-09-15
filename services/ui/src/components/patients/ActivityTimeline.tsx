/**
 * ActivityTimeline: renders all clinical events for a patient in date order.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5D3EA371")
 *
 * Shows encounters, episodes, alerts, referrals, documents, and SBARs in date order.
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import { color } from "@leo/design-system";
import { RecordShowMore } from "./RecordShowMore";
import { RECORD_PAGE_SIZE, remainingCount, visibleSlice } from "./recordPage";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ForwardToInboxOutlinedIcon from "@mui/icons-material/ForwardToInboxOutlined";
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
    color: "#002178",
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
  referral: {
    label: "Referral",
    color: "#4338CA",
    icon: <ForwardToInboxOutlinedIcon fontSize="small" />,
  },
  document: {
    label: "Document",
    color: "#0369A1",
    icon: <DescriptionOutlinedIcon fontSize="small" />,
  },
  sbar: {
    label: "SBAR",
    color: "#047857",
    icon: <AssessmentOutlinedIcon fontSize="small" />,
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

function isClickableType(type: string): boolean {
  return (
    type === "encounter" ||
    type === "document" ||
    type === "referral" ||
    type === "sbar"
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

function TimelineRow({
  item,
  onItemClick,
}: {
  item: TimelineItem;
  onItemClick?: (item: TimelineItem) => void;
}) {
  const cfg = getConfig(item.item_type);
  const clickable = Boolean(onItemClick) && isClickableType(item.item_type);
  return (
    <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start", pb: 1.5 }}>
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
      <Box
        component={clickable ? "button" : "div"}
        type={clickable ? "button" : undefined}
        onClick={clickable ? () => onItemClick?.(item) : undefined}
        sx={{
          flex: 1,
          border: "1px solid",
          borderColor: "divider",
          borderRadius: "8px",
          p: "10px 14px",
          bgcolor: color.surface.alt,
          textAlign: "left",
          font: "inherit",
          cursor: clickable ? "pointer" : "default",
          "@media (hover: hover) and (pointer: fine)": clickable
            ? {
                "&:hover": {
                  borderColor: color.text.caption,
                  bgcolor: color.surface.raised,
                },
              }
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
              fontSize: 12,
              height: 24,
            }}
          />
          <Typography variant="body2" sx={{ color: color.text.caption, fontSize: 12 }}>
            {formatDate(item.item_date)}
          </Typography>
        </Stack>
        <Typography variant="body2" sx={{ mt: 0.5, fontWeight: 500 }}>
          {item.label}
        </Typography>
        {item.extra && (
          <Typography variant="caption" sx={{ color: color.text.caption }}>
            {item.extra}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

export function ActivityTimeline({
  items,
  loading,
  error,
  onItemClick,
}: Props) {
  const [shown, setShown] = useState(RECORD_PAGE_SIZE);
  const listKey = `${items.length}:${items[0]?.item_id ?? ""}:${items[items.length - 1]?.item_id ?? ""}`;
  useEffect(() => {
    setShown(RECORD_PAGE_SIZE);
  }, [listKey]);
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

  const visible = visibleSlice(items, shown);

  return (
    <Stack spacing={0} sx={{ position: "relative" }}>
      <Box
        aria-hidden="true"
        sx={{
          position: "absolute",
          left: 15,
          top: 12,
          bottom: 12,
          width: 2,
          bgcolor: color.surface.divider,
          borderRadius: 1,
        }}
      />
      {visible.map((item, idx) => (
        <TimelineRow
          key={`${item.item_type}-${item.item_id}-${idx}`}
          item={item}
          onItemClick={onItemClick}
        />
      ))}
      <Box sx={{ pl: 6, pt: 1 }}>
        <RecordShowMore
          remaining={remainingCount(items.length, shown)}
          onShowMore={() => setShown((n) => n + RECORD_PAGE_SIZE)}
        />
      </Box>
    </Stack>
  );
}
