/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  IconButton,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  Typography,
} from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';

import {
  dqApi,
  EpisodeHealthResult,
  MilestoneRow,
  OutcomeInferenceResult,
  StaleEpisode,
} from '@/lib/api/dq';

// ---------------------------------------------------------------------------
// Verdict chip
// ---------------------------------------------------------------------------

const VERDICT_COLORS: Record<string, 'error' | 'success' | 'warning' | 'default'> = {
  INFERRED_CANCER: 'error',
  INFERRED_BENIGN: 'success',
  AMBIGUOUS: 'warning',
  UNRESOLVABLE: 'default',
  INFERRED_CANCER_WEAK: 'error',
  INFERRED_BENIGN_WEAK: 'success',
};

function VerdictChip({ verdict, flag }: { verdict: string; flag: string }) {
  const color = VERDICT_COLORS[flag] ?? 'default';
  const label = flag.replace(/_/g, ' ').toLowerCase();
  return <Chip label={label} color={color} size="small" />;
}

function MilestoneCell({ ok }: { ok: boolean }) {
  return <Box component="span" sx={{ color: ok ? 'success.main' : 'error.main' }}>
    {ok ? '✓' : '✗'}
  </Box>;
}

// ---------------------------------------------------------------------------
// Pie colours
// ---------------------------------------------------------------------------
const PIE_COLORS = ['#4caf50', '#ff9800', '#f44336', '#2196f3', '#9c27b0', '#607d8b'];

// ---------------------------------------------------------------------------
// Health tab
// ---------------------------------------------------------------------------

function HealthTab({ health }: { health: EpisodeHealthResult | null }) {
  if (!health) return <CircularProgress />;
  const data = Object.entries(health.status_counts).map(([name, value]) => ({ name, value }));
  return (
    <Box>
      <Stack direction="row" spacing={3} mb={3}>
        <Box><Typography variant="h4" fontWeight={700}>{health.total_count}</Typography><Typography variant="caption">Total</Typography></Box>
        <Box><Typography variant="h4" fontWeight={700} color="warning.main">{health.stale_count}</Typography><Typography variant="caption">Stale</Typography></Box>
        <Box><Typography variant="h4" fontWeight={700} color="info.main">{health.hitl_count}</Typography><Typography variant="caption">HITL</Typography></Box>
        <Box><Typography variant="h4" fontWeight={700} color="text.secondary">{health.auto_closed_count}</Typography><Typography variant="caption">Auto-closed</Typography></Box>
      </Stack>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label>
            {data.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Stale tab
// ---------------------------------------------------------------------------

function StaleRow({ ep }: { ep: StaleEpisode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <TableRow>
        <TableCell>
          <IconButton size="small" onClick={() => setOpen(!open)}>
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>
        <TableCell>
          <Link href={`/admin/data-quality/patient/${ep.patient_id}`}>{ep.patient_id}</Link>
        </TableCell>
        <TableCell>{ep.site}</TableCell>
        <TableCell>{ep.status}</TableCell>
        <TableCell align="right">{ep.days_stale}</TableCell>
        <TableCell>{ep.last_encounter_date ?? '-'}</TableCell>
        <TableCell align="right">{ep.encounter_count}</TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={7} sx={{ p: 0 }}>
          <Collapse in={open}>
            <Box sx={{ px: 3, py: 1, bgcolor: 'grey.50' }}>
              <Typography variant="caption">Referral: {ep.referral_date ?? 'n/a'} &nbsp;|&nbsp; Specialist: {ep.specialist_date ?? 'n/a'}</Typography>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

function StaleTab({ stale }: { stale: StaleEpisode[] | null }) {
  if (!stale) return <CircularProgress />;
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell />
          <TableCell>Patient</TableCell>
          <TableCell>Site</TableCell>
          <TableCell>Status</TableCell>
          <TableCell align="right">Days stale</TableCell>
          <TableCell>Last encounter</TableCell>
          <TableCell align="right">Encounters</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {stale.length === 0
          ? <TableRow><TableCell colSpan={7}><Typography color="text.secondary">No stale episodes</Typography></TableCell></TableRow>
          : stale.map(ep => <StaleRow key={ep.episode_id} ep={ep} />)}
      </TableBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// Completeness tab
// ---------------------------------------------------------------------------

function CompletenessTab({ rows }: { rows: MilestoneRow[] | null }) {
  if (!rows) return <CircularProgress />;
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Patient</TableCell>
          <TableCell>Site</TableCell>
          <TableCell>Status</TableCell>
          <TableCell align="center">Referral</TableCell>
          <TableCell align="center">Specialist</TableCell>
          <TableCell align="center">Diagnosis</TableCell>
          <TableCell align="center">Treatment</TableCell>
          <TableCell align="center">Letter</TableCell>
          <TableCell align="center">Benign close</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map(r => (
          <TableRow key={r.episode_id}>
            <TableCell><Link href={`/admin/data-quality/patient/${r.patient_id}`}>{r.patient_id}</Link></TableCell>
            <TableCell>{r.site}</TableCell>
            <TableCell>{r.status}</TableCell>
            <TableCell align="center"><MilestoneCell ok={r.has_referral} /></TableCell>
            <TableCell align="center"><MilestoneCell ok={r.has_specialist} /></TableCell>
            <TableCell align="center"><MilestoneCell ok={r.has_diagnosis} /></TableCell>
            <TableCell align="center"><MilestoneCell ok={r.has_treatment} /></TableCell>
            <TableCell align="center"><MilestoneCell ok={r.has_letter} /></TableCell>
            <TableCell align="center"><MilestoneCell ok={r.has_benign_closure} /></TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// Outcome Inference tab
// ---------------------------------------------------------------------------

function InferenceRow({ result }: { result: OutcomeInferenceResult }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <TableRow>
        <TableCell>
          <IconButton size="small" onClick={() => setOpen(!open)}>
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>
        <TableCell><Link href={`/admin/data-quality/patient/${result.patient_id}`}>{result.patient_id}</Link></TableCell>
        <TableCell>{result.site}</TableCell>
        <TableCell><VerdictChip verdict={result.verdict} flag={result.flag} /></TableCell>
        <TableCell align="right">{result.cancer_signals.length}</TableCell>
        <TableCell align="right">{result.benign_signals.length}</TableCell>
        <TableCell>{result.private_blocked ? 'Yes' : 'No'}</TableCell>
        <TableCell>{result.specialist_confirmed ? 'Yes' : 'No'}</TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={8} sx={{ p: 0 }}>
          <Collapse in={open}>
            <Box sx={{ px: 3, py: 1, bgcolor: 'grey.50' }}>
              {result.cancer_signals.length > 0 && (
                <Box mb={1}>
                  <Typography variant="caption" color="error.main" fontWeight={600}>Cancer signals:</Typography>
                  {result.cancer_signals.map((s, i) => (
                    <Typography key={i} variant="caption" display="block">{s.date} -- {s.label}: <em>{s.snippet}</em></Typography>
                  ))}
                </Box>
              )}
              {result.benign_signals.length > 0 && (
                <Box>
                  <Typography variant="caption" color="success.main" fontWeight={600}>Benign signals:</Typography>
                  {result.benign_signals.map((s, i) => (
                    <Typography key={i} variant="caption" display="block">{s.date} -- {s.label}: <em>{s.snippet}</em></Typography>
                  ))}
                </Box>
              )}
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

function InferenceTab() {
  const [results, setResults] = useState<OutcomeInferenceResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await dqApi.inferOutcome();
      setResults(data.results);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={2} mb={2}>
        <Button variant="contained" onClick={run} disabled={loading} size="small">
          {loading ? 'Running inference...' : 'Run outcome inference'}
        </Button>
        {loading && <CircularProgress size={20} />}
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
      {results && (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell />
              <TableCell>Patient</TableCell>
              <TableCell>Site</TableCell>
              <TableCell>Verdict</TableCell>
              <TableCell align="right">Cancer signals</TableCell>
              <TableCell align="right">Benign signals</TableCell>
              <TableCell>Private blocked</TableCell>
              <TableCell>Specialist confirmed</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {results.length === 0
              ? <TableRow><TableCell colSpan={8}>No stale episodes to analyse</TableCell></TableRow>
              : results.map(r => <InferenceRow key={r.episode_id} result={r} />)}
          </TableBody>
        </Table>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function EpisodesPage() {
  const [tab, setTab] = useState(0);
  const [health, setHealth] = useState<EpisodeHealthResult | null>(null);
  const [stale, setStale] = useState<StaleEpisode[] | null>(null);
  const [completeness, setCompleteness] = useState<MilestoneRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([
      dqApi.getEpisodeHealth().then(setHealth),
      dqApi.getStaleEpisodes().then(d => setStale(d.episodes)),
      dqApi.getCompleteness().then(d => setCompleteness(d.episodes)),
    ]).then(results => {
      const failed = results.filter(r => r.status === 'rejected');
      if (failed.length) setError('Some data failed to load');
    });
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700} mb={3}>Episode health</Typography>
      {error && <Alert severity="warning" sx={{ mb: 2 }}>{error}</Alert>}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
        <Tab label="Health" />
        <Tab label="Stale" />
        <Tab label="Completeness" />
        <Tab label="Outcome inference" />
      </Tabs>

      {tab === 0 && <HealthTab health={health} />}
      {tab === 1 && <StaleTab stale={stale} />}
      {tab === 2 && <CompletenessTab rows={completeness} />}
      {tab === 3 && <InferenceTab />}
    </Box>
  );
}
