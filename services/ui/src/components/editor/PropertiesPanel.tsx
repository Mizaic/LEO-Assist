/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { useCallback } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import Divider from '@mui/material/Divider';
import Button from '@mui/material/Button';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import ExpandMoreOutlined from '@mui/icons-material/ExpandMoreOutlined';
import PushPinOutlined from '@mui/icons-material/PushPinOutlined';
import SettingsOutlined from '@mui/icons-material/SettingsOutlined';
import BrushOutlined from '@mui/icons-material/BrushOutlined';
import { useEditorStore } from '@/stores/editorStore';
import type {
  LayoutElement,
  TextElement,
  ImageElement,
  TableElement,
  ChartElement,
  HeadingElement,
  BulletListElement,
  ChecklistElement,
  DividerElement,
  CoverElement,
  InterpretationElement,
  ExecutiveSummaryElement,
  KpiCardElement,
  HeroStatsElement,
  ComparisonBarsElement,
  PopulationPyramidElement,
} from '@/lib/types/layout';
import { InterpretationSettings, ExecutiveSummarySettings } from './InterpretationSettings';
import { TextSettings, HeadingSettings, BulletListSettings, ChecklistSettings } from './TextElementSettings';
import { ChartSettings, TableSettings, ImageSettings, DividerSettings, CoverSettings } from './DataElementSettings';
import {
  KpiCardSettings, HeroStatsSettings, ComparisonBarsSettings,
  PopulationPyramidSettings, StyleSettings,
} from './StatsElementSettings';

/* ── Helpers ──────────────────────────────────────────────────────────────── */

const HEADING_TYPES = new Set(['heading1', 'heading2', 'heading3', 'subtitle']);

/* ── Empty / multi-select states ─────────────────────────────────────────── */

function EmptyState({ message }: { message: string }): React.ReactNode {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', p: 1.5, gap: 1.5, height: '100%', overflow: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 1 }}>
        <Typography data-testid="properties-title" sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', textTransform: 'uppercase' }}>
          Properties
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', p: 3, color: 'text.disabled', textAlign: 'center' }}>
        <Typography>{message}</Typography>
      </Box>
    </Box>
  );
}

/* ── Page properties ─────────────────────────────────────────────────────── */

function PageProperties(): React.ReactNode {
  const { selectedPageId, layout, setPageOrientation, updatePage, report, updateReport } = useEditorStore();
  const selectedPage = layout.pages.find((p) => p.id === selectedPageId);
  if (!selectedPage || !selectedPageId) return null;

  const reportPeriod = report?.period || {};
  const updateReportPeriod = (field: 'start' | 'end', value: string) => {
    if (!report) return;
    updateReport({ period: { ...reportPeriod, [field]: value || undefined } });
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', p: 1.5, gap: 1.5, height: '100%', overflow: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 1 }}>
        <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', textTransform: 'uppercase' }}>
          Page Properties
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <TextField select size="small" label="Orientation" value={selectedPage.orientation}
          onChange={(e) => setPageOrientation(selectedPageId, e.target.value as 'portrait' | 'landscape')}>
          <MenuItem value="portrait">Portrait</MenuItem>
          <MenuItem value="landscape">Landscape</MenuItem>
        </TextField>
        <Typography variant="caption" color="text.secondary">Page Color</Typography>
        <input type="color" value={selectedPage.backgroundColor || '#ffffff'}
          onChange={(e) => updatePage(selectedPageId, { backgroundColor: e.target.value })}
          style={{ width: '100%', height: '32px', border: 'none', cursor: 'pointer' }} />
        <FormControlLabel control={<Switch size="small" checked={selectedPage.hideHeader === true}
          onChange={(_, checked) => updatePage(selectedPageId, { hideHeader: checked })} />} label="Hide Header" />
        <FormControlLabel control={<Switch size="small" checked={selectedPage.hideFooter === true}
          onChange={(_, checked) => updatePage(selectedPageId, { hideFooter: checked })} />} label="Hide Footer" />
        <FormControlLabel control={<Switch size="small" checked={selectedPage.hideCover === true}
          onChange={(_, checked) => updatePage(selectedPageId, { hideCover: checked })} />} label="Hide Cover" />
        <Divider />
        <Typography variant="body2" fontWeight={600}>Report period</Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
          <TextField size="small" label="Period start" type="date" value={reportPeriod.start || ''}
            onChange={(e) => updateReportPeriod('start', e.target.value)} disabled={!report}
            InputLabelProps={{ shrink: true }} />
          <TextField size="small" label="Period end" type="date" value={reportPeriod.end || ''}
            onChange={(e) => updateReportPeriod('end', e.target.value)} disabled={!report}
            InputLabelProps={{ shrink: true }} />
        </Box>
      </Box>
    </Box>
  );
}

/* ── Element settings router ─────────────────────────────────────────────── */

function ElementSettingsRouter({ element, handleUpdate }: {
  element: LayoutElement;
  handleUpdate: (updates: Partial<LayoutElement>) => void;
}): React.ReactNode {
  const layout = useEditorStore((s) => s.layout);
  const report = useEditorStore((s) => s.report);
  const { type } = element;

  if (type === 'interpretation') {
    return <InterpretationSettings element={element as InterpretationElement} onUpdate={handleUpdate}
      layoutElements={layout.pages.flatMap((page) => page.elements)} measures={[]} />;
  }
  if (type === 'executiveSummary') return <ExecutiveSummarySettings element={element as ExecutiveSummaryElement} onUpdate={handleUpdate} reportId={report?.id} />;
  if (type === 'text') return <TextSettings element={element as TextElement} onUpdate={handleUpdate} />;
  if (HEADING_TYPES.has(type)) return <HeadingSettings element={element as HeadingElement} onUpdate={handleUpdate} />;
  if (type === 'bulletList') return <BulletListSettings element={element as BulletListElement} onUpdate={handleUpdate} />;
  if (type === 'checklist') return <ChecklistSettings element={element as ChecklistElement} onUpdate={handleUpdate} />;
  if (type === 'divider') return <DividerSettings element={element as DividerElement} onUpdate={handleUpdate} />;
  if (type === 'cover') return <CoverSettings element={element as CoverElement} onUpdate={handleUpdate} />;
  if (type === 'image') return <ImageSettings element={element as ImageElement} onUpdate={handleUpdate} />;
  if (type === 'table') return <TableSettings element={element as TableElement} measures={[]} onUpdate={handleUpdate} />;
  if (type === 'chart') return <ChartSettings element={element as ChartElement} measures={[]} onUpdate={handleUpdate} />;
  if (type === 'kpiCard') return <KpiCardSettings element={element as KpiCardElement} onUpdate={handleUpdate} />;
  if (type === 'heroStats') return <HeroStatsSettings element={element as HeroStatsElement} onUpdate={handleUpdate} />;
  if (type === 'comparisonBars') return <ComparisonBarsSettings element={element as ComparisonBarsElement} onUpdate={handleUpdate} />;
  if (type === 'populationPyramid') return <PopulationPyramidSettings element={element as PopulationPyramidElement} onUpdate={handleUpdate} />;
  return null;
}

/* ── Main component ──────────────────────────────────────────────────────── */

export function PropertiesPanel(): React.ReactNode {
  const {
    selectedPageId, selectedElementIds, layout, updateElement,
    getSelectedElements, setSelection,
  } = useEditorStore();

  const selectedElements = getSelectedElements();
  const selectedElement = selectedElements.length === 1 ? selectedElements[0] : null;
  const selectedPage = layout.pages.find((p) => p.id === selectedPageId);

  const handleUpdate = useCallback(
    (updates: Partial<LayoutElement>) => {
      if (selectedPageId && selectedElement) updateElement(selectedPageId, selectedElement.id, updates);
    },
    [selectedPageId, selectedElement, updateElement],
  );

  const handleNumberChange = useCallback(
    (field: keyof LayoutElement, value: string) => {
      const num = parseFloat(value);
      if (!isNaN(num)) handleUpdate({ [field]: num } as Partial<LayoutElement>);
    },
    [handleUpdate],
  );

  if (!selectedPageId && selectedElements.length === 0) {
    return <EmptyState message="Select a page or element to view properties" />;
  }
  if (selectedElements.length > 1) {
    return <EmptyState message={`${selectedElements.length} elements selected`} />;
  }
  if (!selectedElement && selectedPage) {
    return <PageProperties />;
  }
  if (!selectedElement) return null;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', p: 1.5, gap: 1.5, height: '100%', overflow: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 1 }}>
        <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', textTransform: 'uppercase' }}>
          {selectedElement.type.charAt(0).toUpperCase() + selectedElement.type.slice(1)} Properties
        </Typography>
        <Button variant="text" size="small" onClick={() => { if (selectedPageId) setSelection(selectedPageId, []); }}>
          Page properties
        </Button>
      </Box>

      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMoreOutlined />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <PushPinOutlined fontSize="small" />
            <Typography variant="body2">Position & Size</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
              <TextField size="small" label="X (mm)" type="number" value={selectedElement.x.toString()}
                onChange={(e) => handleNumberChange('x', e.target.value)} />
              <TextField size="small" label="Y (mm)" type="number" value={selectedElement.y.toString()}
                onChange={(e) => handleNumberChange('y', e.target.value)} />
            </Box>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 }}>
              <TextField size="small" label="Width (mm)" type="number" value={selectedElement.w.toString()}
                onChange={(e) => handleNumberChange('w', e.target.value)} />
              <TextField size="small" label="Height (mm)" type="number" value={selectedElement.h.toString()}
                onChange={(e) => handleNumberChange('h', e.target.value)} />
            </Box>
          </Box>
        </AccordionDetails>
      </Accordion>

      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandMoreOutlined />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SettingsOutlined fontSize="small" />
            <Typography variant="body2">Settings</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <ElementSettingsRouter element={selectedElement} handleUpdate={handleUpdate} />
        </AccordionDetails>
      </Accordion>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMoreOutlined />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BrushOutlined fontSize="small" />
            <Typography variant="body2">Style</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <StyleSettings element={selectedElement} onUpdate={handleUpdate} />
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}
