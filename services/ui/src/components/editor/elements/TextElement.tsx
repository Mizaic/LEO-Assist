/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import Box from '@mui/material/Box';
import { TextElement as TextElementType } from '@/lib/types/layout';

interface TextElementProps {
  element: TextElementType;
  onUpdate?: (updates: Partial<TextElementType>) => void;
  readOnly?: boolean;
}

export function TextElement({ element, onUpdate, readOnly = false }: TextElementProps) {
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
      contentRef.current.textContent = element.text || element.placeholder || '';
    }
  }, [element.text, element.placeholder, isEditing]);

  const handleDoubleClick = useCallback(
    (e: React.MouseEvent) => {
      if (readOnly) return;
      e.stopPropagation();
      setIsEditing(true);

      setTimeout(() => {
        if (contentRef.current) {
          contentRef.current.focus();
          const range = document.createRange();
          range.selectNodeContents(contentRef.current);
          const selection = window.getSelection();
          selection?.removeAllRanges();
          selection?.addRange(range);
        }
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

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.stopPropagation();
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        contentRef.current?.blur();
      }
      if (e.key === 'Escape') {
        if (contentRef.current) {
          contentRef.current.textContent = element.text;
        }
        contentRef.current?.blur();
      }
    },
    [element.text]
  );

  const getStyle = (): React.CSSProperties => {
    const style = element.style || {};
    return {
      fontSize: style.fontSize ? `${style.fontSize}px` : undefined,
      fontWeight: style.fontWeight,
      color: style.color || 'var(--brand-text, #111111)',
      fontFamily: 'var(--brand-font-body, inherit)',
      textAlign: style.align,
      backgroundColor: style.backgroundColor,
      padding: style.padding ? `${style.padding}px` : undefined,
    };
  };

  const isEmpty = !localText && !isEditing;

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'flex-start',
        overflow: 'hidden',
      }}
      style={getStyle()}
    >
      <Box
        ref={contentRef}
        contentEditable={!readOnly}
        suppressContentEditableWarning
        onDoubleClick={handleDoubleClick}
        onBlur={handleBlur}
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        sx={{
          width: '100%',
          height: '100%',
          padding: '4px',
          outline: 'none',
          cursor: 'text',
          overflow: 'hidden',
          wordWrap: 'break-word',
          ...(!readOnly && {
            '&:focus': {
              bgcolor: 'rgba(0, 120, 212, 0.05)',
            },
          }),
          ...(isEmpty && {
            color: 'text.disabled',
            fontStyle: 'italic',
          }),
        }}
      >
        {isEmpty ? (element.placeholder || 'Double-click to edit') : localText}
      </Box>
    </Box>
  );
}
