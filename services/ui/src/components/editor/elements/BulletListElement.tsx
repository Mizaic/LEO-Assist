'use client';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { BulletListElement as BulletListElementType } from '@/lib/types/layout';

interface BulletListElementProps {
  element: BulletListElementType;
}

export function BulletListElement({ element }: BulletListElementProps) {
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
        <Box component="ul" sx={{ margin: 0, paddingLeft: '20px' }}>
          {items.map((item, index) => (
            <li key={`${index}-${item}`}>{item}</li>
          ))}
        </Box>
      )}
    </Box>
  );
}
