'use client';

import Box from '@mui/material/Box';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import type {
  TextElement,
  HeadingElement,
  BulletListElement,
  ChecklistElement,
  ChecklistItem,
} from '@/lib/types/layout';

/* ── Helpers ──────────────────────────────────────────────────────────────── */

export function parseChecklistLines(lines: string[]): ChecklistItem[] {
  return lines.map((raw, index) => {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const isChecked = trimmed.toLowerCase().startsWith('[x]') || trimmed.toLowerCase().startsWith('[✓]');
    const text = trimmed.replace(/^\[(x| )\]\s*/i, '');
    return { id: `check-${Date.now()}-${index}`, text: text || trimmed, checked: isChecked } as ChecklistItem;
  }).filter((item): item is ChecklistItem => !!item);
}

/* ── TextSettings ────────────────────────────────────────────────────────── */

export function TextSettings({ element, onUpdate }: {
  element: TextElement;
  onUpdate: (updates: Partial<TextElement>) => void;
}): React.ReactNode {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Placeholder" value={element.placeholder || ''}
        onChange={(e) => onUpdate({ placeholder: e.target.value })} placeholder="Text shown when empty" />
    </Box>
  );
}

/* ── HeadingSettings ─────────────────────────────────────────────────────── */

export function HeadingSettings({ element, onUpdate }: {
  element: HeadingElement;
  onUpdate: (updates: Partial<HeadingElement>) => void;
}): React.ReactNode {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField select size="small" label="Level" value={element.type}
        onChange={(e) => onUpdate({ type: e.target.value as HeadingElement['type'] })}>
        <MenuItem value="heading1">Heading 1</MenuItem>
        <MenuItem value="heading2">Heading 2</MenuItem>
        <MenuItem value="heading3">Heading 3</MenuItem>
        <MenuItem value="subtitle">Subtitle</MenuItem>
      </TextField>
      <TextField size="small" label="Text" value={element.text || ''}
        onChange={(e) => onUpdate({ text: e.target.value })} placeholder="Heading text" />
    </Box>
  );
}

/* ── BulletListSettings ──────────────────────────────────────────────────── */

export function BulletListSettings({ element, onUpdate }: {
  element: BulletListElement;
  onUpdate: (updates: Partial<BulletListElement>) => void;
}): React.ReactNode {
  const value = (element.items || []).join('\n');
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Items (one per line)" multiline rows={6} value={value}
        onChange={(e) => onUpdate({ items: e.target.value.split('\n').filter((line) => line.trim().length > 0) })} />
    </Box>
  );
}

/* ── ChecklistSettings ───────────────────────────────────────────────────── */

export function ChecklistSettings({ element, onUpdate }: {
  element: ChecklistElement;
  onUpdate: (updates: Partial<ChecklistElement>) => void;
}): React.ReactNode {
  const value = (element.items || []).map((item) => `${item.checked ? '[x]' : '[ ]'} ${item.text}`).join('\n');
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <TextField size="small" label="Items (prefix with [x] for checked)" multiline rows={6} value={value}
        onChange={(e) => onUpdate({ items: parseChecklistLines(e.target.value.split('\n')) })} />
    </Box>
  );
}
