'use client';

import { useState, useMemo, useCallback } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import InputAdornment from '@mui/material/InputAdornment';
import SearchOutlined from '@mui/icons-material/SearchOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import BarChartOutlined from '@mui/icons-material/BarChartOutlined';
import CheckCircleOutlined from '@mui/icons-material/CheckCircleOutlined';
import type { Measure } from '@/lib/types/fhir';
import { CATEGORIES, inferCategory, type MeasureCategory } from './measureCategoryUtils';

interface MeasurePickerDialogProps {
  open: boolean;
  onClose: () => void;
  onSelect: (measureId: string) => void;
  measures: Measure[];
  loading?: boolean;
  selectedMeasureId?: string;
}

export function MeasurePickerDialog({
  open, onClose, onSelect, measures, loading, selectedMeasureId,
}: MeasurePickerDialogProps) {
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const enriched = useMemo(
    () => measures.map((m) => ({ measure: m, category: inferCategory(m) })),
    [measures],
  );

  const filtered = useMemo(() => {
    let items = enriched;
    if (activeCategory) items = items.filter((i) => i.category === activeCategory);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      items = items.filter((i) =>
        (i.measure.title || '').toLowerCase().includes(q) ||
        (i.measure.name || '').toLowerCase().includes(q) ||
        (i.measure.description || '').toLowerCase().includes(q) ||
        (i.measure.id || '').toLowerCase().includes(q),
      );
    }
    return items;
  }, [enriched, search, activeCategory]);

  const grouped = useMemo(() => {
    const groups: { category: MeasureCategory; items: typeof filtered }[] = [];
    for (const cat of CATEGORIES) {
      const items = filtered.filter((i) => i.category === cat.key);
      if (items.length > 0) groups.push({ category: cat, items });
    }
    return groups;
  }, [filtered]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of enriched) counts[item.category] = (counts[item.category] || 0) + 1;
    return counts;
  }, [enriched]);

  const selectedMeasure = measures.find((m) => m.id === selectedMeasureId?.replace('Measure/', ''));

  const handleSelect = useCallback((measureId: string) => { onSelect(measureId); onClose(); }, [onSelect, onClose]);
  const handleCategoryToggle = useCallback((key: string) => { setActiveCategory((prev) => (prev === key ? null : key)); }, []);

  return (
    <Dialog open={open} onClose={onClose} maxWidth={false} PaperProps={{ sx: { maxWidth: '880px', width: '90vw', maxHeight: '85vh' } }}>
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        Select a measure
        <IconButton aria-label="Close" onClick={onClose} size="small"><CloseOutlined /></IconButton>
      </DialogTitle>

      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.75, overflow: 'hidden' }}>
        {selectedMeasure && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: '8px 12px', borderRadius: 1, bgcolor: 'grey.200' }}>
            <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary', flexShrink: 0 }}>Current:</Typography>
            <Typography sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.primary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {selectedMeasure.title || selectedMeasure.name || selectedMeasure.id}
            </Typography>
          </Box>
        )}

        <TextField fullWidth placeholder="Search measures..." size="small" value={search} onChange={(e) => setSearch(e.target.value)} autoFocus
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchOutlined /></InputAdornment> }}
        />

        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75 }}>
          {CATEGORIES.filter((cat) => categoryCounts[cat.key] > 0).map((cat) => (
            <Chip key={cat.key} label={`${cat.label} (${categoryCounts[cat.key]})`} icon={cat.icon}
              variant={activeCategory === cat.key ? 'filled' : 'outlined'}
              color={activeCategory === cat.key ? 'primary' : 'default'}
              onClick={() => handleCategoryToggle(cat.key)}
              sx={{ cursor: 'pointer', userSelect: 'none', transition: 'all 0.15s ease', '&:hover': { opacity: 0.85 } }}
            />
          ))}
        </Box>

        <Box sx={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', maxHeight: '55vh', pr: 0.5 }}>
          {loading ? (
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', p: 6 }}><CircularProgress aria-label="Loading" /></Box>
          ) : grouped.length === 0 ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', p: '48px 24px', color: 'text.disabled', gap: 1 }}>
              <BarChartOutlined sx={{ fontSize: 32 }} />
              <Typography fontWeight={600}>No measures found</Typography>
              <Typography sx={{ fontSize: '0.75rem' }}>Try adjusting your search or category filter.</Typography>
            </Box>
          ) : grouped.map(({ category, items }) => (
            <MeasureCategoryGroup key={category.key} category={category} items={items.map((i) => i.measure)} selectedMeasureId={selectedMeasureId} onSelect={handleSelect} />
          ))}
        </Box>
      </DialogContent>

      <DialogActions><Button onClick={onClose}>Cancel</Button></DialogActions>
    </Dialog>
  );
}

interface MeasureCategoryGroupProps {
  category: MeasureCategory;
  items: Measure[];
  selectedMeasureId?: string;
  onSelect: (measureId: string) => void;
}

function MeasureCategoryGroup({ category, items, selectedMeasureId, onSelect }: MeasureCategoryGroupProps) {
  return (
    <Box sx={{ mb: 2.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5, pb: 0.75, borderBottom: '1px solid', borderBottomColor: 'divider' }}>
        <Box component="span" sx={{ display: 'flex', alignItems: 'center', fontSize: '20px', color: category.color }}>{category.icon}</Box>
        <Typography sx={{ fontSize: '1rem', fontWeight: 600 }}>{category.label}</Typography>
        <Typography sx={{ fontSize: '0.75rem', color: 'text.disabled', ml: 'auto' }}>{items.length} measure{items.length !== 1 ? 's' : ''}</Typography>
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 1.5 }}>
        {items.map((measure) => (
          <MeasureCard key={measure.id} measure={measure} category={category} isSelected={measure.id === selectedMeasureId?.replace('Measure/', '')} onSelect={onSelect} />
        ))}
      </Box>
    </Box>
  );
}

interface MeasureCardProps {
  measure: Measure;
  category: MeasureCategory;
  isSelected: boolean;
  onSelect: (measureId: string) => void;
}

function MeasureCard({ measure, category, isSelected, onSelect }: MeasureCardProps) {
  return (
    <Box onClick={() => onSelect(measure.id || '')} role="button" tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(measure.id || ''); } }}
      sx={[
        { display: 'flex', flexDirection: 'column', p: 2, borderRadius: 1, border: '1px solid', borderColor: 'divider', bgcolor: 'background.paper', cursor: 'pointer', transition: 'all 0.15s ease', position: 'relative', minHeight: '110px', '&:hover': { borderColor: 'primary.main', bgcolor: 'action.hover', boxShadow: 2, transform: 'translateY(-1px)' } },
        isSelected && { borderColor: 'primary.main', bgcolor: 'primary.50', boxShadow: (theme) => `0 0 0 2px ${theme.palette.primary.main}` },
      ]}
    >
      <Box sx={{ position: 'absolute', top: 0, left: 0, right: 0, height: '3px', borderRadius: '4px 4px 0 0', backgroundColor: category.color }} />
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, mb: 1, mt: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36, borderRadius: 1, flexShrink: 0, backgroundColor: `${category.color}18`, color: category.color }}>{category.icon}</Box>
        <Typography sx={{ fontSize: '0.875rem', fontWeight: 600, lineHeight: 1.25, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', wordBreak: 'break-word' }}>
          {measure.title || measure.name || 'Untitled'}
        </Typography>
      </Box>
      {measure.description && measure.description !== measure.title && (
        <Typography sx={{ fontSize: '0.75rem', color: 'text.disabled', lineHeight: 1, mt: 'auto', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', wordBreak: 'break-word' }}>
          {measure.description}
        </Typography>
      )}
      <Typography sx={{ fontSize: '10px', color: 'text.disabled', fontFamily: 'monospace', mt: 0.75, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {measure.id}
      </Typography>
      {isSelected && <Box sx={{ position: 'absolute', top: 8, right: 8 }}><CheckCircleOutlined sx={{ color: 'primary.main' }} /></Box>}
    </Box>
  );
}
