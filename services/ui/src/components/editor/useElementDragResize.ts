import { useCallback, useState, useRef, useEffect, type RefObject } from 'react';
import { useEditorStore } from '@/stores/editorStore';
import { LayoutElement, getPageDimensions } from '@/lib/types/layout';

/** Millimetres to pixels at 96 DPI. */
export const MM_TO_PX = 96 / 25.4;

export interface UseElementDragResizeParams {
  element: LayoutElement;
  pageId: string;
  scale: number;
  readOnly: boolean;
  elementRef: RefObject<HTMLDivElement | null>;
  interactiveSelector: string;
}

export interface UseElementDragResizeResult {
  isDragging: boolean;
  isResizing: boolean;
  isSelected: boolean;
  isHovered: boolean;
  handleClick: (e: React.MouseEvent) => void;
  handleMouseDown: (e: React.MouseEvent) => void;
  handleMouseEnter: () => void;
  handleMouseLeave: () => void;
  handleResizeStart: (e: React.MouseEvent, handle: string) => void;
}

export function useElementDragResize({
  element,
  pageId,
  scale,
  readOnly,
  elementRef,
  interactiveSelector,
}: UseElementDragResizeParams): UseElementDragResizeResult {
  const {
    selectedElementIds,
    hoveredElementId,
    setSelection,
    addToSelection,
    setHoveredElement,
    moveElement,
    resizeElement,
    moveElementToPage,
    setAlignmentGuides,
    clearAlignmentGuides,
    layout,
    setIsDraggingElement,
  } = useEditorStore();

  const isSelected = selectedElementIds.includes(element.id);
  const isHovered = hoveredElementId === element.id;

  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [resizeHandle, setResizeHandle] = useState<string | null>(null);
  const dragStartPos = useRef({ x: 0, y: 0 });
  const elementStartPos = useRef({ x: 0, y: 0, w: 0, h: 0 });
  const dragPointerOffset = useRef({ x: 0, y: 0 });

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (readOnly) return;
      const target = e.target as HTMLElement | null;
      if (target?.isContentEditable && document.activeElement === target) return;
      if (target?.closest(interactiveSelector)) return;

      if (e.shiftKey || e.ctrlKey || e.metaKey) {
        addToSelection(element.id);
      } else {
        setSelection(pageId, [element.id]);
      }
    },
    [element.id, pageId, readOnly, addToSelection, setSelection, interactiveSelector]
  );

  const handleMouseEnter = useCallback(() => {
    if (!readOnly && !isDragging && !isResizing) {
      setHoveredElement(element.id);
    }
  }, [element.id, readOnly, isDragging, isResizing, setHoveredElement]);

  const handleMouseLeave = useCallback(() => {
    if (!isDragging && !isResizing) {
      setHoveredElement(null);
    }
  }, [isDragging, isResizing, setHoveredElement]);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (readOnly || e.button !== 0) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest('[data-resize-handle]')) return;
      if (target?.isContentEditable && document.activeElement === target) return;
      if (target?.closest(interactiveSelector)) return;

      e.preventDefault();
      e.stopPropagation();

      if (!isSelected) {
        setSelection(pageId, [element.id]);
      }

      setIsDragging(true);
      setIsDraggingElement(true);
      dragStartPos.current = { x: e.clientX, y: e.clientY };
      elementStartPos.current = { x: element.x, y: element.y, w: element.w, h: element.h };
      if (elementRef.current) {
        const rect = elementRef.current.getBoundingClientRect();
        dragPointerOffset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
      } else {
        dragPointerOffset.current = { x: 0, y: 0 };
      }
    },
    [element, pageId, isSelected, readOnly, setSelection, setIsDraggingElement, interactiveSelector, elementRef]
  );

  const handleResizeStart = useCallback(
    (e: React.MouseEvent, handle: string) => {
      if (readOnly) return;
      e.preventDefault();
      e.stopPropagation();
      setIsResizing(true);
      setResizeHandle(handle);
      dragStartPos.current = { x: e.clientX, y: e.clientY };
      elementStartPos.current = { x: element.x, y: element.y, w: element.w, h: element.h };
    },
    [element, readOnly]
  );

  /** Build alignment candidates for a given axis. */
  function buildAlignmentCandidates(
    page: { elements: LayoutElement[] },
    pageCenter: number,
    elementCenter: number,
    elementEdge: number,
    axis: 'x' | 'y',
  ): Array<{ value: number; diff: number }> {
    const candidates = [
      { value: pageCenter, diff: Math.abs(elementCenter - pageCenter) },
    ];
    for (const el of page.elements) {
      if (el.id === element.id) continue;
      if (axis === 'x') {
        candidates.push(
          { value: el.x, diff: Math.abs(elementEdge - el.x) },
          { value: el.x + el.w, diff: Math.abs(elementEdge + element.w - (el.x + el.w)) },
          { value: el.x + el.w / 2, diff: Math.abs(elementCenter - (el.x + el.w / 2)) },
        );
      } else {
        candidates.push(
          { value: el.y, diff: Math.abs(elementEdge - el.y) },
          { value: el.y + el.h, diff: Math.abs(elementEdge + element.h - (el.y + el.h)) },
          { value: el.y + el.h / 2, diff: Math.abs(elementCenter - (el.y + el.h / 2)) },
        );
      }
    }
    return candidates;
  }

  /** Move the element and compute alignment guides during a drag. */
  function handleDragMove(_e: MouseEvent, deltaX: number, deltaY: number): void {
    const newX = elementStartPos.current.x + deltaX;
    const newY = elementStartPos.current.y + deltaY;
    moveElement(pageId, element.id, newX, newY);

    const page = layout.pages.find((p) => p.id === pageId);
    if (!page) return;

    const pageDims = getPageDimensions(layout.pageSize, page.orientation);
    const centerX = newX + element.w / 2;
    const centerY = newY + element.h / 2;
    const threshold = 2;

    const xCandidates = buildAlignmentCandidates(page, pageDims.width / 2, centerX, newX, 'x');
    const yCandidates = buildAlignmentCandidates(page, pageDims.height / 2, centerY, newY, 'y');
    const nearestX = xCandidates.sort((a, b) => a.diff - b.diff)[0];
    const nearestY = yCandidates.sort((a, b) => a.diff - b.diff)[0];

    setAlignmentGuides({
      x: nearestX && nearestX.diff <= threshold ? nearestX.value : undefined,
      y: nearestY && nearestY.diff <= threshold ? nearestY.value : undefined,
    });
  }

  /** Apply resize deltas, enforcing a minimum element size. */
  function handleResizeMove(deltaX: number, deltaY: number): void {
    let newX = elementStartPos.current.x;
    let newY = elementStartPos.current.y;
    let newW = elementStartPos.current.w;
    let newH = elementStartPos.current.h;

    if (resizeHandle?.includes('w')) { newX += deltaX; newW -= deltaX; }
    if (resizeHandle?.includes('e')) { newW += deltaX; }
    if (resizeHandle?.includes('n')) { newY += deltaY; newH -= deltaY; }
    if (resizeHandle?.includes('s')) { newH += deltaY; }

    if (newW < 10 || newH < 10) return;
    if (newX !== element.x || newY !== element.y) moveElement(pageId, element.id, newX, newY);
    if (newW !== element.w || newH !== element.h) resizeElement(pageId, element.id, newW, newH);
  }

  /** Detect cross-page drops on drag end. */
  function handleDragEnd(e: MouseEvent): void {
    const target = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;
    const targetPage = target?.closest?.('[data-page-id]') as HTMLElement | null;
    const targetPageId = targetPage?.dataset?.pageId || null;

    if (!targetPageId || targetPageId === pageId || !targetPage) return;

    const pageRect = targetPage.getBoundingClientRect();
    const newX = (e.clientX - pageRect.left - dragPointerOffset.current.x) / scale / MM_TO_PX;
    const newY = (e.clientY - pageRect.top - dragPointerOffset.current.y) / scale / MM_TO_PX;
    moveElementToPage(pageId, targetPageId, element.id, newX, newY);
  }

  useEffect(() => {
    if (!isDragging && !isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const deltaX = (e.clientX - dragStartPos.current.x) / scale / MM_TO_PX;
      const deltaY = (e.clientY - dragStartPos.current.y) / scale / MM_TO_PX;

      if (isDragging) {
        handleDragMove(e, deltaX, deltaY);
      }

      if (isResizing && resizeHandle) {
        handleResizeMove(deltaX, deltaY);
      }
    };

    const handleMouseUp = (e: MouseEvent) => {
      if (isDragging) {
        handleDragEnd(e);
      }
      setIsDragging(false);
      setIsResizing(false);
      setResizeHandle(null);
      setIsDraggingElement(false);
      clearAlignmentGuides();
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  });

  return {
    isDragging,
    isResizing,
    isSelected,
    isHovered,
    handleClick,
    handleMouseDown,
    handleMouseEnter,
    handleMouseLeave,
    handleResizeStart,
  };
}
