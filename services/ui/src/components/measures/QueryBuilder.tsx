'use client';

import { useState, useEffect } from 'react';
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
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import Add from '@mui/icons-material/Add';
import Delete from '@mui/icons-material/Delete';
import {
  getPatientGraphSchema,
  generateMeasureQuery,
  previewMeasureQuery,
  getBenchmarkSets,
  getBenchmarkValues,
  getBenchmarkComparison,
  getDistinctFilterValues,
  type PatientGraphSchema,
  type QueryDefinition,
} from '@/lib/api';
import type { BenchmarkSet, BenchmarkValue, BenchmarkPoint } from '@/lib/api';
import { useOrgId } from '@/context/OrgContext';
import { inferDataShape } from '@/lib/chartRecommendations';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { chartTheme, getSeriesColor } from '@/lib/chartTheme';

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
  referral_route: 'Referral route',
  place_of_presentation: 'Place of presentation',
  gender: 'Gender',
  'Patient.gender': 'Gender (patient)',
  'Patient.age_band_at_diagnosis': 'Age band at diagnosis',
  birthDate: 'Birth date',
  date: 'Date',
  encounter_type: 'Encounter type',
  actioned: 'Actioned',
  alert_type: 'Alert type',
  diagnosis_date: 'Diagnosis date',
  first_presentation_date: 'First presentation date',
  cancer_stage: 'Cancer stage',
  ethnicity: 'Ethnicity',
  primary_care_interval_band: 'Primary care interval band',
  diagnostic_interval_band: 'Diagnostic interval band',
  count_per_patient_band: 'Consultations per patient (<3 vs 3+)',
  count_per_patient: 'Consultations per patient',
};

const GENDER_SPECIFIC_CANCERS = ['breast', 'prostate', 'gynaecological'];

/** Date properties (fhirType date) - use date picker / financial year */
const DATE_PROPERTIES = ['referral_date', 'diagnosis_date', 'first_presentation_date', 'date', 'birthDate'];

/** Financial year: Apr 1 - Mar 31. "2024/25" = Apr 2024 to Mar 2025 */
function financialYearToRange(fy: string): [string, string] {
  const [startY] = fy.split('/').map(Number);
  return [`${startY}-04-01`, `${startY + 1}-03-31`];
}

function getFinancialYearOptions(count = 6): { label: string; value: string }[] {
  const current = new Date().getFullYear();
  const options: { label: string; value: string }[] = [];
  for (let i = 0; i < count; i++) {
    const y = current - i;
    const fy = `${y}/${String(y + 1).slice(-2)}`;
    options.push({
      label: `${fy} (Apr ${y} – Mar ${y + 1})`,
      value: fy,
    });
  }
  return options;
}

function formatFilterForDisplay(f: { property: string; op: string; value: unknown }): string {
  const opLabels: Record<string, string> = { eq: 'equals', neq: 'not equals', in: 'in', nin: 'not in', between: 'between' };
  const op = opLabels[f.op] ?? f.op;
  let valStr: string;
  if (Array.isArray(f.value) && f.value.length === 2) {
    const [a, b] = f.value as string[];
    const startY = a?.slice?.(0, 4);
    const endY = b?.slice?.(0, 4);
    const isFY =
      a?.endsWith?.('-04-01') &&
      b?.endsWith?.('-03-31') &&
      startY &&
      endY &&
      Number(endY) === Number(startY) + 1;
    valStr = isFY ? `${startY}/${String(Number(startY) + 1).slice(-2)} (Apr–Mar)` : `${a} to ${b}`;
  } else if (Array.isArray(f.value)) {
    valStr = (f.value as string[]).join(', ');
  } else {
    valStr = String(f.value);
  }
  return `${PROPERTY_LABELS[f.property] ?? f.property} ${op} ${valStr}`;
}

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
  { label: 'Safety alerts actioned', nodeLabel: 'CSSAlert', groupBy: undefined, filters: [{ property: 'actioned', op: 'eq', value: true }] },
  // NCDA measure templates (1, 2, 5, 7, 8, 11, 13, 14, 15)
  { label: 'NCDA 1: Sex distribution', nodeLabel: 'CancerEpisode', groupBy: 'Patient.gender', filters: [], cohortVariant: 'diagnosed' },
  { label: 'NCDA 2a: Age band at diagnosis', nodeLabel: 'CancerEpisode', groupBy: 'Patient.age_band_at_diagnosis', filters: [], cohortVariant: 'diagnosed' },
  { label: 'NCDA 2b: Median age at diagnosis', nodeLabel: 'CancerEpisode', groupBy: undefined, aggregation: 'median', valueProperty: 'age_at_diagnosis', filters: [], cohortVariant: 'diagnosed' },
  { label: 'NCDA 5: Cancer type', nodeLabel: 'CancerEpisode', groupBy: 'cancer_type', filters: [], cohortVariant: 'diagnosed' },
  { label: 'NCDA 7: Place of presentation', nodeLabel: 'CancerEpisode', groupBy: 'place_of_presentation', filters: [], cohortVariant: 'diagnosed' },
  { label: 'NCDA 8: Median consultations per patient', nodeLabel: 'Encounter', groupBy: undefined, aggregation: 'median', valueProperty: 'count_per_patient', filters: [], cohortVariant: undefined },
  { label: 'NCDA 11: Referral route', nodeLabel: 'CancerEpisode', groupBy: 'referral_route', filters: [], cohortVariant: 'diagnosed' },
  { label: 'NCDA 13: Median primary care interval', nodeLabel: 'CancerEpisode', groupBy: undefined, aggregation: 'median', valueProperty: 'primary_care_interval_days', filters: [], cohortVariant: 'diagnosed' },
  { label: 'NCDA 14: Median diagnostic interval', nodeLabel: 'CancerEpisode', groupBy: undefined, aggregation: 'median', valueProperty: 'diagnostic_interval_days', filters: [], cohortVariant: 'diagnosed' },
  { label: 'NCDA 15: Safety netting recorded (%)', nodeLabel: 'CancerEpisode', groupBy: undefined, aggregation: 'percentage', percentageProperty: 'safety_netting_recorded', filters: [], cohortVariant: 'diagnosed' },
];

interface QueryBuilderProps {
  onLibraryCreated: (libraryId: string) => void;
  benchmarkSetId?: string;
  benchmarkMetricId?: string;
  onBenchmarkConfigChange?: (config: { benchmarkSetId: string; benchmarkMetricId: string } | null) => void;
}

export function QueryBuilder({
  onLibraryCreated,
  benchmarkSetId = '',
  benchmarkMetricId = '',
  onBenchmarkConfigChange,
}: QueryBuilderProps) {
  const [schema, setSchema] = useState<PatientGraphSchema | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState(0);

  const [nodeLabel, setNodeLabel] = useState<string>('CancerEpisode');
  const [cohortVariant, setCohortVariant] = useState<'diagnosed' | 'referred_excluded' | 'all_referred'>('diagnosed');
  const [filters, setFilters] = useState<Array<{ property: string; op: string; value: unknown }>>([]);
  const [groupBy, setGroupBy] = useState<string | null>(null);
  const [scopeType, setScopeType] = useState<string>('gp');
  const [aggregation, setAggregation] = useState<'count' | 'median' | 'percentage'>('count');
  const [valueProperty, setValueProperty] = useState<string>('');
  const [percentageProperty, setPercentageProperty] = useState<string>('');

  const [newFilterProp, setNewFilterProp] = useState('');
  const [newFilterOp, setNewFilterOp] = useState('eq');
  const [newFilterValue, setNewFilterValue] = useState('');
  const [newFilterDateMode, setNewFilterDateMode] = useState<'financial' | 'custom'>('financial');
  const [newFilterFinancialYear, setNewFilterFinancialYear] = useState('');
  const [newFilterDateStart, setNewFilterDateStart] = useState('');
  const [newFilterDateEnd, setNewFilterDateEnd] = useState('');
  const [distinctValues, setDistinctValues] = useState<string[]>([]);
  const [distinctValuesLoading, setDistinctValuesLoading] = useState(false);
  const [newFilterSelectedValues, setNewFilterSelectedValues] = useState<string[]>([]);

  const [previewRows, setPreviewRows] = useState<Array<Record<string, unknown>> | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const orgId = useOrgId();

  const [benchmarkSets, setBenchmarkSets] = useState<BenchmarkSet[]>([]);
  const [benchmarkMetrics, setBenchmarkMetrics] = useState<BenchmarkValue[]>([]);
  const [benchmarkComparison, setBenchmarkComparison] = useState<BenchmarkPoint[] | null>(null);
  const [benchmarkComparisonLoading, setBenchmarkComparisonLoading] = useState(false);

  useEffect(() => {
    getPatientGraphSchema()
      .then(setSchema)
      .catch(() => setError('Failed to load schema'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    getBenchmarkSets().then(setBenchmarkSets).catch(() => {});
  }, []);

  useEffect(() => {
    if (!benchmarkSetId) {
      setBenchmarkMetrics([]);
      return;
    }
    getBenchmarkValues(benchmarkSetId)
      .then((vals) => {
        const seen = new Set<string>();
        setBenchmarkMetrics(vals.filter((v) => {
          if (seen.has(v.metric_id)) return false;
          seen.add(v.metric_id);
          return true;
        }));
      })
      .catch(() => setBenchmarkMetrics([]));
  }, [benchmarkSetId]);

  useEffect(() => {
    if (!benchmarkSetId || !benchmarkMetricId || !groupBy) {
      setBenchmarkComparison(null);
      return;
    }
    setBenchmarkComparisonLoading(true);
    getBenchmarkComparison(benchmarkSetId, benchmarkMetricId)
      .then(setBenchmarkComparison)
      .catch(() => setBenchmarkComparison(null))
      .finally(() => setBenchmarkComparisonLoading(false));
  }, [benchmarkSetId, benchmarkMetricId, groupBy]);

  useEffect(() => {
    if (!newFilterProp || !schema) {
      setDistinctValues([]);
      setNewFilterSelectedValues([]);
      return;
    }
    const filterDef = (schema.filters[nodeLabel] ?? []).find((f) => f.property === newFilterProp);
    if (!filterDef?.distinctFromNeo4j) {
      setDistinctValues([]);
      setNewFilterSelectedValues([]);
      return;
    }
    setDistinctValuesLoading(true);
    getDistinctFilterValues(nodeLabel, newFilterProp)
      .then(setDistinctValues)
      .catch(() => setDistinctValues([]))
      .finally(() => setDistinctValuesLoading(false));
    setNewFilterSelectedValues([]);
  }, [newFilterProp, nodeLabel, schema]);

  const buildDefinition = (): QueryDefinition => ({
    nodeLabel: nodeLabel,
    filters: filters.length ? filters : undefined,
    groupBy: groupBy ?? undefined,
    scopeType,
    cohortVariant: nodeLabel === 'CancerEpisode' ? cohortVariant : undefined,
    aggregation: aggregation !== 'count' ? aggregation : undefined,
    valueProperty:
      aggregation === 'median'
        ? (nodeLabel === 'Encounter' ? 'count_per_patient' : valueProperty || undefined)
        : undefined,
    percentageProperty: aggregation === 'percentage' && percentageProperty ? percentageProperty : undefined,
    percentageValue: aggregation === 'percentage' ? true : undefined,
  });

  useEffect(() => {
    if (
      newFilterOp === 'between' &&
      DATE_PROPERTIES.includes(newFilterProp) &&
      newFilterDateMode === 'financial' &&
      !newFilterFinancialYear
    ) {
      const opts = getFinancialYearOptions(1);
      if (opts[0]) setNewFilterFinancialYear(opts[0].value);
    }
  }, [newFilterProp, newFilterOp, newFilterDateMode]);

  useEffect(() => {
    if (activeStep !== 3) {
      setPreviewRows(null);
      setPreviewError(null);
      return;
    }
    if (!orgId) {
      setPreviewRows(null);
      setPreviewError(null);
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    previewMeasureQuery(buildDefinition(), orgId)
      .then((res) => {
        setPreviewRows(res.rows ?? []);
      })
      .catch((err) => {
        setPreviewError(err instanceof Error ? err.message : 'Preview failed');
        setPreviewRows(null);
      })
      .finally(() => setPreviewLoading(false));
  }, [activeStep, orgId, nodeLabel, filters, groupBy, scopeType, cohortVariant, aggregation, valueProperty, percentageProperty]);

  const handleTemplateSelect = (t: (typeof TEMPLATES)[0]) => {
    setNodeLabel(t.nodeLabel);
    setGroupBy(t.groupBy ?? null);
    setFilters(t.filters ?? []);
    if ('cohortVariant' in t && t.cohortVariant) {
      setCohortVariant(t.cohortVariant as typeof cohortVariant);
    }
    if ('aggregation' in t && t.aggregation) {
      setAggregation(t.aggregation as typeof aggregation);
    } else {
      setAggregation('count');
    }
    if ('valueProperty' in t && t.valueProperty) {
      setValueProperty(t.valueProperty);
    } else {
      setValueProperty('');
    }
    if ('percentageProperty' in t && t.percentageProperty) {
      setPercentageProperty(t.percentageProperty);
    } else {
      setPercentageProperty('');
    }
    setActiveStep(1);
  };

  const filterDef = schema ? (schema.filters[nodeLabel] ?? []).find((f) => f.property === newFilterProp) : null;
  const useDistinctSelect = filterDef?.distinctFromNeo4j && distinctValues.length > 0;

  const addFilter = () => {
    if (!newFilterProp) return;
    let value: unknown = newFilterValue;
    const isDateBetween =
      newFilterOp === 'between' && DATE_PROPERTIES.includes(newFilterProp);
    if (useDistinctSelect) {
      if (newFilterOp === 'in' || newFilterOp === 'nin') {
        if (newFilterSelectedValues.length === 0) return;
        value = newFilterSelectedValues;
      } else {
        if (!newFilterValue) return;
        value = newFilterValue;
      }
    } else if (newFilterOp === 'eq' && (newFilterValue === 'true' || newFilterValue === 'false')) {
      value = newFilterValue === 'true';
    } else if ((newFilterOp === 'in' || newFilterOp === 'nin') && newFilterValue.trim()) {
      value = newFilterValue.split(',').map((v) => v.trim()).filter(Boolean);
    } else if (isDateBetween) {
      if (newFilterDateMode === 'financial' && newFilterFinancialYear) {
        value = financialYearToRange(newFilterFinancialYear);
      } else if (newFilterDateMode === 'custom' && newFilterDateStart && newFilterDateEnd) {
        value = [newFilterDateStart, newFilterDateEnd];
      } else return; // don't add if date range incomplete
    }
    setFilters((prev) => [...prev, { property: newFilterProp, op: newFilterOp, value }]);
    setNewFilterProp('');
    setNewFilterValue('');
    setNewFilterSelectedValues([]);
    setNewFilterFinancialYear('');
    setNewFilterDateStart('');
    setNewFilterDateEnd('');
  };

  const removeFilter = (idx: number) => {
    setFilters((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    setError(null);
    setSaving(true);
    try {
      const { libraryId } = await generateMeasureQuery(buildDefinition());
      onLibraryCreated(libraryId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create query');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!schema) {
    return <Alert severity="error">Could not load schema</Alert>;
  }

  const filterOpts = schema.filters[nodeLabel] ?? [];
  const groupByOpts = schema.groupBy[nodeLabel] ?? [];
  const scopeOpts = schema.scopeTypes ?? [];

  const steps = ['What to count', 'Narrow it down', 'How to split', 'Preview and save'];

  return (
    <Box sx={{ maxWidth: 640 }}>
      <Stepper activeStep={activeStep} sx={{ mb: 3 }}>
        {steps.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* Step 1: What to count */}
      {activeStep === 0 && (
        <Card>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
              What do you want to count?
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 3 }}>
              {schema.aggregationTargets.map((t) => (
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
                  <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                    <Typography fontWeight={500}>
                      {NODE_LABELS[t.nodeLabel] ?? t.nodeLabel}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {t.description}
                    </Typography>
                  </CardContent>
                </Card>
              ))}
            </Box>
            {nodeLabel === 'CancerEpisode' && (
              <FormControl size="small" fullWidth sx={{ mb: 2 }}>
                <FormLabel>Cohort</FormLabel>
                <Select
                  value={cohortVariant}
                  onChange={(e) => setCohortVariant(e.target.value as typeof cohortVariant)}
                >
                  <MenuItem value="diagnosed">Diagnosed (cancer confirmed)</MenuItem>
                  <MenuItem value="referred_excluded">Referred, cancer excluded</MenuItem>
                  <MenuItem value="all_referred">All referred</MenuItem>
                </Select>
              </FormControl>
            )}
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
              Or start from a template
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {TEMPLATES.map((t) => (
                <Chip
                  key={t.label}
                  label={t.label}
                  onClick={() => handleTemplateSelect(t)}
                  variant="outlined"
                  sx={{ cursor: 'pointer' }}
                />
              ))}
            </Box>
            <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-end' }}>
              <Button variant="contained" onClick={() => setActiveStep(1)}>
                Next
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Filters */}
      {activeStep === 1 && (
        <Card>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
              Narrow it down (optional)
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Add filters to focus on specific data
            </Typography>
            {filters.length > 0 && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                {filters.map((f, i) => {
                  let valStr: string;
                  if (Array.isArray(f.value) && f.value.length === 2) {
                    const [a, b] = f.value as string[];
                    const startY = a?.slice?.(0, 4);
                    const endY = b?.slice?.(0, 4);
                    const isFY =
                      a?.endsWith?.('-04-01') &&
                      b?.endsWith?.('-03-31') &&
                      startY &&
                      endY &&
                      Number(endY) === Number(startY) + 1;
                    valStr = isFY ? `${startY}/${String(Number(startY) + 1).slice(-2)} (Apr–Mar)` : `${a} to ${b}`;
                  } else if (Array.isArray(f.value)) {
                    valStr = (f.value as string[]).join(', ');
                  } else {
                    valStr = String(f.value);
                  }
                  return (
                    <Chip
                      key={i}
                      label={`${PROPERTY_LABELS[f.property] ?? f.property} ${f.op} ${valStr}`}
                      onDelete={() => removeFilter(i)}
                      size="small"
                    />
                  );
                })}
              </Box>
            )}
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <FormControl size="small" sx={{ minWidth: 140 }}>
                <FormLabel>Property</FormLabel>
                <Select
                  value={newFilterProp}
                  onChange={(e) => setNewFilterProp(e.target.value)}
                  displayEmpty
                >
                  <MenuItem value="">Select...</MenuItem>
                  {filterOpts.map((f) => (
                    <MenuItem key={f.property} value={f.property}>
                      {PROPERTY_LABELS[f.property] ?? f.property}
                    </MenuItem>
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
              {(newFilterOp === 'eq' || newFilterOp === 'neq') && DATE_PROPERTIES.includes(newFilterProp) ? (
                <TextField
                  size="small"
                  label="Date"
                  type="date"
                  value={newFilterValue as string}
                  onChange={(e) => setNewFilterValue(e.target.value)}
                  InputLabelProps={{ shrink: true }}
                  sx={{ minWidth: 160 }}
                />
              ) : useDistinctSelect ? (
                <FormControl size="small" sx={{ minWidth: 200 }}>
                  <FormLabel>
                    {newFilterOp === 'in' || newFilterOp === 'nin' ? 'Select one or more' : 'Value'}
                  </FormLabel>
                  <Select
                    multiple={newFilterOp === 'in' || newFilterOp === 'nin'}
                    value={newFilterOp === 'in' || newFilterOp === 'nin' ? newFilterSelectedValues : newFilterValue}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (newFilterOp === 'in' || newFilterOp === 'nin') {
                        setNewFilterSelectedValues(typeof v === 'string' ? [v] : v);
                      } else {
                        setNewFilterValue(v as string);
                      }
                    }}
                    displayEmpty
                    disabled={distinctValuesLoading}
                    renderValue={(v) =>
                      Array.isArray(v) ? (v.length ? v.join(', ') : 'Select...') : (v || 'Select...')
                    }
                  >
                    {distinctValues.map((val) => (
                      <MenuItem key={val} value={val}>
                        {val}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              ) : newFilterOp === 'between' && DATE_PROPERTIES.includes(newFilterProp) ? (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'flex-end' }}>
                  <FormControl size="small" sx={{ minWidth: 140 }}>
                    <FormLabel>Period</FormLabel>
                    <Select
                      value={newFilterDateMode}
                      onChange={(e) => setNewFilterDateMode(e.target.value as 'financial' | 'custom')}
                    >
                      <MenuItem value="financial">Financial year (Apr–Mar)</MenuItem>
                      <MenuItem value="custom">Custom range</MenuItem>
                    </Select>
                  </FormControl>
                  {newFilterDateMode === 'financial' ? (
                    <FormControl size="small" sx={{ minWidth: 180 }}>
                      <FormLabel>Financial year</FormLabel>
                      <Select
                        value={newFilterFinancialYear}
                        onChange={(e) => setNewFilterFinancialYear(e.target.value)}
                        displayEmpty
                      >
                        <MenuItem value="">Select year...</MenuItem>
                        {getFinancialYearOptions().map((opt) => (
                          <MenuItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  ) : (
                    <>
                      <TextField
                        size="small"
                        label="From"
                        type="date"
                        value={newFilterDateStart}
                        onChange={(e) => setNewFilterDateStart(e.target.value)}
                        InputLabelProps={{ shrink: true }}
                        sx={{ minWidth: 140 }}
                      />
                      <TextField
                        size="small"
                        label="To"
                        type="date"
                        value={newFilterDateEnd}
                        onChange={(e) => setNewFilterDateEnd(e.target.value)}
                        InputLabelProps={{ shrink: true }}
                        sx={{ minWidth: 140 }}
                      />
                    </>
                  )}
                </Box>
              ) : (
                <TextField
                  size="small"
                  label="Value"
                  value={newFilterValue}
                  onChange={(e) => setNewFilterValue(e.target.value)}
                  placeholder={
                    newFilterOp === 'in' || newFilterOp === 'nin'
                      ? 'e.g. breast, prostate, lung'
                      : 'e.g. Lung, true'
                  }
                  helperText={
                    (newFilterOp === 'in' || newFilterOp === 'nin') && newFilterValue
                      ? 'Comma-separated values'
                      : undefined
                  }
                  sx={{ minWidth: 120 }}
                />
              )}
              <Button
                startIcon={<Add />}
                onClick={addFilter}
                disabled={
                  !newFilterProp ||
                  (useDistinctSelect &&
                    ((newFilterOp === 'in' || newFilterOp === 'nin')
                      ? newFilterSelectedValues.length === 0
                      : !newFilterValue)) ||
                  ((newFilterOp === 'eq' || newFilterOp === 'neq') &&
                    !useDistinctSelect &&
                    DATE_PROPERTIES.includes(newFilterProp) &&
                    !newFilterValue) ||
                  (newFilterOp === 'between' &&
                    DATE_PROPERTIES.includes(newFilterProp) &&
                    ((newFilterDateMode === 'financial' && !newFilterFinancialYear) ||
                      (newFilterDateMode === 'custom' && (!newFilterDateStart || !newFilterDateEnd))))
                }
              >
                Add filter
              </Button>
            </Box>
            <Box sx={{ mt: 3, display: 'flex', justifyContent: 'space-between' }}>
              <Button onClick={() => setActiveStep(0)}>Back</Button>
              <Button variant="contained" onClick={() => setActiveStep(2)}>
                Next
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Group by */}
      {activeStep === 2 && (
        <Card>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
              How should the numbers be split?
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Choose how to break down the count
            </Typography>
            <FormControl size="small" fullWidth>
              <FormLabel>Group by</FormLabel>
              <Select
                value={groupBy ?? ''}
                onChange={(e) => setGroupBy(e.target.value || null)}
                displayEmpty
              >
                <MenuItem value="">Just the total</MenuItem>
                {groupByOpts.map((opt) => (
                  <MenuItem key={opt} value={opt}>
                    {PROPERTY_LABELS[opt] ?? opt}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            {((nodeLabel === 'CancerEpisode' || nodeLabel === 'Encounter') && !groupBy) && (
              <>
                <FormControl size="small" fullWidth sx={{ mt: 2 }}>
                  <FormLabel>Aggregation</FormLabel>
                  <Select value={aggregation} onChange={(e) => setAggregation(e.target.value as typeof aggregation)}>
                    <MenuItem value="count">Count</MenuItem>
                    <MenuItem value="median">Median</MenuItem>
                    {nodeLabel === 'CancerEpisode' && (
                      <MenuItem value="percentage">Percentage</MenuItem>
                    )}
                  </Select>
                </FormControl>
                {aggregation === 'median' && nodeLabel === 'CancerEpisode' && (
                  <FormControl size="small" fullWidth sx={{ mt: 2 }}>
                    <FormLabel>Value (days)</FormLabel>
                    <Select value={valueProperty} onChange={(e) => setValueProperty(e.target.value)}>
                      <MenuItem value="">Select...</MenuItem>
                      <MenuItem value="primary_care_interval_days">Primary care interval (days)</MenuItem>
                      <MenuItem value="diagnostic_interval_days">Diagnostic interval (days)</MenuItem>
                      <MenuItem value="age_at_diagnosis">Age at diagnosis (years)</MenuItem>
                    </Select>
                  </FormControl>
                )}
                {aggregation === 'median' && nodeLabel === 'Encounter' && (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    Median consultations per patient
                  </Typography>
                )}
                {aggregation === 'percentage' && nodeLabel === 'CancerEpisode' && (
                  <FormControl size="small" fullWidth sx={{ mt: 2 }}>
                    <FormLabel>Percentage of</FormLabel>
                    <Select value={percentageProperty} onChange={(e) => setPercentageProperty(e.target.value)}>
                      <MenuItem value="">Select...</MenuItem>
                      <MenuItem value="safety_netting_recorded">Safety netting recorded</MenuItem>
                    </Select>
                  </FormControl>
                )}
              </>
            )}
            <FormControl size="small" fullWidth sx={{ mt: 2 }}>
              <FormLabel>Scope (tenant filter)</FormLabel>
              <Select value={scopeType} onChange={(e) => setScopeType(e.target.value)}>
                {scopeOpts.map((s) => (
                  <MenuItem key={s.scopeType} value={s.scopeType}>
                    {s.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Box sx={{ mt: 3, display: 'flex', justifyContent: 'space-between' }}>
              <Button onClick={() => setActiveStep(1)}>Back</Button>
              <Button variant="contained" onClick={() => setActiveStep(3)}>
                Next
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Step 4: Preview and save */}
      {activeStep === 3 && (
        <Card>
          <CardContent>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
              Preview and save
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
              <InfoOutlined fontSize="small" color="action" />
              <Typography variant="body2" color="text.secondary">
                Your query will {aggregation === 'median' ? 'median' : aggregation === 'percentage' ? 'percentage' : 'count'}{' '}
                {NODE_LABELS[nodeLabel] ?? nodeLabel}
                {groupBy ? ` grouped by ${PROPERTY_LABELS[groupBy] ?? groupBy}` : ' (total)'}
                {aggregation === 'median' && valueProperty ? ` (${valueProperty.replace(/_/g, ' ')})` : ''}
                {aggregation === 'percentage' && percentageProperty ? ` (${percentageProperty.replace(/_/g, ' ')})` : ''}
                {filters.length ? ` with ${filters.length} filter(s)` : ''}
              </Typography>
            </Box>
            {filters.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                  Applied filters
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  {filters.map((f, i) => (
                    <Chip
                      key={i}
                      label={formatFilterForDisplay(f)}
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: '0.75rem' }}
                    />
                  ))}
                </Box>
              </Box>
            )}
            {groupBy && (
              <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mb: 2 }}>
                <FormControl size="small" fullWidth>
                  <FormLabel sx={{ mb: 0.5, fontSize: '0.875rem' }}>Benchmark set</FormLabel>
                  <Select
                    value={benchmarkSetId}
                    onChange={(e) => {
                      const v = String(e.target.value ?? '');
                      onBenchmarkConfigChange?.(v ? { benchmarkSetId: v, benchmarkMetricId: '' } : null);
                    }}
                    displayEmpty
                  >
                    <MenuItem value="">None</MenuItem>
                    {benchmarkSets.map((s) => (
                      <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl size="small" fullWidth disabled={!benchmarkSetId}>
                  <FormLabel sx={{ mb: 0.5, fontSize: '0.875rem' }}>Metric</FormLabel>
                  <Select
                    value={benchmarkMetricId}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (benchmarkSetId && v) {
                        onBenchmarkConfigChange?.({ benchmarkSetId, benchmarkMetricId: v });
                      }
                    }}
                    displayEmpty
                  >
                    <MenuItem value="">Select metric...</MenuItem>
                    {benchmarkMetrics.map((v) => (
                      <MenuItem key={v.metric_id} value={v.metric_id}>{v.label || v.metric_id}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
            )}
            {!orgId && (
              <Alert severity="info" sx={{ mb: 2 }}>
                Select an organisation in the header to preview results for your data.
              </Alert>
            )}
            {previewError && (
              <Alert severity="warning" sx={{ mb: 2 }}>{previewError}</Alert>
            )}
            {previewLoading && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <CircularProgress size={20} />
                <Typography variant="body2" color="text.secondary">Loading preview...</Typography>
              </Box>
            )}
            {previewRows && previewRows.length > 0 && !previewLoading && (
              <>
                {(() => {
                  const rows = previewRows as Array<Record<string, string | number>>;
                  const shape = inferDataShape(rows);
                  const hasNameValue = rows[0] && 'name' in rows[0] && 'value' in rows[0];
                  const chartData = hasNameValue
                    ? rows.map((r) => ({ name: String(r.name ?? '(unknown)'), value: Number(r.value ?? 0) }))
                    : [];

                  if (shape === 'grouped' && chartData.length > 0 && chartData.length <= 12) {
                    const keys = chartData.map((r) => r.name);
                    const total = chartData.reduce((s, r) => s + r.value, 0);
                    const yourPracticePct = total > 0
                      ? Object.fromEntries(keys.map((k) => {
                          const row = chartData.find((r) => r.name === k);
                          return [k, Math.round(((row?.value ?? 0) / total) * 100)];
                        }))
                      : Object.fromEntries(keys.map((k) => [k, 0]));
                    const stackedData: Array<Record<string, string | number>> = [
                      { name: 'Your practice (GP)', ...yourPracticePct },
                    ];
                    const year = benchmarkSets.find((s) => s.id === benchmarkSetId)?.audit_year;
                    const yearSuffix = year ? ` (${year})` : '';
                    const pts = benchmarkComparison ?? [];
                    const alliancePt = pts.find((p) => p.scope_type === 'cancer_alliance');
                    const englandPt = pts.find((p) => p.scope_type === 'national');
                    const toBenchRow = (bp: BenchmarkPoint): Record<string, string | number> => {
                      const benchRow: Record<string, string | number> = { name: `${bp.scope_name || 'Benchmark'}${yearSuffix}` };
                      if (!bp.value_breakdown || Object.keys(bp.value_breakdown).length === 0) return benchRow;
                      const benchKeys = Object.keys(bp.value_breakdown);
                      for (const k of keys) {
                        const lower = k.toLowerCase();
                        const match = benchKeys.find((bk) => bk.toLowerCase() === lower);
                        benchRow[k] = match ? (bp.value_breakdown![match] ?? 0) : 0;
                      }
                      return benchRow;
                    };
                    if (alliancePt?.value_breakdown) stackedData.push(toBenchRow(alliancePt));
                    if (englandPt?.value_breakdown) stackedData.push(toBenchRow(englandPt));
                    const stackKeys = keys.filter((k) => k);
                    return (
                      <Box sx={{ mb: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <Typography variant="subtitle2">Preview</Typography>
                          {benchmarkSetId && benchmarkMetricId && benchmarkComparisonLoading && (
                            <Typography variant="caption" color="text.secondary">Loading benchmark...</Typography>
                          )}
                        </Box>
                        <Box sx={{ height: 260 }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={stackedData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }} barCategoryGap="20%">
                              <CartesianGrid strokeDasharray={chartTheme.grid.strokeDasharray} stroke={chartTheme.grid.stroke} />
                              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
                              <Tooltip formatter={(v: number, name: string) => [`${v}%`, name]} />
                              <Legend />
                              {stackKeys.map((key, i) => (
                                <Bar key={key} dataKey={key} stackId="a" fill={getSeriesColor(i)} radius={i === stackKeys.length - 1 ? chartTheme.bar.radius : 0} />
                              ))}
                            </BarChart>
                          </ResponsiveContainer>
                        </Box>
                      </Box>
                    );
                  }
                  if (shape === 'single' && rows.length === 1 && 'value' in rows[0]) {
                    return (
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Preview</Typography>
                        <Typography variant="h4" fontWeight={600} color="primary">
                          {String(rows[0].value ?? 0)}
                        </Typography>
                      </Box>
                    );
                  }
                  return null;
                })()}
                <Box sx={{ mb: 2, overflowX: 'auto' }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Sample results</Typography>
                  <table style={{ width: '100%', fontSize: '0.875rem', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      {Object.keys(previewRows[0]).map((key) => (
                        <th key={key} style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '1px solid #e0e0e0' }}>
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.slice(0, 10).map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((val, j) => (
                          <td key={j} style={{ padding: '6px 8px', borderBottom: '1px solid #eee' }}>
                            {val != null ? String(val) : '—'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {previewRows.length > 10 && (
                  <Typography variant="caption" color="text.secondary">
                    Showing first 10 of {previewRows.length} rows
                  </Typography>
                )}
                </Box>
              </>
            )}
            {previewRows && previewRows.length === 0 && !previewLoading && orgId && (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                No data matches your query for the selected organisation.
              </Typography>
            )}
            <Box sx={{ mt: 2 }}>
              <Button
                variant="contained"
                onClick={handleSave}
                disabled={
                  saving ||
                  (aggregation === 'median' && nodeLabel === 'CancerEpisode' && !valueProperty) ||
                  (aggregation === 'percentage' && !percentageProperty)
                }
              >
                {saving ? 'Creating...' : 'Save as measure'}
              </Button>
            </Box>
            <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-start' }}>
              <Button onClick={() => setActiveStep(2)}>Back</Button>
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
