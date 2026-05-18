/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
'use client';

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  CircularProgress,
  Divider,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { dqApi, SitrepResult } from '@/lib/api/dq';

function StatBox({ label, value, color }: { label: string; value: number | string; color?: string }) {
  return (
    <Box>
      <Typography variant="h4" fontWeight={700} color={color}>{value}</Typography>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
    </Box>
  );
}

export default function SitrepPage() {
  const [data, setData] = useState<SitrepResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    dqApi.getSitrep()
      .then(setData)
      .catch(e => setError(String(e)));
  }, []);

  if (error) return <Alert severity="error" sx={{ m: 3 }}>{error}</Alert>;
  if (!data) return <Box display="flex" justifyContent="center" p={6}><CircularProgress /></Box>;

  const statusEntries = Object.entries(data.episode_status_counts).sort(
    ([, a], [, b]) => b - a
  );

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700} mb={1}>Situation report</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Current operational state snapshot -- no filters applied.
      </Typography>

      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}>
          <StatBox label="Stale episodes" value={data.stale_count} color="warning.main" />
        </Grid>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}>
          <StatBox label="HITL queue" value={data.hitl_queue_depth} color="info.main" />
        </Grid>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}>
          <StatBox label="SF task backlog" value={data.sf_task_backlog} />
        </Grid>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}>
          <StatBox label="Gold labels" value={data.gold_label_count} />
        </Grid>
        <Grid size={{ xs: 6, sm: 4, md: 2 }}>
          <StatBox label="Training candidates" value={data.training_candidate_count} />
        </Grid>
      </Grid>

      <Divider sx={{ mb: 3 }} />

      <Typography variant="h6" fontWeight={600} mb={2}>Episode status breakdown</Typography>
      <Table size="small" sx={{ maxWidth: 480 }}>
        <TableHead>
          <TableRow>
            <TableCell>Status</TableCell>
            <TableCell align="right">Count</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {statusEntries.map(([status, count]) => (
            <TableRow key={status}>
              <TableCell>{status}</TableCell>
              <TableCell align="right">{count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
