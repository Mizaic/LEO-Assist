/**
 * Element-level, selection, UI, and history actions for the editor store.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
import { generateElementId } from '@/lib/types/layout';
import type { LayoutElement } from '@/lib/types/layout';
import type { EditorSet, EditorGet } from './types';
import { pushHistory, snapToGrid } from './utils';

export function createElementActions(set: EditorSet) {
  return {
    addElement: (pageId: string, element: Omit<LayoutElement, 'id'>): string => {
      const elementId = generateElementId(element.type);
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;
        pushHistory(state.past, state.future, state.layout);

        const newEl = {
          ...element,
          id: elementId,
          zIndex: page.elements.length,
        } as LayoutElement;
        page.elements.push(newEl);
        state.selectedPageId = pageId;
        state.selectedElementIds = [elementId];
        state.isDirty = true;
      });
      return elementId;
    },

    updateElement: (
      pageId: string,
      elementId: string,
      updates: Partial<LayoutElement>
    ) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;
        const element = page.elements.find((el) => el.id === elementId);
        if (!element) return;
        pushHistory(state.past, state.future, state.layout);
        Object.assign(element, updates);
        state.isDirty = true;
      });
    },

    deleteElement: (pageId: string, elementId: string) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;
        const index = page.elements.findIndex((el) => el.id === elementId);
        if (index === -1) return;
        pushHistory(state.past, state.future, state.layout);
        page.elements.splice(index, 1);
        state.selectedElementIds = state.selectedElementIds.filter(
          (id) => id !== elementId
        );
        state.isDirty = true;
      });
    },

    deleteSelectedElements: () => {
      set((state) => {
        if (!state.selectedPageId || state.selectedElementIds.length === 0) return;
        const page = state.layout.pages.find(
          (p) => p.id === state.selectedPageId
        );
        if (!page) return;
        pushHistory(state.past, state.future, state.layout);
        page.elements = page.elements.filter(
          (el) => !state.selectedElementIds.includes(el.id)
        );
        state.selectedElementIds = [];
        state.isDirty = true;
      });
    },

    duplicateElement: (pageId: string, elementId: string) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;
        const element = page.elements.find((el) => el.id === elementId);
        if (!element) return;
        pushHistory(state.past, state.future, state.layout);

        const newEl: LayoutElement = {
          ...JSON.parse(JSON.stringify(element)),
          id: generateElementId(element.type),
          x: element.x + 10,
          y: element.y + 10,
          zIndex: page.elements.length,
        };
        page.elements.push(newEl);
        state.selectedElementIds = [newEl.id];
        state.isDirty = true;
      });
    },

    moveElement: (pageId: string, elementId: string, x: number, y: number) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;
        const element = page.elements.find((el) => el.id === elementId);
        if (!element) return;
        const finalX = state.snapToGrid ? snapToGrid(x) : x;
        const finalY = state.snapToGrid ? snapToGrid(y) : y;
        if (element.x !== finalX || element.y !== finalY) {
          element.x = finalX;
          element.y = finalY;
          state.isDirty = true;
        }
      });
    },

    resizeElement: (pageId: string, elementId: string, w: number, h: number) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;
        const element = page.elements.find((el) => el.id === elementId);
        if (!element) return;
        const finalW = state.snapToGrid ? snapToGrid(w) : w;
        const finalH = state.snapToGrid ? snapToGrid(h) : h;
        if (element.w !== finalW || element.h !== finalH) {
          element.w = Math.max(10, finalW);
          element.h = Math.max(10, finalH);
          state.isDirty = true;
        }
      });
    },

    moveElementToPage: (
      fromPageId: string,
      toPageId: string,
      elementId: string,
      x: number,
      y: number
    ) => {
      set((state) => {
        if (fromPageId === toPageId) return;
        const fromPage = state.layout.pages.find((p) => p.id === fromPageId);
        const toPage = state.layout.pages.find((p) => p.id === toPageId);
        if (!fromPage || !toPage) return;
        const idx = fromPage.elements.findIndex((el) => el.id === elementId);
        if (idx === -1) return;

        const [element] = fromPage.elements.splice(idx, 1);
        element.x = state.snapToGrid ? snapToGrid(x) : x;
        element.y = state.snapToGrid ? snapToGrid(y) : y;
        element.zIndex = toPage.elements.length;
        toPage.elements.push(element);
        state.selectedPageId = toPageId;
        state.selectedElementIds = [elementId];
        state.isDirty = true;
      });
    },

    bringToFront: (pageId: string, elementId: string) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;
        const element = page.elements.find((el) => el.id === elementId);
        if (!element) return;
        pushHistory(state.past, state.future, state.layout);
        const maxZ = Math.max(...page.elements.map((el) => el.zIndex || 0));
        element.zIndex = maxZ + 1;
        state.isDirty = true;
      });
    },

    sendToBack: (pageId: string, elementId: string) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;
        const element = page.elements.find((el) => el.id === elementId);
        if (!element) return;
        pushHistory(state.past, state.future, state.layout);
        const minZ = Math.min(...page.elements.map((el) => el.zIndex || 0));
        element.zIndex = minZ - 1;
        state.isDirty = true;
      });
    },
  };
}

export function createSelectionActions(set: EditorSet) {
  return {
    setSelection: (pageId: string | null, elementIds: string[]) => {
      set((state) => {
        state.selectedPageId = pageId;
        state.selectedElementIds = elementIds;
      });
    },
    addToSelection: (elementId: string) => {
      set((state) => {
        if (!state.selectedElementIds.includes(elementId)) {
          state.selectedElementIds.push(elementId);
        }
      });
    },
    removeFromSelection: (elementId: string) => {
      set((state) => {
        state.selectedElementIds = state.selectedElementIds.filter(
          (id) => id !== elementId
        );
      });
    },
    clearSelection: () => {
      set((state) => {
        state.selectedElementIds = [];
      });
    },
    selectAll: (pageId: string) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;
        state.selectedPageId = pageId;
        state.selectedElementIds = page.elements.map((el) => el.id);
      });
    },
    setHoveredElement: (elementId: string | null) => {
      set((state) => {
        state.hoveredElementId = elementId;
      });
    },
  };
}

export function createUIActions(set: EditorSet) {
  return {
    setZoom: (zoom: number) => {
      set((state) => { state.zoom = Math.max(0.25, Math.min(4, zoom)); });
    },
    setBaseZoom: (zoom: number) => {
      set((state) => { state.baseZoom = Math.max(0.25, Math.min(4, zoom)); });
    },
    zoomIn: () => {
      set((state) => {
        const step = Math.max(0.05, state.baseZoom * 0.1);
        state.zoom = Math.min(4, state.zoom + step);
      });
    },
    zoomOut: () => {
      set((state) => {
        const step = Math.max(0.05, state.baseZoom * 0.1);
        state.zoom = Math.max(0.25, state.zoom - step);
      });
    },
    resetZoom: () => {
      set((state) => { state.zoom = state.baseZoom; });
    },
    toggleGrid: () => {
      set((state) => { state.showGrid = !state.showGrid; });
    },
    toggleSnapToGrid: () => {
      set((state) => { state.snapToGrid = !state.snapToGrid; });
    },
    setIsPreviewing: (previewing: boolean) => {
      set((state) => { state.isPreviewing = previewing; });
    },
    setAlignmentGuides: (guides: { x?: number; y?: number } | null) => {
      set((state) => { state.alignmentGuides = guides; });
    },
    clearAlignmentGuides: () => {
      set((state) => { state.alignmentGuides = null; });
    },
    setIsDraggingElement: (dragging: boolean) => {
      set((state) => { state.isDraggingElement = dragging; });
    },
  };
}

export function createHistoryActions(set: EditorSet, get: EditorGet) {
  return {
    undo: () => {
      set((state) => {
        if (state.past.length === 0) return;
        const previous = state.past.pop()!;
        state.future.push(JSON.parse(JSON.stringify(state.layout)));
        state.layout = previous;
        state.selectedElementIds = [];
        state.isDirty = true;
      });
    },
    redo: () => {
      set((state) => {
        if (state.future.length === 0) return;
        const next = state.future.pop()!;
        state.past.push(JSON.parse(JSON.stringify(state.layout)));
        state.layout = next;
        state.selectedElementIds = [];
        state.isDirty = true;
      });
    },
    canUndo: () => get().past.length > 0,
    canRedo: () => get().future.length > 0,
  };
}

export function createGetters(get: EditorGet) {
  return {
    getPage: (pageId: string) =>
      get().layout.pages.find((p) => p.id === pageId),
    getElement: (pageId: string, elementId: string) => {
      const page = get().layout.pages.find((p) => p.id === pageId);
      return page?.elements.find((el) => el.id === elementId);
    },
    getSelectedPage: () => {
      const { selectedPageId, layout } = get();
      return layout.pages.find((p) => p.id === selectedPageId);
    },
    getSelectedElements: () => {
      const { selectedPageId, selectedElementIds, layout } = get();
      const page = layout.pages.find((p) => p.id === selectedPageId);
      if (!page) return [];
      return page.elements.filter((el) => selectedElementIds.includes(el.id));
    },
  };
}
