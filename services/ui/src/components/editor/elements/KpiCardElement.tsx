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
import ArrowUpwardOutlined from '@mui/icons-material/ArrowUpwardOutlined';
import ArrowDownwardOutlined from '@mui/icons-material/ArrowDownwardOutlined';
import { KpiCardElement as KpiCardElementType } from '@/lib/types/layout';

interface KpiCardElementProps {
  element: KpiCardElementType;
}

export function KpiCardElement({ element }: KpiCardElementProps) {
  const trendIcon =
    element.trend === 'up' ? (
      <ArrowUpwardOutlined sx={{ color: 'success.main' }} />
    ) : element.trend === 'down' ? (
      <ArrowDownwardOutlined sx={{ color: 'error.main' }} />
    ) : null;

  return (
    <Card
      sx={{
        height: '100%',
        bgcolor: 'background.paper',
        border: 1,
        borderColor: 'divider',
        borderRadius: 0.5,
      }}
    >
      <CardContent
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          padding: '16px',
          '&:last-child': { paddingBottom: '16px' },
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary' }}>
            {element.title}
          </Typography>
          {trendIcon}
        </Box>
        <Typography sx={{ fontSize: '2rem', fontWeight: 700, color: 'text.primary' }}>
          {element.value}
          {element.unit || ''}
        </Typography>
        {(element.target != null || element.comparison != null) && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'text.secondary' }}>
            {element.target != null && (
              <Box
                component="span"
                sx={{
                  padding: '2px 8px',
                  borderRadius: 0.5,
                  bgcolor: 'grey.200',
                  fontSize: '0.625rem',
                }}
              >
                Target {element.target}
                {element.unit || ''}
              </Box>
            )}
            {element.comparison != null && (
              <Box
                component="span"
                sx={{
                  padding: '2px 8px',
                  borderRadius: 0.5,
                  bgcolor: 'grey.200',
                  fontSize: '0.625rem',
                }}
              >
                {element.comparisonLabel || 'Comparison'} {element.comparison}
                {element.unit || ''}
              </Box>
            )}
          </Box>
        )}
        {element.metTarget != null && (
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {element.metTarget ? 'Target met' : 'Below target'}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
