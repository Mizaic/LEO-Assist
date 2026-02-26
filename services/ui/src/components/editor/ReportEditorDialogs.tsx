'use client';

import { useMemo, type Dispatch, type SetStateAction } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import SearchOutlined from '@mui/icons-material/SearchOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import { useEditorStore } from '@/stores/editorStore';
import type { LayoutElement, MeasureElement } from '@/lib/types/layout';
import type { Measure } from '@/lib/types/fhir';
import type { AgentInterpretation, AgentModelSize } from './agentTypes';
import { MeasurePickerDialog } from '@/components/measures/MeasurePickerDialog';
import {
  formatValue,
  formatInsight,
  formatQualityCheck,
  formatRecommendation,
  type PendingDrop,
} from './reportEditorHelpers';

// ── Measure picker wrapper ───────────────────────────────────────────────────

interface MeasurePickerWrapperProps {
  open: boolean;
  measures: Measure[];
  pendingDrop: PendingDrop | null;
  onClose: () => void;
  setPendingDrop: (v: PendingDrop | null) => void;
}

export function MeasurePickerWrapper({
  open,
  measures,
  pendingDrop,
  onClose,
  setPendingDrop,
}: MeasurePickerWrapperProps) {
  const addElement = useEditorStore((s) => s.addElement);

  return (
    <MeasurePickerDialog
      open={open}
      onClose={() => {
        onClose();
        setPendingDrop(null);
      }}
      onSelect={(measureId) => {
        if (!pendingDrop) return;
        addElement(pendingDrop.pageId, {
          type: 'measure',
          x: pendingDrop.x,
          y: pendingDrop.y,
          w: pendingDrop.w,
          h: pendingDrop.h,
          measureId: `Measure/${measureId}`,
          displayMode: 'bar',
          showTitle: true,
          showScore: true,
        } as Omit<MeasureElement, 'id'>);
        setPendingDrop(null);
      }}
      measures={measures}
    />
  );
}

// ── Agent interpretation dialog ──────────────────────────────────────────────

interface AgentDialogProps {
  open: boolean;
  busy: boolean;
  goal: string;
  error: string | null;
  summary: AgentInterpretation | null;
  onClose: () => void;
  onGoalChange: (goal: string) => void;
  onRun: () => void;
}

export function AgentInterpretationDialog({
  open, busy, goal, error, summary, onClose, onGoalChange, onRun,
}: AgentDialogProps) {
  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>Interpret Measures</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: 1 }}>
          <TextField
            label="Focus or question (optional)"
            multiline
            placeholder="e.g. Highlight trends, risks, and suggested follow-up measures."
            value={goal}
            onChange={(e) => onGoalChange(e.target.value)}
            size="small"
          />
          {error && (
            <Typography variant="body2" color="error">{error}</Typography>
          )}
          {summary && <InterpretationSummary summary={summary} />}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button variant="outlined" onClick={onClose}>Close</Button>
        <Button variant="contained" onClick={onRun} disabled={busy}>
          {busy ? 'Running...' : 'Run'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function InterpretationSummary({ summary }: { summary: AgentInterpretation }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      <Typography variant="body2" fontWeight={600}>Summary</Typography>
      <Typography variant="body2">{summary.summary}</Typography>
      <SummarySection title="Insights" items={summary.insights ?? []} formatter={formatInsight} keyPrefix="agent-insight" />
      <SummarySection title="Data quality checks" items={summary.quality_checks ?? []} formatter={formatQualityCheck} keyPrefix="agent-quality" />
      <SummarySection title="Recommended measures" items={summary.recommended_measures ?? []} formatter={formatRecommendation} keyPrefix="agent-rec" />
      <SummarySection title="Follow-up questions" items={summary.follow_up_questions ?? []} formatter={formatValue} keyPrefix="agent-follow" />
    </Box>
  );
}

interface SummarySectionProps {
  title: string;
  items: unknown[];
  formatter: (item: unknown) => string;
  keyPrefix: string;
}

function SummarySection({ title, items, formatter, keyPrefix }: SummarySectionProps) {
  if (!items?.length) return null;
  return (
    <>
      <Typography variant="body2" fontWeight={600}>{title}</Typography>
      {items.map((item, idx) => (
        <Typography key={`${keyPrefix}-${idx}`} variant="body2">
          • {formatter(item)}
        </Typography>
      ))}
    </>
  );
}

// ── Interpretation link dialog ───────────────────────────────────────────────

interface InterpretationLinkDialogProps {
  open: boolean;
  measures: Measure[];
  pendingDrop: PendingDrop | null;
  selectedLinks: string[];
  searchQuery: string;
  agentModelSize: AgentModelSize;
  setSelectedLinks: Dispatch<SetStateAction<string[]>>;
  setSearchQuery: (v: string) => void;
  onClose: () => void;
  onCancel: () => void;
}

export function InterpretationLinkDialog({
  open, measures, pendingDrop, selectedLinks, searchQuery,
  agentModelSize, setSelectedLinks, setSearchQuery, onClose, onCancel,
}: InterpretationLinkDialogProps) {
  const { addElement, layout } = useEditorStore();

  const measureElements = useMemo(() => {
    return layout.pages.flatMap((page, pageIndex) =>
      page.elements
        .filter((el) => el.type === 'measure')
        .map((el) => ({
          elementId: el.id,
          measureId: (el as MeasureElement).measureId,
          pageIndex,
        })),
    );
  }, [layout.pages]);

  const measureLabelById = useMemo(() => {
    const map = new Map<string, string>();
    measures.forEach((m) => {
      if (m.id) map.set(m.id, m.title || m.name || m.id);
    });
    return map;
  }, [measures]);

  const handleConfirm = () => {
    if (!pendingDrop) return;
    addElement(pendingDrop.pageId, {
      type: 'interpretation',
      x: pendingDrop.x,
      y: pendingDrop.y,
      w: pendingDrop.w,
      h: pendingDrop.h,
      linkedElementIds: selectedLinks,
      modelSize: agentModelSize,
      contentFormat: 'summary',
    } as Omit<LayoutElement, 'id'>);
    onClose();
  };

  return (
    <Dialog open={open} onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle>Link interpretation to a measure</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Select one or more measures to link.
          </Typography>
          {measureElements.length > 0 && (
            <MeasureSearchField query={searchQuery} onChange={setSearchQuery} />
          )}
          <MeasureCheckboxList
            measureElements={measureElements}
            measureLabelById={measureLabelById}
            selectedLinks={selectedLinks}
            searchQuery={searchQuery}
            setSelectedLinks={setSelectedLinks}
          />
          {selectedLinks.length > 0 && (
            <Typography variant="body2" color="text.secondary">
              {selectedLinks.length} measure{selectedLinks.length !== 1 ? 's' : ''} selected
            </Typography>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button variant="outlined" onClick={onCancel}>Cancel</Button>
        <Button
          variant="contained"
          disabled={selectedLinks.length === 0 || !pendingDrop}
          onClick={handleConfirm}
        >
          Add interpretation
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Sub-components ───────────────────────────────────────────────────────────

function MeasureSearchField({
  query,
  onChange,
}: {
  query: string;
  onChange: (v: string) => void;
}) {
  return (
    <TextField
      placeholder="Search measures..."
      size="small"
      value={query}
      onChange={(e) => onChange(e.target.value)}
      InputProps={{
        startAdornment: (
          <InputAdornment position="start"><SearchOutlined /></InputAdornment>
        ),
        endAdornment: query ? (
          <InputAdornment position="end">
            <IconButton size="small" onClick={() => onChange('')} aria-label="Clear search">
              <CloseOutlined fontSize="small" />
            </IconButton>
          </InputAdornment>
        ) : undefined,
      }}
    />
  );
}

interface MeasureCheckboxListProps {
  measureElements: Array<{ elementId: string; measureId: string; pageIndex: number }>;
  measureLabelById: Map<string, string>;
  selectedLinks: string[];
  searchQuery: string;
  setSelectedLinks: Dispatch<SetStateAction<string[]>>;
}

function MeasureCheckboxList({
  measureElements, measureLabelById, selectedLinks, searchQuery, setSelectedLinks,
}: MeasureCheckboxListProps) {
  const { enriched, filtered, grouped, pageKeys, showPageHeaders } = useMemo(() => {
    const query = searchQuery.toLowerCase();
    const enrichedItems = measureElements.map((item) => {
      const measureId = item.measureId?.replace('Measure/', '') || '';
      const label = measureLabelById.get(measureId) || measureId || 'Unselected measure';
      const checked = selectedLinks.includes(item.elementId);
      return { ...item, label, checked };
    });
    const filteredItems = query
      ? enrichedItems.filter((item) => item.label.toLowerCase().includes(query))
      : enrichedItems;
    const sorted = [...filteredItems].sort((a, b) => {
      if (a.checked !== b.checked) return a.checked ? -1 : 1;
      return a.label.localeCompare(b.label);
    });
    const groupedMap = new Map<number, typeof sorted>();
    sorted.forEach((item) => {
      const group = groupedMap.get(item.pageIndex) || [];
      group.push(item);
      groupedMap.set(item.pageIndex, group);
    });
    const keys = Array.from(groupedMap.keys()).sort((a, b) => a - b);
    const headers = keys.length > 1 || (keys.length === 1 && keys[0] > 0);
    return { enriched: enrichedItems, filtered: filteredItems, grouped: groupedMap, pageKeys: keys, showPageHeaders: headers };
  }, [measureElements, measureLabelById, selectedLinks, searchQuery]);

  const containerSx = {
    maxHeight: '360px',
    overflowY: 'auto' as const,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 0.5,
    border: measureElements.length > 0 ? 1 : 'none',
    borderColor: 'grey.300',
    borderRadius: 1,
    p: measureElements.length > 0 ? 1 : 0,
  };

  if (measureElements.length === 0) {
    return (
      <Box sx={containerSx}>
        <Typography variant="body2" color="text.secondary">
          Add a measure to the canvas first.
        </Typography>
      </Box>
    );
  }

  if (filtered.length === 0) {
    return (
      <Box sx={containerSx}>
        <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
          No measures match &quot;{searchQuery}&quot;
        </Typography>
      </Box>
    );
  }

  const toggleLink = (elementId: string, checked: boolean) => {
    setSelectedLinks((prev) => {
      const next = new Set(prev);
      if (checked) next.add(elementId); else next.delete(elementId);
      return Array.from(next);
    });
  };

  return (
    <Box sx={containerSx}>
      {pageKeys.map((pageIndex) => (
        <div key={`page-group-${pageIndex}`}>
          {showPageHeaders && (
            <Typography
              variant="caption"
              fontWeight={600}
              sx={{ color: 'text.disabled', p: '6px 4px 2px', display: 'block', textTransform: 'uppercase', letterSpacing: '0.5px' }}
            >
              Page {pageIndex + 1}
            </Typography>
          )}
          {grouped.get(pageIndex)!.map((item) => (
            <FormControlLabel
              key={`interpretation-link-${item.elementId}`}
              control={
                <Checkbox
                  checked={item.checked}
                  onChange={(_, c) => toggleLink(item.elementId, c)}
                  size="small"
                />
              }
              label={<Typography variant="body2" sx={{ lineHeight: '1.4' }}>{item.label}</Typography>}
              sx={{ alignItems: 'flex-start' }}
            />
          ))}
        </div>
      ))}
    </Box>
  );
}
