/**
 * Type definitions for the editor store.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
import type {
  LayoutJson,
  LayoutPage,
  LayoutElement,
  PageOrientation,
  ReportScope,
} from '@/lib/types/layout';
import type { MeasureReport } from '@/lib/types/fhir';

export interface EditorState {
  reportId: string | null;
  report: MeasureReport | null;
  layout: LayoutJson;
  isDirty: boolean;

  selectedPageId: string | null;
  selectedElementIds: string[];
  hoveredElementId: string | null;
  zoom: number;
  baseZoom: number;
  showGrid: boolean;
  snapToGrid: boolean;
  isPreviewing: boolean;
  alignmentGuides: { x?: number; y?: number } | null;
  isDraggingElement: boolean;

  past: LayoutJson[];
  future: LayoutJson[];

  initializeEditor: (report: MeasureReport | null, layout: LayoutJson) => void;
  resetEditor: () => void;
  setDirty: (dirty: boolean) => void;
  setReport: (report: MeasureReport | null) => void;
  updateReport: (updates: Partial<MeasureReport>) => void;
  setReportScope: (scope: ReportScope) => void;
  setRuntimeParams: (params: Partial<NonNullable<LayoutJson['runtimeParams']>>) => void;

  addPage: (orientation?: PageOrientation, insertIndex?: number) => void;
  deletePage: (pageId: string) => void;
  reorderPages: (fromIndex: number, toIndex: number) => void;
  setPageOrientation: (pageId: string, orientation: PageOrientation) => void;
  updatePage: (pageId: string, updates: Partial<LayoutPage>) => void;
  duplicatePage: (pageId: string) => void;

  addElement: (pageId: string, element: Omit<LayoutElement, 'id'>) => string;
  updateElement: (pageId: string, elementId: string, updates: Partial<LayoutElement>) => void;
  deleteElement: (pageId: string, elementId: string) => void;
  deleteSelectedElements: () => void;
  duplicateElement: (pageId: string, elementId: string) => void;
  moveElement: (pageId: string, elementId: string, x: number, y: number) => void;
  resizeElement: (pageId: string, elementId: string, w: number, h: number) => void;
  moveElementToPage: (fromPageId: string, toPageId: string, elementId: string, x: number, y: number) => void;
  bringToFront: (pageId: string, elementId: string) => void;
  sendToBack: (pageId: string, elementId: string) => void;

  setSelection: (pageId: string | null, elementIds: string[]) => void;
  addToSelection: (elementId: string) => void;
  removeFromSelection: (elementId: string) => void;
  clearSelection: () => void;
  selectAll: (pageId: string) => void;
  setHoveredElement: (elementId: string | null) => void;

  setZoom: (zoom: number) => void;
  setBaseZoom: (zoom: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
  toggleGrid: () => void;
  toggleSnapToGrid: () => void;
  setIsPreviewing: (previewing: boolean) => void;
  setAlignmentGuides: (guides: { x?: number; y?: number } | null) => void;
  clearAlignmentGuides: () => void;
  setIsDraggingElement: (dragging: boolean) => void;

  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  getPage: (pageId: string) => LayoutPage | undefined;
  getElement: (pageId: string, elementId: string) => LayoutElement | undefined;
  getSelectedPage: () => LayoutPage | undefined;
  getSelectedElements: () => LayoutElement[];
}

export type EditorSet = (fn: (state: EditorState) => void) => void;
export type EditorGet = () => EditorState;
