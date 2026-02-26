"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Chip from "@mui/material/Chip";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import Grid from "@mui/material/Grid";
import { fetchCSSAlerts } from "@/lib/analyticsApi";

interface CSSAlert {
  episode_id: string;
  type: string;
  severity: string;
  description: string;
}

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const SEVERITY_COLORS: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "info",
};

export default function CSSAlertsPage() {
  const [alerts, setAlerts] = useState<CSSAlert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCSSAlerts()
      .then(setAlerts)
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false));
  }, []);

  const sorted = [...alerts].sort(
    (a, b) => (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99),
  );

  const bySeverity = alerts.reduce<Record<string, number>>((acc, a) => {
    acc[a.severity] = (acc[a.severity] ?? 0) + 1;
    return acc;
  }, {});

  const byType = alerts.reduce<Record<string, number>>((acc, a) => {
    acc[a.type] = (acc[a.type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 3 }}>
        Clinical Safety Signals (CSS)
      </Typography>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Card>
            <CardContent sx={{ py: 2 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5, fontSize: "0.8rem" }}>
                Total Alerts
              </Typography>
              {loading ? (
                <Skeleton width={60} height={36} />
              ) : (
                <Typography variant="h4" sx={{ fontSize: "1.8rem" }}>
                  {alerts.length}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        {["critical", "high", "medium", "low"].map((sev) => (
          <Grid key={sev} size={{ xs: 6, sm: 3, md: 2.25 }}>
            <Card>
              <CardContent sx={{ py: 2 }}>
                <Chip
                  label={sev}
                  size="small"
                  color={SEVERITY_COLORS[sev] ?? "default"}
                  sx={{ mb: 0.5, textTransform: "capitalize" }}
                />
                {loading ? (
                  <Skeleton width={40} height={28} />
                ) : (
                  <Typography variant="h6">{bySeverity[sev] ?? 0}</Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {!loading && Object.keys(byType).length > 0 && (
        <Box sx={{ display: "flex", gap: 1, mb: 2.5, flexWrap: "wrap" }}>
          {Object.entries(byType)
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => (
              <Chip key={type} label={`${type} (${count})`} variant="outlined" size="small" />
            ))}
        </Box>
      )}

      <Card>
        <CardContent sx={{ p: 0 }}>
          {loading ? (
            <Box sx={{ p: 3 }}>
              <Skeleton variant="rectangular" height={300} />
            </Box>
          ) : sorted.length === 0 ? (
            <Box sx={{ p: 3, textAlign: "center" }}>
              <Typography color="text.secondary">
                No clinical safety signal alerts detected.
              </Typography>
            </Box>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Severity</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Description</TableCell>
                  <TableCell>Episode</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sorted.map((a, i) => (
                  <TableRow key={`${a.episode_id}-${a.type}-${i}`}>
                    <TableCell>
                      <Chip
                        label={a.severity}
                        size="small"
                        color={SEVERITY_COLORS[a.severity] ?? "default"}
                        sx={{ textTransform: "capitalize", minWidth: 64 }}
                      />
                    </TableCell>
                    <TableCell sx={{ fontWeight: 500, fontSize: "0.85rem" }}>{a.type}</TableCell>
                    <TableCell sx={{ fontSize: "0.85rem" }}>{a.description}</TableCell>
                    <TableCell>
                      <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                        {a.episode_id}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
