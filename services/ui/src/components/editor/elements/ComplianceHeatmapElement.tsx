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
import Typography from '@mui/material/Typography';
import Tooltip from '@mui/material/Tooltip';
import { ComplianceHeatmapElement as ComplianceHeatmapElementType } from '@/lib/types/layout';

interface ComplianceHeatmapElementProps {
  element: ComplianceHeatmapElementType;
}

function getComplianceColor(value: number): string {
  if (value >= 90) return '#2E7D32';
  if (value >= 75) return '#66BB6A';
  if (value >= 50) return '#FFA726';
  if (value >= 25) return '#EF5350';
  return '#C62828';
}

export function ComplianceHeatmapElement({ element }: ComplianceHeatmapElementProps) {
  const { rows = [], columns = [] } = element;

  return (
    <Box sx={{ height: '100%', p: 2, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: 0.5, overflow: 'auto' }}>
      {element.title && (
        <Typography sx={{ fontSize: '0.875rem', fontWeight: 600, mb: 1.5 }}>
          {element.title}
        </Typography>
      )}

      <Box sx={{ display: 'grid', gridTemplateColumns: `120px repeat(${columns.length}, 1fr)`, gap: 0.25 }}>
        {/* Header row */}
        <Box />
        {columns.map((col) => (
          <Typography key={col} sx={{ fontSize: '0.625rem', textAlign: 'center', color: 'text.secondary', fontWeight: 600 }}>
            {col}
          </Typography>
        ))}

        {/* Data rows */}
        {rows.map((row) => (
          <Box key={row.label} sx={{ display: 'contents' }}>
            <Typography sx={{ fontSize: '0.625rem', color: 'text.secondary', display: 'flex', alignItems: 'center' }}>
              {row.label}
            </Typography>
            {row.values.map((val, idx) => (
              <Tooltip key={idx} title={`${row.label} / ${columns[idx]}: ${val}%`}>
                <Box
                  sx={{
                    bgcolor: getComplianceColor(val),
                    borderRadius: 0.25,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minHeight: 24,
                  }}
                >
                  <Typography sx={{ fontSize: '0.5rem', color: 'white', fontWeight: 600 }}>
                    {val}%
                  </Typography>
                </Box>
              </Tooltip>
            ))}
          </Box>
        ))}
      </Box>
    </Box>
  );
}
