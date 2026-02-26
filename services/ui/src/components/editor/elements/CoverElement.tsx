'use client';

import Box from '@mui/material/Box';
import { CoverElement as CoverElementType } from '@/lib/types/layout';

interface CoverElementProps {
  element: CoverElementType;
}

export function CoverElement({ element }: CoverElementProps) {
  const borderColor = element.panelBorderColor || 'var(--brand-primary, #0078D4)';
  const panelBackground = element.panelBackgroundColor || 'rgba(255, 255, 255, 0.85)';

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '24px',
        boxSizing: 'border-box',
        overflow: 'hidden',
        gap: '12px',
      }}
      style={{
        backgroundColor: element.backgroundColor || 'var(--brand-background, #ffffff)',
        color: 'var(--brand-text, #111111)',
      }}
    >
      {element.backgroundImageUrl && (
        <Box
          component="img"
          src={element.backgroundImageUrl}
          alt="Cover background"
          sx={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            opacity: 0.18,
          }}
        />
      )}
      {element.logoUrl && (
        <Box
          component="img"
          src={element.logoUrl}
          alt="Brand logo"
          sx={{
            position: 'absolute',
            top: '24px',
            right: '24px',
            maxWidth: '160px',
            maxHeight: '80px',
          }}
        />
      )}
      <Box
        sx={{
          alignSelf: 'center',
          width: '70%',
          padding: '28px 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          textAlign: 'center',
          borderTopWidth: '2px',
          borderBottomWidth: '2px',
          borderTopStyle: 'solid',
          borderBottomStyle: 'solid',
        }}
        style={{
          borderTopColor: borderColor,
          borderBottomColor: borderColor,
          backgroundColor: panelBackground,
        }}
      >
        <Box
          sx={{
            fontSize: '32px',
            fontWeight: 700,
            fontFamily: 'var(--brand-font-heading, inherit)',
            letterSpacing: '2px',
            lineHeight: 1.1,
          }}
        >
          {element.title || 'Cover Title'}
        </Box>
        {element.subtitle && (
          <Box
            sx={{
              fontSize: '18px',
              fontWeight: 400,
              fontFamily: 'var(--brand-font-body, inherit)',
              letterSpacing: '2px',
            }}
          >
            {element.subtitle}
          </Box>
        )}
        {element.date && (
          <Box
            sx={{
              fontSize: '14px',
              fontWeight: 500,
              fontFamily: 'var(--brand-font-body, inherit)',
              letterSpacing: '2px',
            }}
          >
            {element.date}
          </Box>
        )}
      </Box>
    </Box>
  );
}
