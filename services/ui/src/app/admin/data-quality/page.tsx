/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-0998FAF5
 *   Also implements: DO-86800C9B
 *   DI: DI-FC80B65A
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-0998FAF5")
 */
'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import AssessmentOutlinedIcon from '@mui/icons-material/AssessmentOutlined';
import BugReportOutlinedIcon from '@mui/icons-material/BugReportOutlined';
import LibraryBooksOutlinedIcon from '@mui/icons-material/LibraryBooksOutlined';
import TuneOutlinedIcon from '@mui/icons-material/TuneOutlined';

import { dqApi, DQCheckResult, DQRulesResult, EpisodeHealthResult, SurfaceFormAuditResult } from '@/lib/api/dq';

// ---------------------------------------------------------------------------
// Status chip helpers
// ---------------------------------------------------------------------------

function RuleStatusChip({ status }: { status: string }) {
  const map: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
    pass: 'success',
    warn: 'warning',
    fail: 'error',
  };
  return <Chip label={status.toUpperCase()} color={map[status] ?? 'default'} size="small" />;
}

function SeverityChip({ severity }: { severity: string }) {
  const map: Record<string, 'error' | 'warning' | 'info' | 'default'> = {
    critical: 'error',
    high: 'warning',
    medium: 'info',
    low: 'default',
  };
  return <Chip label={severity} color={map[severity] ?? 'default'} size="small" variant="outlined" />;
}

// ---------------------------------------------------------------------------
// Summary card
// ---------------------------------------------------------------------------

interface SummaryCardProps {
  title: string;
  value: string | number;
  sub: string;
  href: string;
  icon: React.ReactElement;
  alert?: boolean;
}

function SummaryCard({ title, value, sub, href, icon, alert }: SummaryCardProps) {
  return (
    <Card variant="outlined" sx={{ borderColor: alert ? 'error.main' : undefined }}>
      <CardActionArea component={Link} href={href}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center" mb={1}>
            {icon}
            <Typography variant="subtitle2" color="text.secondary">{title}</Typography>
          </Stack>
          <Typography variant="h4" fontWeight={700}>{value}</Typography>
          <Typography variant="body2" color="text.secondary" mt={0.5}>{sub}</Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DataQualityDashboard() {
  const [rules, setRules] = useState<DQRulesResult | null>(null);
  const [episodes, setEpisodes] = useState<EpisodeHealthResult | null>(null);
  const [sfAudit, setSfAudit] = useState<SurfaceFormAuditResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rulesLoading, setRulesLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [ep, sf] = await Promise.allSettled([
      dqApi.getEpisodeHealth(),
      dqApi.getSfAudit(),
    ]);
    if (ep.status === 'fulfilled') setEpisodes(ep.value);
    if (sf.status === 'fulfilled') setSfAudit(sf.value);
    setLoading(false);
  }, []);

  const runRules = useCallback(async () => {
    setRulesLoading(true);
    try {
      const result = await dqApi.runRules();
      setRules(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setRulesLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Data quality</Typography>
          <Typography variant="body2" color="text.secondary">
            ISO-25012 scorecard across 10 dimensions
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button
            startIcon={<RefreshIcon />}
            onClick={loadData}
            disabled={loading}
            size="small"
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<AssessmentOutlinedIcon />}
            onClick={runRules}
            disabled={rulesLoading}
            size="small"
          >
            {rulesLoading ? 'Running...' : 'Re-run checks'}
          </Button>
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* Summary cards */}
      {loading ? (
        <Box display="flex" justifyContent="center" py={6}>
          <CircularProgress />
        </Box>
      ) : (
        <Grid container spacing={2} sx={{ mb: 4 }}>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <SummaryCard
              title="Episodes"
              value={episodes?.total_count ?? '-'}
              sub={`${episodes?.stale_count ?? 0} stale · ${episodes?.hitl_count ?? 0} HITL`}
              href="/admin/data-quality/episodes"
              icon={<AssessmentOutlinedIcon color="primary" />}
              alert={(episodes?.stale_count ?? 0) > 0}
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <SummaryCard
              title="Surface forms"
              value={sfAudit?.total_count ?? '-'}
              sub={`${sfAudit?.orphan_count ?? 0} orphans · ${sfAudit?.duplicate_count ?? 0} duplicates`}
              href="/admin/data-quality/terminology"
              icon={<LibraryBooksOutlinedIcon color="primary" />}
              alert={(sfAudit?.orphan_count ?? 0) > 0}
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <SummaryCard
              title="Domain coverage"
              value="--"
              sub="Orphan codes & pathway gaps"
              href="/admin/data-quality/domain"
              icon={<TuneOutlinedIcon color="primary" />}
            />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <SummaryCard
              title="Sitrep"
              value="--"
              sub="Operational situation report"
              href="/admin/data-quality/sitrep"
              icon={<BugReportOutlinedIcon color="primary" />}
            />
          </Grid>
        </Grid>
      )}

      {/* DQ rules scorecard */}
      <Typography variant="h6" fontWeight={600} mb={2}>
        DQ rules scorecard
      </Typography>

      {!rules && !rulesLoading && (
        <Alert severity="info">
          Click <strong>Re-run checks</strong> to evaluate all DQ rules and see the traffic-light scorecard.
        </Alert>
      )}

      {rulesLoading && (
        <Box display="flex" alignItems="center" gap={1} py={2}>
          <CircularProgress size={20} />
          <Typography variant="body2">Running DQ rules...</Typography>
        </Box>
      )}

      {rules && (
        <>
          <Stack direction="row" spacing={2} mb={2}>
            <Chip label={`${rules.summary.pass} pass`} color="success" />
            <Chip label={`${rules.summary.warn} warn`} color="warning" />
            <Chip label={`${rules.summary.fail} fail`} color="error" />
            {rules.summary.critical_failures.length > 0 && (
              <Alert severity="error" sx={{ py: 0 }}>
                Critical: {rules.summary.critical_failures.join(', ')}
              </Alert>
            )}
          </Stack>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Rule</TableCell>
                <TableCell>Dimension</TableCell>
                <TableCell>Severity</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Violations</TableCell>
                <TableCell>Description</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rules.results.map((r: DQCheckResult) => (
                <TableRow key={r.rule_id} sx={{
                  bgcolor: r.status === 'fail' ? 'error.50' :
                    r.status === 'warn' ? 'warning.50' : undefined,
                }}>
                  <TableCell><code>{r.rule_id}</code></TableCell>
                  <TableCell>{r.dimension}</TableCell>
                  <TableCell><SeverityChip severity={r.severity} /></TableCell>
                  <TableCell><RuleStatusChip status={r.status} /></TableCell>
                  <TableCell align="right">{r.violation_count}</TableCell>
                  <TableCell sx={{ maxWidth: 300 }}>{r.description}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </>
      )}
    </Box>
  );
}
