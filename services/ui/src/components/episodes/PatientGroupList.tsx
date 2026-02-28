"use client";

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";
import UnfoldLessIcon from "@mui/icons-material/UnfoldLess";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import { Virtuoso } from "react-virtuoso";
import type {
  PatientGroup,
  RiskLevel,
  PathwayRisk,
  Episode,
} from "@/lib/pathwayRisk";
import { formatBreachLabel } from "@/lib/pathwayRisk";

type EpisodeWithRisk = Episode & { risk: PathwayRisk };

const RISK_CHIP: Record<
  RiskLevel,
  { label: string; color: "error" | "warning" | "success" | "default" }
> = {
  breached: { label: "Overdue", color: "error" },
  "at-risk": { label: "At risk", color: "warning" },
  "on-track": { label: "On track", color: "success" },
  completed: { label: "Completed", color: "default" },
  unknown: { label: "Unknown", color: "default" },
};

const BORDER_COLORS: Record<RiskLevel, string> = {
  breached: "#dc2626",
  "at-risk": "#d97706",
  "on-track": "#16a34a",
  completed: "#d1d5db",
  unknown: "#d1d5db",
};

const MILESTONE_LABELS: Record<string, string> = {
  presentation: "Presentation",
  referral: "Referral",
  first_clinic: "First Specialist Clinic",
  diagnosis: "Diagnosis",
  treatment_decision: "Treatment Decision",
  first_treatment: "First Treatment",
};

function PatientHeader({
  group,
  expanded,
  onToggle,
}: {
  group: PatientGroup;
  expanded: boolean;
  onToggle: () => void;
}) {
  const riskCfg = RISK_CHIP[group.worstRisk];
  const borderColor = BORDER_COLORS[group.worstRisk];

  return (
    <Box
      onClick={onToggle}
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        px: 2,
        py: 1.25,
        cursor: "pointer",
        borderLeft: "4px solid",
        borderLeftColor: borderColor,
        bgcolor: "background.paper",
        borderRadius: 1,
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      <IconButton
        size="small"
        sx={{
          transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
          transition: "transform 0.2s",
          p: 0.25,
        }}
        tabIndex={-1}
      >
        <ExpandMoreIcon fontSize="small" />
      </IconButton>

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography
            variant="body2"
            sx={{ fontWeight: 600, fontSize: "0.85rem" }}
          >
            {group.patientId.startsWith("_no_patient_")
              ? "Unknown patient"
              : group.patientId}
          </Typography>
          <Chip label={riskCfg.label} size="small" color={riskCfg.color} />
          {group.hasConvergenceRisk && (
            <Tooltip title={group.convergenceNote ?? "This patient has several referrals that may be related"}>
              <Chip
                icon={<CallSplitIcon sx={{ fontSize: 14 }} />}
                label="Multiple referrals"
                size="small"
                color="warning"
                variant="outlined"
                sx={{ fontSize: "0.7rem", height: 22 }}
              />
            </Tooltip>
          )}
        </Box>
        <Typography variant="caption" color="text.secondary">
          {group.episodes.length} pathway{group.episodes.length !== 1 && "s"}
          {group.activeCount > 0 &&
            ` (${group.activeCount} active)`}
        </Typography>
      </Box>
    </Box>
  );
}

function PathwayCard({
  episode,
  isSelected,
  onSelect,
}: {
  episode: EpisodeWithRisk;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const riskCfg = RISK_CHIP[episode.risk.level];
  const worst = episode.risk.worstBreach;

  return (
    <Card
      onClick={onSelect}
      sx={{
        cursor: "pointer",
        border: isSelected ? "2px solid" : "1px solid",
        borderColor: isSelected ? "primary.main" : "divider",
        bgcolor: isSelected ? "primary.50" : "background.paper",
        transition: "box-shadow 0.15s ease",
        "&:hover": { boxShadow: 2 },
      }}
    >
      <Box sx={{ px: 2, py: 1.25 }}>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            mb: 0.25,
          }}
        >
          <Typography
            variant="body2"
            sx={{ fontWeight: 600, fontSize: "0.82rem" }}
          >
            {episode.condition_type || "Unknown type"}
          </Typography>
          <Chip
            label={riskCfg.label}
            size="small"
            color={riskCfg.color}
            sx={{ height: 20, fontSize: "0.7rem" }}
          />
        </Box>

        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 1,
          }}
        >
          <Typography variant="caption" color="text.secondary">
            {episode.referral_date && `Referred: ${episode.referral_date}`}
          </Typography>
          {worst && !worst.achieved && (
            <BreachLabel worst={worst} />
          )}
        </Box>

        {episode.risk.nextExpectedMilestone && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.25 }}
          >
            Next:{" "}
            {MILESTONE_LABELS[episode.risk.nextExpectedMilestone] ??
              episode.risk.nextExpectedMilestone}
          </Typography>
        )}
      </Box>
    </Card>
  );
}

function BreachLabel({
  worst,
}: {
  worst: { target: { label: string }; daysRemaining: number | null; achieved?: boolean };
}) {
  const remaining = worst.daysRemaining ?? 0;
  const overdue = remaining < 0;
  const label = formatBreachLabel(worst as import("@/lib/pathwayRisk").BreachStatus);

  return (
    <Typography
      variant="caption"
      sx={{
        color: overdue ? "error.main" : remaining <= 7 ? "error.main" : "warning.main",
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </Typography>
  );
}

export default function PatientGroupList({
  groups,
  selected,
  onSelect,
}: {
  groups: PatientGroup[];
  selected: EpisodeWithRisk | null;
  onSelect: (ep: EpisodeWithRisk) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    for (const g of groups) {
      if (
        g.worstRisk === "breached" ||
        g.worstRisk === "at-risk" ||
        g.hasConvergenceRisk
      ) {
        initial.add(g.patientId);
      }
    }
    return initial;
  });

  const toggleExpand = (patientId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(patientId)) next.delete(patientId);
      else next.add(patientId);
      return next;
    });
  };

  const allExpanded = useMemo(
    () => groups.length > 0 && groups.every((g) => expanded.has(g.patientId)),
    [groups, expanded],
  );

  const toggleAll = () => {
    if (allExpanded) {
      setExpanded(new Set());
    } else {
      setExpanded(new Set(groups.map((g) => g.patientId)));
    }
  };

  if (!groups.length) {
    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: 200,
        }}
      >
        <Typography variant="body2" color="text.secondary">
          No referral pathways match your filters.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "70vh" }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "flex-end",
          mb: 0.75,
          flexShrink: 0,
        }}
      >
        <Button
          size="small"
          variant="text"
          onClick={toggleAll}
          startIcon={allExpanded ? <UnfoldLessIcon sx={{ fontSize: 16 }} /> : <UnfoldMoreIcon sx={{ fontSize: 16 }} />}
          aria-label={allExpanded ? "collapse all patients" : "expand all patients"}
          sx={{ fontSize: "0.75rem", textTransform: "none", color: "text.secondary" }}
        >
          {allExpanded ? "Collapse all" : "Expand all"}
        </Button>
      </Box>
    <Virtuoso
      data={groups}
      style={{ flex: 1 }}
      itemContent={(_index, group) => {
        const isExpanded = expanded.has(group.patientId);

        return (
          <Box sx={{ pb: 1 }}>
            <Card
              variant="outlined"
              sx={{
                overflow: "visible",
                borderLeft: "4px solid",
                borderLeftColor: BORDER_COLORS[group.worstRisk],
              }}
            >
              <PatientHeader
                group={group}
                expanded={isExpanded}
                onToggle={() => toggleExpand(group.patientId)}
              />

              <Collapse in={isExpanded}>
                <Box sx={{ px: 2, pb: 1.5, pt: 0.5 }}>
                  {group.hasConvergenceRisk && group.convergenceNote && (
                    <Box
                      sx={{
                        mb: 1,
                        px: 1.5,
                        py: 0.75,
                        borderRadius: 1,
                        bgcolor: "warning.50",
                        border: "1px solid",
                        borderColor: "warning.200",
                      }}
                    >
                      <Typography
                        variant="caption"
                        sx={{ color: "warning.dark", fontWeight: 500 }}
                      >
                        {group.convergenceNote}
                      </Typography>
                    </Box>
                  )}

                  <Box
                    sx={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 0.75,
                    }}
                  >
                    {group.episodes.map((ep) => (
                      <PathwayCard
                        key={ep.episode_id}
                        episode={ep}
                        isSelected={
                          selected?.episode_id === ep.episode_id
                        }
                        onSelect={() => onSelect(ep)}
                      />
                    ))}
                  </Box>
                </Box>
              </Collapse>
            </Card>
          </Box>
        );
      }}
    />
    </Box>
  );
}
