'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Divider from '@mui/material/Divider';
import FormControl from '@mui/material/FormControl';
import IconButton from '@mui/material/IconButton';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined';
import DeleteOutlined from '@mui/icons-material/DeleteOutlined';
import EditOutlined from '@mui/icons-material/EditOutlined';
import CheckOutlined from '@mui/icons-material/CheckOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import ConfirmDialog from '@/components/ConfirmDialog';
import {
  getBenchmarkSet,
  getBenchmarkCategories,
  getBenchmarkScopes,
  getBenchmarkValues,
  updateBenchmarkValue,
  deleteBenchmarkValue,
} from '@/lib/api';
import type { BenchmarkSet, BenchmarkValue, BenchmarkScope } from '@/lib/api/benchmarks';

const SCOPE_TYPE_LABELS: Record<string, string> = {
  gp_practice: 'GP Practice',
  cancer_alliance: 'Cancer Alliance',
  national: 'England / National',
  unknown: 'Unknown',
};

const SCOPE_COLOURS: Record<string, string> = {
  gp_practice: 'primary',
  cancer_alliance: 'success',
  national: 'warning',
};

interface EditState {
  valueId: string;
  currentValue: string;
}

interface Props {
  setId: string;
}

export function BenchmarkSetDetail({ setId }: Props) {
  const router = useRouter();
  const [set, setSet] = useState<BenchmarkSet | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [scopes, setScopes] = useState<BenchmarkScope[]>([]);
  const [values, setValues] = useState<BenchmarkValue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedScopeId, setSelectedScopeId] = useState<string>('');

  const [editState, setEditState] = useState<EditState | null>(null);
  const [confirmDeleteValueId, setConfirmDeleteValueId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [setData, cats, sc] = await Promise.all([
        getBenchmarkSet(setId),
        getBenchmarkCategories(setId),
        getBenchmarkScopes(setId),
      ]);
      setSet(setData);
      setCategories(cats);
      setScopes(sc);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load benchmark set');
    } finally {
      setLoading(false);
    }
  }, [setId]);

  const loadValues = useCallback(async () => {
    try {
      const params: Record<string, string> = {};
      if (selectedCategory) params.category = selectedCategory;
      if (selectedScopeId) params.scope_id = selectedScopeId;
      const data = await getBenchmarkValues(setId, params);
      setValues(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load values');
    }
  }, [setId, selectedCategory, selectedScopeId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (!loading) loadValues(); }, [loading, loadValues]);

  const handleSaveEdit = async () => {
    if (!editState) return;
    const newVal = parseFloat(editState.currentValue);
    if (isNaN(newVal)) { setError('Value must be a number'); return; }
    setSaving(true);
    try {
      await updateBenchmarkValue(setId, editState.valueId, newVal);
      setEditState(null);
      await loadValues();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update value');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteValue = async (valueId: string) => {
    setConfirmDeleteValueId(null);
    try {
      await deleteBenchmarkValue(setId, valueId);
      await loadValues();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete value');
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
        <CircularProgress aria-label="Loading benchmark set" />
      </Box>
    );
  }

  if (!set) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">Benchmark set not found.</Alert>
        <Button sx={{ mt: 2 }} startIcon={<ArrowBackOutlined />} onClick={() => router.push('/benchmarks')}>
          Back to Benchmarks
        </Button>
      </Box>
    );
  }

  const practiceScopes = scopes.filter((s) => s.scope_type === 'gp_practice');
  const otherScopes = scopes.filter((s) => s.scope_type !== 'gp_practice');
  const allScopes = [...practiceScopes, ...otherScopes];

  return (
    <Box sx={{ p: 3, maxWidth: 1200 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <Button variant="text" startIcon={<ArrowBackOutlined />} onClick={() => router.push('/benchmarks')}>
          Back
        </Button>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 600 }}>{set.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            ID: {set.id} · Year: {set.audit_year ?? '—'} · Source: {set.source}
          </Typography>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Scope summary */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
            Organisations in this set
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {allScopes.map((s) => (
              <Chip
                key={s.scope_id}
                label={`${s.scope_name} (${SCOPE_TYPE_LABELS[s.scope_type] ?? s.scope_type})`}
                size="small"
                color={(SCOPE_COLOURS[s.scope_type] as 'primary' | 'success' | 'warning') ?? 'default'}
                variant="outlined"
              />
            ))}
            {allScopes.length === 0 && (
              <Typography variant="body2" color="text.secondary">No scope data loaded yet.</Typography>
            )}
          </Box>
        </CardContent>
      </Card>

      {/* Filters */}
      <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel>Category</InputLabel>
          <Select
            value={selectedCategory}
            label="Category"
            onChange={(e) => setSelectedCategory(e.target.value)}
          >
            <MenuItem value="">All categories</MenuItem>
            {categories.map((c) => (
              <MenuItem key={c} value={c}>{c}</MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 240 }}>
          <InputLabel>Organisation</InputLabel>
          <Select
            value={selectedScopeId}
            label="Organisation"
            onChange={(e) => setSelectedScopeId(e.target.value)}
          >
            <MenuItem value="">All organisations</MenuItem>
            {allScopes.map((s) => (
              <MenuItem key={s.scope_id} value={s.scope_id}>
                {s.scope_name} ({SCOPE_TYPE_LABELS[s.scope_type] ?? s.scope_type})
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <Button size="small" variant="outlined" onClick={() => { setSelectedCategory(''); setSelectedScopeId(''); }}>
          Clear filters
        </Button>
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Values table */}
      <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
        Benchmark Values ({values.length})
      </Typography>

      {values.length === 0 ? (
        <Typography color="text.secondary" variant="body2">
          No values match the current filters.
        </Typography>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 600 }}>Metric ID</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Label</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Organisation</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Type</TableCell>
                <TableCell sx={{ fontWeight: 600 }} align="right">Value</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>Unit</TableCell>
                <TableCell align="right" sx={{ fontWeight: 600 }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {values.map((v) => {
                const isEditing = editState?.valueId === v.id;
                return (
                  <TableRow key={`${v.metric_id}-${v.scope_id}`} hover>
                    <TableCell>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                        {v.metric_id}
                      </Typography>
                    </TableCell>
                    <TableCell>{v.label}</TableCell>
                    <TableCell>
                      <Tooltip title={`ID: ${v.scope_id}`}>
                        <span>{v.scope_name}</span>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={SCOPE_TYPE_LABELS[v.scope_type] ?? v.scope_type}
                        size="small"
                        color={(SCOPE_COLOURS[v.scope_type] as 'primary' | 'success' | 'warning') ?? 'default'}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right">
                      {isEditing ? (
                        <TextField
                          size="small"
                          value={editState.currentValue}
                          onChange={(e) => setEditState({ ...editState, currentValue: e.target.value })}
                          sx={{ width: 100 }}
                          inputProps={{ 'aria-label': 'Edit value' }}
                          autoFocus
                        />
                      ) : (
                        <Typography variant="body2">
                          {v.value_json
                            ? Object.entries(v.value_json).map(([k, val]) => `${k}: ${val}`).join(', ')
                            : (v.value ?? '—')}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>{v.unit || '—'}</TableCell>
                    <TableCell align="right">
                      {isEditing ? (
                        <>
                          <IconButton size="small" onClick={handleSaveEdit} disabled={saving} aria-label="Save value" color="primary">
                            <CheckOutlined fontSize="small" />
                          </IconButton>
                          <IconButton size="small" onClick={() => setEditState(null)} aria-label="Cancel edit">
                            <CloseOutlined fontSize="small" />
                          </IconButton>
                        </>
                      ) : (
                        <>
                          {v.id && !v.value_json && (
                            <IconButton
                              size="small"
                              aria-label="Edit value"
                              onClick={() => setEditState({ valueId: v.id!, currentValue: String(v.value ?? '') })}
                            >
                              <EditOutlined fontSize="small" />
                            </IconButton>
                          )}
                          {v.id && (
                            <IconButton
                              size="small"
                              color="error"
                              aria-label="Delete value"
                              onClick={() => setConfirmDeleteValueId(v.id!)}
                            >
                              <DeleteOutlined fontSize="small" />
                            </IconButton>
                          )}
                        </>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {confirmDeleteValueId && (
        <ConfirmDialog
          title="Delete benchmark value?"
          body="This will permanently remove this benchmark value. This cannot be undone."
          confirmLabel="Delete"
          variant="danger"
          onConfirm={() => handleDeleteValue(confirmDeleteValueId)}
          onCancel={() => setConfirmDeleteValueId(null)}
        />
      )}
    </Box>
  );
}
