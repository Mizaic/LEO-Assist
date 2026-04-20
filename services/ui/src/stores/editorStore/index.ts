/**
 * Editor store -- Zustand + immer.
 *
 * Composed from focused slice files.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { DEFAULT_LAYOUT } from '@/lib/types/layout';
import type { EditorState } from './types';
import { createDocumentActions } from './documentActions';
import { createPageActions } from './pageActions';
import {
  createElementActions,
  createSelectionActions,
  createUIActions,
  createHistoryActions,
  createGetters,
} from './elementActions';

export { GRID_SIZE, snapToGrid } from './utils';
export type { EditorState } from './types';

export const useEditorStore = create<EditorState>()(
  immer((set, get) => ({
    reportId: null,
    report: null,
    layout: DEFAULT_LAYOUT,
    isDirty: false,

    selectedPageId: null,
    selectedElementIds: [],
    hoveredElementId: null,
    zoom: 1,
    baseZoom: 1,
    showGrid: true,
    snapToGrid: true,
    isPreviewing: false,
    alignmentGuides: null,
    isDraggingElement: false,

    past: [],
    future: [],

    ...createDocumentActions(set),
    ...createPageActions(set),
    ...createElementActions(set),
    ...createSelectionActions(set),
    ...createUIActions(set),
    ...createHistoryActions(set, get),
    ...createGetters(get),
  }))
);
