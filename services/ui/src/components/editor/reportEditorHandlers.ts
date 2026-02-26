import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { DragEndEvent } from '@dnd-kit/core';
import { useEditorStore, snapToGrid } from '@/stores/editorStore';
import {
  saveMeasureReportWithLayout,
  interpretMeasures,
} from '@/lib/api';
import type {
  ElementType,
  LayoutElement,
  TextElement,
  ImageElement,
  TableElement,
  ChartElement,
  MeasureElement,
  KpiCardElement,
  HeroStatsElement,
  ComparisonBarsElement,
  PopulationPyramidElement,
  TableOfContentsElement,
} from '@/lib/types/layout';
import type { MeasureReport } from '@/lib/types/fhir';
import type { AgentInterpretation, AgentModelSize } from './agentTypes';
import { DEFAULT_ELEMENT_SIZES, collectMeasureIds, type PendingDrop } from './reportEditorHelpers';

// ── Deps interface ───────────────────────────────────────────────────────────

export interface ReportEditorHandlerDeps {
  reportId?: string;
  saving: boolean;
  agentModelSize: AgentModelSize;
  agentGoal: string;
  setSaving: (v: boolean) => void;
  setAgentError: (v: string | null) => void;
  setAgentSummary: (v: AgentInterpretation | null) => void;
  setAgentBusy: (v: boolean) => void;
  setPendingDrop: (v: PendingDrop | null) => void;
  setPendingInterpretationDrop: (v: PendingDrop | null) => void;
  setIsMeasureDialogOpen: (v: boolean) => void;
  setIsInterpretationDialogOpen: (v: boolean) => void;
  setSelectedInterpretationLink: (v: string[]) => void;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useReportEditorHandlers(deps: ReportEditorHandlerDeps) {
  const router = useRouter();
  const { report, setReport, setDirty, addElement } = useEditorStore();

  const handleSave = useCallback(async () => {
    deps.setSaving(true);
    try {
      const currentLayout = useEditorStore.getState().layout;
      const reportData = buildReportData(report, currentLayout);
      const savedReport = await saveMeasureReportWithLayout(reportData, currentLayout);
      setReport(savedReport);
      setDirty(false);
      navigateAfterSave(deps.reportId, savedReport, router);
    } catch (error) {
      console.error('Failed to save report:', error);
    } finally {
      deps.setSaving(false);
    }
  }, [report, deps.reportId, router, setDirty, setReport, deps.setSaving]);

  const handleInterpret = useCallback(async () => {
    deps.setAgentError(null);
    deps.setAgentSummary(null);

    const currentReportId = resolveReportId(report, deps.reportId);
    if (!currentReportId) {
      deps.setAgentError('Save the report before running interpretation.');
      return;
    }

    const currentLayout = useEditorStore.getState().layout;
    const measureIds = collectMeasureIds(currentLayout.pages);
    if (measureIds.length === 0) {
      deps.setAgentError('Add at least one measure to the report before running interpretation.');
      return;
    }

    deps.setAgentBusy(true);
    try {
      const response = await interpretMeasures({
        report_id: currentReportId,
        measure_ids: measureIds,
        model_size: deps.agentModelSize,
        user_goal: deps.agentGoal.trim() || undefined,
        organization_id: currentLayout.runtimeParams?.organizationId,
        cohort_filters: currentLayout.runtimeParams?.cohortFilters,
      });
      deps.setAgentSummary(response.interpretation);
    } catch (error) {
      console.error('Failed to interpret measures:', error);
      deps.setAgentError('Failed to interpret measures. Check the server logs for details.');
    } finally {
      deps.setAgentBusy(false);
    }
  }, [deps.agentGoal, deps.agentModelSize, report, deps.reportId]);

  const handlePreview = useCallback(() => {
    console.log('Preview not implemented yet');
  }, []);

  const handleExport = useCallback(async () => {
    if (deps.saving) return;
    if (useEditorStore.getState().isDirty) {
      await handleSave();
    }
    const exportId =
      useEditorStore.getState().report?.id ||
      (deps.reportId && deps.reportId !== 'new' ? deps.reportId : null);
    if (!exportId) {
      console.warn('Save the report before exporting.');
      return;
    }
    window.open(`/reports/${exportId}/export`, '_blank', 'noopener,noreferrer');
  }, [handleSave, deps.reportId, deps.saving]);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over) return;

      const activeData = active.data.current;
      const overData = over.data.current;
      if (!activeData?.fromPalette || !overData?.pageId) return;

      const elementType = activeData.elementType as ElementType;
      const pageId = overData.pageId as string;
      const { w, h } = DEFAULT_ELEMENT_SIZES[elementType];
      const x = snapToGrid(50);
      const y = snapToGrid(50);

      if (elementType === 'measure') {
        deps.setPendingDrop({ pageId, x, y, w, h });
        deps.setIsMeasureDialogOpen(true);
        return;
      }
      if (elementType === 'interpretation') {
        deps.setPendingInterpretationDrop({ pageId, x, y, w, h });
        deps.setSelectedInterpretationLink([]);
        deps.setIsInterpretationDialogOpen(true);
        return;
      }

      const elementData = buildDropElement(elementType, x, y, w, h);
      if (elementData) addElement(pageId, elementData as Omit<LayoutElement, 'id'>);
    },
    [addElement, deps],
  );

  return { handleSave, handleInterpret, handlePreview, handleExport, handleDragEnd };
}

// ── Pure helpers ──────────────────────────────────────────────────────────────

function resolveReportId(
  report: MeasureReport | null,
  routeReportId?: string,
): string | null {
  return report?.id || (routeReportId && routeReportId !== 'new' ? routeReportId : null);
}

function navigateAfterSave(
  reportId: string | undefined,
  savedReport: MeasureReport,
  router: ReturnType<typeof useRouter>,
): void {
  if (!reportId || reportId === 'new') {
    router.push(`/reports/${savedReport.id}/edit`);
  }
}

function buildReportData(
  report: MeasureReport | null,
  currentLayout: ReturnType<typeof useEditorStore.getState>['layout'],
): MeasureReport {
  const reportData: MeasureReport = report
    ? { ...report }
    : {
        resourceType: 'MeasureReport',
        status: 'pending',
        type: currentLayout.reportScope === 'patient' ? 'individual' : 'summary',
        measure: 'Measure/placeholder',
        period: {
          start: new Date().toISOString().split('T')[0],
          end: new Date().toISOString().split('T')[0],
        },
      };
  reportData.type = currentLayout.reportScope === 'patient' ? 'individual' : 'summary';

  if (currentLayout.reportScope === 'patient' && currentLayout.runtimeParams?.subjectRef) {
    reportData.subject = { reference: currentLayout.runtimeParams.subjectRef };
  } else if (currentLayout.reportScope !== 'patient') {
    reportData.subject = undefined;
  }
  return reportData;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function buildDropElement(
  type: ElementType,
  x: number,
  y: number,
  w: number,
  h: number,
): Record<string, any> | null {
  const base = { x, y, w, h };
  const builders: Partial<Record<ElementType, () => Record<string, any>>> = {
    executiveSummary: () => ({
      ...base, type: 'executiveSummary', title: 'Executive Summary',
      mode: 'default', modelSize: 'small', excludedMeasureIds: [],
    }),
    text: () => ({ ...base, type: 'text', text: 'Double-click to edit' } as Omit<TextElement, 'id'>),
    heading1: () => ({ ...base, type: 'heading1', text: 'Heading' }),
    heading2: () => ({ ...base, type: 'heading2', text: 'Heading' }),
    heading3: () => ({ ...base, type: 'heading3', text: 'Heading' }),
    subtitle: () => ({ ...base, type: 'subtitle', text: 'Heading' }),
    bulletList: () => ({ ...base, type: 'bulletList', items: ['First item', 'Second item'] }),
    checklist: () => ({
      ...base, type: 'checklist', items: [
        { id: `check-${Date.now()}-1`, text: 'Checklist item', checked: false },
        { id: `check-${Date.now()}-2`, text: 'Second item', checked: false },
      ],
    }),
    divider: () => ({ ...base, type: 'divider', thickness: 2 }),
    cover: () => ({
      ...base, type: 'cover', title: 'Report Title', subtitle: 'Subtitle',
      date: new Date().toISOString().split('T')[0],
      panelBackgroundColor: 'rgba(255, 255, 255, 0.85)',
      panelBorderColor: '#0078D4',
    }),
    image: () => ({ ...base, type: 'image', src: '', objectFit: 'contain' } as Omit<ImageElement, 'id'>),
    table: () => ({
      ...base, type: 'table',
      columns: [{ id: 'col1', header: 'Column 1' }, { id: 'col2', header: 'Column 2' }],
      rows: [], showHeader: true,
    } as Omit<TableElement, 'id'>),
    chart: () => ({
      ...base, type: 'chart', chartType: 'bar', showLegend: true, showGrid: true,
    } as Omit<ChartElement, 'id'>),
    kpiCard: () => ({
      ...base, type: 'kpiCard', title: 'KPI', value: 75, unit: '%',
      target: 80, metTarget: false, comparison: 70, comparisonLabel: 'Previous', trend: 'up',
    } as Omit<KpiCardElement, 'id'>),
    heroStats: () => ({
      ...base, type: 'heroStats', title: 'Hero Stats', stats: [
        { label: 'Total Patients', value: 120 }, { label: 'Urgent Referrals', value: 32 },
        { label: 'Routine', value: 68 }, { label: 'Screening', value: 20 },
      ],
    } as Omit<HeroStatsElement, 'id'>),
    comparisonBars: () => ({
      ...base, type: 'comparisonBars', title: 'Comparison', metrics: [
        { metric: 'Timeliness', current: 72, target: 80, benchmark: 75, unit: '%' },
        { metric: 'Completion', current: 84, target: 90, benchmark: 88, unit: '%' },
      ],
    } as Omit<ComparisonBarsElement, 'id'>),
    populationPyramid: () => ({
      ...base, type: 'populationPyramid', title: 'Population Pyramid', data: [
        { ageBand: '0-18', male: 12, female: 10 }, { ageBand: '19-35', male: 30, female: 28 },
        { ageBand: '36-50', male: 22, female: 25 }, { ageBand: '51-65', male: 18, female: 20 },
        { ageBand: '66+', male: 10, female: 12 },
      ],
    } as Omit<PopulationPyramidElement, 'id'>),
    tableOfContents: () => ({
      ...base, type: 'tableOfContents', title: 'Table of Contents', showPageNumbers: true,
    } as Omit<TableOfContentsElement, 'id'>),
  };

  const builder = builders[type];
  return builder ? builder() : null;
}
/* eslint-enable @typescript-eslint/no-explicit-any */
