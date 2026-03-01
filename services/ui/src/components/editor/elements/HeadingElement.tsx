'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import Box from '@mui/material/Box';
import { HeadingElement as HeadingElementType } from '@/lib/types/layout';

const DEFAULT_FONT_SIZES: Record<HeadingElementType['type'], number> = {
  heading1: 32,
  heading2: 24,
  heading3: 20,
  subtitle: 16,
};

interface HeadingElementProps {
  element: HeadingElementType;
  onUpdate?: (updates: Partial<HeadingElementType>) => void;
  readOnly?: boolean;
}

export function HeadingElement({ element, onUpdate, readOnly = false }: HeadingElementProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [localText, setLocalText] = useState(element.text);
  const [prevText, setPrevText] = useState(element.text);

  if (element.text !== prevText) {
    setPrevText(element.text);
    setLocalText(element.text);
  }

  useEffect(() => {
    if (contentRef.current && !isEditing) {
      contentRef.current.textContent = element.text || '';
    }
  }, [element.text, isEditing]);

  const handleDoubleClick = useCallback(
    (e: React.MouseEvent) => {
      if (readOnly) return;
      e.stopPropagation();
      setIsEditing(true);
      setTimeout(() => {
        contentRef.current?.focus();
      }, 0);
    },
    [readOnly]
  );

  const handleBlur = useCallback(() => {
    setIsEditing(false);
    if (contentRef.current && onUpdate) {
      const newText = contentRef.current.textContent || '';
      if (newText !== element.text) {
        onUpdate({ text: newText });
      }
    }
  }, [element.text, onUpdate]);

  const handleInput = useCallback(() => {
    if (contentRef.current) {
      setLocalText(contentRef.current.textContent || '');
    }
  }, []);

  const style = element.style || {};
  const fontSize = style.fontSize ?? DEFAULT_FONT_SIZES[element.type];
  const isEmpty = !localText && !isEditing;

  return (
    <Box sx={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', overflow: 'hidden' }}>
      <Box
        ref={contentRef}
        contentEditable={!readOnly}
        suppressContentEditableWarning
        onDoubleClick={handleDoubleClick}
        onBlur={handleBlur}
        onInput={handleInput}
        sx={{
          width: '100%',
          outline: 'none',
          cursor: 'text',
          wordWrap: 'break-word',
          fontSize: `${fontSize}px`,
          lineHeight: '1.2',
          fontWeight: style.fontWeight || 'bold',
          color: style.color || 'var(--brand-text, #111111)',
          fontFamily: 'var(--brand-font-heading, inherit)',
          textAlign: style.align,
          ...(isEmpty && { color: 'text.disabled', fontStyle: 'italic' }),
        }}
      >
        {isEmpty ? 'Double-click to edit' : localText}
      </Box>
    </Box>
  );
}
