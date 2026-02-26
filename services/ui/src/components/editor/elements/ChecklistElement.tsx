'use client';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { ChecklistElement as ChecklistElementType } from '@/lib/types/layout';

interface ChecklistElementProps {
  element: ChecklistElementType;
  onToggle?: (itemId: string) => void;
  readOnly?: boolean;
}

export function ChecklistElement({ element, onToggle, readOnly = false }: ChecklistElementProps) {
  const items = element.items || [];
  const style = element.style || {};

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        padding: '4px 8px',
        overflow: 'hidden',
      }}
      style={{
        fontSize: style.fontSize ? `${style.fontSize}px` : '14px',
        color: style.color || 'var(--brand-text, #111111)',
        fontFamily: 'var(--brand-font-body, inherit)',
      }}
    >
      {items.length === 0 ? (
        <Typography sx={{ color: 'text.disabled', fontStyle: 'italic' }}>
          Edit items in properties
        </Typography>
      ) : (
        <Box
          component="ul"
          sx={{
            margin: 0,
            paddingLeft: 0,
            listStyle: 'none',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
          }}
        >
          {items.map((item) => (
            <Box
              component="li"
              key={item.id}
              sx={{ display: 'flex', alignItems: 'center', gap: '8px' }}
            >
              <input
                type="checkbox"
                checked={item.checked}
                onChange={() => onToggle?.(item.id)}
                disabled={readOnly}
              />
              <span>{item.text}</span>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
