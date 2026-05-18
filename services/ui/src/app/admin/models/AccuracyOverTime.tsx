/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   VT: VT-F1C75ADC
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import * as React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";

export type AccuracyVersion = {
  model_version: string;
  registered_at: string;
  offline_precision: number | null;
  offline_recall: number | null;
};

type Metric = "precision" | "recall" | "f1";

const METRIC_LABELS: Record<Metric, string> = {
  precision: "Precision",
  recall: "Recall",
  f1: "F1",
};

function f1Score(p: number, r: number): number {
  const denom = p + r;
  return denom <= 0 ? 0 : (2 * p * r) / denom;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function AccuracyOverTime({
  versions,
}: {
  versions: AccuracyVersion[];
}) {
  const [metric, setMetric] = React.useState<Metric>("f1");

  const data = React.useMemo(() => {
    return versions
      .filter(
        (v) =>
          v.offline_precision != null &&
          v.offline_recall != null &&
          !!v.registered_at,
      )
      .slice()
      .sort(
        (a, b) =>
          new Date(a.registered_at).getTime() -
          new Date(b.registered_at).getTime(),
      )
      .map((v) => {
        const p = v.offline_precision ?? 0;
        const r = v.offline_recall ?? 0;
        const value =
          metric === "precision"
            ? p
            : metric === "recall"
              ? r
              : f1Score(p, r);
        return {
          registered: v.registered_at,
          label: fmtDate(v.registered_at),
          version: v.model_version,
          value,
        };
      });
  }, [versions, metric]);

  if (data.length < 2) {
    return (
      <Alert severity="info" data-testid="accuracy-empty">
        Need at least two registered versions with offline test results to plot
        a trend. Once a second version is validated, the chart will appear here.
      </Alert>
    );
  }

  return (
    <Box>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", sm: "center" }}
        sx={{ mb: 1.5 }}
      >
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ maxWidth: 560 }}
        >
          Trend on the held-out gold dataset (offline test). The dataset stays
          the same across versions, so changes in the line reflect changes in
          the model. Trial-run scores are shown per-version inside each
          accordion below; they are not plotted here because the trial cohort
          can shift over time.
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={metric}
          onChange={(_, v) => v && setMetric(v as Metric)}
          aria-label="Metric"
        >
          <ToggleButton value="precision">Precision</ToggleButton>
          <ToggleButton value="recall">Recall</ToggleButton>
          <ToggleButton value="f1">F1</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <Box sx={{ width: "100%", height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 8, right: 24, left: 0, bottom: 8 }}
          >
            <defs>
              <linearGradient id="accuracyArea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#1976d2" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#1976d2" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis
              domain={[0, 1]}
              tick={{ fontSize: 11 }}
              tickFormatter={(v) =>
                `${Math.round((typeof v === "number" ? v : 0) * 100)}%`
              }
            />
            <RTooltip
              formatter={(value: number) => [
                `${Math.round(value * 100)}%`,
                METRIC_LABELS[metric],
              ]}
              labelFormatter={(label, items) => {
                const item = items?.[0]?.payload as
                  | { version?: string; label?: string }
                  | undefined;
                return item?.version ? `v${item.version}` : String(label);
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#1976d2"
              strokeWidth={2}
              fill="url(#accuracyArea)"
              name={METRIC_LABELS[metric]}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}
