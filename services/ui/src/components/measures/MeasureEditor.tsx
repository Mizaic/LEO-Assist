'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import FormLabel from '@mui/material/FormLabel';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CircularProgress from '@mui/material/CircularProgress';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import SaveOutlined from '@mui/icons-material/SaveOutlined';
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined';
import Add from '@mui/icons-material/Add';
import FolderOutlined from '@mui/icons-material/FolderOutlined';
import { getMeasure, createMeasure, updateMeasure, getBenchmarkSets, getBenchmarkValues } from '@/lib/api';
import type { Measure } from '@/lib/types/fhir';
import type { BenchmarkSet, BenchmarkValue } from '@/lib/api/benchmarks';
import { LibraryPicker } from './LibraryPicker';
import { QueryBuilder } from './QueryBuilder';

const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'active', label: 'Active' },
  { value: 'retired', label: 'Retired' },
];

const CATEGORY_OPTIONS = [
  { value: 'demographics', label: 'Demographics' },
  { value: 'cancer-type', label: 'Cancer Type' },
  { value: 'place-of-presentation', label: 'Place of Presentation' },
  { value: 'consultations', label: 'Consultations' },
  { value: 'investigations', label: 'Investigations' },
  { value: 'referrals', label: 'Referrals' },
  { value: 'intervals', label: 'Intervals' },
  { value: 'safety-netting', label: 'Safety Netting' },
  { value: 'avoidable-delays', label: 'Avoidable Delays' },
];

interface MeasureEditorProps {
  measureId?: string;
}

export function MeasureEditor({ measureId }: MeasureEditorProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(!!measureId);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [queryTab, setQueryTab] = useState<'build' | 'existing'>(measureId ? 'existing' : 'build');
  const [formData, setFormData] = useState({
    name: '',
    title: '',
    status: 'draft' as 'draft' | 'active' | 'retired' | 'unknown',
    description: '',
    category: '',
    libraryId: '',
    benchmarkSetId: '',
    benchmarkMetricId: '',
  });
  const [benchmarkSets, setBenchmarkSets] = useState<BenchmarkSet[]>([]);
  const [benchmarkMetrics, setBenchmarkMetrics] = useState<BenchmarkValue[]>([]);

  useEffect(() => {
    if (measureId) loadMeasure();
  }, [measureId]);

  useEffect(() => {
    getBenchmarkSets().then(setBenchmarkSets).catch(() => {});
  }, []);

  useEffect(() => {
    if (!formData.benchmarkSetId) {
      setBenchmarkMetrics([]);
      return;
    }
    getBenchmarkValues(formData.benchmarkSetId)
      .then((vals) => {
        const seen = new Set<string>();
        const unique = vals.filter((v) => {
          if (seen.has(v.metric_id)) return false;
          seen.add(v.metric_id);
          return true;
        });
        setBenchmarkMetrics(unique);
      })
      .catch(() => setBenchmarkMetrics([]));
  }, [formData.benchmarkSetId]);

  const loadMeasure = async () => {
    if (!measureId) return;
    setLoading(true);
    try {
      const measure = await getMeasure(measureId);
      const bc = measure.benchmarkConfig;
      setFormData({
        name: measure.name || '',
        title: measure.title || '',
        status: measure.status || 'draft',
        description: measure.description || '',
        category: measure.topic?.[0]?.coding?.[0]?.code || '',
        libraryId: measure.library?.[0]?.replace('Library/', '') || '',
        benchmarkSetId: bc?.benchmarkSetId || '',
        benchmarkMetricId: bc?.metricMapping?.[0]?.benchmarkMetricId || '',
      });
    } catch {
      setError('Failed to load measure');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSaving(true);

    try {
      const measure: Measure = {
        resourceType: 'Measure',
        name: formData.name,
        title: formData.title,
        status: formData.status,
        description: formData.description,
        topic: formData.category ? [{
          coding: [{ system: 'http://example.org/fhir/CodeSystem/measure-category', code: formData.category }],
        }] : undefined,
        library: formData.libraryId ? [`Library/${formData.libraryId}`] : undefined,
        benchmarkConfig:
          formData.benchmarkSetId && formData.benchmarkMetricId
            ? {
                benchmarkSetId: formData.benchmarkSetId,
                metricMapping: [{ benchmarkMetricId: formData.benchmarkMetricId }],
              }
            : undefined,
      };

      if (measureId) {
        measure.id = measureId;
        await updateMeasure(measureId, measure);
        setSuccess('Measure updated successfully');
      } else {
        const created = await createMeasure(measure);
        setSuccess('Measure created successfully');
        router.push('/measures');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save measure');
    } finally {
      setSaving(false);
    }
  };

  const updateField = (field: keyof typeof formData, value: string) => {
    setFormData((prev) => {
      const next = { ...prev, [field]: value };
      if (field === 'benchmarkSetId') next.benchmarkMetricId = '';
      return next;
    });
  };

  if (loading) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}><CircularProgress aria-label="Loading" /></Box>;
  }

  return (
    <Box sx={{ p: 3, maxWidth: 800 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Button variant="text" startIcon={<ArrowBackOutlined />} aria-label="Back to Measures" onClick={() => router.push('/measures')} />
          <Typography variant="h5" sx={{ fontWeight: 600 }}>
            {measureId ? 'Edit Measure' : 'Create Measure'}
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<SaveOutlined />} onClick={handleSubmit} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <Card>
          <CardContent sx={{ p: 3 }}>
            <Typography sx={{ fontSize: '1rem', fontWeight: 600, mb: 2 }}>Basic Information</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
              <TextField label="Name" required value={formData.name} onChange={(e) => updateField('name', e.target.value)} placeholder="e.g., mvp-demographics" size="small" />
              <FormControl size="small" required>
                <FormLabel sx={{ mb: 0.5, fontSize: '0.875rem' }}>Status</FormLabel>
                <Select value={formData.status} onChange={(e) => updateField('status', e.target.value)}>
                  {STATUS_OPTIONS.map((opt) => <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>)}
                </Select>
              </FormControl>
            </Box>
            <TextField label="Title" required fullWidth value={formData.title} onChange={(e) => updateField('title', e.target.value)} placeholder="e.g., Patient Demographics Summary" size="small" sx={{ mt: 2 }} />
            <TextField label="Description" fullWidth multiline rows={3} value={formData.description} onChange={(e) => updateField('description', e.target.value)} placeholder="Describe what this measure calculates..." size="small" sx={{ mt: 2 }} />
          </CardContent>
        </Card>

        <Card>
          <CardContent sx={{ p: 3 }}>
            <Typography sx={{ fontSize: '1rem', fontWeight: 600, mb: 2 }}>Classification</Typography>
            <FormControl size="small" fullWidth>
              <FormLabel sx={{ mb: 0.5, fontSize: '0.875rem' }}>Category</FormLabel>
              <Select value={formData.category} onChange={(e) => updateField('category', e.target.value)} displayEmpty>
                <MenuItem value="">Select a category...</MenuItem>
                {CATEGORY_OPTIONS.map((opt) => <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>)}
              </Select>
            </FormControl>
          </CardContent>
        </Card>

        <Card>
          <CardContent sx={{ p: 3 }}>
            <Typography sx={{ fontSize: '1rem', fontWeight: 600, mb: 2 }}>Query Definition</Typography>
            <Tabs value={queryTab} onChange={(_, v) => setQueryTab(v)} sx={{ mb: 2 }}>
              <Tab value="build" label="Build a new query" icon={<Add />} iconPosition="start" />
              <Tab value="existing" label="Use an existing query" icon={<FolderOutlined />} iconPosition="start" />
            </Tabs>
            {queryTab === 'build' && (
              <QueryBuilder
                onLibraryCreated={(libraryId) => {
                  updateField('libraryId', libraryId);
                  setQueryTab('existing');
                }}
                benchmarkSetId={formData.benchmarkSetId}
                benchmarkMetricId={formData.benchmarkMetricId}
                onBenchmarkConfigChange={(c) => {
                  setFormData((prev) => ({
                    ...prev,
                    benchmarkSetId: c?.benchmarkSetId ?? '',
                    benchmarkMetricId: c?.benchmarkMetricId ?? '',
                  }));
                }}
              />
            )}
            {queryTab === 'existing' && (
              <LibraryPicker value={formData.libraryId} onChange={(id) => updateField('libraryId', id)} />
            )}
          </CardContent>
        </Card>

        {queryTab === 'existing' && (
          <Card>
            <CardContent sx={{ p: 3 }}>
              <Typography sx={{ fontSize: '1rem', fontWeight: 600, mb: 2 }}>Benchmark Comparison</Typography>
              <Typography sx={{ fontSize: '0.875rem', color: 'text.secondary', mb: 2 }}>
                Compare measure results with reference benchmarks (e.g. NCDA, PHE).
              </Typography>
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
                <FormControl size="small" fullWidth>
                  <FormLabel sx={{ mb: 0.5, fontSize: '0.875rem' }}>Benchmark Set</FormLabel>
                  <Select
                    value={formData.benchmarkSetId}
                    onChange={(e) => updateField('benchmarkSetId', e.target.value)}
                    displayEmpty
                  >
                    <MenuItem value="">None</MenuItem>
                    {benchmarkSets.map((s) => (
                      <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl size="small" fullWidth disabled={!formData.benchmarkSetId}>
                  <FormLabel sx={{ mb: 0.5, fontSize: '0.875rem' }}>Metric</FormLabel>
                  <Select
                    value={formData.benchmarkMetricId}
                    onChange={(e) => updateField('benchmarkMetricId', e.target.value)}
                    displayEmpty
                  >
                    <MenuItem value="">Select metric...</MenuItem>
                    {benchmarkMetrics.map((v) => (
                      <MenuItem key={v.metric_id} value={v.metric_id}>{v.label || v.metric_id}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
            </CardContent>
          </Card>
        )}

        <Box sx={{ display: 'flex', gap: 1.5, mt: 3 }}>
          <Button variant="outlined" onClick={() => router.push('/measures')}>Cancel</Button>
          <Button variant="contained" type="submit" disabled={saving}>
            {saving ? 'Saving...' : measureId ? 'Update Measure' : 'Create Measure'}
          </Button>
        </Box>
      </form>
    </Box>
  );
}
