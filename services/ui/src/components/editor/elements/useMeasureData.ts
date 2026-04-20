/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
import { useState, useEffect, useMemo } from 'react';
import { getMeasure, evaluateMeasure } from '@/lib/api';
import { Measure, MeasureReport } from '@/lib/types/fhir';
import { ApiError } from '@/lib/api/client';
import { BenchmarkPoint, extractBenchmarkComparison } from '@/lib/measureData';
import { MeasureElement as MeasureElementType } from '@/lib/types/layout';
import { useEditorStore } from '@/stores/editorStore';
import { useOrgId } from '@/context/OrgContext';

export interface UseMeasureDataResult {
  measure: Measure | null;
  measureReport: MeasureReport | null;
  benchmarks: BenchmarkPoint[] | null;
  loading: boolean;
  dataLoading: boolean;
  errorMessage: string | null;
}

export function useMeasureData(element: MeasureElementType): UseMeasureDataResult {
  const [measure, setMeasure] = useState<Measure | null>(null);
  const [loading, setLoading] = useState(false);
  const [dataLoading, setDataLoading] = useState(false);
  const [measureReport, setMeasureReport] = useState<MeasureReport | null>(null);
  const [benchmarks, setBenchmarks] = useState<BenchmarkPoint[] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const report = useEditorStore((state) => state.report);
  const reportScope = useEditorStore((state) => state.layout.reportScope);
  const runtimeParams = useEditorStore((state) => state.layout.runtimeParams);
  const globalOrgId = useOrgId();
  const orgIdsKey = (runtimeParams?.organizationIds || []).join('|');

  const mergedFilters = useMemo(() => ({
    ...(runtimeParams?.cohortFilters || {}),
    ...(element.cohortFilters || {}),
  }), [runtimeParams?.cohortFilters, element.cohortFilters]);

  const cohortFiltersKey = JSON.stringify(mergedFilters || {});

  useEffect(() => {
    if (!element.measureId) return;

    const loadAll = async () => {
      // Phase 1: load measure metadata
      setLoading(true);
      let loaded: Measure | null = null;
      try {
        const measureId = element.measureId!.replace('Measure/', '');
        loaded = await getMeasure(measureId);
        setMeasure(loaded);
        setErrorMessage(null);
      } catch (error) {
        const msg = error instanceof ApiError ? error.message : (error instanceof Error ? error.message : 'Failed to load measure');
        setErrorMessage(msg);
        setMeasure(null);
        setLoading(false);
        return;
      } finally {
        setLoading(false);
      }

      // Phase 2: skip evaluation for draft / retired measures
      if (loaded?.status === 'draft' || loaded?.status === 'retired') {
        setMeasureReport(null);
        setBenchmarks(null);
        return;
      }

      // Phase 3: evaluate (org_id required for organization scope)
      const orgId = reportScope === 'organization'
        ? (runtimeParams?.organizationId || globalOrgId)
        : undefined;
      if (reportScope === 'organization' && !orgId) {
        setMeasureReport(null);
        setBenchmarks(null);
        setErrorMessage('Select an organization in the toolbar (or header) to evaluate this measure.');
        return;
      }

      setDataLoading(true);
      try {
        const measureId = element.measureId!.replace('Measure/', '');
        const periodStart = report?.period?.start || new Date().toISOString().split('T')[0];
        const periodEnd = report?.period?.end || new Date().toISOString().split('T')[0];
        const subject = reportScope === 'patient' ? runtimeParams?.subjectRef : undefined;
        const orgIds = reportScope === 'organization' ? runtimeParams?.organizationIds : undefined;
        const result = await evaluateMeasure(measureId, {
          periodStart,
          periodEnd,
          subject,
          orgId,
          orgIds,
          cohortFilters: mergedFilters,
        });
        const evaluated = result as MeasureReport;
        setMeasureReport(evaluated);
        setBenchmarks(extractBenchmarkComparison(evaluated));
        setErrorMessage(null);
      } catch (error) {
        const msg = error instanceof ApiError ? error.message : (error instanceof Error ? error.message : 'Failed to evaluate measure');
        setErrorMessage(msg);
        setMeasureReport(null);
        setBenchmarks(null);
      } finally {
        setDataLoading(false);
      }
    };

    void loadAll();
  }, [
    element.measureId,
    report?.period?.start,
    report?.period?.end,
    reportScope,
    runtimeParams?.subjectRef,
    runtimeParams?.organizationId,
    globalOrgId,
    orgIdsKey,
    cohortFiltersKey,
    runtimeParams?.refreshToken,
    mergedFilters,
  ]);

  return { measure, measureReport, benchmarks, loading, dataLoading, errorMessage };
}
