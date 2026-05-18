/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import Divider from '@mui/material/Divider';
import Button from '@mui/material/Button';
import { useEditorStore } from '@/stores/editorStore';
import { useOrgId } from '@/context/OrgContext';
import type { MeasureElement, CohortFilters } from '@/lib/types/layout';
import { evaluateMeasure } from '@/lib/api';
import { extractMeasureReportRows } from '@/lib/measureData';
import { MeasurePickerDialog } from '@/components/measures/MeasurePickerDialog';
import type { Measure } from '@/lib/types/fhir';
import { recommendChart, inferDataShapeFromAxis } from '@/lib/chartRecommendations';

/* ── Helpers ──────────────────────────────────────────────────────────────── */

const DISPLAY_MODE_OPTIONS: { value: string; label: string }[] = [
  { value: 'value', label: 'Value' }, { value: 'bar', label: 'Bar Chart' },
  { value: 'horizontalBar', label: 'Horizontal Bar Chart' }, { value: 'boxPlot', label: 'Box Plot' },
  { value: 'pie', label: 'Pie Chart' }, { value: 'line', label: 'Line Chart' },
  { value: 'area', label: 'Area Chart' }, { value: 'radar', label: 'Radar Chart' },
  { value: 'radialBar', label: 'Radial Bar Chart' }, { value: 'scatter', label: 'Scatter Chart' },
  { value: 'composed', label: 'Composed Chart' }, { value: 'funnel', label: 'Funnel Chart' },
  { value: 'heatmap', label: 'Heatmap' }, { value: 'bullet', label: 'Bullet/Target Band' },
  { value: 'sankey', label: 'Sankey' }, { value: 'populationPyramid', label: 'Population Pyramid' },
  { value: 'table', label: 'Table' },
];

const CHART_DISPLAY_MODES = new Set([
  'bar', 'horizontalBar', 'pie', 'line', 'area', 'radar', 'radialBar', 'scatter', 'composed', 'funnel',
]);

function axisLabel(key: string): string {
  if (key === '__field') return 'Field name';
  if (key === '__value') return 'Field value';
  return key;
}

function getMeasureDefaults(measureId: string): Partial<MeasureElement> {
  switch (measureId) {
    case 'place-of-presentation':
      return { displayMode: 'heatmap', dataBindings: { xAxisKey: 'condition_type', seriesKey: 'place_name', yAxisKey: 'episode_count' } };
    case 'pathway-funnel':
      return { displayMode: 'funnel', dataBindings: undefined };
    case 'diagnostic-interval':
    case 'primary-care-interval':
    case 'referral-to-diagnosis-interval':
      return { displayMode: 'boxPlot' };
    default:
      return {};
  }
}

/* ── AxisFields sub-component (renders field selectors per display mode) ── */

interface AxisFieldsProps {
  element: MeasureElement;
  axisOptions: { categoryKeys: string[]; valueKeys: string[] };
  axisLoading: boolean;
  updateDataBindings: (updates: Partial<NonNullable<MeasureElement['dataBindings']>>) => void;
}

function ChartAxisFields({ element, axisOptions, axisLoading, updateDataBindings }: AxisFieldsProps): React.ReactNode {
  const isBoxPlot = element.displayMode === 'boxPlot';
  const isFieldValueMode = axisOptions.categoryKeys.includes('__field') && axisOptions.valueKeys.includes('__value');
  const fieldGroup = element.dataBindings?.fieldGroup || 'all';
  const categoryOptions = isBoxPlot
    ? axisOptions.categoryKeys.filter((k) => k !== '__field')
    : axisOptions.categoryKeys;
  const valueOptions = isBoxPlot
    ? axisOptions.valueKeys.filter((k) => k !== '__value')
    : axisOptions.valueKeys;

  if (CHART_DISPLAY_MODES.has(element.displayMode || '')) {
    return (
      <>
        {isFieldValueMode && (
          <TextField select size="small" label="Field Group" value={fieldGroup}
            onChange={(e) => updateDataBindings({ fieldGroup: (e.target.value as NonNullable<MeasureElement['dataBindings']>['fieldGroup']) || 'all' })}>
            <MenuItem value="all">All fields</MenuItem>
            <MenuItem value="pct">Percentages only</MenuItem>
            <MenuItem value="count">Counts only</MenuItem>
          </TextField>
        )}
        <TextField select size="small" label="Category Field" value={element.dataBindings?.xAxisKey || ''}
          onChange={(e) => updateDataBindings({ xAxisKey: e.target.value || undefined })} disabled={axisLoading || categoryOptions.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {categoryOptions.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Value Field (count/percentage)" value={element.dataBindings?.yAxisKey || ''}
          onChange={(e) => updateDataBindings({ yAxisKey: e.target.value || undefined })} disabled={axisLoading || valueOptions.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {valueOptions.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
      </>
    );
  }

  if (isBoxPlot) {
    return (
      <>
        <TextField select size="small" label="Category Field" value={element.dataBindings?.xAxisKey || ''}
          onChange={(e) => updateDataBindings({ xAxisKey: e.target.value || undefined })} disabled={axisLoading || categoryOptions.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {categoryOptions.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Value Field" value={element.dataBindings?.yAxisKey || ''}
          onChange={(e) => updateDataBindings({ yAxisKey: e.target.value || undefined })} disabled={axisLoading || valueOptions.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {valueOptions.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
      </>
    );
  }

  if (element.displayMode === 'value') {
    return (
      <TextField select size="small" label="Value Field" value={element.dataBindings?.yAxisKey || ''}
        onChange={(e) => updateDataBindings({ yAxisKey: e.target.value || undefined })} disabled={axisLoading || valueOptions.length === 0}>
        <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
        {valueOptions.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
      </TextField>
    );
  }

  if (element.displayMode === 'heatmap') {
    return (
      <>
        <TextField select size="small" label="Column Field (X)" value={element.dataBindings?.xAxisKey || ''}
          onChange={(e) => updateDataBindings({ xAxisKey: e.target.value || undefined })} disabled={axisLoading || axisOptions.categoryKeys.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {axisOptions.categoryKeys.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Row Field (Y)" value={element.dataBindings?.seriesKey || ''}
          onChange={(e) => updateDataBindings({ seriesKey: e.target.value || undefined })} disabled={axisLoading || axisOptions.categoryKeys.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {axisOptions.categoryKeys.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Value Field" value={element.dataBindings?.yAxisKey || ''}
          onChange={(e) => updateDataBindings({ yAxisKey: e.target.value || undefined })} disabled={axisLoading || axisOptions.valueKeys.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {axisOptions.valueKeys.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
      </>
    );
  }

  if (element.displayMode === 'bullet') {
    return (
      <>
        <TextField select size="small" label="Label Field" value={element.dataBindings?.xAxisKey || ''}
          onChange={(e) => updateDataBindings({ xAxisKey: e.target.value || undefined })} disabled={axisLoading || axisOptions.categoryKeys.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {axisOptions.categoryKeys.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Value Field" value={element.dataBindings?.yAxisKey || ''}
          onChange={(e) => updateDataBindings({ yAxisKey: e.target.value || undefined })} disabled={axisLoading || axisOptions.valueKeys.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {axisOptions.valueKeys.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Target Field" value={element.dataBindings?.seriesKey || ''}
          onChange={(e) => updateDataBindings({ seriesKey: e.target.value || undefined })} disabled={axisLoading || axisOptions.valueKeys.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {axisOptions.valueKeys.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
      </>
    );
  }

  if (element.displayMode === 'populationPyramid') {
    return (
      <>
        <TextField select size="small" label="Age Band Field" value={element.dataBindings?.xAxisKey || ''}
          onChange={(e) => updateDataBindings({ xAxisKey: e.target.value || undefined })} disabled={axisLoading || axisOptions.categoryKeys.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {axisOptions.categoryKeys.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Gender Field" value={element.dataBindings?.seriesKey || ''}
          onChange={(e) => updateDataBindings({ seriesKey: e.target.value || undefined })} disabled={axisLoading || axisOptions.categoryKeys.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {axisOptions.categoryKeys.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Value Field (count/percentage)" value={element.dataBindings?.yAxisKey || ''}
          onChange={(e) => updateDataBindings({ yAxisKey: e.target.value || undefined })} disabled={axisLoading || axisOptions.valueKeys.length === 0}>
          <MenuItem value="">{axisLoading ? 'Loading fields...' : 'Select field'}</MenuItem>
          {axisOptions.valueKeys.map((key) => <MenuItem key={key} value={key}>{axisLabel(key)}</MenuItem>)}
        </TextField>
      </>
    );
  }

  return null;
}

/* ── CohortFiltersEditor ─────────────────────────────────────────────────── */

export function CohortFiltersEditor({ filters, onUpdate, cancerTypeOptions, cancerTypeLoading }: {
  filters: CohortFilters;
  onUpdate: (updates: Partial<CohortFilters>) => void;
  cancerTypeOptions?: string[];
  cancerTypeLoading?: boolean;
}): React.ReactNode {
  const cohortStatusValue = useMemo(() => {
    const status = filters.ce_status || [];
    if (status.length === 0) return 'all';
    if (status.length === 1) return status[0];
    return 'custom';
  }, [filters.ce_status]);

  const excludedStatusValue = useMemo(
    () => (filters.ce_status_exclude || []).join(', '),
    [filters.ce_status_exclude],
  );
  const cancerTypeValue = useMemo(
    () => (filters.ce_condition_type || []).join(', '),
    [filters.ce_condition_type],
  );
  const cancerTypeSelectValue = useMemo(() => {
    if (!cancerTypeOptions || cancerTypeOptions.length === 0) return 'custom';
    const selected = filters.ce_condition_type || [];
    if (selected.length === 0) return 'all';
    if (selected.length === 1 && cancerTypeOptions.includes(selected[0])) return selected[0];
    return 'custom';
  }, [cancerTypeOptions, filters.ce_condition_type]);

  const dateFields = [
    'ce_created_at', 'ce_first_encounter_date', 'ce_last_encounter_date',
    'ce_referral_date', 'ce_diagnosis_date', 'ce_treatment_start_date',
  ] as const;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField select size="small" label="Outcome" value={cohortStatusValue}
        onChange={(e) => {
          const v = e.target.value;
          if (v === 'all') onUpdate({ ce_status: undefined });
          else if (v === 'custom') onUpdate({ ce_status: [] });
          else onUpdate({ ce_status: [v] });
        }}>
        <MenuItem value="all">Entire cohort</MenuItem>
        <MenuItem value="confirmed">Diagnosed</MenuItem>
        <MenuItem value="excluded">Cancer excluded</MenuItem>
        <MenuItem value="inconclusive">Inconclusive</MenuItem>
        <MenuItem value="pending">Pending/unknown</MenuItem>
      </TextField>

      <TextField size="small" label="Exclude outcomes" placeholder="e.g. pending, inconclusive"
        value={excludedStatusValue}
        onChange={(e) => {
          const parsed = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
          onUpdate({ ce_status_exclude: parsed.length ? parsed : undefined });
        }} />

      <Typography variant="caption" color="text.secondary">Cancer type</Typography>
      {cancerTypeOptions && cancerTypeOptions.length > 0 ? (
        <TextField select size="small" value={cancerTypeSelectValue} disabled={cancerTypeLoading}
          onChange={(e) => {
            const v = e.target.value;
            if (v === 'all') onUpdate({ ce_condition_type: undefined });
            else if (v === 'custom') onUpdate({ ce_condition_type: filters.ce_condition_type || [] });
            else onUpdate({ ce_condition_type: [v] });
          }}>
          <MenuItem value="all">All cancer types</MenuItem>
          {cancerTypeOptions.map((opt) => <MenuItem key={opt} value={opt}>{opt}</MenuItem>)}
          <MenuItem value="custom">Custom...</MenuItem>
        </TextField>
      ) : (
        <TextField size="small" placeholder="e.g. Breast, Lung" value={cancerTypeValue}
          onChange={(e) => {
            const parsed = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
            onUpdate({ ce_condition_type: parsed.length ? parsed : undefined });
          }} />
      )}

      {cancerTypeOptions && cancerTypeOptions.length > 0 && cancerTypeSelectValue === 'custom' && (
        <TextField size="small" placeholder="e.g. Breast, Lung" value={cancerTypeValue}
          onChange={(e) => {
            const parsed = e.target.value.split(',').map((s) => s.trim()).filter(Boolean);
            onUpdate({ ce_condition_type: parsed.length ? parsed : undefined });
          }} />
      )}

      <TextField size="small" label="Agent confidence" type="number"
        inputProps={{ step: '0.01', min: '0', max: '1' }}
        value={filters.ce_agent_confidence != null ? String(filters.ce_agent_confidence) : ''}
        onChange={(e) => onUpdate({ ce_agent_confidence: e.target.value ? Number(e.target.value) : undefined })} />

      {dateFields.map((prefix) => {
        const label = prefix.replace('ce_', '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        const startKey = `${prefix}_start` as keyof CohortFilters;
        const endKey = `${prefix}_end` as keyof CohortFilters;
        return (
          <Box key={prefix}>
            <Typography variant="caption" color="text.secondary">{label}</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, mt: 0.5 }}>
              <TextField size="small" type="date" value={(filters[startKey] as string) || ''}
                onChange={(e) => onUpdate({ [startKey]: e.target.value || undefined })}
                InputLabelProps={{ shrink: true }} />
              <TextField size="small" type="date" value={(filters[endKey] as string) || ''}
                onChange={(e) => onUpdate({ [endKey]: e.target.value || undefined })}
                InputLabelProps={{ shrink: true }} />
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

/* ── useAxisOptions hook ─────────────────────────────────────────────────── */

function useAxisOptions(element: MeasureElement) {
  const report = useEditorStore((state) => state.report);
  const reportScope = useEditorStore((state) => state.layout.reportScope);
  const runtimeParams = useEditorStore((state) => state.layout.runtimeParams);
  const globalOrgId = useOrgId();
  const orgIdsKey = (runtimeParams?.organizationIds || []).join('|');
  const [axisOptions, setAxisOptions] = useState<{ categoryKeys: string[]; valueKeys: string[] }>({ categoryKeys: [], valueKeys: [] });
  const [axisLoading, setAxisLoading] = useState(false);
  const isBoxPlot = element.displayMode === 'boxPlot';

  useEffect(() => {
    const loadAxisOptions = async () => {
      if (!element.measureId) { setAxisOptions({ categoryKeys: [], valueKeys: [] }); return; }
      const orgId = reportScope === 'organization'
        ? (runtimeParams?.organizationId || globalOrgId)
        : undefined;
      if (reportScope === 'organization' && !orgId) {
        setAxisOptions({ categoryKeys: [], valueKeys: [] });
        return;
      }
      setAxisLoading(true);
      try {
        const measureId = element.measureId.replace('Measure/', '');
        const periodStart = report?.period?.start || new Date().toISOString().split('T')[0];
        const periodEnd = report?.period?.end || new Date().toISOString().split('T')[0];
        const subject = reportScope === 'patient' ? runtimeParams?.subjectRef : undefined;
        const orgIds = reportScope === 'organization' ? runtimeParams?.organizationIds : undefined;
        const mergedFilters = { ...(runtimeParams?.cohortFilters || {}), ...(element.cohortFilters || {}) };
        const result = await evaluateMeasure(measureId, { periodStart, periodEnd, subject, orgId, orgIds, cohortFilters: mergedFilters });
        const rows = extractMeasureReportRows(result as any);
        const sample = rows[0] || {};
        const entries = Object.entries(sample);
        const stringKeys = entries.filter(([, v]) => typeof v === 'string').map(([k]) => k);
        const numericKeys = entries.filter(([, v]) => typeof v === 'number').map(([k]) => k);
        let categoryKeys = stringKeys;
        let valueKeys = numericKeys;
        if (!isBoxPlot && categoryKeys.length === 0 && numericKeys.length > 0) categoryKeys = [...numericKeys];
        if (!isBoxPlot && stringKeys.length === 0 && numericKeys.length > 1) {
          categoryKeys = ['__field', ...categoryKeys];
          valueKeys = ['__value', ...numericKeys];
        }
        setAxisOptions({ categoryKeys, valueKeys });
      } catch (error) {
        console.error('Failed to load axis options:', error);
        setAxisOptions({ categoryKeys: [], valueKeys: [] });
      } finally { setAxisLoading(false); }
    };
    loadAxisOptions();
  }, [element.measureId, element.cohortFilters, element.displayMode, report?.period?.start, report?.period?.end, reportScope, runtimeParams?.subjectRef, runtimeParams?.organizationId, globalOrgId, orgIdsKey, runtimeParams?.refreshToken]);

  return { axisOptions, axisLoading, report, reportScope, runtimeParams, orgIdsKey };
}

/* ── useCancerTypes hook ─────────────────────────────────────────────────── */

function useCancerTypes() {
  const report = useEditorStore((state) => state.report);
  const reportScope = useEditorStore((state) => state.layout.reportScope);
  const runtimeParams = useEditorStore((state) => state.layout.runtimeParams);
  const globalOrgId = useOrgId();
  const orgIdsKey = (runtimeParams?.organizationIds || []).join('|');
  const [cancerTypeOptions, setCancerTypeOptions] = useState<string[]>([]);
  const [cancerTypeLoading, setCancerTypeLoading] = useState(false);

  useEffect(() => {
    const loadCancerTypes = async () => {
      if (!report) { setCancerTypeOptions([]); return; }
      const orgId = reportScope === 'organization'
        ? (runtimeParams?.organizationId || globalOrgId)
        : undefined;
      if (reportScope === 'organization' && !orgId) {
        setCancerTypeOptions([]);
        return;
      }
      setCancerTypeLoading(true);
      try {
        const periodStart = report?.period?.start || new Date().toISOString().split('T')[0];
        const periodEnd = report?.period?.end || new Date().toISOString().split('T')[0];
        const subject = reportScope === 'patient' ? runtimeParams?.subjectRef : undefined;
        const orgIds = reportScope === 'organization' ? runtimeParams?.organizationIds : undefined;
        const result = await evaluateMeasure('diagnosis-cancer-types', { periodStart, periodEnd, subject, orgId, orgIds });
        const rows = extractMeasureReportRows(result as any);
        const options = rows.map((row) => {
          const value = (row as any).condition_type || (row as any).cancerType || Object.values(row).find((item) => typeof item === 'string');
          return typeof value === 'string' ? value : null;
        }).filter((v): v is string => Boolean(v));
        const unique = Array.from(new Set(options));
        unique.sort((a, b) => a.localeCompare(b));
        setCancerTypeOptions(unique);
      } catch (error) {
        console.error('Failed to load cancer types:', error);
        setCancerTypeOptions([]);
      } finally { setCancerTypeLoading(false); }
    };
    loadCancerTypes();
  }, [report?.period?.start, report?.period?.end, reportScope, runtimeParams?.subjectRef, runtimeParams?.organizationId, globalOrgId, orgIdsKey, runtimeParams?.refreshToken]);

  return { cancerTypeOptions, cancerTypeLoading };
}

/* ── MeasureSettings ─────────────────────────────────────────────────────── */

export function MeasureSettings({ element, measures, onUpdate }: {
  element: MeasureElement;
  measures: Measure[];
  onUpdate: (updates: Partial<MeasureElement>) => void;
}): React.ReactNode {
  const [measurePickerOpen, setMeasurePickerOpen] = useState(false);
  const { axisOptions, axisLoading } = useAxisOptions(element);
  const { cancerTypeOptions, cancerTypeLoading } = useCancerTypes();
  const isBoxPlot = element.displayMode === 'boxPlot';

  useEffect(() => {
    if (!isBoxPlot) return;
    if (element.dataBindings?.xAxisKey === '__field' || element.dataBindings?.yAxisKey === '__value') {
      onUpdate({ dataBindings: { ...element.dataBindings, xAxisKey: undefined, yAxisKey: undefined } });
    }
  }, [isBoxPlot, element.dataBindings, onUpdate]);

  const updateDataBindings = useCallback(
    (updates: Partial<NonNullable<MeasureElement['dataBindings']>>) => {
      onUpdate({ dataBindings: { ...(element.dataBindings || {}), ...updates } });
    },
    [element.dataBindings, onUpdate],
  );

  const updateFilters = useCallback(
    (updates: Partial<CohortFilters>) => {
      onUpdate({ cohortFilters: { ...(element.cohortFilters || {}), ...updates } });
    },
    [element.cohortFilters, onUpdate],
  );

  const clearFilters = useCallback(() => { onUpdate({ cohortFilters: {} }); }, [onUpdate]);

  const selectedMeasure = measures.find((m) => m.id === element.measureId?.replace('Measure/', ''));
  const titlePlaceholder = selectedMeasure?.title || selectedMeasure?.name || 'Measure title';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Typography variant="caption" color="text.secondary">Measure</Typography>
      <Button variant="outlined" onClick={() => setMeasurePickerOpen(true)}
        sx={{ justifyContent: 'flex-start', fontWeight: selectedMeasure ? 'normal' : undefined, color: selectedMeasure ? undefined : 'text.disabled' }}>
        {selectedMeasure ? selectedMeasure.title || selectedMeasure.name || selectedMeasure.id : 'Select a measure...'}
      </Button>
      <MeasurePickerDialog open={measurePickerOpen} onClose={() => setMeasurePickerOpen(false)}
        onSelect={(measureId) => { onUpdate({ measureId: `Measure/${measureId}`, ...getMeasureDefaults(measureId) }); }}
        measures={measures} selectedMeasureId={element.measureId} />
      <TextField size="small" label="Title" value={element.title || ''}
        onChange={(e) => onUpdate({ title: e.target.value })} placeholder={titlePlaceholder} />
      <TextField select size="small" label="Display Mode" value={element.displayMode || 'value'}
        onChange={(e) => onUpdate({ displayMode: e.target.value as MeasureElement['displayMode'] })}>
        {DISPLAY_MODE_OPTIONS.map((opt) => <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>)}
      </TextField>

      {!axisLoading && (axisOptions.categoryKeys.length > 0 || axisOptions.valueKeys.length > 0) && (() => {
        const dataShape = inferDataShapeFromAxis(axisOptions.categoryKeys, axisOptions.valueKeys);
        const hasBenchmark = Boolean(selectedMeasure?.benchmarkConfig?.benchmarkSetId);
        const rec = recommendChart(dataShape, hasBenchmark);
        const isCurrent = element.displayMode === rec.displayMode;
        return (
          <Box sx={{ p: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
            <Typography variant="caption" color="text.secondary">Suggested: {rec.label}</Typography>
            <Typography variant="body2" sx={{ fontSize: '0.75rem', mt: 0.5 }}>{rec.reason}</Typography>
            {!isCurrent && (
              <Button size="small" sx={{ mt: 1 }} onClick={() => {
                onUpdate({
                  displayMode: rec.displayMode as MeasureElement['displayMode'],
                  ...(rec.axisMapping && {
                    dataBindings: {
                      ...element.dataBindings,
                      xAxisKey: rec.axisMapping.xAxisKey,
                      yAxisKey: rec.axisMapping.yAxisKey,
                      seriesKey: rec.axisMapping.seriesKey,
                    },
                  }),
                });
              }}>
                Apply suggestion
              </Button>
            )}
          </Box>
        );
      })()}

      <ChartAxisFields element={element} axisOptions={axisOptions} axisLoading={axisLoading}
        updateDataBindings={updateDataBindings} />

      <FormControlLabel control={<Switch size="small" checked={element.showTitle !== false}
        onChange={(_, checked) => onUpdate({ showTitle: checked })} />} label="Show Title" />
      <FormControlLabel control={<Switch size="small" checked={element.showScore !== false}
        onChange={(_, checked) => onUpdate({ showScore: checked })} />} label="Show Score" />
      <Divider />
      <Typography variant="body2" fontWeight={600}>Measure filters</Typography>
      <CohortFiltersEditor filters={element.cohortFilters || {}} onUpdate={updateFilters}
        cancerTypeOptions={cancerTypeOptions} cancerTypeLoading={cancerTypeLoading} />
      <Button size="small" variant="outlined" onClick={clearFilters}>Clear measure filters</Button>
    </Box>
  );
}
