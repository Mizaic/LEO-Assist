/**
 * Pathway variation panel.
 *
 * Atlas trace:
 *   DO: DO-64B006B5
 *   DI: DI-EF8EA3BD
 *   UN: UN-86B5D433
 *   R:  R-31217EFA
 *   VT: VT-3B37176C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-64B006B5")
 *
 * Surfaces the variation_flag, variation_score, first divergence step, and
 * attributed root-cause node for one EpisodeOfCare. All display values come
 * from the cohort-percentile + scorer chain in libs/variation. The panel is
 * read-only: the flag is a reviewer proposal and does not drive action.
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";
import {
  fetchEpisodeVariation,
  type CohortPercentile,
  type EpisodeVariationDetail,
  type MissionEpisode,
} from "@/lib/missionControlApi";

interface Props {
  episode: MissionEpisode;
}

function formatScore(score: number | null | undefined): string {
  if (score == null) return "--";
  return `${Math.round(score * 100)}%`;
}

function splitStep(step: string): { from: string; to: string } | null {
  const idx = step.indexOf("->");
  if (idx < 0) return null;
  return { from: step.slice(0, idx), to: step.slice(idx + 2) };
}

function PercentileBar({
  percentile,
}: {
  percentile: CohortPercentile;
}) {
  const max = Math.max(percentile.p75 * 1.2, 1);
  const p25pct = Math.min((percentile.p25 / max) * 100, 100);
  const p50pct = Math.min((percentile.p50 / max) * 100, 100);
  const p75pct = Math.min((percentile.p75 / max) * 100, 100);
  return (
    <Box sx={{ position: "relative", height: 8, bgcolor: "grey.200", borderRadius: 1 }}>
      <Box
        sx={{
          position: "absolute",
          left: `${p25pct}%`,
          width: `${Math.max(p75pct - p25pct, 1)}%`,
          height: "100%",
          bgcolor: "primary.light",
          borderRadius: 1,
        }}
      />
      <Box
        sx={{
          position: "absolute",
          left: `${p50pct}%`,
          top: -2,
          width: 2,
          height: 12,
          bgcolor: "primary.dark",
        }}
      />
    </Box>
  );
}

function FlaggedStepRow({
  step,
  percentiles,
}: {
  step: string;
  percentiles: CohortPercentile[];
}) {
  const parts = splitStep(step);
  const pct = parts
    ? percentiles.find(
        (p) => p.from_step === parts.from && p.to_step === parts.to
      )
    : undefined;
  const label = parts
    ? `${parts.from} -> ${parts.to}`
    : step;
  return (
    <Box sx={{ mb: 1 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
        <Typography variant="caption" sx={{ fontWeight: 600 }}>
          {label}
        </Typography>
        {pct && (
          <Typography variant="caption" color="text.secondary">
            peer median {Math.round(pct.p50)} days (P25 {Math.round(pct.p25)} /
            P75 {Math.round(pct.p75)})
          </Typography>
        )}
      </Box>
      {pct ? (
        <PercentileBar percentile={pct} />
      ) : (
        <Typography variant="caption" color="text.secondary">
          No peer cohort data
        </Typography>
      )}
    </Box>
  );
}

export default function VariationPanel({ episode }: Props) {
  const [detail, setDetail] = useState<EpisodeVariationDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasAnyVariationSignal = useMemo(() => {
    if (episode.variation_flag) return true;
    if (episode.variation_score != null) return true;
    if (episode.variation_community_id != null) return true;
    return false;
  }, [episode]);

  useEffect(() => {
    if (!hasAnyVariationSignal) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEpisodeVariation(episode.episode_id)
      .then((res) => {
        if (!cancelled) setDetail(res);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "Unknown error";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [episode.episode_id, hasAnyVariationSignal]);

  if (!hasAnyVariationSignal) {
    return null;
  }

  return (
    <Box
      sx={{
        mb: 2,
        p: 1.5,
        border: "1px solid",
        borderColor: episode.variation_flag ? "warning.main" : "divider",
        borderRadius: 1,
        bgcolor: episode.variation_flag ? "warning.lighter" : "grey.50",
      }}
      data-testid="variation-panel"
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <Typography variant="subtitle2">Pathway variation</Typography>
        {episode.variation_flag ? (
          <Chip
            size="small"
            color="warning"
            label={`Flagged - ${formatScore(episode.variation_score)} of pairs above peer P75`}
          />
        ) : (
          <Chip size="small" label="Within peer range" />
        )}
        {episode.variation_community_id != null && (
          <Typography variant="caption" color="text.secondary">
            Peer cohort #{episode.variation_community_id}
            {detail ? ` (${detail.cohort_size} patients)` : ""}
          </Typography>
        )}
      </Box>
      {loading && <LinearProgress sx={{ mb: 1 }} />}
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      {!error && detail && detail.variation_outlier_steps.length > 0 && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Slower than peer cohort on these steps:
          </Typography>
          <Box sx={{ mt: 0.5 }}>
            {detail.variation_outlier_steps.map((step) => (
              <FlaggedStepRow
                key={step}
                step={step}
                percentiles={detail.cohort_percentiles}
              />
            ))}
          </Box>
        </Box>
      )}
      {!error && detail && detail.variation_attributed_node_name && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Attributed root cause node
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {detail.variation_attributed_node_name}
            {detail.variation_attributed_node_type
              ? ` (${detail.variation_attributed_node_type})`
              : ""}
          </Typography>
        </Box>
      )}
      {!error && !loading && !detail && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <CircularProgress size={12} />
          <Typography variant="caption" color="text.secondary">
            Loading peer cohort detail...
          </Typography>
        </Box>
      )}
    </Box>
  );
}
