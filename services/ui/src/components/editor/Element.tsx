'use client';

import { useRef } from 'react';
import Box from '@mui/material/Box';
import { useEditorStore } from '@/stores/editorStore';
import { LayoutElement, ChecklistElement as ChecklistElementType } from '@/lib/types/layout';
import { useElementDragResize, MM_TO_PX } from './useElementDragResize';
import { MeasureElement } from './elements/MeasureElement';
import { InterpretationElement } from './elements/InterpretationElement';
import { ExecutiveSummaryElement } from './elements/ExecutiveSummaryElement';
import { TextElement } from './elements/TextElement';
import { HeadingElement } from './elements/HeadingElement';
import { BulletListElement } from './elements/BulletListElement';
import { ChecklistElement } from './elements/ChecklistElement';
import { DividerElement } from './elements/DividerElement';
import { CoverElement } from './elements/CoverElement';
import { ImageElement } from './elements/ImageElement';
import { TableElement } from './elements/TableElement';
import { ChartElement } from './elements/ChartElement';
import { KpiCardElement } from './elements/KpiCardElement';
import { HeroStatsElement } from './elements/HeroStatsElement';
import { ComparisonBarsElement } from './elements/ComparisonBarsElement';
import { PopulationPyramidElement } from './elements/PopulationPyramidElement';
import { TableOfContentsElement } from './elements/TableOfContentsElement';
import { PathwayGanttElement } from './elements/PathwayGanttElement';
import { ComplianceHeatmapElement } from './elements/ComplianceHeatmapElement';
import { CSSMatchProgressionElement } from './elements/CSSMatchProgressionElement';

interface ResizeHandle {
  position: 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';
  cursor: string;
}

const RESIZE_HANDLES: ResizeHandle[] = [
  { position: 'nw', cursor: 'nw-resize' },
  { position: 'n', cursor: 'n-resize' },
  { position: 'ne', cursor: 'ne-resize' },
  { position: 'e', cursor: 'e-resize' },
  { position: 'se', cursor: 'se-resize' },
  { position: 's', cursor: 's-resize' },
  { position: 'sw', cursor: 'sw-resize' },
  { position: 'w', cursor: 'w-resize' },
];

const HANDLE_POSITIONS: Record<string, React.CSSProperties> = {
  nw: { top: '-4px', left: '-4px', cursor: 'nw-resize' },
  n: { top: '-4px', left: '50%', transform: 'translateX(-50%)', cursor: 'n-resize' },
  ne: { top: '-4px', right: '-4px', cursor: 'ne-resize' },
  e: { top: '50%', right: '-4px', transform: 'translateY(-50%)', cursor: 'e-resize' },
  se: { bottom: '-4px', right: '-4px', cursor: 'se-resize' },
  s: { bottom: '-4px', left: '50%', transform: 'translateX(-50%)', cursor: 's-resize' },
  sw: { bottom: '-4px', left: '-4px', cursor: 'sw-resize' },
  w: { top: '50%', left: '-4px', transform: 'translateY(-50%)', cursor: 'w-resize' },
};

interface ElementProps {
  element: LayoutElement;
  pageId: string;
  scale: number;
  readOnly?: boolean;
}

export function Element({ element, pageId, scale, readOnly = false }: ElementProps) {
  const elementRef = useRef<HTMLDivElement>(null);
  const interactiveSelector =
    'button, input, textarea, select, option, a, [role="button"], [role="link"], [data-no-drag]';

  const {
    isSelected,
    isHovered,
    handleClick,
    handleMouseDown,
    handleMouseEnter,
    handleMouseLeave,
    handleResizeStart,
  } = useElementDragResize({ element, pageId, scale, readOnly, elementRef, interactiveSelector });

  const updateElement = useEditorStore((s) => s.updateElement);

  const left = element.x * MM_TO_PX * scale;
  const top = element.y * MM_TO_PX * scale;
  const width = element.w * MM_TO_PX * scale;
  const height = element.h * MM_TO_PX * scale;

  const renderContent = () => {
    switch (element.type) {
      case 'measure':
        return <MeasureElement element={element} />;
      case 'interpretation':
        return <InterpretationElement element={element} pageId={pageId} readOnly={readOnly} />;
      case 'executiveSummary':
        return <ExecutiveSummaryElement element={element} pageId={pageId} readOnly={readOnly} />;
      case 'text':
        return (
          <TextElement
            element={element}
            onUpdate={(updates) => updateElement(pageId, element.id, updates)}
            readOnly={readOnly}
          />
        );
      case 'heading1':
      case 'heading2':
      case 'heading3':
      case 'subtitle':
        return (
          <HeadingElement
            element={element}
            onUpdate={(updates) => updateElement(pageId, element.id, updates)}
            readOnly={readOnly}
          />
        );
      case 'bulletList':
        return <BulletListElement element={element} />;
      case 'checklist':
        return (
          <ChecklistElement
            element={element}
            readOnly={readOnly}
            onToggle={(itemId) => {
              if (readOnly) return;
              const checklist = element as ChecklistElementType;
              const updatedItems = checklist.items.map((item) =>
                item.id === itemId ? { ...item, checked: !item.checked } : item
              );
              updateElement(pageId, element.id, { items: updatedItems });
            }}
          />
        );
      case 'divider':
        return <DividerElement element={element} />;
      case 'cover':
        return <CoverElement element={element} />;
      case 'image':
        return <ImageElement element={element} />;
      case 'table':
        return <TableElement element={element} />;
      case 'chart':
        return <ChartElement element={element} />;
      case 'kpiCard':
        return <KpiCardElement element={element} />;
      case 'heroStats':
        return <HeroStatsElement element={element} />;
      case 'comparisonBars':
        return <ComparisonBarsElement element={element} />;
      case 'populationPyramid':
        return <PopulationPyramidElement element={element} />;
      case 'tableOfContents':
        return <TableOfContentsElement element={element} readOnly={readOnly} />;
      case 'pathwayGantt':
        return <PathwayGanttElement element={element} />;
      case 'complianceHeatmap':
        return <ComplianceHeatmapElement element={element} />;
      case 'cssMatchProgression':
        return <CSSMatchProgressionElement element={element} />;
      default:
        return <div>Unknown element type</div>;
    }
  };

  return (
    <Box
      ref={elementRef}
      sx={(theme) => ({
        position: 'absolute',
        cursor: readOnly ? 'default' : 'move',
        userSelect: 'none',
        ...(isSelected && {
          outline: `2px solid ${theme.palette.primary.main}`,
          outlineOffset: '1px',
        }),
        ...(!isSelected && isHovered && {
          outline: `1px dashed ${theme.palette.primary.main}`,
          outlineOffset: '1px',
        }),
      })}
      style={{
        left,
        top,
        width,
        height,
        zIndex: element.zIndex || 0,
      }}
      onClick={handleClick}
      onMouseDown={handleMouseDown}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      id={`el-${element.id}`}
      data-element-id={element.id}
    >
      {renderContent()}

      {isSelected && !readOnly && (
        <>
          {RESIZE_HANDLES.map((handle) => (
            <Box
              key={handle.position}
              data-resize-handle
              sx={(theme) => ({
                position: 'absolute',
                width: '8px',
                height: '8px',
                bgcolor: theme.palette.primary.main,
                border: '1px solid #fff',
                borderRadius: '1px',
              })}
              style={HANDLE_POSITIONS[handle.position]}
              onMouseDown={(e) => handleResizeStart(e, handle.position)}
            />
          ))}
        </>
      )}
    </Box>
  );
}
