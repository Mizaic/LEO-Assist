'use client';

import { useMemo } from 'react';
import Box from '@mui/material/Box';
import { useEditorStore } from '@/stores/editorStore';
import { TableOfContentsElement as TableOfContentsElementType } from '@/lib/types/layout';
import { buildTocEntries, TocEntry } from '@/lib/utils/toc';

interface TableOfContentsElementProps {
  element: TableOfContentsElementType;
  readOnly?: boolean;
}

export function TableOfContentsElement({
  element,
  readOnly = false,
}: TableOfContentsElementProps) {
  const layout = useEditorStore((s) => s.layout);
  const entries: TocEntry[] = useMemo(
    () => buildTocEntries(layout, element.id),
    [layout, element.id],
  );

  const style = element.style || {};
  const padding = style.padding ?? 10;

  const handleClick = (
    e: React.MouseEvent<HTMLAnchorElement>,
    elementId: string,
  ) => {
    if (!readOnly) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    const target = document.getElementById(`el-${elementId}`);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const fontSizeForLevel = (level: 1 | 2 | 3): number => {
    const base = style.fontSize ?? 13;
    if (level === 1) return base;
    if (level === 2) return Math.max(base - 2, 9);
    return Math.max(base - 3, 8);
  };

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        boxSizing: 'border-box',
        fontFamily: 'var(--brand-font-body, inherit)',
      }}
      style={{
        padding: `${padding}px`,
        color: style.color || 'var(--brand-text, #111111)',
        backgroundColor: style.backgroundColor || 'transparent',
        borderRadius: style.borderRadius ? `${style.borderRadius}px` : undefined,
      }}
    >
      <h2
        style={{
          margin: '0 0 8px 0',
          fontFamily: 'var(--brand-font-heading, inherit)',
          lineHeight: '1.3',
          fontSize: `${(style.fontSize ?? 13) + 5}px`,
          fontWeight: style.fontWeight || 'bold',
          color: style.color || 'var(--brand-text, #111111)',
        }}
      >
        {element.title || 'Table of Contents'}
      </h2>

      {entries.length === 0 ? (
        <span style={{ fontSize: '12px', color: 'rgba(0, 0, 0, 0.38)', fontStyle: 'italic' }}>
          Add headings or titled elements to populate the table of contents.
        </span>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {entries.map((entry) => (
            <li
              key={entry.elementId}
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: '6px',
                lineHeight: '1.6',
                paddingLeft: `${(entry.level - 1) * 14}px`,
              }}
            >
              <Box
                component="a"
                href={`#el-${entry.elementId}`}
                onClick={(e: React.MouseEvent<HTMLAnchorElement>) => handleClick(e, entry.elementId)}
                sx={{
                  color: 'var(--brand-primary, #0078d4)',
                  textDecoration: 'none',
                  cursor: 'pointer',
                  '&:hover': {
                    textDecoration: 'underline',
                  },
                  fontSize: `${fontSizeForLevel(entry.level)}px`,
                  fontWeight: entry.level === 1 ? 600 : 400,
                }}
              >
                {entry.label}
              </Box>

              {element.showPageNumbers && (
                <>
                  <span
                    style={{
                      flex: 1,
                      borderBottom: '1px dotted #E0E0E0',
                      minWidth: '20px',
                      alignSelf: 'center',
                      marginBottom: '3px',
                    }}
                  />
                  <span
                    style={{
                      color: 'rgba(0, 0, 0, 0.38)',
                      whiteSpace: 'nowrap',
                      flexShrink: 0,
                      fontSize: `${fontSizeForLevel(entry.level) - 1}px`,
                    }}
                  >
                    {entry.pageIndex + 1}
                  </span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </Box>
  );
}
