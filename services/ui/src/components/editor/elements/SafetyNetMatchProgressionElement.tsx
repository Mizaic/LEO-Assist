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
import Chip from '@mui/material/Chip';
import { SafetyNetMatchProgressionElement as SafetyNetMatchProgressionElementType } from '@/lib/types/layout';

interface SafetyNetMatchProgressionElementProps {
  element: SafetyNetMatchProgressionElementType;
}

const STATUS_COLORS: Record<string, string> = {
  matched: '#4CAF50',
  missed: '#F44336',
  actioned: '#2196F3',
  pending: '#FF9800',
  covered: '#9C27B0',
};

export function SafetyNetMatchProgressionElement({ element }: SafetyNetMatchProgressionElementProps) {
  const { rules = [], summary } = element;

  return (
    <Box sx={{ height: '100%', p: 2, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: 0.5, overflow: 'auto' }}>
      {element.title && (
        <Typography sx={{ fontSize: '0.875rem', fontWeight: 600, mb: 1.5 }}>
          {element.title}
        </Typography>
      )}

      {/* Summary chips */}
      {summary && (
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mb: 1.5 }}>
          <Chip label={`Created: ${summary.alertsCreated}`} size="small" sx={{ fontSize: '0.625rem' }} />
          <Chip label={`Actioned: ${summary.alertsActioned}`} size="small" color="info" sx={{ fontSize: '0.625rem' }} />
          <Chip label={`Covered: ${summary.alertsCovered}`} size="small" color="secondary" sx={{ fontSize: '0.625rem' }} />
          <Chip label={`Missed: ${summary.alertsMissed}`} size="small" color="error" sx={{ fontSize: '0.625rem' }} />
        </Box>
      )}

      {/* Rule progression bars */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
        {rules.map((rule) => {
          const total = rule.total || 1;
          const matchPct = (rule.matched / total) * 100;
          const color = STATUS_COLORS[rule.status] || '#757575';

          return (
            <Box key={rule.ruleId} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography
                sx={{ fontSize: '0.625rem', width: 100, flexShrink: 0, color: 'text.secondary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              >
                {rule.ruleName}
              </Typography>
              <Box sx={{ flex: 1, bgcolor: 'grey.200', borderRadius: 0.5, height: 12, position: 'relative', overflow: 'hidden' }}>
                <Box
                  sx={{
                    position: 'absolute',
                    left: 0,
                    top: 0,
                    bottom: 0,
                    width: `${matchPct}%`,
                    bgcolor: color,
                    borderRadius: 0.5,
                  }}
                />
              </Box>
              <Typography sx={{ fontSize: '0.625rem', width: 40, textAlign: 'right', color: 'text.secondary' }}>
                {rule.matched}/{rule.total}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
