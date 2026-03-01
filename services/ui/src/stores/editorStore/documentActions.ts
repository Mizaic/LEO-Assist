/**
 * Document-level actions for the editor store.
 */

import { DEFAULT_LAYOUT } from '@/lib/types/layout';
import type { EditorSet } from './types';
import { normalizeLayout, MAX_HISTORY } from './utils';
import type { MeasureReport } from '@/lib/types/fhir';
import type { LayoutJson, ReportScope } from '@/lib/types/layout';

export function createDocumentActions(set: EditorSet) {
  return {
    initializeEditor: (report: MeasureReport | null, layout: LayoutJson) => {
      set((state) => {
        const merged: LayoutJson = {
          ...DEFAULT_LAYOUT,
          ...layout,
          pages: layout.pages?.length ? layout.pages : DEFAULT_LAYOUT.pages,
          reportScope: layout.reportScope ?? DEFAULT_LAYOUT.reportScope,
          runtimeParams: {
            ...(DEFAULT_LAYOUT.runtimeParams || {}),
            ...(layout.runtimeParams || {}),
          },
        };
        const { layout: sanitized, didNormalize } = normalizeLayout(merged);
        state.reportId = report?.id || null;
        state.report = report;
        state.layout = sanitized;
        state.isDirty = didNormalize;
        state.past = [];
        state.future = [];
        state.selectedPageId = sanitized.pages[0]?.id || null;
        state.selectedElementIds = [];
      });
    },

    resetEditor: () => {
      set((state) => {
        state.reportId = null;
        state.report = null;
        state.layout = DEFAULT_LAYOUT;
        state.isDirty = false;
        state.past = [];
        state.future = [];
        state.selectedPageId = DEFAULT_LAYOUT.pages[0]?.id || null;
        state.selectedElementIds = [];
      });
    },

    setDirty: (dirty: boolean) => {
      set((state) => {
        state.isDirty = dirty;
      });
    },

    setReport: (report: MeasureReport | null) => {
      set((state) => {
        state.report = report;
      });
    },

    updateReport: (updates: Partial<MeasureReport>) => {
      set((state) => {
        const today = new Date().toISOString().split('T')[0];
        if (!state.report) {
          state.report = {
            resourceType: 'MeasureReport',
            status: 'pending',
            type:
              state.layout.reportScope === 'patient'
                ? 'individual'
                : 'summary',
            measure: 'Measure/placeholder',
            period: { start: today, end: today },
          };
          if (
            state.layout.reportScope === 'patient' &&
            state.layout.runtimeParams?.subjectRef
          ) {
            state.report.subject = {
              reference: state.layout.runtimeParams.subjectRef,
            };
          }
        }
        if (!state.report) return;

        if (updates.period) {
          state.report.period = {
            ...(state.report.period || {}),
            ...updates.period,
          };
        }
        const { period, ...rest } = updates;
        Object.assign(state.report, rest);
        state.isDirty = true;
      });
    },

    setReportScope: (scope: ReportScope) => {
      set((state) => {
        if (state.layout.reportScope === scope) return;
        state.past.push(JSON.parse(JSON.stringify(state.layout)));
        if (state.past.length > MAX_HISTORY) state.past.shift();
        state.future = [];
        state.layout.reportScope = scope;
        state.isDirty = true;
      });
    },

    setRuntimeParams: (params: Partial<NonNullable<LayoutJson['runtimeParams']>>) => {
      set((state) => {
        state.past.push(JSON.parse(JSON.stringify(state.layout)));
        if (state.past.length > MAX_HISTORY) state.past.shift();
        state.future = [];
        state.layout.runtimeParams = {
          ...(state.layout.runtimeParams || {}),
          ...(params || {}),
        };
        state.isDirty = true;
      });
    },
  };
}
