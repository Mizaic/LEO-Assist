"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import Link from "next/link";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from "recharts";
import { FONT_SIZES } from "@/theme/tokens";

interface AccuracyPoint {
  date: string;
  accuracy: number;
}

interface AlertItem {
  id: string;
  message: string;
  severity: "error" | "warning" | "info";
  created_at: string;
}

interface ProblemEncounter {
  encounter_id: string;
  patient_ref?: string;
  reason?: string;
  care_url?: string;
}

interface MonitorData {
  trend: AccuracyPoint[];
  per_entity: Record<string, number>;
  alerts: AlertItem[];
  problem_encounters: ProblemEncounter[];
}

export function MonitorStage() {
  const [data, setData] = useState<MonitorData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/training/monitor/summary")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) setData(d);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Box sx={{ pt: 2, color: "text.secondary", fontSize: FONT_SIZES.body }}>
        Loading monitor data…
      </Box>
    );
  }

  if (!data) {
    return (
      <Box sx={{ pt: 2, color: "text.secondary", fontSize: FONT_SIZES.body }}>
        No monitoring data available yet. Data appears after the first completed training run.
      </Box>
    );
  }

  const entityData = Object.entries(data.per_entity ?? {})
    .map(([label, acc]) => ({ label, acc }))
    .sort((a, b) => b.acc - a.acc);

  return (
    <Box sx={{ pt: 2, display: "flex", flexDirection: "column", gap: 2.5 }}>
      {/* 30-day accuracy sparkline */}
      {data.trend?.length > 1 && (
        <Box>
          <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
            30-day coding accuracy
          </Typography>
          <ResponsiveContainer width="100%" height={120}>
            <LineChart data={data.trend} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} />
              <YAxis
                domain={[0, 1]}
                tick={{ fontSize: 10 }}
                tickFormatter={(v) =>
                  `${((typeof v === "number" ? v : 0) * 100).toFixed(0)}%`
                }
              />
              <RTooltip
                formatter={(v) =>
                  `${((typeof v === "number" ? v : 0) * 100).toFixed(1)}%`
                }
              />
              <Line type="monotone" dataKey="accuracy" stroke="#1565c0" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </Box>
      )}

      {/* Per-entity accuracy breakdown */}
      {entityData.length > 0 && (
        <Box>
          <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
            Accuracy by entity type
          </Typography>
          <ResponsiveContainer width="100%" height={Math.max(80, entityData.length * 26)}>
            <BarChart data={entityData} layout="vertical" margin={{ left: 8, right: 8 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.3} />
              <XAxis
                type="number"
                domain={[0, 1]}
                tick={{ fontSize: 10 }}
                tickFormatter={(v) =>
                  `${((typeof v === "number" ? v : 0) * 100).toFixed(0)}%`
                }
              />
              <YAxis type="category" dataKey="label" tick={{ fontSize: 10 }} width={130} />
              <RTooltip
                formatter={(v) =>
                  `${((typeof v === "number" ? v : 0) * 100).toFixed(1)}%`
                }
              />
              <Bar dataKey="acc" maxBarSize={16} radius={[0, 3, 3, 0]}>
                {entityData.map((d) => (
                  <Cell key={d.label} fill={d.acc >= 0.85 ? "#2e7d32" : d.acc >= 0.7 ? "#ed6c02" : "#d32f2f"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Box>
      )}

      {/* Unacknowledged alerts */}
      {data.alerts?.length > 0 && (
        <Box>
          <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
            Active alerts
          </Typography>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
            {data.alerts.slice(0, 5).map((a) => (
              <Alert key={a.id} severity={a.severity} sx={{ fontSize: FONT_SIZES.body }}>
                {a.message}
              </Alert>
            ))}
          </Box>
        </Box>
      )}

      {/* Problem encounters */}
      {data.problem_encounters?.length > 0 && (
        <Box>
          <Typography sx={{ fontWeight: 600, fontSize: FONT_SIZES.subtitle, mb: 1 }}>
            Problem encounters
          </Typography>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
            {data.problem_encounters.slice(0, 5).map((enc) => (
              <Box
                key={enc.encounter_id}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1,
                  p: 1,
                  bgcolor: "action.hover",
                  borderRadius: 1,
                  fontSize: FONT_SIZES.body,
                }}
              >
                <Typography sx={{ flex: 1, fontSize: FONT_SIZES.body }}>
                  {enc.reason ?? enc.encounter_id}
                </Typography>
                {enc.care_url && (
                  <Link
                    href={enc.care_url}
                    style={{ fontSize: FONT_SIZES.label, color: "#1565c0", textDecoration: "underline" }}
                  >
                    View
                  </Link>
                )}
              </Box>
            ))}
          </Box>
        </Box>
      )}

      {!data.trend?.length && !entityData.length && !data.alerts?.length && (
        <Typography sx={{ fontSize: FONT_SIZES.body, color: "text.secondary" }}>
          All metrics healthy. No alerts to show.
        </Typography>
      )}
    </Box>
  );
}
