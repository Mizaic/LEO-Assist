/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import AddOutlined from '@mui/icons-material/AddOutlined';
import UploadOutlined from '@mui/icons-material/UploadOutlined';
import DeleteOutlined from '@mui/icons-material/DeleteOutlined';
import EditOutlined from '@mui/icons-material/EditOutlined';
import PlayArrowOutlined from '@mui/icons-material/PlayArrowOutlined';
import OpenInNewOutlined from '@mui/icons-material/OpenInNewOutlined';
import ConfirmDialog from '@/components/ConfirmDialog';
import { getBenchmarkSets, getBenchmarkRules, deleteBenchmarkSet, deleteBenchmarkRule, runBenchmarkRule } from '@/lib/api';
import type { BenchmarkSet, BenchmarkRule } from '@/lib/api/benchmarks';

export function BenchmarkSetList() {
  const router = useRouter();
  const [sets, setSets] = useState<BenchmarkSet[]>([]);
  const [rules, setRules] = useState<BenchmarkRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDeleteSet, setConfirmDeleteSet] = useState<string | null>(null);
  const [confirmDeleteRule, setConfirmDeleteRule] = useState<string | null>(null);

  useEffect(() => {
    load();
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const [setsData, rulesData] = await Promise.all([getBenchmarkSets(), getBenchmarkRules()]);
      setSets(setsData);
      setRules(rulesData);
    } catch {
      setSets([]);
      setRules([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSet = async (id: string) => {
    setConfirmDeleteSet(null);
    try {
      await deleteBenchmarkSet(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete');
    }
  };

  const handleDeleteRule = async (id: string) => {
    setConfirmDeleteRule(null);
    try {
      await deleteBenchmarkRule(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete');
    }
  };

  const handleRunRule = async (id: string) => {
    try {
      await runBenchmarkRule(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to run rule');
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
        <CircularProgress aria-label="Loading" />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 1000 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 600 }}>
          Benchmarks
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button variant="outlined" startIcon={<UploadOutlined />} onClick={() => router.push('/benchmarks/upload')}>
            Upload
          </Button>
          <Button variant="contained" startIcon={<AddOutlined />} onClick={() => router.push('/benchmarks/rules/new')}>
            New Rule
          </Button>
        </Box>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Upload benchmark data (e.g. NCDA, PHE) or create rules to compute benchmarks from your patient graph.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
            Benchmark Sets
          </Typography>
          {sets.length === 0 ? (
            <Typography color="text.secondary">No benchmark sets yet. Upload JSON or run a rule.</Typography>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Name</TableCell>
                    <TableCell>Source</TableCell>
                    <TableCell>Year</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sets.map((s) => (
                    <TableRow
                      key={s.id}
                      hover
                      sx={{ cursor: 'pointer' }}
                      onClick={() => router.push(`/benchmarks/sets/${s.id}`)}
                    >
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>{s.name}</Typography>
                        <Typography variant="caption" color="text.secondary">{s.id}</Typography>
                      </TableCell>
                      <TableCell>
                        <Chip label={s.source} size="small" variant="outlined" />
                      </TableCell>
                      <TableCell>{s.audit_year ?? '-'}</TableCell>
                      <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                        <IconButton
                          size="small"
                          onClick={() => router.push(`/benchmarks/sets/${s.id}`)}
                          title="View details"
                          aria-label="View benchmark set details"
                        >
                          <OpenInNewOutlined fontSize="small" />
                        </IconButton>
                        <IconButton size="small" onClick={() => setConfirmDeleteSet(s.id)} color="error" aria-label="Delete benchmark set">
                          <DeleteOutlined fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
            Benchmark Rules
          </Typography>
          {rules.length === 0 ? (
            <Typography color="text.secondary">No rules yet. Create a rule to compute benchmarks from your data.</Typography>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Name</TableCell>
                    <TableCell>Scope</TableCell>
                    <TableCell>Last Run</TableCell>
                    <TableCell align="right">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rules.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>{r.name}</TableCell>
                      <TableCell>
                        <Chip label={r.scope} size="small" variant="outlined" />
                      </TableCell>
                      <TableCell>{r.last_run_at ? new Date(r.last_run_at).toLocaleDateString() : '-'}</TableCell>
                      <TableCell align="right">
                        <IconButton size="small" onClick={() => handleRunRule(r.id)} title="Run now" aria-label="Run now">
                          <PlayArrowOutlined fontSize="small" />
                        </IconButton>
                        <IconButton size="small" onClick={() => router.push(`/benchmarks/rules/${r.id}`)} title="Edit" aria-label="Edit">
                          <EditOutlined fontSize="small" />
                        </IconButton>
                        <IconButton size="small" onClick={() => setConfirmDeleteRule(r.id)} color="error" aria-label="Delete benchmark rule">
                          <DeleteOutlined fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>
      {confirmDeleteSet && (
        <ConfirmDialog
          title="Delete benchmark set?"
          body="This will permanently delete the benchmark set and all its values."
          confirmLabel="Delete"
          variant="danger"
          onConfirm={() => handleDeleteSet(confirmDeleteSet)}
          onCancel={() => setConfirmDeleteSet(null)}
        />
      )}
      {confirmDeleteRule && (
        <ConfirmDialog
          title="Delete benchmark rule?"
          body="This will permanently delete the benchmark rule."
          confirmLabel="Delete"
          variant="danger"
          onConfirm={() => handleDeleteRule(confirmDeleteRule)}
          onCancel={() => setConfirmDeleteRule(null)}
        />
      )}
    </Box>
  );
}
