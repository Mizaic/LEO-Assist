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
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  Typography,
} from '@mui/material';
import Link from 'next/link';
import { dqApi } from '@/lib/api/dq';

function OrphansTab() {
  const [rows, setRows] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    dqApi.getDomainOrphans()
      .then(d => setRows(d.orphans))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <CircularProgress />;
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Concept ID</TableCell>
          <TableCell>Preferred term</TableCell>
          <TableCell>Active</TableCell>
          <TableCell align="right">Patients affected</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.length === 0
          ? <TableRow><TableCell colSpan={4}>No orphan concepts</TableCell></TableRow>
          : (rows as any[]).map((r, i) => (
            <TableRow key={i}>
              <TableCell><code>{r.concept_id}</code></TableCell>
              <TableCell>{r.preferred_term ?? '-'}</TableCell>
              <TableCell>{r.active ? 'Yes' : 'No'}</TableCell>
              <TableCell align="right">{r.patient_count}</TableCell>
            </TableRow>
          ))}
      </TableBody>
    </Table>
  );
}

function GapsTab() {
  const [rows, setRows] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    dqApi.getDomainGaps()
      .then(d => setRows(d.gaps))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <CircularProgress />;
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Patient</TableCell>
          <TableCell>Site</TableCell>
          <TableCell>Gap type</TableCell>
          <TableCell>Date</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.length === 0
          ? <TableRow><TableCell colSpan={4}>No pathway gaps</TableCell></TableRow>
          : (rows as any[]).map((r, i) => (
            <TableRow key={i}>
              <TableCell>
                <Link href={`/admin/data-quality/patient/${r.patient_id}`}>{r.patient_id}</Link>
              </TableCell>
              <TableCell>{r.site}</TableCell>
              <TableCell>{r.gap_type}</TableCell>
              <TableCell>{r.date ?? '-'}</TableCell>
            </TableRow>
          ))}
      </TableBody>
    </Table>
  );
}

function CoverageTab() {
  const [data, setData] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    dqApi.getDomainCoverage()
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <CircularProgress />;
  if (error) return <Alert severity="error">{error}</Alert>;
  return (
    <Box component="pre" sx={{ bgcolor: 'grey.100', p: 2, borderRadius: 1, fontSize: 12, overflow: 'auto' }}>
      {JSON.stringify(data, null, 2)}
    </Box>
  );
}

export default function DomainPage() {
  const [tab, setTab] = useState(0);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700} mb={3}>Domain coverage</Typography>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
        <Tab label="Orphan concepts" />
        <Tab label="Pathway gaps" />
        <Tab label="Coverage" />
      </Tabs>

      {tab === 0 && <OrphansTab />}
      {tab === 1 && <GapsTab />}
      {tab === 2 && <CoverageTab />}
    </Box>
  );
}
