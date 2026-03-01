'use client';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Tooltip from '@mui/material/Tooltip';
import { PathwayGanttElement as PathwayGanttElementType } from '@/lib/types/layout';

interface PathwayGanttElementProps {
  element: PathwayGanttElementType;
}

const MILESTONE_COLORS: Record<string, string> = {
  presentation: '#2196F3',
  referral: '#FF9800',
  first_clinic: '#9C27B0',
  diagnosis: '#F44336',
  treatment_decision: '#4CAF50',
  first_treatment: '#00BCD4',
};

const MILESTONE_LABELS: Record<string, string> = {
  presentation: 'Presentation',
  referral: 'Referral',
  first_clinic: 'First Clinic',
  diagnosis: 'Diagnosis',
  treatment_decision: 'Tx Decision',
  first_treatment: 'Treatment',
};

export function PathwayGanttElement({ element }: PathwayGanttElementProps) {
  const { milestones = [], nhsTargets = [] } = element;

  const allDates = milestones.map((m) => m.dayOffset).filter(Boolean);
  const maxDay = Math.max(...allDates, 62, 1);

  return (
    <Box sx={{ height: '100%', p: 2, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: 0.5, overflow: 'hidden' }}>
      {element.title && (
        <Typography sx={{ fontSize: '0.875rem', fontWeight: 600, mb: 1.5 }}>
          {element.title}
        </Typography>
      )}

      {/* NHS Target lines */}
      <Box sx={{ position: 'relative', height: 24, mb: 1 }}>
        {nhsTargets.map((target) => (
          <Tooltip key={target.name} title={`${target.name}: ${target.days} days`}>
            <Box
              sx={{
                position: 'absolute',
                left: `${(target.days / maxDay) * 100}%`,
                top: 0,
                bottom: 0,
                width: 2,
                bgcolor: target.breached ? 'error.main' : 'success.main',
                opacity: 0.6,
              }}
            />
          </Tooltip>
        ))}
      </Box>

      {/* Milestone bars */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        {milestones.map((milestone) => {
          const color = MILESTONE_COLORS[milestone.type] || '#757575';
          const label = MILESTONE_LABELS[milestone.type] || milestone.type;
          const width = Math.max(2, (milestone.dayOffset / maxDay) * 100);

          return (
            <Box key={milestone.type} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography
                sx={{ fontSize: '0.625rem', width: 70, flexShrink: 0, textAlign: 'right', color: 'text.secondary' }}
              >
                {label}
              </Typography>
              <Box sx={{ flex: 1, position: 'relative', height: 16 }}>
                <Box
                  sx={{
                    position: 'absolute',
                    left: 0,
                    top: 2,
                    height: 12,
                    width: `${width}%`,
                    bgcolor: color,
                    borderRadius: 0.5,
                    minWidth: 4,
                  }}
                />
              </Box>
              <Typography sx={{ fontSize: '0.625rem', width: 40, color: 'text.secondary' }}>
                Day {milestone.dayOffset}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
