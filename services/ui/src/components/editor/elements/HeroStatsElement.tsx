/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import { HeroStatsElement as HeroStatsElementType } from '@/lib/types/layout';

interface HeroStatsElementProps {
  element: HeroStatsElementType;
}

export function HeroStatsElement({ element }: HeroStatsElementProps) {
  return (
    <Card
      sx={{
        height: '100%',
        background: (theme) =>
          `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.primary.dark} 100%)`,
        color: 'primary.contrastText',
        borderRadius: 1,
      }}
    >
      <CardContent
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          padding: '16px',
          '&:last-child': { paddingBottom: '16px' },
        }}
      >
        <Typography sx={{ fontSize: '1rem', fontWeight: 600 }}>
          {element.title}
        </Typography>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
            gap: '12px',
          }}
        >
          {element.stats.map((stat, index) => (
            <Box key={`${stat.label}-${index}`}>
              <Typography sx={{ fontSize: '1.5rem', fontWeight: 700 }}>
                {stat.value}
                {stat.unit || ''}
              </Typography>
              <Typography sx={{ fontSize: '0.625rem', opacity: 0.9 }}>
                {stat.label}
              </Typography>
            </Box>
          ))}
        </Box>
      </CardContent>
    </Card>
  );
}
