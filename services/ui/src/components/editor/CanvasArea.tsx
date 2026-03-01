'use client';

import { useRef, useEffect } from 'react';
import Box from '@mui/material/Box';
import { useDroppable } from '@dnd-kit/core';
import { useEditorStore } from '@/stores/editorStore';
import { Page } from './Page';
import { getPageDimensions } from '@/lib/types/layout';

const MM_TO_PX = 96 / 25.4;

interface DroppablePageProps {
  children: React.ReactNode;
  pageId: string;
}

function DroppablePage({ children, pageId }: DroppablePageProps) {
  const { isOver, setNodeRef } = useDroppable({
    id: `page-drop-${pageId}`,
    data: { pageId },
  });

  return (
    <Box ref={setNodeRef} sx={{ position: 'relative' }}>
      {children}
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          border: '2px dashed',
          borderColor: 'primary.main',
          borderRadius: 1,
          pointerEvents: 'none',
          opacity: isOver ? 1 : 0,
          transition: 'opacity 0.2s ease',
          bgcolor: isOver ? 'rgba(0, 120, 212, 0.1)' : 'transparent',
        }}
      />
    </Box>
  );
}

export function CanvasArea() {
  const containerRef = useRef<HTMLDivElement>(null);

  const {
    layout,
    zoom,
    setZoom,
    setBaseZoom,
    selectedPageId,
    setSelection,
  } = useEditorStore();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const { deleteSelectedElements, undo, redo, canUndo, canRedo, selectAll, selectedPageId } = useEditorStore.getState();

      if (e.key === 'Delete' || e.key === 'Backspace') {
        if (document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
          e.preventDefault();
          deleteSelectedElements();
        }
      }

      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault();
        if (e.shiftKey) {
          if (canRedo()) redo();
        } else {
          if (canUndo()) undo();
        }
      }

      if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
        e.preventDefault();
        if (canRedo()) redo();
      }

      if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
        if (document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
          e.preventDefault();
          if (selectedPageId) {
            selectAll(selectedPageId);
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const element = containerRef.current;
    const updateZoom = () => {
      const containerWidth = element.clientWidth;
      const containerHeight = element.clientHeight;
      const page = layout.pages[0];
      if (!page) return;
      const pageDims = getPageDimensions(layout.pageSize, page.orientation);
      const pageWidthPx = pageDims.width * MM_TO_PX;
      const pageHeightPx = pageDims.height * MM_TO_PX;
      const padding = 48;
      const fitZoom = Math.min(
        (containerWidth - padding) / pageWidthPx,
        (containerHeight - padding) / pageHeightPx
      );
      if (Number.isFinite(fitZoom) && fitZoom > 0) {
        const clamped = Math.max(0.25, Math.min(4, fitZoom));
        setBaseZoom(clamped);
        setZoom(clamped);
      }
    };
    updateZoom();
    const resizeObserver = new ResizeObserver(() => updateZoom());
    resizeObserver.observe(element);
    return () => resizeObserver.disconnect();
  }, [layout.pageSize, layout.pages, setBaseZoom, setZoom]);

  return (
    <Box
      ref={containerRef}
      sx={{
        flex: 1,
        overflow: 'auto',
        bgcolor: '#e5e5e5',
        display: 'flex',
        justifyContent: 'center',
        p: 3,
      }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'center' }}>
        {layout.pages.map((page) => (
          <DroppablePage key={page.id} pageId={page.id}>
            <Page
              page={page}
              scale={zoom}
              isSelected={page.id === selectedPageId}
              onClick={() => setSelection(page.id, [])}
            />
          </DroppablePage>
        ))}
      </Box>
    </Box>
  );
}
