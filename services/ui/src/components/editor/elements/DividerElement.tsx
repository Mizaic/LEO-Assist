'use client';

import { DividerElement as DividerElementType } from '@/lib/types/layout';

interface DividerElementProps {
  element: DividerElementType;
}

export function DividerElement({ element }: DividerElementProps) {
  const thickness = element.thickness ?? 2;
  const color = element.color || 'var(--brand-primary, #0078D4)';

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
      }}
    >
      <div
        style={{
          height: `${thickness}px`,
          width: '100%',
          backgroundColor: color,
        }}
      />
    </div>
  );
}
