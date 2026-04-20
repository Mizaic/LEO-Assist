/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-3AD4D385
 *   DI: DI-9DCBC4BA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-3AD4D385")
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import { useTheme } from "@mui/material/styles";
import TroubleshootOutlinedIcon from "@mui/icons-material/TroubleshootOutlined";
import GroupWorkOutlinedIcon from "@mui/icons-material/GroupWorkOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import FindInPageOutlinedIcon from "@mui/icons-material/FindInPageOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import PeopleOutlinedIcon from "@mui/icons-material/PeopleOutlined";
import StarOutlinedIcon from "@mui/icons-material/StarOutlined";
import SpeedOutlinedIcon from "@mui/icons-material/SpeedOutlined";
import LinkOffOutlinedIcon from "@mui/icons-material/LinkOffOutlined";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";
import type { MissionDescription, PersonaLens } from "@/lib/researchApi";

interface Props {
  mission: MissionDescription;
  lens: PersonaLens;
  onSelect: (mission: MissionDescription) => void;
}

const MISSION_ICONS: Record<string, React.ReactElement> = {
  bottleneck: <TroubleshootOutlinedIcon />,
  gaps: <FindInPageOutlinedIcon />,
  circles: <SearchOutlinedIcon />,
  groups: <GroupWorkOutlinedIcon />,
  similar: <PeopleOutlinedIcon />,
  teams: <HubOutlinedIcon />,
  critical: <StarOutlinedIcon />,
  busiest: <SpeedOutlinedIcon />,
  missing: <LinkOffOutlinedIcon />,
};

const TIER_LABELS: Record<number, string> = {
  1: "Core",
  2: "Extended",
  3: "Advanced",
};

export default function MissionCard({ mission, lens, onSelect }: Props) {
  const theme = useTheme();
  const isLocked = !mission.data_available;
  const title = mission.titles[lens] ?? mission.titles.patients;
  const description = mission.descriptions[lens] ?? mission.descriptions.patients;
  const icon = MISSION_ICONS[mission.id] ?? <HubOutlinedIcon />;

  const tierColor =
    mission.tier === 1
      ? theme.palette.secondary.main
      : mission.tier === 2
      ? theme.palette.info.main
      : theme.palette.primary.main;

  const handleClick = () => {
    if (!isLocked) onSelect(mission);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleClick();
    }
  };

  return (
    <Box
      role="button"
      tabIndex={isLocked ? -1 : 0}
      aria-label={title}
      aria-disabled={isLocked}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      sx={{
        p: 2.5,
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        cursor: isLocked ? "default" : "pointer",
        opacity: isLocked ? 0.55 : 1,
        transition: "box-shadow 0.15s, border-color 0.15s",
        "&:hover": isLocked
          ? {}
          : {
              boxShadow: 3,
              borderColor: "primary.main",
            },
        "&:focus-visible": {
          outline: `2px solid ${theme.palette.primary.main}`,
          outlineOffset: 2,
        },
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
        minHeight: 160,
      }}
    >
      {/* Header row: icon + tier badge */}
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
        <Box
          sx={{
            color: isLocked ? "text.disabled" : tierColor,
            mt: 0.25,
            flexShrink: 0,
          }}
        >
          {isLocked ? <LockOutlinedIcon fontSize="small" /> : icon}
        </Box>
        <Box sx={{ flex: 1 }} />
        <Chip
          label={isLocked ? "Coming soon" : TIER_LABELS[mission.tier]}
          size="small"
          sx={{
            height: 20,
            fontSize: "0.7rem",
            bgcolor: isLocked
              ? "action.disabledBackground"
              : `${tierColor}1A`,
            color: isLocked ? "text.disabled" : tierColor,
            fontWeight: 600,
            border: "none",
          }}
        />
      </Box>

      {/* Title */}
      <Typography
        variant="body2"
        sx={{
          fontWeight: 600,
          fontSize: "0.875rem",
          color: isLocked ? "text.disabled" : "text.primary",
          lineHeight: 1.4,
          flex: 1,
        }}
      >
        {title}
      </Typography>

      {/* Description */}
      <Typography
        variant="caption"
        sx={{
          color: isLocked ? "text.disabled" : "text.secondary",
          lineHeight: 1.5,
          display: "-webkit-box",
          WebkitLineClamp: 3,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}
      >
        {isLocked
          ? `Requires referral data. This investigation will light up automatically once referral data is loaded for your organisation.`
          : description}
      </Typography>
    </Box>
  );
}
