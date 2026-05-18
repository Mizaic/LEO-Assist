/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
export const chartColors = {
  series: [
    '#0d46d6',
    '#10B981',
    '#7C3AED',
    '#F59E0B',
    '#06B6D4',
    '#EF4444',
    '#EC4899',
    '#84CC16',
  ],
  clinical: {
    symptom: '#0d46d6',
    test: '#F97316',
    diagnosis: '#EF4444',
    treatment: '#10B981',
    outcome: '#7C3AED',
    risk: '#F59E0B',
  },
  status: {
    success: '#10B981',
    warning: '#F59E0B',
    error: '#EF4444',
    info: '#0d46d6',
    neutral: '#64748B',
  },
};

export const chartTheme = {
  fonts: {
    family: "'Segoe UI', sans-serif",
    sizes: {
      title: '16px',
      subtitle: '14px',
      label: '12px',
      axis: '11px',
      legend: '12px',
      tooltip: '13px',
    },
    weights: {
      title: 600,
      subtitle: 500,
      label: 400,
      axis: 400,
      legend: 500,
      tooltip: 500,
    },
  },
  grid: {
    stroke: '#E2E8F0',
    strokeDasharray: '3 3',
    strokeWidth: 1,
  },
  axis: {
    stroke: '#64748B',
    strokeWidth: 1,
    tick: {
      fill: '#64748B',
      fontSize: '11px',
    },
    label: {
      fill: '#475569',
      fontSize: '12px',
      fontWeight: 500,
    },
  },
  tooltip: {
    background: '#FFFFFF',
    border: '1px solid #E2E8F0',
    borderRadius: '8px',
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
    padding: '12px',
    fontSize: '13px',
    fontWeight: 500,
    color: '#0F172A',
  },
  legend: {
    fontSize: '12px',
    fontWeight: 500,
    color: '#475569',
    iconType: 'circle' as const,
    iconSize: 10,
  },
  line: {
    strokeWidth: 2.5,
    activeDot: {
      r: 6,
      strokeWidth: 2,
      stroke: '#FFFFFF',
    },
    dot: {
      r: 4,
      strokeWidth: 1.5,
      stroke: '#FFFFFF',
    },
  },
  bar: {
    radius: [4, 4, 0, 0] as [number, number, number, number],
    maxBarSize: 60,
  },
  area: {
    fillOpacity: 0.2,
    strokeWidth: 2,
  },
  sankey: {
    nodePadding: 24,
    nodeThickness: 18,
    linkOpacity: 0.5,
    linkHoverOpacity: 0.8,
  },
};

export const getSeriesColor = (index: number): string => {
  return chartColors.series[index % chartColors.series.length];
};

export const getClinicalColor = (type: keyof typeof chartColors.clinical): string => {
  return chartColors.clinical[type];
};

export const getStatusColor = (status: keyof typeof chartColors.status): string => {
  return chartColors.status[status];
};
