"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import KeyboardArrowDown from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUp from "@mui/icons-material/KeyboardArrowUp";
import OpenInNew from "@mui/icons-material/OpenInNew";
import EpisodeTimeline from "./EpisodeTimeline";
import StatusBadge from "./StatusBadge";
import {
  getCancerTypeLabel,
  getReviewLabel,
  getDiagnosticIntervalColour,
  getStatusLabel,
} from "@/lib/pathwayLabels";
import type { MissionPatient } from "@/lib/missionControlApi";

function formatDate(iso: string | null): string {
  if (!iso) return "--";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "2-digit",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

interface Props {
  patient: MissionPatient;
  onOpen: (patient: MissionPatient) => void;
}

export default function PatientCaseRow({ patient, onOpen }: Props) {
  const [expanded, setExpanded] = useState(false);
  const uniqueEpisodes = patient.episodes.filter((episode, index, allEpisodes) => {
    return allEpisodes.findIndex((item) => item.episode_id === episode.episode_id) === index;
  });
  const ep = uniqueEpisodes[0];
  const hasEpisodes = Boolean(ep);
  useEffect(() => {
    if (!hasEpisodes) {
      setExpanded(false);
    }
  }, [hasEpisodes]);

  const intervalColour = ep ? getDiagnosticIntervalColour(ep.diagnostic_interval_days) : "warning";
  const reviewed = Boolean(ep?.reviewed_by);
  const multiEpisode = uniqueEpisodes.length > 1;

  return (
    <>
      <TableRow
        hover
        sx={{ "& > *": { borderBottom: expanded ? "unset" : undefined }, cursor: "pointer" }}
        onClick={() => onOpen(patient)}
      >
        {/* Expand toggle */}
        <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
          <IconButton
            size="small"
            aria-label={
              hasEpisodes
                ? expanded
                  ? "Collapse timeline"
                  : "Expand timeline"
                : "No episodes to expand"
            }
            onClick={() => hasEpisodes && setExpanded((v) => !v)}
            disabled={!hasEpisodes}
          >
            {expanded ? <KeyboardArrowUp /> : <KeyboardArrowDown />}
          </IconButton>
        </TableCell>

        {/* Status dot */}
        <TableCell>
          {ep ? (
            <StatusBadge status={ep.status} />
          ) : (
            <Chip
              label="No episodes yet"
              size="small"
              color="warning"
              variant="outlined"
              sx={{ fontSize: "0.65rem" }}
            />
          )}
        </TableCell>

        {/* Patient */}
        <TableCell>
          <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
            {patient.patient_id}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {patient.age ?? "--"} &middot; {patient.gender ?? "--"}
          </Typography>
          {multiEpisode && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {uniqueEpisodes.length} pathways
            </Typography>
          )}
        </TableCell>

        {/* Cancer type */}
        <TableCell>
          {ep?.cancer_type ? (
            <Typography variant="body2">{getCancerTypeLabel(ep.cancer_type)}</Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">
              {ep ? getStatusLabel(ep.status) : "Awaiting rebuild"}
            </Typography>
          )}
        </TableCell>

        {/* Stage */}
        <TableCell>
          {ep?.cancer_stage ? (
            <Chip label={ep.cancer_stage} size="small" variant="outlined" />
          ) : (
            <Typography variant="body2" color="text.disabled">
              --
            </Typography>
          )}
        </TableCell>

        {/* Key dates */}
        <TableCell>
          <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
            {ep ? formatDate(ep.referral_date) : "No pathway dates yet"}
            {ep?.end_date && ` -> ${formatDate(ep.end_date)}`}
          </Typography>
        </TableCell>

        {/* Time to diagnosis */}
        <TableCell>
          {ep?.diagnostic_interval_days != null ? (
            <Tooltip title="Days from referral to diagnosis (NCDA 62-day target)" arrow>
              <Typography
                variant="body2"
                sx={{
                  color:
                    intervalColour === "success"
                      ? "success.main"
                      : intervalColour === "warning"
                      ? "warning.main"
                      : "error.main",
                  fontWeight: 600,
                }}
              >
                {ep.diagnostic_interval_days}d
              </Typography>
            </Tooltip>
          ) : (
            <Typography variant="body2" color="text.disabled">
              --
            </Typography>
          )}
        </TableCell>

        {/* Review */}
        <TableCell>
          <Chip
            label={ep ? getReviewLabel(ep.reviewed_by) : "Needs rebuild"}
            size="small"
            color={ep ? (reviewed ? "success" : "warning") : "default"}
            variant={ep ? (reviewed ? "filled" : "outlined") : "outlined"}
            sx={{ fontSize: "0.65rem" }}
          />
        </TableCell>

        {/* Open drawer */}
        <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
          <IconButton
            size="small"
            aria-label="Open patient details"
            onClick={() => onOpen(patient)}
          >
            <OpenInNew fontSize="small" />
          </IconButton>
        </TableCell>
      </TableRow>

      {/* Expanded timeline row */}
      <TableRow>
        <TableCell colSpan={9} sx={{ py: 0, px: 2 }}>
          <Collapse in={expanded} timeout="auto" unmountOnExit>
            <Box sx={{ py: 1.5 }}>
              {uniqueEpisodes.map((episode) => (
                <Box key={episode.episode_id} sx={{ mb: 1 }}>
                  <EpisodeTimeline episode={episode} />
                </Box>
              ))}
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}
