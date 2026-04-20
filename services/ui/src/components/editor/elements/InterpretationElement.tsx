/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import TextFieldsOutlined from '@mui/icons-material/TextFieldsOutlined';
import {
  InterpretationElement as InterpretationElementType,
  MeasureElement as MeasureElementType,
  LayoutJson,
} from '@/lib/types/layout';
import { interpretMeasures, evaluateMeasure } from '@/lib/api';
import { MeasureReport } from '@/lib/types/fhir';
import { useEditorStore } from '@/stores/editorStore';
import { useOrgId } from '@/context/OrgContext';
import {
  parsePreview,
  formatInsight,
  formatQualityCheck,
  formatRecommendation,
} from '@/components/editor/elements/interpretationParsing';

const containerSx = {
  width: '100%',
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  bgcolor: 'background.paper',
  border: 1,
  borderColor: 'divider',
  borderRadius: 0.5,
  overflow: 'hidden',
} as const;

interface InterpretationElementProps {
  element: InterpretationElementType;
  pageId: string;
  readOnly?: boolean;
}

export function InterpretationElement({ element, pageId, readOnly = false }: InterpretationElementProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { layout, report, updateElement } = useEditorStore();
  const globalOrgId = useOrgId();

  const parsedPreview = useMemo(() => parsePreview(element.preview), [element.preview]);

  const linkedMeasures = useMemo(() => {
    if (!element.linkedElementIds || element.linkedElementIds.length === 0) return [];
    const result: MeasureElementType[] = [];
    for (const page of layout.pages) {
      for (const el of page.elements) {
        if (element.linkedElementIds.includes(el.id) && el.type === 'measure') {
          result.push(el as MeasureElementType);
        }
      }
    }
    return result;
  }, [element.linkedElementIds, layout.pages]);

  const handleRun = async () => {
    if (readOnly || linkedMeasures.length === 0) return;
    if (!report?.id) {
      setError('Save the report before running interpretation.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const orgId = layout.reportScope === 'organization'
        ? (layout.runtimeParams?.organizationId || globalOrgId)
        : undefined;
      if (layout.reportScope === 'organization' && !orgId) {
        setError('Select an organization in the toolbar (or header) to run interpretation.');
        return;
      }
      const measureReports = await fetchMeasureReports(linkedMeasures, layout, report, globalOrgId);
      const measureTitleOverrides = buildTitleOverrides(linkedMeasures);

      const response = await interpretMeasures({
        report_id: report.id || '',
        measure_ids: linkedMeasures.map((m) => m.measureId.replace('Measure/', '')),
        measure_reports: measureReports.map((item) => ({
          measure_id: item.measure_id,
          report: item.report,
          title: item.title,
          cohort_filters: item.cohort_filters,
        })),
        measure_title_overrides:
          Object.keys(measureTitleOverrides).length > 0 ? measureTitleOverrides : undefined,
        model_size: element.modelSize || 'small',
        organization_id: orgId,
        cohort_filters: layout.runtimeParams?.cohortFilters,
      });

      updateElement(pageId, element.id, {
        preview: response.interpretation,
        lastRunAt: response.interpretation.generated_at,
      });
    } catch (err) {
      console.error('Failed to run interpretation:', err);
      setError('Failed to run interpretation.');
    } finally {
      setBusy(false);
    }
  };

  const format = element.contentFormat || 'summary';
  const title = element.title?.trim() || 'Interpretation';
  const { summary, insights, quality_checks: qualityChecks, recommended_measures: recommended } = parsedPreview;

  return (
    <Box sx={containerSx}>
      <InterpretationHeader title={title} busy={busy} readOnly={readOnly} disabled={linkedMeasures.length === 0} onRun={handleRun} />
      <Box sx={{ flex: 1, padding: '8px', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {linkedMeasures.length === 0 && <EmptyLinkedState />}
        {linkedMeasures.length > 0 && !summary && !element.preview && !error && <EmptyRunState />}
        {summary && format === 'summary' && (
          <Typography sx={{ fontSize: '0.75rem', color: 'text.primary' }}>{summary}</Typography>
        )}
        {summary && format === 'bullets' && (
          <>
            {insights.slice(0, 4).map((item: string | Record<string, unknown>, idx: number) => (
              <Typography key={`${element.id}-insight-${idx}`} sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
                • {formatInsight(item)}
              </Typography>
            ))}
          </>
        )}
        {summary && format === 'full' && (
          <FullFormatContent elementId={element.id} summary={summary} insights={insights} qualityChecks={qualityChecks} recommended={recommended} />
        )}
        {error && (
          <Typography sx={{ color: 'error.main', fontSize: '0.625rem' }}>{error}</Typography>
        )}
      </Box>
    </Box>
  );
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

interface InterpretationHeaderProps {
  title: string;
  busy: boolean;
  readOnly: boolean;
  disabled: boolean;
  onRun: () => void;
}

function InterpretationHeader({ title, busy, readOnly, disabled, onRun }: InterpretationHeaderProps) {
  return (
    <Box
      sx={{
        padding: '8px',
        bgcolor: 'grey.200',
        borderBottom: 1,
        borderColor: 'divider',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '8px',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
        <TextFieldsOutlined />
        <Typography
          sx={{
            fontSize: '0.75rem',
            fontWeight: 600,
            color: 'text.primary',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {title}
        </Typography>
      </Box>
      <Button size="small" onClick={onRun} disabled={busy || readOnly || disabled}>
        {busy ? <CircularProgress aria-label="Loading" size={16} /> : 'Run'}
      </Button>
    </Box>
  );
}

function EmptyLinkedState() {
  return (
    <Box sx={{ color: 'text.disabled', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', gap: '8px', height: '100%' }}>
      <TextFieldsOutlined sx={{ fontSize: '28px' }} />
      <Typography>Select at least one measure to link.</Typography>
    </Box>
  );
}

function EmptyRunState() {
  return (
    <Box sx={{ color: 'text.disabled', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', gap: '8px', height: '100%' }}>
      <Typography>Run interpretation to preview output.</Typography>
    </Box>
  );
}

interface FullFormatContentProps {
  elementId: string;
  summary: string;
  insights: Array<string | Record<string, unknown>>;
  qualityChecks: Array<string | Record<string, unknown>>;
  recommended: Array<string | Record<string, unknown>>;
}

function FullFormatContent({ elementId, summary, insights, qualityChecks, recommended }: FullFormatContentProps) {
  return (
    <>
      <Typography sx={{ fontSize: '0.75rem', color: 'text.primary' }}>{summary}</Typography>
      {insights.slice(0, 3).map((item: string | Record<string, unknown>, idx: number) => (
        <Typography key={`${elementId}-insight-${idx}`} sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
          • {formatInsight(item)}
        </Typography>
      ))}
      {qualityChecks.slice(0, 2).map((item: string | Record<string, unknown>, idx: number) => (
        <Typography key={`${elementId}-quality-${idx}`} sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
          • {formatQualityCheck(item)}
        </Typography>
      ))}
      {recommended.slice(0, 2).map((item: string | Record<string, unknown>, idx: number) => (
        <Typography key={`${elementId}-rec-${idx}`} sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
          • {formatRecommendation(item)}
        </Typography>
      ))}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Data helpers                                                       */
/* ------------------------------------------------------------------ */

interface MeasureReportItem {
  measure_id: string;
  report: MeasureReport;
  title?: string;
  cohort_filters: Record<string, unknown>;
}

async function fetchMeasureReports(
  linkedMeasures: MeasureElementType[],
  layout: LayoutJson,
  report: MeasureReport,
  globalOrgId?: string,
): Promise<MeasureReportItem[]> {
  const periodStart = report.period?.start || new Date().toISOString().split('T')[0];
  const periodEnd = report.period?.end || new Date().toISOString().split('T')[0];
  const reportScope = layout.reportScope || 'organization';
  const subject = reportScope === 'patient' ? layout.runtimeParams?.subjectRef : undefined;
  const orgId = reportScope === 'organization'
    ? (layout.runtimeParams?.organizationId || globalOrgId)
    : undefined;
  const orgIds = reportScope === 'organization' ? layout.runtimeParams?.organizationIds : undefined;

  return Promise.all(
    linkedMeasures.map(async (measureElement) => {
      const measureId = measureElement.measureId.replace('Measure/', '');
      const mergedFilters = {
        ...(layout.runtimeParams?.cohortFilters || {}),
        ...(measureElement.cohortFilters || {}),
      };
      const measureReport = await evaluateMeasure(measureId, {
        periodStart,
        periodEnd,
        subject,
        orgId,
        orgIds,
        cohortFilters: mergedFilters,
      });
      return {
        measure_id: measureId,
        report: measureReport as MeasureReport,
        title: measureElement.title?.trim() || undefined,
        cohort_filters: mergedFilters,
      };
    }),
  );
}

function buildTitleOverrides(linkedMeasures: MeasureElementType[]): Record<string, string> {
  const titleByMeasureId = new Map<string, Set<string>>();
  linkedMeasures.forEach((measureElement) => {
    const customTitle = measureElement.title?.trim();
    if (!customTitle) return;
    const measureId = measureElement.measureId.replace('Measure/', '');
    const titles = titleByMeasureId.get(measureId) ?? new Set<string>();
    titles.add(customTitle);
    titleByMeasureId.set(measureId, titles);
  });

  return Array.from(titleByMeasureId.entries()).reduce<Record<string, string>>(
    (acc, [measureId, titles]) => {
      if (titles.size === 1) {
        acc[measureId] = Array.from(titles)[0];
      }
      return acc;
    },
    {},
  );
}
