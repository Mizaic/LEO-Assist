/**
 * Page-level actions for the editor store.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
import {
  generatePageId,
  generateElementId,
} from '@/lib/types/layout';
import type { LayoutPage, PageOrientation } from '@/lib/types/layout';
import type { EditorSet } from './types';
import { pushHistory } from './utils';

export function createPageActions(set: EditorSet) {
  return {
    addPage: (orientation: PageOrientation = 'portrait', insertIndex?: number) => {
      set((state) => {
        pushHistory(state.past, state.future, state.layout);

        const newPage: LayoutPage = {
          id: generatePageId(),
          orientation,
          elements: [],
        };

        if (insertIndex !== undefined && insertIndex >= 0) {
          state.layout.pages.splice(insertIndex, 0, newPage);
        } else {
          state.layout.pages.push(newPage);
        }

        state.selectedPageId = newPage.id;
        state.selectedElementIds = [];
        state.isDirty = true;
      });
    },

    deletePage: (pageId: string) => {
      set((state) => {
        if (state.layout.pages.length <= 1) return;

        pushHistory(state.past, state.future, state.layout);

        const index = state.layout.pages.findIndex((p) => p.id === pageId);
        if (index === -1) return;

        state.layout.pages.splice(index, 1);
        if (state.selectedPageId === pageId) {
          state.selectedPageId =
            state.layout.pages[Math.max(0, index - 1)]?.id || null;
          state.selectedElementIds = [];
        }
        state.isDirty = true;
      });
    },

    reorderPages: (fromIndex: number, toIndex: number) => {
      set((state) => {
        if (fromIndex === toIndex) return;
        if (fromIndex < 0 || fromIndex >= state.layout.pages.length) return;
        if (toIndex < 0 || toIndex >= state.layout.pages.length) return;

        pushHistory(state.past, state.future, state.layout);

        const [page] = state.layout.pages.splice(fromIndex, 1);
        state.layout.pages.splice(toIndex, 0, page);
        state.isDirty = true;
      });
    },

    setPageOrientation: (pageId: string, orientation: PageOrientation) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page || page.orientation === orientation) return;

        pushHistory(state.past, state.future, state.layout);
        page.orientation = orientation;
        state.isDirty = true;
      });
    },

    updatePage: (pageId: string, updates: Partial<LayoutPage>) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;

        pushHistory(state.past, state.future, state.layout);
        Object.assign(page, updates);
        state.isDirty = true;
      });
    },

    duplicatePage: (pageId: string) => {
      set((state) => {
        const page = state.layout.pages.find((p) => p.id === pageId);
        if (!page) return;

        pushHistory(state.past, state.future, state.layout);

        const newPage: LayoutPage = {
          ...JSON.parse(JSON.stringify(page)),
          id: generatePageId(),
          elements: page.elements.map((el) => ({
            ...JSON.parse(JSON.stringify(el)),
            id: generateElementId(el.type),
          })),
        };

        const index = state.layout.pages.findIndex((p) => p.id === pageId);
        state.layout.pages.splice(index + 1, 0, newPage);
        state.selectedPageId = newPage.id;
        state.selectedElementIds = [];
        state.isDirty = true;
      });
    },
  };
}
