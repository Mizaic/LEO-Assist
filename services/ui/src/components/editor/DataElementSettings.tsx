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
import Autocomplete from '@mui/material/Autocomplete';
import type {
  ChartElement,
  TableElement,
  ImageElement,
  DividerElement,
  CoverElement,
  SankeyData,
} from '@/lib/types/layout';
import type { Measure } from '@/lib/types/fhir';

/* ── DividerSettings ─────────────────────────────────────────────────────── */

export function DividerSettings({ element, onUpdate }: {
  element: DividerElement;
  onUpdate: (updates: Partial<DividerElement>) => void;
}): React.ReactNode {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Thickness (px)" type="number"
        value={element.thickness?.toString() || '2'}
        onChange={(e) => onUpdate({ thickness: parseFloat(e.target.value) || 2 })} />
      <Typography variant="caption" color="text.secondary">Color</Typography>
      <input type="color" value={element.color || '#0078D4'}
        onChange={(e) => onUpdate({ color: e.target.value })}
        style={{ width: '100%', height: '32px', border: 'none', cursor: 'pointer' }} />
    </Box>
  );
}

/* ── CoverSettings ───────────────────────────────────────────────────────── */

export function CoverSettings({ element, onUpdate }: {
  element: CoverElement;
  onUpdate: (updates: Partial<CoverElement>) => void;
}): React.ReactNode {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Title" value={element.title || ''}
        onChange={(e) => onUpdate({ title: e.target.value })} />
      <TextField size="small" label="Subtitle" value={element.subtitle || ''}
        onChange={(e) => onUpdate({ subtitle: e.target.value })} />
      <TextField size="small" label="Date" value={element.date || ''}
        onChange={(e) => onUpdate({ date: e.target.value })} placeholder="September 2020" />
      <Typography variant="caption" color="text.secondary">Background Color</Typography>
      <input type="color" value={element.backgroundColor || '#ffffff'}
        onChange={(e) => onUpdate({ backgroundColor: e.target.value })}
        style={{ width: '100%', height: '32px', border: 'none', cursor: 'pointer' }} />
      <TextField size="small" label="Background Image URL" value={element.backgroundImageUrl || ''}
        onChange={(e) => onUpdate({ backgroundImageUrl: e.target.value })} placeholder="https://..." />
      <TextField size="small" label="Logo URL" value={element.logoUrl || ''}
        onChange={(e) => onUpdate({ logoUrl: e.target.value })} placeholder="https://..." />
    </Box>
  );
}

/* ── ImageSettings ───────────────────────────────────────────────────────── */

export function ImageSettings({ element, onUpdate }: {
  element: ImageElement;
  onUpdate: (updates: Partial<ImageElement>) => void;
}): React.ReactNode {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Image URL" value={element.src || ''}
        onChange={(e) => onUpdate({ src: e.target.value })} placeholder="https://..." />
      <TextField size="small" label="Alt Text" value={element.alt || ''}
        onChange={(e) => onUpdate({ alt: e.target.value })} placeholder="Image description" />
      <TextField select size="small" label="Object Fit" value={element.objectFit || 'contain'}
        onChange={(e) => onUpdate({ objectFit: e.target.value as ImageElement['objectFit'] })}>
        <MenuItem value="contain">Contain</MenuItem>
        <MenuItem value="cover">Cover</MenuItem>
        <MenuItem value="fill">Fill</MenuItem>
        <MenuItem value="none">None</MenuItem>
      </TextField>
    </Box>
  );
}

/* ── TableSettings ───────────────────────────────────────────────────────── */

export function TableSettings({ element, measures, onUpdate }: {
  element: TableElement;
  measures: Measure[];
  onUpdate: (updates: Partial<TableElement>) => void;
}): React.ReactNode {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Autocomplete size="small" options={measures}
        getOptionLabel={(m) => m.title || m.name || m.id || ''}
        value={measures.find((m) => `Measure/${m.id}` === element.dataSource) || null}
        onChange={(_, newValue) => onUpdate({ dataSource: newValue ? `Measure/${newValue.id}` : undefined })}
        renderInput={(params) => <TextField {...params} label="Data Source" placeholder="Select a measure..." />} />
      <FormControlLabel
        control={<Switch size="small" checked={element.showHeader !== false}
          onChange={(_, checked) => onUpdate({ showHeader: checked })} />}
        label="Show Header" />
      <FormControlLabel
        control={<Switch size="small" checked={element.striped === true}
          onChange={(_, checked) => onUpdate({ striped: checked })} />}
        label="Striped Rows" />
    </Box>
  );
}

/* ── ChartSettings ───────────────────────────────────────────────────────── */

const CHART_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'bar', label: 'Bar' }, { value: 'horizontalBar', label: 'Horizontal Bar' },
  { value: 'boxPlot', label: 'Box Plot' }, { value: 'pie', label: 'Pie' },
  { value: 'line', label: 'Line' }, { value: 'area', label: 'Area' },
  { value: 'radar', label: 'Radar' }, { value: 'radialBar', label: 'Radial Bar' },
  { value: 'scatter', label: 'Scatter' }, { value: 'composed', label: 'Composed' },
  { value: 'funnel', label: 'Funnel' }, { value: 'heatmap', label: 'Heatmap' },
  { value: 'bullet', label: 'Bullet/Target Band' }, { value: 'sankey', label: 'Sankey' },
];

const MULTI_SERIES_CHART_TYPES = new Set(['bar', 'horizontalBar', 'line', 'area', 'radar', 'scatter']);

function parseJson(value: string): unknown | null {
  try { return JSON.parse(value); } catch { return null; }
}

function ChartAxisFieldsSection({ element, onUpdate }: {
  element: ChartElement;
  onUpdate: (updates: Partial<ChartElement>) => void;
}): React.ReactNode {
  if (element.chartType === 'heatmap' || element.chartType === 'bullet') {
    return (
      <>
        <TextField size="small"
          label={element.chartType === 'heatmap' ? 'Column Field (X)' : 'Label Field'}
          value={element.xAxisKey || ''}
          onChange={(e) => onUpdate({ xAxisKey: e.target.value || undefined })} placeholder="name" />
        <TextField size="small"
          label={element.chartType === 'heatmap' ? 'Row Field (Y)' : 'Target Field'}
          value={element.chartType === 'heatmap' ? element.seriesKey || '' : element.targetKey || ''}
          onChange={(e) => onUpdate(
            element.chartType === 'heatmap'
              ? { seriesKey: e.target.value || undefined }
              : { targetKey: e.target.value || undefined },
          )}
          placeholder={element.chartType === 'heatmap' ? 'group' : 'target'} />
        <TextField size="small" label="Value Field" value={element.yAxisKey || ''}
          onChange={(e) => onUpdate({ yAxisKey: e.target.value || undefined })} placeholder="value" />
        {element.chartType === 'bullet' && (
          <TextField size="small" label="Range Keys (comma-separated)"
            value={(element.rangeKeys || []).join(', ')}
            onChange={(e) => onUpdate({ rangeKeys: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
            placeholder="range_low, range_mid, range_high" />
        )}
      </>
    );
  }

  return (
    <>
      <TextField size="small" label="Category Field" value={element.xAxisKey || ''}
        onChange={(e) => onUpdate({ xAxisKey: e.target.value || undefined })} placeholder="name" />
      <TextField size="small" label="Value Field (count/percentage)" value={element.yAxisKey || ''}
        onChange={(e) => onUpdate({ yAxisKey: e.target.value || undefined })} placeholder="value" />
    </>
  );
}

function ChartJsonFields({ element, onUpdate }: {
  element: ChartElement;
  onUpdate: (updates: Partial<ChartElement>) => void;
}): React.ReactNode {
  const [multiSeriesText, setMultiSeriesText] = useState(JSON.stringify(element.multiSeries || [], null, 2));
  const [composedSeriesText, setComposedSeriesText] = useState(JSON.stringify(element.composedSeries || [], null, 2));
  const [shadedAreasText, setShadedAreasText] = useState(JSON.stringify(element.shadedAreas || [], null, 2));
  const [highlightedPointsText, setHighlightedPointsText] = useState(JSON.stringify(element.highlightedPoints || [], null, 2));
  const [sankeyText, setSankeyText] = useState(JSON.stringify(element.sankey || { nodes: [], links: [] }, null, 2));
  const [prevElementId, setPrevElementId] = useState(element.id);

  if (element.id !== prevElementId) {
    setPrevElementId(element.id);
    setMultiSeriesText(JSON.stringify(element.multiSeries || [], null, 2));
    setComposedSeriesText(JSON.stringify(element.composedSeries || [], null, 2));
    setShadedAreasText(JSON.stringify(element.shadedAreas || [], null, 2));
    setHighlightedPointsText(JSON.stringify(element.highlightedPoints || [], null, 2));
    setSankeyText(JSON.stringify(element.sankey || { nodes: [], links: [] }, null, 2));
  }

  const showLineOverlays = element.chartType === 'line' || element.chartType === 'area' || element.chartType === 'composed';

  return (
    <>
      {MULTI_SERIES_CHART_TYPES.has(element.chartType) && (
        <TextField size="small" label="Series (JSON)" multiline rows={6} value={multiSeriesText}
          onChange={(e) => setMultiSeriesText(e.target.value)}
          onBlur={() => { const p = parseJson(multiSeriesText); if (Array.isArray(p)) onUpdate({ multiSeries: p }); }} />
      )}
      {element.chartType === 'composed' && (
        <TextField size="small" label="Composed Series (JSON)" multiline rows={6} value={composedSeriesText}
          onChange={(e) => setComposedSeriesText(e.target.value)}
          onBlur={() => { const p = parseJson(composedSeriesText); if (Array.isArray(p)) onUpdate({ composedSeries: p }); }} />
      )}
      {showLineOverlays && (
        <>
          <TextField size="small" label="Shaded Areas (JSON)" multiline rows={4} value={shadedAreasText}
            onChange={(e) => setShadedAreasText(e.target.value)}
            onBlur={() => { const p = parseJson(shadedAreasText); if (Array.isArray(p)) onUpdate({ shadedAreas: p }); }} />
          <TextField size="small" label="Highlighted Points (JSON)" multiline rows={4} value={highlightedPointsText}
            onChange={(e) => setHighlightedPointsText(e.target.value)}
            onBlur={() => { const p = parseJson(highlightedPointsText); if (Array.isArray(p)) onUpdate({ highlightedPoints: p }); }} />
        </>
      )}
      {element.chartType === 'sankey' && (
        <TextField size="small" label="Sankey Data (JSON)" multiline rows={6} value={sankeyText}
          onChange={(e) => setSankeyText(e.target.value)}
          onBlur={() => { const p = parseJson(sankeyText); if (p && typeof p === 'object' && 'nodes' in (p as Record<string, unknown>) && 'links' in (p as Record<string, unknown>)) onUpdate({ sankey: p as SankeyData }); }} />
      )}
    </>
  );
}

export function ChartSettings({ element, measures, onUpdate }: {
  element: ChartElement;
  measures: Measure[];
  onUpdate: (updates: Partial<ChartElement>) => void;
}): React.ReactNode {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Autocomplete size="small" options={measures}
        getOptionLabel={(m) => m.title || m.name || m.id || ''}
        value={measures.find((m) => `Measure/${m.id}` === element.dataSource) || null}
        onChange={(_, newValue) => onUpdate({ dataSource: newValue ? `Measure/${newValue.id}` : undefined })}
        renderInput={(params) => <TextField {...params} label="Data Source" placeholder="Select a measure..." />} />
      <TextField select size="small" label="Chart Type" value={element.chartType}
        onChange={(e) => onUpdate({ chartType: e.target.value as ChartElement['chartType'] })}>
        {CHART_TYPE_OPTIONS.map((opt) => <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>)}
      </TextField>

      <ChartAxisFieldsSection element={element} onUpdate={onUpdate} />

      <FormControlLabel
        control={<Switch size="small" checked={element.showLegend !== false}
          onChange={(_, checked) => onUpdate({ showLegend: checked })} />}
        label="Show Legend" />
      <FormControlLabel
        control={<Switch size="small" checked={element.showGrid !== false}
          onChange={(_, checked) => onUpdate({ showGrid: checked })} />}
        label="Show Grid" />

      <ChartJsonFields element={element} onUpdate={onUpdate} />
    </Box>
  );
}
