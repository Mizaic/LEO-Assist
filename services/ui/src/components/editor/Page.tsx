/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { useCallback, forwardRef } from 'react';
import Box from '@mui/material/Box';
import { useEditorStore } from '@/stores/editorStore';
import { LayoutPage, getPageDimensions } from '@/lib/types/layout';
import { Element } from './Element';

const MM_TO_PX = 96 / 25.4;

interface PageProps {
  page: LayoutPage;
  scale?: number;
  isSelected?: boolean;
  onClick?: () => void;
  readOnly?: boolean;
}

export const Page = forwardRef<HTMLDivElement, PageProps>(function Page(
  { page, scale = 1, isSelected = false, onClick, readOnly = false },
  ref
) {
  const { showGrid, selectedPageId, setSelection, alignmentGuides, isDraggingElement } =
    useEditorStore();

  const dimensions = getPageDimensions('A4', page.orientation);
  const widthPx = dimensions.width * MM_TO_PX * scale;
  const heightPx = dimensions.height * MM_TO_PX * scale;

  const handlePageClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        setSelection(page.id, []);
        onClick?.();
      }
    },
    [page.id, setSelection, onClick]
  );

  return (
    <Box
      ref={ref}
      sx={(theme) => ({
        bgcolor: '#ffffff',
        boxShadow: isSelected
          ? `0 0 0 2px ${theme.palette.primary.main}, 0 2px 8px rgba(0, 0, 0, 0.15)`
          : '0 2px 8px rgba(0, 0, 0, 0.15)',
        border: '1px solid #ddd',
        position: 'relative',
        overflow: isDraggingElement ? 'visible' : 'hidden',
        flexShrink: 0,
      })}
      style={{
        width: widthPx,
        height: heightPx,
        backgroundColor: page.backgroundColor || '#ffffff',
        color: '#111111',
      }}
      onClick={handlePageClick}
      data-page-id={page.id}
    >
      {showGrid && !readOnly && (
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'none',
            backgroundImage:
              'linear-gradient(to right, rgba(0, 0, 0, 0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(0, 0, 0, 0.05) 1px, transparent 1px)',
            backgroundSize: '5mm 5mm',
            zIndex: 1,
          }}
        />
      )}
      {page.id === selectedPageId && alignmentGuides?.x !== undefined && (
        <Box
          sx={(theme) => ({
            position: 'absolute',
            bgcolor: theme.palette.primary.main,
            opacity: 0.7,
            pointerEvents: 'none',
            width: '1px',
            top: 0,
            bottom: 0,
          })}
          style={{ left: alignmentGuides.x * MM_TO_PX * scale }}
        />
      )}
      {page.id === selectedPageId && alignmentGuides?.y !== undefined && (
        <Box
          sx={(theme) => ({
            position: 'absolute',
            bgcolor: theme.palette.primary.main,
            opacity: 0.7,
            pointerEvents: 'none',
            height: '1px',
            left: 0,
            right: 0,
          })}
          style={{ top: alignmentGuides.y * MM_TO_PX * scale }}
        />
      )}
      <Box sx={{ position: 'absolute', inset: 0, zIndex: 2 }}>
        {page.elements
          .slice()
          .sort((a, b) => (a.zIndex || 0) - (b.zIndex || 0))
          .map((element) => (
            <Element
              key={element.id}
              element={element}
              pageId={page.id}
              scale={scale}
              readOnly={readOnly}
            />
          ))}
      </Box>
    </Box>
  );
});
