/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Slider from "@mui/material/Slider";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import { GiRabbit, GiTurtle } from "react-icons/gi";
import type { EncounterListItem } from "@/lib/missionControlApi";
import { computeRecommendation, type TrainingRecommendation } from "./trainingAdvisorUtils";
import ScoreHistogram from "./ScoreHistogram";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AppliedConfig {
  minCombinedScore: number;
  enableDedup: boolean;
  dedupThreshold: number;
}

interface Props {
  rows: EncounterListItem[];
  currentMinScore: number;
  onApply: (config: AppliedConfig) => void;
  onThresholdChange: (combined: number) => void;
  onShow3D: () => void;
}

// ---------------------------------------------------------------------------
// Match type display helpers
// ---------------------------------------------------------------------------

const TYPE_LABELS: Record<string, string> = {
  keyword: "Keyword hits",
  hybrid: "Keyword + meaning",
  semantic: "Condition variants",
  none: "Not matched",
};

const TYPE_COLORS: Record<string, string> = {
  keyword: "#1565C0",
  hybrid: "#7B1FA2",
  semantic: "#00695C",
  none: "#9E9E9E",
};
const DEDUP_LEVELS = [0.99, 0.98, 0.97, 0.96, 0.95] as const;

function scoreLabel(score: number): string {
  if (score >= 0.9) return "Excellent";
  if (score >= 0.7) return "Great";
  if (score >= 0.5) return "Good";
  if (score >= 0.3) return "Fair";
  return "Weak";
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MatchTypePill({ type, count }: { type: string; count: number }) {
  const color = TYPE_COLORS[type] ?? "#9E9E9E";
  return (
    <Tooltip title={TYPE_LABELS[type] ?? type} arrow>
      <Box
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 0.5,
          px: 1,
          py: 0.25,
          borderRadius: 4,
          border: `1px solid ${color}`,
          color,
          fontSize: "0.72rem",
          fontWeight: 600,
          cursor: "default",
          userSelect: "none",
        }}
      >
        <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: color }} />
        {count}
      </Box>
    </Tooltip>
  );
}

function ScoreBadge({ label, value }: { label: string; value: number }) {
  const text = scoreLabel(value);
  const color = value >= 0.7 ? "#2E7D32" : value >= 0.4 ? "#E65100" : "#C62828";
  return (
    <Box sx={{ textAlign: "center", minWidth: 72 }}>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={700} sx={{ color }}>
        {text}
      </Typography>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Recommendation summary
// ---------------------------------------------------------------------------

function RecommendationBody({
  rec,
  dedupThreshold,
  onApply,
  onDedupeModeChange,
}: {
  rec: TrainingRecommendation;
  dedupThreshold: number;
  onApply: () => void;
  onDedupeModeChange: (mode: number) => void;
}) {
  const pct = Math.round(rec.minCombinedScore * 100);
  const types = Object.entries(rec.byMatchType).filter(([, n]) => n > 0);
  const dedupMode = dedupThreshold >= 0.99
    ? "Keep more variation"
    : dedupThreshold >= 0.98
      ? "Light clean-up"
      : dedupThreshold >= 0.97
        ? "Balanced"
        : dedupThreshold >= 0.96
          ? "Focused"
          : "Narrow hard";

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 1 }}>
        <Typography variant="body2" color="text.secondary">
          Recommended quality:
        </Typography>
        <Typography variant="body1" fontWeight={700}>
          {pct}% quality
        </Typography>
        <Box
          sx={{
            px: 1,
            py: 0.25,
            borderRadius: 4,
            bgcolor: "#E8F5E9",
            color: "#2E7D32",
            fontSize: "0.75rem",
            fontWeight: 600,
          }}
        >
          Up to {rec.keptCount} kept after quality check
        </Box>
        <Box
          sx={{
            px: 1,
            py: 0.25,
            borderRadius: 4,
            bgcolor: "#F5F5F5",
            color: "#757575",
            fontSize: "0.75rem",
            fontWeight: 600,
          }}
        >
          {rec.removedCount} removed by quality check
        </Box>
        <Box
          sx={{
            px: 1,
            py: 0.25,
            borderRadius: 4,
            bgcolor: "#E3F2FD",
            color: "#0D47A1",
            fontSize: "0.75rem",
            fontWeight: 600,
          }}
        >
          Duplicate clean-up: {dedupMode}
        </Box>
      </Box>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "1.45fr 1fr" },
          gap: 2,
          alignItems: "start",
        }}
      >
        <Box>
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mb: 1.5 }}>
            {types.map(([type, count]) => (
              <MatchTypePill key={type} type={type} count={count} />
            ))}
          </Box>

          <Box sx={{ display: "flex", gap: 2, mb: 1.5 }}>
            <ScoreBadge label="Match quality" value={rec.qualityScore} />
            <Divider orientation="vertical" flexItem />
            <ScoreBadge label="Coverage" value={rec.coverageScore} />
          </Box>

          <Box sx={{ mb: 1.5 }}>
            {rec.bullets.map((b, i) => (
              <Typography key={i} variant="body2" color="text.secondary" sx={{ mb: 0.5, pl: 1.5, position: "relative" }}>
                <Box component="span" sx={{ position: "absolute", left: 0 }}>-</Box>
                {b}
              </Typography>
            ))}
            {rec.enableDedup && (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.4, pl: 1.5, position: "relative" }}>
                <Box component="span" sx={{ position: "absolute", left: 0 }}>-</Box>
                Final kept count may be lower after duplicate clean-up.
              </Typography>
            )}
          </Box>

          {rec.warnings.length > 0 && (
            <Box sx={{ mb: 1.5 }}>
              {rec.warnings.map((w, i) => (
                <Alert key={i} severity="warning" sx={{ py: 0, mb: 0.5, fontSize: "0.8rem" }}>
                  {w}
                </Alert>
              ))}
            </Box>
          )}

          <Button
            variant="contained"
            size="small"
            startIcon={<AutoFixHighIcon />}
            onClick={onApply}
            sx={{ textTransform: "none" }}
          >
            Apply these case-finding settings
          </Button>
        </Box>

        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 2,
            p: 1.5,
            bgcolor: "background.paper",
          }}
        >
          <Typography variant="body2" color="text.secondary" sx={{ display: "block", mb: 0.6 }}>
            Duplicate clean-up
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
            Move left to keep more variation. Move right to remove more similar notes.
          </Typography>
          <Box sx={{ px: 0.5 }}>
            <Slider
              min={0}
              max={DEDUP_LEVELS.length - 1}
              step={1}
              marks
              value={Math.max(0, DEDUP_LEVELS.findIndex((v) => v === dedupThreshold))}
              onChange={(_, value) => onDedupeModeChange(Array.isArray(value) ? value[0] : value)}
              valueLabelDisplay="auto"
              valueLabelFormat={(value) => `${Math.round(DEDUP_LEVELS[value] * 100)}%`}
              sx={{ mt: 0.5, mb: 0 }}
            />
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mt: 0.35 }}>
              <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                <GiTurtle size={15} color="#596577" />
                <Typography variant="caption">Keep variation</Typography>
              </Box>
              <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
                <Typography variant="caption">Narrow hard</Typography>
                <GiRabbit size={15} color="#596577" />
              </Box>
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              Current setting: {dedupMode} ({Math.round(dedupThreshold * 100)}% similar)
            </Typography>
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TrainingSetAdvisor({
  rows,
  currentMinScore,
  onApply,
  onThresholdChange,
  onShow3D,
}: Props) {
  const [showChart, setShowChart] = useState(false);
  const [dedupThreshold, setDedupThreshold] = useState(0.99);

  const rec = useMemo(() => computeRecommendation(rows), [rows]);
  useEffect(() => {
    setDedupThreshold(rec.dedupThreshold);
  }, [rec.dedupThreshold]);

  const handleApply = () => {
    onApply({
      minCombinedScore: rec.minCombinedScore,
      enableDedup: rec.enableDedup,
      dedupThreshold,
    });
  };
  const handleDedupeModeChange = (mode: number) => {
    const idx = Math.min(DEDUP_LEVELS.length - 1, Math.max(0, mode));
    setDedupThreshold(DEDUP_LEVELS[idx]);
  };

  return (
    <Paper
      elevation={0}
      sx={{
        mt: 1.25,
        mb: 1.25,
        p: 2,
        border: "1px solid",
        borderColor: rec.warnings.length > 0 ? "warning.light" : "success.light",
        borderLeft: "4px solid",
        borderLeftColor: rec.warnings.length > 0 ? "warning.main" : "success.main",
        borderRadius: 2,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
        <AutoFixHighIcon sx={{ fontSize: 18, color: "success.main" }} />
        <Typography variant="subtitle2" fontWeight={700}>
          Best settings for case finding
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
          Based on all {rows.length} candidates
        </Typography>
      </Box>

      <RecommendationBody
        rec={rec}
        dedupThreshold={dedupThreshold}
        onApply={handleApply}
        onDedupeModeChange={handleDedupeModeChange}
      />

      <Button
        size="small"
        endIcon={showChart ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        onClick={() => setShowChart((v) => !v)}
        sx={{ mt: 1.5, textTransform: "none", color: "text.secondary", fontSize: "0.78rem" }}
      >
        {showChart ? "Hide chart" : "Show score chart"}
      </Button>

      <Collapse in={showChart} unmountOnExit>
        <Box sx={{ mt: 1 }}>
          <ScoreHistogram
            rows={rows}
            minCombinedScore={currentMinScore}
            onThresholdChange={onThresholdChange}
            onShow3D={onShow3D}
          />
        </Box>
      </Collapse>
    </Paper>
  );
}
