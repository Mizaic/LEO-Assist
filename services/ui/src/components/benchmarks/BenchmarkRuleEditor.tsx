'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Stepper from '@mui/material/Stepper';
import Step from '@mui/material/Step';
import StepLabel from '@mui/material/StepLabel';
import FormControl from '@mui/material/FormControl';
import FormLabel from '@mui/material/FormLabel';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import Chip from '@mui/material/Chip';
import Alert from '@mui/material/Alert';
import CircularProgress from '@mui/material/CircularProgress';
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined';
import Add from '@mui/icons-material/Add';
import Delete from '@mui/icons-material/Delete';
import PlayArrowOutlined from '@mui/icons-material/PlayArrowOutlined';
import {
  getPatientGraphSchema,
  type PatientGraphSchema,
} from '@/lib/api';
import {
  getBenchmarkRule,
  createBenchmarkRule,
  updateBenchmarkRule,
  getBenchmarkSets,
  runBenchmarkRule,
} from '@/lib/api';
import type { BenchmarkSet } from '@/lib/api/benchmarks';

const NODE_LABELS: Record<string, string> = {
  Patient: 'Patients',
  CancerEpisode: 'Cancer episodes',
  Encounter: 'Consultations',
  CSSAlert: 'Safety alerts',
};

const PROPERTY_LABELS: Record<string, string> = {
  cancer_type: 'Cancer type',
  status: 'Status',
  referral_date: 'Referral date',
  gender: 'Gender',
  'Patient.gender': 'Gender (patient)',
  date: 'Date',
  encounter_type: 'Encounter type',
  actioned: 'Actioned',
};

const GENDER_SPECIFIC_CANCERS = ['breast', 'prostate', 'gynaecological'];

const TEMPLATES = [
  { label: 'Patients by cancer type', nodeLabel: 'CancerEpisode', groupBy: 'cancer_type', filters: [] },
  { label: 'Episodes by status', nodeLabel: 'CancerEpisode', groupBy: 'status', filters: [] },
  {
    label: 'Male/female split (excl. gender-specific cancers)',
    nodeLabel: 'CancerEpisode',
    groupBy: 'Patient.gender',
    filters: [{ property: 'cancer_type', op: 'nin', value: GENDER_SPECIFIC_CANCERS }],
  },
  { label: 'Consultations this year', nodeLabel: 'Encounter', groupBy: undefined, filters: [{ property: 'date', op: 'between', value: ['2024-01-01', '2024-12-31'] }] },
];

const SCOPE_OPTIONS = [
  { value: 'practice', label: 'This practice' },
  { value: 'alliance', label: 'This alliance' },
  { value: 'all', label: 'All data (England)' },
];

interface BenchmarkRuleEditorProps {
  ruleId?: string;
}

export function BenchmarkRuleEditor({ ruleId }: BenchmarkRuleEditorProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(!!ruleId);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schema, setSchema] = useState<PatientGraphSchema | null>(null);
  const [benchmarkSets, setBenchmarkSets] = useState<BenchmarkSet[]>([]);
  const [activeStep, setActiveStep] = useState(0);

  const [name, setName] = useState('');
  const [nodeLabel, setNodeLabel] = useState('CancerEpisode');
  const [cohortVariant, setCohortVariant] = useState<'diagnosed' | 'referred_excluded' | 'all_referred'>('diagnosed');
  const [filters, setFilters] = useState<Array<{ property: string; op: string; value: unknown }>>([]);
  const [groupBy, setGroupBy] = useState<string | null>(null);
  const [scopeType, setScopeType] = useState('gp');
  const [scope, setScope] = useState('all');
  const [outputMetricId, setOutputMetricId] = useState('');
  const [benchmarkSetId, setBenchmarkSetId] = useState('');

  const [newFilterProp, setNewFilterProp] = useState('');
  const [newFilterOp, setNewFilterOp] = useState('eq');
  const [newFilterValue, setNewFilterValue] = useState('');

  useEffect(() => {
    getPatientGraphSchema().then(setSchema).catch(() => setError('Failed to load schema'));
    getBenchmarkSets().then(setBenchmarkSets).catch(() => {});
  }, []);

  useEffect(() => {
    if (ruleId) {
      setLoading(true);
      getBenchmarkRule(ruleId)
        .then((r) => {
          setName(r.name);
          const qd = r.query_definition || {};
          setNodeLabel((qd.nodeLabel as string) || 'CancerEpisode');
          setCohortVariant((qd.cohortVariant as typeof cohortVariant) || 'diagnosed');
          setFilters((qd.filters as Array<{ property: string; op: string; value: unknown }>) || []);
          setGroupBy((qd.groupBy as string) || null);
          setScopeType((qd.scopeType as string) || 'gp');
          setScope(r.scope || 'all');
          setOutputMetricId(r.output_metric_id || '');
          setBenchmarkSetId(r.benchmark_set_id || '');
        })
        .catch(() => setError('Failed to load rule'))
        .finally(() => setLoading(false));
    }
  }, [ruleId]);

  const addFilter = () => {
    if (!newFilterProp) return;
    let value: unknown = newFilterValue;
    if (newFilterOp === 'eq' && (newFilterValue === 'true' || newFilterValue === 'false')) {
      value = newFilterValue === 'true';
    } else if ((newFilterOp === 'in' || newFilterOp === 'nin') && newFilterValue.trim()) {
      value = newFilterValue.split(',').map((v) => v.trim()).filter(Boolean);
    }
    setFilters((prev) => [...prev, { property: newFilterProp, op: newFilterOp, value }]);
    setNewFilterProp('');
    setNewFilterValue('');
  };

  const removeFilter = (idx: number) => {
    setFilters((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    setError(null);
    setSaving(true);
    try {
      const queryDefinition = {
        nodeLabel,
        filters: filters.length ? filters : undefined,
        groupBy: groupBy ?? undefined,
        scopeType,
        cohortVariant: nodeLabel === 'CancerEpisode' ? cohortVariant : undefined,
      };
      const targetSetId = benchmarkSetId || `computed-${Date.now()}`;
      if (ruleId) {
        await updateBenchmarkRule(ruleId, {
          name,
          query_definition: queryDefinition,
          scope,
          output_metric_id: outputMetricId || name,
          benchmark_set_id: targetSetId,
        });
        router.push('/benchmarks');
      } else {
        await createBenchmarkRule({
          name,
          query_definition: queryDefinition,
          scope,
          output_metric_id: outputMetricId || name,
          benchmark_set_id: targetSetId,
        });
        router.push('/benchmarks');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleRun = async () => {
    if (!ruleId) return;
    setError(null);
    setRunning(true);
    try {
      await runBenchmarkRule(ruleId);
      setRunning(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run');
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!schema) {
    return <Alert severity="error">Could not load schema</Alert>;
  }

  const filterOpts = schema.filters?.[nodeLabel] ?? [];
  const groupByOpts = schema.groupBy?.[nodeLabel] ?? [];
  const scopeOpts = schema.scopeTypes ?? [{ scopeType: 'gp', label: 'Practice' }, { scopeType: 'alliance', label: 'Alliance' }];

  const steps = ruleId
    ? ['Query', 'Scope & Output', 'Run']
    : ['What to count', 'Filters', 'Group & Scope', 'Output config', 'Save'];

  const isEditMode = !!ruleId;

  return (
    <Box sx={{ p: 3, maxWidth: 640 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <Button variant="text" startIcon={<ArrowBackOutlined />} onClick={() => router.push('/benchmarks')}>
          Back
        </Button>
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          {ruleId ? 'Edit Benchmark Rule' : 'New Benchmark Rule'}
        </Typography>
        {ruleId && (
          <Button variant="outlined" startIcon={<PlayArrowOutlined />} onClick={handleRun} disabled={running}>
            {running ? 'Running...' : 'Run now'}
          </Button>
        )}
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Stepper activeStep={activeStep} sx={{ mb: 3 }}>
        {steps.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {!isEditMode && activeStep === 0 && (
        <Card>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>What do you want to count?</Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 2 }}>
              {schema.aggregationTargets?.map((t) => (
                <Card
                  key={t.nodeLabel}
                  variant="outlined"
                  sx={{
                    cursor: 'pointer',
                    borderColor: nodeLabel === t.nodeLabel ? 'primary.main' : 'divider',
                    borderWidth: nodeLabel === t.nodeLabel ? 2 : 1,
                    minWidth: 140,
                  }}
                  onClick={() => setNodeLabel(t.nodeLabel)}
                >
                  <CardContent sx={{ py: 1.5 }}>
                    <Typography fontWeight={500}>{NODE_LABELS[t.nodeLabel] ?? t.nodeLabel}</Typography>
                  </CardContent>
                </Card>
              ))}
            </Box>
            {nodeLabel === 'CancerEpisode' && (
              <FormControl size="small" fullWidth sx={{ mb: 2 }}>
                <FormLabel>Cohort</FormLabel>
                <Select value={cohortVariant} onChange={(e) => setCohortVariant(e.target.value as typeof cohortVariant)}>
                  <MenuItem value="diagnosed">Diagnosed (cancer confirmed)</MenuItem>
                  <MenuItem value="referred_excluded">Referred, cancer excluded</MenuItem>
                  <MenuItem value="all_referred">All referred</MenuItem>
                </Select>
              </FormControl>
            )}
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
              {TEMPLATES.map((t) => (
                <Chip
                  key={t.label}
                  label={t.label}
                  onClick={() => {
                    setNodeLabel(t.nodeLabel);
                    setGroupBy(t.groupBy ?? null);
                    setFilters(t.filters ?? []);
                    if ('cohortVariant' in t && t.cohortVariant) setCohortVariant(t.cohortVariant as typeof cohortVariant);
                    setActiveStep(1);
                  }}
                  variant="outlined"
                  sx={{ cursor: 'pointer' }}
                />
              ))}
            </Box>
            <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
              <Button variant="contained" onClick={() => setActiveStep(1)}>Next</Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {!isEditMode && activeStep === 1 && (
        <Card>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>Filters (optional)</Typography>
            {filters.length > 0 && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                {filters.map((f, i) => (
                  <Chip key={i} label={`${PROPERTY_LABELS[f.property] ?? f.property} ${f.op} ${String(f.value)}`} onDelete={() => removeFilter(i)} size="small" />
                ))}
              </Box>
            )}
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <FormLabel>Property</FormLabel>
                <Select value={newFilterProp} onChange={(e) => setNewFilterProp(e.target.value)} displayEmpty>
                  <MenuItem value="">Select...</MenuItem>
                  {filterOpts.map((f) => (
                    <MenuItem key={f.property} value={f.property}>{PROPERTY_LABELS[f.property] ?? f.property}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 100 }}>
                <FormLabel>Operator</FormLabel>
                <Select value={newFilterOp} onChange={(e) => setNewFilterOp(e.target.value)}>
                  <MenuItem value="eq">equals</MenuItem>
                  <MenuItem value="neq">not equals</MenuItem>
                  <MenuItem value="in">in list</MenuItem>
                  <MenuItem value="nin">not in list</MenuItem>
                  <MenuItem value="between">between</MenuItem>
                </Select>
              </FormControl>
              <TextField size="small" label="Value" value={newFilterValue} onChange={(e) => setNewFilterValue(e.target.value)} placeholder="e.g. Lung" sx={{ minWidth: 120 }} />
              <Button startIcon={<Add />} onClick={addFilter} disabled={!newFilterProp}>Add filter</Button>
            </Box>
            <Box sx={{ mt: 3, display: 'flex', justifyContent: 'space-between' }}>
              <Button onClick={() => setActiveStep(0)}>Back</Button>
              <Button variant="contained" onClick={() => setActiveStep(2)}>Next</Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {!isEditMode && activeStep === 2 && (
        <Card>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>Group & scope</Typography>
            <FormControl size="small" fullWidth sx={{ mb: 2 }}>
              <FormLabel>Group by</FormLabel>
              <Select value={groupBy ?? ''} onChange={(e) => setGroupBy(e.target.value || null)} displayEmpty>
                <MenuItem value="">Just the total</MenuItem>
                {groupByOpts.map((opt) => (
                  <MenuItem key={opt} value={opt}>{PROPERTY_LABELS[opt] ?? opt}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small" fullWidth>
              <FormLabel>Tenant scope</FormLabel>
              <Select value={scopeType} onChange={(e) => setScopeType(e.target.value)}>
                {scopeOpts.map((s) => (
                  <MenuItem key={s.scopeType} value={s.scopeType}>{s.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <Box sx={{ mt: 3, display: 'flex', justifyContent: 'space-between' }}>
              <Button onClick={() => setActiveStep(1)}>Back</Button>
              <Button variant="contained" onClick={() => setActiveStep(3)}>Next</Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {(!isEditMode ? activeStep === 3 : activeStep === 0) && (
        <Card>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>Output config</Typography>
            <TextField fullWidth size="small" label="Rule name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Cancer by type" sx={{ mb: 2 }} />
            <FormControl size="small" fullWidth sx={{ mb: 2 }}>
              <FormLabel>Compute for</FormLabel>
              <Select value={scope} onChange={(e) => setScope(e.target.value)}>
                {SCOPE_OPTIONS.map((s) => (
                  <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField fullWidth size="small" label="Output metric ID" value={outputMetricId} onChange={(e) => setOutputMetricId(e.target.value)} placeholder="e.g. cancer_by_type" sx={{ mb: 2 }} />
            <FormControl size="small" fullWidth>
              <FormLabel>Target benchmark set</FormLabel>
              <Select value={benchmarkSetId} onChange={(e) => setBenchmarkSetId(e.target.value)} displayEmpty>
                <MenuItem value="">Create new set</MenuItem>
                {benchmarkSets.map((s) => (
                  <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>
                ))}
              </Select>
            </FormControl>
            {!isEditMode && (
              <Box sx={{ mt: 3, display: 'flex', justifyContent: 'space-between' }}>
                <Button onClick={() => setActiveStep(2)}>Back</Button>
                <Button variant="contained" onClick={handleSave} disabled={saving || !name}>
                  {saving ? 'Saving...' : 'Save'}
                </Button>
              </Box>
            )}
            {isEditMode && (
              <Box sx={{ mt: 3, display: 'flex', justifyContent: 'space-between' }}>
                <Button onClick={() => router.push('/benchmarks')}>Cancel</Button>
                <Button variant="contained" onClick={handleSave} disabled={saving}>
                  {saving ? 'Saving...' : 'Update'}
                </Button>
              </Box>
            )}
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
