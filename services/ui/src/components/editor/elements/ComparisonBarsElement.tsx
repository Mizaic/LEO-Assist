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
import { ComparisonBarsElement as ComparisonBarsElementType } from '@/lib/types/layout';

interface ComparisonBarsElementProps {
  element: ComparisonBarsElementType;
}

export function ComparisonBarsElement({ element }: ComparisonBarsElementProps) {
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
          gap: '12px',
          padding: '16px',
          '&:last-child': { paddingBottom: '16px' },
        }}
      >
        <Typography sx={{ fontSize: '0.875rem', fontWeight: 600 }}>
          {element.title}
        </Typography>
        {element.source && (
          <Typography
            sx={{
              fontSize: '0.625rem',
              color: 'text.disabled',
              fontStyle: 'italic',
              mt: '-4px',
              mb: '2px',
            }}
          >
            Source: {element.source}
          </Typography>
        )}
        {element.metrics.map((metric) => {
          if (metric.scopeDisplayValues && Object.keys(metric.scopeDisplayValues).length > 0) {
            const scopeOrder = ['practice', 'cancer_alliance', 'national'];
            return (
              <Box key={metric.metric} sx={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <Typography sx={{ fontWeight: 600 }}>{metric.metric}</Typography>
                {scopeOrder
                  .filter((s) => metric.scopeDisplayValues![s])
                  .map((scopeType) => (
                    <Box
                      key={scopeType}
                      sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                    >
                      <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
                        {scopeType === 'practice'
                          ? 'Practice'
                          : scopeType === 'cancer_alliance'
                            ? 'Alliance'
                            : 'England'}
                      </Typography>
                      <Typography sx={{ fontSize: '0.75rem', fontWeight: 500 }}>
                        {metric.scopeDisplayValues![scopeType]}
                      </Typography>
                    </Box>
                  ))}
              </Box>
            );
          }

          const max = Math.max(metric.current, metric.target, metric.benchmark || 0) || 1;
          const currentPct = Math.min((metric.current / max) * 100, 100);
          const targetPct = Math.min((metric.target / max) * 100, 100);
          const benchmarkPct = metric.benchmark
            ? Math.min((metric.benchmark / max) * 100, 100)
            : 0;

          return (
            <Box key={metric.metric} sx={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography sx={{ fontWeight: 600 }}>{metric.metric}</Typography>
                <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
                  {metric.current}
                  {metric.unit || ''}
                </Typography>
              </Box>
              <Box>
                <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
                  Current
                </Typography>
                <Box sx={{ height: 8, borderRadius: 0.5, bgcolor: 'grey.200', overflow: 'hidden' }}>
                  <Box
                    sx={{
                      height: '100%',
                      borderRadius: 0.5,
                    }}
                    style={{
                      width: `${currentPct}%`,
                      background: 'linear-gradient(90deg, var(--mui-palette-primary-main, #1976d2) 0%, var(--mui-palette-primary-dark, #1565c0) 100%)',
                    }}
                  />
                </Box>
              </Box>
              <Box>
                <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
                  Target
                </Typography>
                <Box sx={{ height: 8, borderRadius: 0.5, bgcolor: 'grey.200', overflow: 'hidden' }}>
                  <Box
                    sx={{
                      height: '100%',
                      borderRadius: 0.5,
                      bgcolor: 'success.light',
                    }}
                    style={{ width: `${targetPct}%` }}
                  />
                </Box>
              </Box>
              {metric.benchmark != null && (
                <Box>
                  <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary' }}>
                    Benchmark
                  </Typography>
                  <Box sx={{ height: 8, borderRadius: 0.5, bgcolor: 'grey.200', overflow: 'hidden' }}>
                    <Box
                      sx={{
                        height: '100%',
                        borderRadius: 0.5,
                        color: 'text.disabled',
                        bgcolor: 'text.disabled',
                      }}
                      style={{ width: `${benchmarkPct}%` }}
                    />
                  </Box>
                </Box>
              )}
            </Box>
          );
        })}
      </CardContent>
    </Card>
  );
}
