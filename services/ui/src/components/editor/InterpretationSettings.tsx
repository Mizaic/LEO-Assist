/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { useEffect, useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import Divider from '@mui/material/Divider';
import type {
  LayoutElement,
  MeasureElement,
  InterpretationElement,
  InterpretationContentFormat,
  ExecutiveSummaryElement,
} from '@/lib/types/layout';
import { getMeasureReport } from '@/lib/api';
import type { Measure } from '@/lib/types/fhir';
import { extractAgentSummaryEntries } from '@/lib/api/measureReports';

/* ── JSON extraction helper (shared by both preview components) ──────────── */

function extractSummaryField(text: string): string | null {
  const match = text.match(/"summary"\s*:\s*"([^"]*(?:\\.[^"]*)*)"/);
  if (!match) return null;
  try { return JSON.parse(`"${match[1]}"`); } catch { return match[1]; }
}

function extractJsonBlock(raw: string): string | null {
  const fenceMatch = raw.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
  if (fenceMatch) return fenceMatch[1].trim();

  const start = raw.indexOf('{');
  if (start === -1) return null;

  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let i = start; i < raw.length; i++) {
    const char = raw[i];
    if (inString) {
      if (escaped) { escaped = false; continue; }
      if (char === '\\') { escaped = true; continue; }
      if (char === '"') { inString = false; }
      continue;
    }
    if (char === '"') { inString = true; continue; }
    if (char === '{') depth++;
    else if (char === '}') { depth--; if (depth === 0) return raw.slice(start, i + 1); }
  }
  return null;
}

/* ── InterpretationPreviewDisplay ────────────────────────────────────────── */

export function InterpretationPreviewDisplay({ preview }: {
  preview: InterpretationElement['preview'];
}): React.ReactNode {
  const parsed = useMemo(() => {
    if (!preview) return null;
    const summaryStr = typeof preview.summary === 'string' ? preview.summary : '';

    if (summaryStr.includes('```') || (summaryStr.trim().startsWith('{') && summaryStr.includes('"summary"'))) {
      const jsonStr = extractJsonBlock(summaryStr);
      if (jsonStr) {
        try {
          const obj = JSON.parse(jsonStr);
          return {
            summary: typeof obj.summary === 'string' ? obj.summary : '',
            insights: Array.isArray(obj.insights) ? obj.insights : [],
          };
        } catch { /* fallthrough */ }
      }
    }
    const field = extractSummaryField(summaryStr);
    if (field) return { summary: field, insights: [] };
    return { summary: summaryStr, insights: preview.insights || [] };
  }, [preview]);

  if (!parsed) return null;

  const formatItem = (item: unknown): string => {
    if (typeof item === 'string') return item;
    if (item && typeof item === 'object') {
      const rec = item as Record<string, unknown>;
      const parts = [rec.theme ? `${rec.theme}` : '', rec.observation ? `${rec.observation}` : ''].filter(Boolean);
      return parts.join(' – ') || JSON.stringify(item);
    }
    return String(item);
  };

  return (
    <>
      <Typography>{parsed.summary}</Typography>
      {parsed.insights.length > 0 && (
        <Typography variant="body2">Insights: {parsed.insights.map((i: unknown) => formatItem(i)).join(' | ')}</Typography>
      )}
    </>
  );
}

/* ── InterpretationSettings ──────────────────────────────────────────────── */

export function InterpretationSettings({ element, onUpdate, layoutElements, measures }: {
  element: InterpretationElement;
  onUpdate: (updates: Partial<InterpretationElement>) => void;
  layoutElements: LayoutElement[];
  measures: Measure[];
}): React.ReactNode {
  const measureElements = layoutElements.filter((el) => el.type === 'measure') as MeasureElement[];
  const measureLabelById = useMemo(() => {
    const map = new Map<string, string>();
    measures.forEach((m) => { if (m.id) map.set(m.id, m.title || m.name || m.id); });
    return map;
  }, [measures]);

  const linkedMeasureIds = element.linkedElementIds || [];

  const getMeasureElementLabel = (item: MeasureElement): string => {
    const customTitle = item.title?.trim();
    if (customTitle) return customTitle;
    const measureId = item.measureId?.replace('Measure/', '') || '';
    return measureLabelById.get(measureId) || measureId || 'Unselected measure';
  };

  const linkedMeasureLabels = linkedMeasureIds
    .map((id) => measureElements.find((el) => el.id === id))
    .filter(Boolean)
    .map((linked) => getMeasureElementLabel(linked as MeasureElement));

  const format = element.contentFormat || 'summary';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Title" value={element.title || ''}
        onChange={(e) => onUpdate({ title: e.target.value })} placeholder="Interpretation" />
      <Typography variant="caption" color="text.secondary">Linked measure elements</Typography>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
        {measureElements.map((item) => {
          const label = getMeasureElementLabel(item);
          const checked = linkedMeasureIds.includes(item.id);
          return (
            <label key={item.id} style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input type="checkbox" checked={checked} onChange={(event) => {
                const next = new Set(linkedMeasureIds);
                if (event.target.checked) next.add(item.id); else next.delete(item.id);
                onUpdate({ linkedElementIds: Array.from(next), preview: undefined, lastRunAt: undefined });
              }} />
              <Typography variant="body2">{label} ({item.id})</Typography>
            </label>
          );
        })}
      </Box>
      <Typography variant="body2" color="text.secondary">
        Linked to: {linkedMeasureLabels.length > 0 ? linkedMeasureLabels.join(', ') : 'Unlinked'}
      </Typography>
      <TextField select size="small" label="Model size" value={element.modelSize || 'small'}
        onChange={(e) => onUpdate({ modelSize: e.target.value as 'small' | 'big' })}>
        <MenuItem value="small">Small</MenuItem><MenuItem value="big">Big</MenuItem>
      </TextField>
      <TextField select size="small" label="Content format" value={format}
        onChange={(e) => onUpdate({ contentFormat: e.target.value as InterpretationContentFormat })}>
        <MenuItem value="summary">Summary</MenuItem>
        <MenuItem value="bullets">Bullets</MenuItem>
        <MenuItem value="full">Full</MenuItem>
      </TextField>
      {element.preview?.summary && (
        <>
          <Divider />
          <Typography variant="body2" fontWeight={600}>Preview</Typography>
          <InterpretationPreviewDisplay preview={element.preview} />
        </>
      )}
    </Box>
  );
}

/* ── ExecutiveSummaryPreviewDisplay ───────────────────────────────────────── */

export function ExecutiveSummaryPreviewDisplay({ summary }: { summary?: string }): React.ReactNode {
  const parsed = useMemo(() => {
    if (!summary) return '';

    if (summary.includes('```') || (summary.trim().startsWith('{') && summary.includes('"summary"'))) {
      const jsonStr = extractJsonBlock(summary);
      if (jsonStr) {
        try {
          const obj = JSON.parse(jsonStr);
          return typeof obj.summary === 'string' ? obj.summary : summary;
        } catch { /* fallthrough */ }
      }
    }
    return extractSummaryField(summary) || summary;
  }, [summary]);

  return <Typography>{parsed}</Typography>;
}

/* ── ExecutiveSummarySettings ────────────────────────────────────────────── */

export function ExecutiveSummarySettings({ element, onUpdate, reportId }: {
  element: ExecutiveSummaryElement;
  onUpdate: (updates: Partial<ExecutiveSummaryElement>) => void;
  reportId?: string | null;
}): React.ReactNode {
  const [entries, setEntries] = useState<{ measure_id?: string | null; summary: Record<string, unknown> }[]>([]);

  useEffect(() => {
    const load = async () => {
      if (!reportId) { setEntries([]); return; }
      try {
        const report = await getMeasureReport(reportId);
        const parsed = extractAgentSummaryEntries(report)
          .filter((entry) => entry.measure_id)
          .map((entry) => ({ measure_id: entry.measure_id, summary: entry.summary }));
        setEntries(parsed);
      } catch (error) {
        console.error('Failed to load agent summaries:', error);
        setEntries([]);
      }
    };
    load();
  }, [reportId]);

  const excluded = new Set(element.excludedMeasureIds || []);
  const toggleExclude = (measureId?: string | null) => {
    if (!measureId) return;
    const next = new Set(element.excludedMeasureIds || []);
    if (next.has(measureId)) next.delete(measureId); else next.add(measureId);
    onUpdate({ excludedMeasureIds: Array.from(next) });
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Title" value={element.title || ''}
        onChange={(e) => onUpdate({ title: e.target.value })} placeholder="Executive Summary" />
      <TextField select size="small" label="Mode" value={element.mode || 'default'}
        onChange={(e) => onUpdate({ mode: e.target.value as 'default' | 'tight' })}>
        <MenuItem value="default">Default</MenuItem><MenuItem value="tight">Board tight</MenuItem>
      </TextField>
      <TextField select size="small" label="Model size" value={element.modelSize || 'small'}
        onChange={(e) => onUpdate({ modelSize: e.target.value as 'small' | 'big' })}>
        <MenuItem value="small">Small</MenuItem><MenuItem value="big">Big</MenuItem>
      </TextField>
      <Divider />
      <Typography variant="body2" fontWeight={600}>Exclude interpretations</Typography>
      {entries.length === 0 && (
        <Typography variant="body2" color="text.secondary">No interpretations found yet.</Typography>
      )}
      {entries.map((entry) => {
        const measureId = entry.measure_id || '';
        return (
          <FormControlLabel key={measureId}
            control={<Switch size="small" checked={excluded.has(measureId)} onChange={() => toggleExclude(measureId)} />}
            label={measureId} />
        );
      })}
      {element.preview?.summary && (
        <>
          <Divider />
          <Typography variant="body2" fontWeight={600}>Preview</Typography>
          <ExecutiveSummaryPreviewDisplay summary={element.preview.summary} />
        </>
      )}
    </Box>
  );
}
