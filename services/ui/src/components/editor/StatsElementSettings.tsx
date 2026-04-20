/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import type {
  LayoutElement,
  KpiCardElement,
  HeroStatsElement,
  ComparisonBarsElement,
  PopulationPyramidElement,
} from '@/lib/types/layout';

/* ── Parse helpers ────────────────────────────────────────────────────────── */

export function parseStatsLines(value: string): { label: string; value: number; unit?: string }[] {
  return value.split('\n').map((line) => line.trim()).filter((line) => line.length > 0).flatMap((line) => {
    const [label, valuePart, unit] = line.split('|').map((p) => p.trim());
    const numericValue = Number(valuePart);
    if (!label || Number.isNaN(numericValue)) return [];
    return [{ label, value: numericValue, unit: unit || undefined }];
  });
}

export function parseComparisonLines(value: string): {
  metric: string; current: number; target: number; benchmark?: number; unit?: string;
}[] {
  return value.split('\n').map((line) => line.trim()).filter((line) => line.length > 0).flatMap((line) => {
    const [metric, current, target, benchmark, unit] = line.split('|').map((p) => p.trim());
    const currentV = Number(current);
    const targetV = Number(target);
    const benchmarkV = benchmark && !Number.isNaN(Number(benchmark)) ? Number(benchmark) : undefined;
    if (!metric || Number.isNaN(currentV) || Number.isNaN(targetV)) return [];
    return [{ metric, current: currentV, target: targetV, benchmark: benchmarkV, unit: unit || undefined }];
  });
}

export function parsePyramidLines(value: string): { ageBand: string; male: number; female: number }[] {
  return value.split('\n').map((line) => line.trim()).filter((line) => line.length > 0).flatMap((line) => {
    const [ageBand, male, female] = line.split(',').map((p) => p.trim());
    const maleV = Number(male);
    const femaleV = Number(female);
    if (!ageBand) return [];
    return [{ ageBand, male: Number.isNaN(maleV) ? 0 : maleV, female: Number.isNaN(femaleV) ? 0 : femaleV }];
  });
}

/* ── KpiCardSettings ─────────────────────────────────────────────────────── */

export function KpiCardSettings({ element, onUpdate }: {
  element: KpiCardElement;
  onUpdate: (updates: Partial<KpiCardElement>) => void;
}): React.ReactNode {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Title" value={element.title || ''}
        onChange={(e) => onUpdate({ title: e.target.value })} />
      <TextField size="small" label="Value" type="number" value={element.value?.toString() || '0'}
        onChange={(e) => onUpdate({ value: Number(e.target.value) || 0 })} />
      <TextField size="small" label="Unit" value={element.unit || ''}
        onChange={(e) => onUpdate({ unit: e.target.value })} />
      <TextField size="small" label="Target" type="number" value={element.target?.toString() || ''}
        onChange={(e) => onUpdate({ target: e.target.value ? Number(e.target.value) : undefined })} />
      <FormControlLabel
        control={<Switch size="small" checked={element.metTarget === true}
          onChange={(_, checked) => onUpdate({ metTarget: checked })} />}
        label="Target Met" />
      <TextField size="small" label="Comparison" type="number" value={element.comparison?.toString() || ''}
        onChange={(e) => onUpdate({ comparison: e.target.value ? Number(e.target.value) : undefined })} />
      <TextField size="small" label="Comparison Label" value={element.comparisonLabel || ''}
        onChange={(e) => onUpdate({ comparisonLabel: e.target.value })} />
      <TextField select size="small" label="Trend" value={element.trend || ''}
        onChange={(e) => onUpdate({ trend: (e.target.value || undefined) as 'up' | 'down' })}>
        <MenuItem value="">None</MenuItem>
        <MenuItem value="up">Up</MenuItem>
        <MenuItem value="down">Down</MenuItem>
      </TextField>
    </Box>
  );
}

/* ── HeroStatsSettings ───────────────────────────────────────────────────── */

export function HeroStatsSettings({ element, onUpdate }: {
  element: HeroStatsElement;
  onUpdate: (updates: Partial<HeroStatsElement>) => void;
}): React.ReactNode {
  const [statsText, setStatsText] = useState(
    (element.stats || []).map((s) => `${s.label}|${s.value}|${s.unit || ''}`).join('\n'),
  );
  const [prevStatsElementId, setPrevStatsElementId] = useState(element.id);

  if (element.id !== prevStatsElementId) {
    setPrevStatsElementId(element.id);
    setStatsText((element.stats || []).map((s) => `${s.label}|${s.value}|${s.unit || ''}`).join('\n'));
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Title" value={element.title || ''}
        onChange={(e) => onUpdate({ title: e.target.value })} />
      <TextField size="small" label="Stats (Label|Value|Unit)" multiline rows={6} value={statsText}
        onChange={(e) => setStatsText(e.target.value)}
        onBlur={() => { const stats = parseStatsLines(statsText); if (stats.length > 0) onUpdate({ stats }); }} />
    </Box>
  );
}

/* ── ComparisonBarsSettings ──────────────────────────────────────────────── */

export function ComparisonBarsSettings({ element, onUpdate }: {
  element: ComparisonBarsElement;
  onUpdate: (updates: Partial<ComparisonBarsElement>) => void;
}): React.ReactNode {
  const [metricsText, setMetricsText] = useState(
    (element.metrics || []).map((m) => `${m.metric}|${m.current}|${m.target}|${m.benchmark ?? ''}|${m.unit || ''}`).join('\n'),
  );
  const [prevMetricsElementId, setPrevMetricsElementId] = useState(element.id);

  if (element.id !== prevMetricsElementId) {
    setPrevMetricsElementId(element.id);
    setMetricsText(
      (element.metrics || []).map((m) => `${m.metric}|${m.current}|${m.target}|${m.benchmark ?? ''}|${m.unit || ''}`).join('\n'),
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Title" value={element.title || ''}
        onChange={(e) => onUpdate({ title: e.target.value })} />
      <TextField size="small" label="Metrics (Metric|Current|Target|Benchmark|Unit)" multiline rows={6}
        value={metricsText}
        onChange={(e) => setMetricsText(e.target.value)}
        onBlur={() => { const metrics = parseComparisonLines(metricsText); if (metrics.length > 0) onUpdate({ metrics }); }} />
    </Box>
  );
}

/* ── PopulationPyramidSettings ───────────────────────────────────────────── */

export function PopulationPyramidSettings({ element, onUpdate }: {
  element: PopulationPyramidElement;
  onUpdate: (updates: Partial<PopulationPyramidElement>) => void;
}): React.ReactNode {
  const [dataText, setDataText] = useState(
    (element.data || []).map((r) => `${r.ageBand},${r.male ?? 0},${r.female ?? 0}`).join('\n'),
  );
  const [prevDataElementId, setPrevDataElementId] = useState(element.id);

  if (element.id !== prevDataElementId) {
    setPrevDataElementId(element.id);
    setDataText((element.data || []).map((r) => `${r.ageBand},${r.male ?? 0},${r.female ?? 0}`).join('\n'));
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Title" value={element.title || ''}
        onChange={(e) => onUpdate({ title: e.target.value })} />
      <Typography variant="caption" color="text.secondary">Male Color</Typography>
      <input type="color" value={element.colors?.male || '#0d46d6'}
        onChange={(e) => onUpdate({ colors: { ...element.colors, male: e.target.value, female: element.colors?.female || '#F97316' } })}
        style={{ width: '100%', height: '32px', border: 'none', cursor: 'pointer' }} />
      <Typography variant="caption" color="text.secondary">Female Color</Typography>
      <input type="color" value={element.colors?.female || '#F97316'}
        onChange={(e) => onUpdate({ colors: { ...element.colors, female: e.target.value, male: element.colors?.male || '#0d46d6' } })}
        style={{ width: '100%', height: '32px', border: 'none', cursor: 'pointer' }} />
      <TextField size="small" label="Data (ageBand,male,female)" multiline rows={6} value={dataText}
        onChange={(e) => setDataText(e.target.value)}
        onBlur={() => { const parsed = parsePyramidLines(dataText); if (parsed.length > 0) onUpdate({ data: parsed }); }} />
    </Box>
  );
}

/* ── StyleSettings ───────────────────────────────────────────────────────── */

export function StyleSettings({ element, onUpdate }: {
  element: LayoutElement;
  onUpdate: (updates: Partial<LayoutElement>) => void;
}): React.ReactNode {
  const style = element.style || {};
  const handleStyleUpdate = (styleUpdates: Record<string, unknown>) => {
    onUpdate({ style: { ...style, ...styleUpdates } });
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Font Size" type="number" value={style.fontSize?.toString() || ''}
        onChange={(e) => handleStyleUpdate({ fontSize: parseFloat(e.target.value) || undefined })} placeholder="12" />
      <TextField select size="small" label="Font Weight" value={style.fontWeight || 'normal'}
        onChange={(e) => handleStyleUpdate({ fontWeight: e.target.value })}>
        <MenuItem value="normal">Normal</MenuItem><MenuItem value="bold">Bold</MenuItem>
      </TextField>
      <TextField select size="small" label="Text Align" value={style.align || 'left'}
        onChange={(e) => handleStyleUpdate({ align: e.target.value })}>
        <MenuItem value="left">Left</MenuItem>
        <MenuItem value="center">Center</MenuItem>
        <MenuItem value="right">Right</MenuItem>
      </TextField>
      <Typography variant="caption" color="text.secondary">Text Color</Typography>
      <input type="color" value={style.color || '#000000'}
        onChange={(e) => handleStyleUpdate({ color: e.target.value })}
        style={{ width: '100%', height: '32px', border: 'none', cursor: 'pointer' }} />
      <Typography variant="caption" color="text.secondary">Background Color</Typography>
      <input type="color" value={style.backgroundColor || '#ffffff'}
        onChange={(e) => handleStyleUpdate({ backgroundColor: e.target.value })}
        style={{ width: '100%', height: '32px', border: 'none', cursor: 'pointer' }} />
    </Box>
  );
}
