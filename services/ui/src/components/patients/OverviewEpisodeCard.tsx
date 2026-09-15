/**
 * Compact episode card for the EPR overview strip.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { motion as fm } from "framer-motion";
import {
  color,
  elevation,
  radius,
  springOrInstant,
  springs,
  useMotion,
} from "@leo/design-system";
import type { EpisodeSummaryEpr } from "@/lib/patientEprApi";
import { accentFor, outcomeColor, outcomeLabel } from "./episodeAccent";

interface Props {
  ep: EpisodeSummaryEpr;
  index: number;
}

export function OverviewEpisodeCard({ ep, index }: Props) {
  const { reducedMotion } = useMotion();
  const accent = accentFor(ep.condition_type);
  const stagingText = [ep.staging_value, ep.staging_early_late]
    .filter(Boolean)
    .join(" - ");
  const isActive = (ep.status ?? "").toLowerCase() === "active";
  const statusColor = isActive ? color.status.success : color.text.caption;

  return (
    <fm.div
      initial={reducedMotion ? false : { opacity: 0, transform: "translateY(8px)" }}
      animate={{ opacity: 1, transform: "translateY(0px)" }}
      transition={{
        ...springOrInstant(reducedMotion, springs.ui),
        delay: reducedMotion ? 0 : Math.min(index, 12) * 0.04,
      }}
      style={{ height: "100%" }}
    >
      <Box
        sx={{
          position: "relative",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: `${radius.md}px`,
          p: "14px 16px 14px 18px",
          bgcolor: color.surface.raised,
          boxShadow: elevation.card,
          height: "100%",
        }}
      >
        <Box
          aria-hidden="true"
          sx={{
            position: "absolute",
            left: 0,
            top: 14,
            bottom: 14,
            width: 3,
            borderRadius: 2,
            bgcolor: accent,
          }}
        />
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          flexWrap="wrap"
          useFlexGap
          sx={{ mb: 0.5, gap: "8px" }}
        >
          <Typography
            variant="body2"
            fontWeight={700}
            sx={{ textTransform: "capitalize", color: color.text.primary }}
          >
            {ep.condition_type ?? "Episode"}
          </Typography>
          <Chip
            label={ep.status ?? "unknown"}
            size="small"
            sx={{
              height: 24,
              fontSize: 12,
              bgcolor: `${statusColor}18`,
              color: statusColor,
              textTransform: "capitalize",
            }}
          />
          {ep.inferred_outcome && (
            <Chip
              label={outcomeLabel(ep.inferred_outcome)}
              size="small"
              sx={{
                height: 24,
                fontSize: 12,
                bgcolor: `${outcomeColor(ep.inferred_outcome)}15`,
                color: outcomeColor(ep.inferred_outcome),
              }}
            />
          )}
        </Stack>
        <Stack direction="row" spacing={1.5} flexWrap="wrap">
          {ep.referral_date && (
            <Typography variant="caption" sx={{ color: color.text.caption }}>
              Referred {ep.referral_date.slice(0, 10)}
            </Typography>
          )}
          {stagingText && (
            <Typography variant="caption" sx={{ color: color.text.caption }}>
              Stage {stagingText}
            </Typography>
          )}
        </Stack>
      </Box>
    </fm.div>
  );
}
