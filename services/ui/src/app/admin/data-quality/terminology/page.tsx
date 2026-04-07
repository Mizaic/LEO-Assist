'use client';

import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { dqApi, SurfaceFormAuditResult } from '@/lib/api/dq';

// ---------------------------------------------------------------------------
// Health Report tab
// ---------------------------------------------------------------------------

function HealthTab({ audit }: { audit: SurfaceFormAuditResult | null }) {
  if (!audit) return <CircularProgress />;
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={3}>
        <Box><Typography variant="h4" fontWeight={700}>{audit.total_count}</Typography><Typography variant="caption">Total SFs</Typography></Box>
        <Box><Typography variant="h4" fontWeight={700} color="error.main">{audit.orphan_count}</Typography><Typography variant="caption">Orphans</Typography></Box>
        <Box><Typography variant="h4" fontWeight={700} color="warning.main">{audit.duplicate_count}</Typography><Typography variant="caption">Duplicates</Typography></Box>
        <Box><Typography variant="h4" fontWeight={700} color="warning.main">{audit.inactive_target_count}</Typography><Typography variant="caption">Inactive targets</Typography></Box>
        <Box><Typography variant="h4" fontWeight={700} color="info.main">{audit.low_confidence_count}</Typography><Typography variant="caption">Low confidence</Typography></Box>
      </Stack>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// SF Inspector tab
// ---------------------------------------------------------------------------

function InspectTab() {
  const [term, setTerm] = useState('');
  const [result, setResult] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    if (!term.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await dqApi.inspectSf(term.trim());
      setResult(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      <Stack direction="row" spacing={1} mb={2}>
        <TextField
          size="small"
          placeholder="Enter normalized term..."
          value={term}
          onChange={e => setTerm(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
          sx={{ width: 400 }}
        />
        <Button
          variant="contained"
          startIcon={<SearchIcon />}
          onClick={search}
          disabled={loading}
          size="small"
        >
          Look up
        </Button>
      </Stack>
      {loading && <CircularProgress size={20} />}
      {error && <Alert severity="error">{error}</Alert>}
      {result && (
        <Box component="pre" sx={{ bgcolor: 'grey.100', p: 2, borderRadius: 1, fontSize: 12, overflow: 'auto' }}>
          {JSON.stringify(result, null, 2)}
        </Box>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Duplicates tab
// ---------------------------------------------------------------------------

function DuplicatesTab() {
  const [dups, setDups] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    dqApi.getSfAudit().then(data => {
      // Duplicates = anomalous_forms with >1 MAPS_TO edge
      setDups((data as any).anomalous_forms?.filter((f: any) => f.maps_to?.length > 1) ?? []);
      setLoading(false);
    });
  }, []);

  if (loading) return <CircularProgress />;

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Term</TableCell>
          <TableCell>Target 1</TableCell>
          <TableCell>Score 1</TableCell>
          <TableCell>Target 2</TableCell>
          <TableCell>Score 2</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {dups.length === 0
          ? <TableRow><TableCell colSpan={5}>No duplicates</TableCell></TableRow>
          : (dups as any[]).map((d, i) => (
            <TableRow key={i}>
              <TableCell><code>{d.normalized_term}</code></TableCell>
              <TableCell>{d.maps_to?.[0]?.concept_id ?? '-'}</TableCell>
              <TableCell>{d.maps_to?.[0]?.score?.toFixed(2) ?? '-'}</TableCell>
              <TableCell>{d.maps_to?.[1]?.concept_id ?? '-'}</TableCell>
              <TableCell>{d.maps_to?.[1]?.score?.toFixed(2) ?? '-'}</TableCell>
            </TableRow>
          ))}
      </TableBody>
    </Table>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function TerminologyPage() {
  const [tab, setTab] = useState(0);
  const [audit, setAudit] = useState<SurfaceFormAuditResult | null>(null);

  useEffect(() => {
    dqApi.getSfAudit().then(setAudit);
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700} mb={3}>Terminology</Typography>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
        <Tab label="Health report" />
        <Tab label="SF inspector" />
        <Tab label="Duplicates" />
      </Tabs>

      {tab === 0 && <HealthTab audit={audit} />}
      {tab === 1 && <InspectTab />}
      {tab === 2 && <DuplicatesTab />}
    </Box>
  );
}
