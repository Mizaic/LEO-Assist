"use client";

import { useMemo, useEffect, useRef, useState } from "react";
import { searchTerms } from "@/lib/api";
import type { TermSearchResult, Correction } from "@/lib/types";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";
import SearchIcon from "@mui/icons-material/Search";

function parseSemanticTag(term: string, semanticTag: string | null): string {
  if (semanticTag) return semanticTag;
  const match = term.match(/\(([^)]+)\)\s*$/);
  return match ? match[1].toLowerCase() : "other";
}

/** Parse value, unit, reference range, and interpretation from lab-style text.
 * e.g. "Lymphocyte count (42M..) 2.24 10^9/L [1-4]", "Mean cell volume (42A..) 91 fL [80 - 99]",
 * or "Nucleated red blood cell count (4266.) < 0.2 10^9/L [0 - 0.2]"
 */
function parseLabResult(text: string): {
  value?: string;
  unit?: string;
  reference_range?: string;
  interpretation?: "normal" | "low" | "high";
} {
  const out: ReturnType<typeof parseLabResult> = {};
  const rangeMatch = text.match(/\[([^\]]+)\]/);
  if (rangeMatch) out.reference_range = rangeMatch[1].trim();
  const valueWithOp = text.match(/([<>=])\s*(\d+\.?\d*)\s*([a-zA-Z0-9^/\\%-]+?)(?:\s*\[|\s*$)/);
  const simpleValue = text.match(/(\d+\.?\d*)\s*([a-zA-Z0-9^/\\%-]+?)(?:\s*\[|\s*$)/);
  const m = valueWithOp || simpleValue;
  if (m) {
    out.value = valueWithOp ? `${m[1]} ${m[2]}` : m[1];
    out.unit = (valueWithOp ? m[3] : m[2]).trim() || undefined;
  }
  if (out.reference_range && out.value) {
    const valStr = out.value.replace(/^[<>=]\s*/, "");
    const val = parseFloat(valStr);
    const rangeNums = out.reference_range.match(/(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)/);
    if (rangeNums && !Number.isNaN(val)) {
      const low = parseFloat(rangeNums[1]);
      const high = parseFloat(rangeNums[2]);
      if (!Number.isNaN(low) && !Number.isNaN(high)) {
        if (val < low) out.interpretation = "low";
        else if (val > high) out.interpretation = "high";
        else out.interpretation = "normal";
      }
    }
  }
  return out;
}

export interface TermContext {
  negated?: boolean;
  uncertain?: boolean;
  historical?: boolean;
}

interface Props {
  onSelect: (result: TermSearchResult, modifiers?: { value?: string; unit?: string; reference_range?: string; interpretation?: string }, context?: TermContext) => void;
  onClose: () => void;
  onCorrection: (c: Correction) => void;
  initialQuery?: string;
  /** When true, show value/unit form before confirming (for add flow) */
  captureValueUnit?: boolean;
  /** Selected text to try parsing value/unit from (e.g. "Mean cell volume (42A..) 91 fL [80 - 99]") */
  initialEvidence?: string;
  /** Pre-fill value/unit/range (e.g. when recoding, pass old link modifiers) */
  initialModifiers?: { value?: string | number; unit?: string; reference_range?: string; interpretation?: string };
  /** Label for confirm button when captureValueUnit */
  confirmLabel?: string;
}

export default function TermSearch({
  onSelect,
  onClose,
  onCorrection,
  initialQuery = "",
  captureValueUnit = false,
  initialEvidence = "",
  initialModifiers,
  confirmLabel = "Add code",
}: Props) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<TermSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [selectedResult, setSelectedResult] = useState<TermSearchResult | null>(null);
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("");
  const [referenceRange, setReferenceRange] = useState("");
  const [interpretation, setInterpretation] = useState("");
  const [negated, setNegated] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [historical, setHistorical] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const tags = useMemo(() => {
    const seen = new Set<string>();
    for (const r of results) {
      const tag = parseSemanticTag(r.term, r.semantic_tag ?? null);
      if (tag) seen.add(tag);
    }
    return [...seen].sort();
  }, [results]);

  const filteredResults = useMemo(() => {
    if (selectedTags.size === 0) return results;
    return results.filter((r) => {
      const tag = parseSemanticTag(r.term, r.semantic_tag ?? null);
      return selectedTags.has(tag);
    });
  }, [results, selectedTags]);

  function toggleTag(tag: string) {
    setSelectedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  }

  useEffect(() => {
    if (initialQuery && initialQuery.length >= 2) {
      setQuery(initialQuery);
      setLoading(true);
      searchTerms(initialQuery).then(setResults).catch(() => setResults([])).finally(() => setLoading(false));
    }
  }, [initialQuery]);

  useEffect(() => {
    if (captureValueUnit) {
      if (initialModifiers?.value != null || initialModifiers?.unit || initialModifiers?.reference_range || initialModifiers?.interpretation) {
        setValue(String(initialModifiers.value ?? ""));
        setUnit(String(initialModifiers.unit ?? ""));
        setReferenceRange(String(initialModifiers.reference_range ?? ""));
        setInterpretation(String(initialModifiers.interpretation ?? ""));
      } else if (initialEvidence) {
        const parsed = parseLabResult(initialEvidence);
        if (parsed.value) setValue(parsed.value);
        if (parsed.unit) setUnit(parsed.unit);
        if (parsed.reference_range) setReferenceRange(parsed.reference_range);
        if (parsed.interpretation) setInterpretation(parsed.interpretation);
      }
    }
  }, [captureValueUnit, initialEvidence, initialModifiers]);

  useEffect(() => {
    setSelectedTags(new Set());
  }, [results]);

  function handleChange(val: string) {
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (val.trim().length < 2) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        setResults(await searchTerms(val));
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  }

  function handleResultClick(r: TermSearchResult) {
    if (captureValueUnit) {
      setSelectedResult(r);
      return;
    }
    onSelect(r);
    onCorrection({
      type: "reassign",
      text: r.term,
      detail: `Reassigned to SNOMED ${r.snomed_concept_id}`,
      time: new Date().toISOString(),
    });
    onClose();
  }

  function handleConfirm() {
    if (!selectedResult) return;
    const mods: { value?: string; unit?: string; reference_range?: string; interpretation?: string } = {};
    if (value.trim()) mods.value = value.trim();
    if (unit.trim()) mods.unit = unit.trim();
    if (referenceRange.trim()) mods.reference_range = referenceRange.trim();
    if (interpretation.trim()) mods.interpretation = interpretation.trim();
    const ctx: TermContext = {};
    if (negated) ctx.negated = true;
    if (uncertain) ctx.uncertain = true;
    if (historical) ctx.historical = true;
    onSelect(
      selectedResult,
      Object.keys(mods).length ? mods : undefined,
      Object.keys(ctx).length ? ctx : undefined,
    );
    onClose();
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Search SNOMED terms</DialogTitle>

      <DialogContent dividers sx={{ display: "flex", flexDirection: "column", gap: 1.5, p: 2 }}>
        <TextField
          autoFocus
          fullWidth
          size="small"
          placeholder="Search SNOMED terms…"
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />

        {tags.length > 0 && (
          <Stack direction="row" flexWrap="wrap" gap={0.5}>
            {tags.map((tag) => (
              <Chip
                key={tag}
                label={tag}
                size="small"
                variant={selectedTags.has(tag) ? "filled" : "outlined"}
                color={selectedTags.has(tag) ? "primary" : "default"}
                onClick={() => toggleTag(tag)}
              />
            ))}
            {selectedTags.size > 0 && (
              <Chip
                label="Clear"
                size="small"
                variant="outlined"
                onDelete={() => setSelectedTags(new Set())}
                onClick={() => setSelectedTags(new Set())}
              />
            )}
          </Stack>
        )}

        {captureValueUnit && selectedResult && (
          <Box sx={{ p: 1.5, bgcolor: "action.hover", borderRadius: 1 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              Add: {selectedResult.term}
            </Typography>
            <Stack direction="row" gap={0.75} flexWrap="wrap" sx={{ mb: 1 }}>
              <Chip
                label="Negated"
                size="small"
                variant={negated ? "filled" : "outlined"}
                color={negated ? "error" : "default"}
                onClick={() => setNegated(!negated)}
              />
              <Chip
                label="Uncertain"
                size="small"
                variant={uncertain ? "filled" : "outlined"}
                color={uncertain ? "warning" : "default"}
                onClick={() => setUncertain(!uncertain)}
              />
              <Chip
                label="Historical"
                size="small"
                variant={historical ? "filled" : "outlined"}
                color={historical ? "info" : "default"}
                onClick={() => setHistorical(!historical)}
              />
            </Stack>
            <Stack direction="row" gap={1} flexWrap="wrap">
              <TextField
                size="small"
                label="Value"
                placeholder="e.g. 91 or < 0.2"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                sx={{ width: 120 }}
              />
              <TextField
                size="small"
                label="Unit"
                placeholder="e.g. fL"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                sx={{ width: 120 }}
              />
              <TextField
                size="small"
                label="Ref range"
                placeholder="e.g. 80 - 99"
                value={referenceRange}
                onChange={(e) => setReferenceRange(e.target.value)}
                sx={{ width: 130 }}
              />
              <TextField
                size="small"
                label="Interpretation"
                placeholder="normal / low / high"
                value={interpretation}
                onChange={(e) => setInterpretation(e.target.value)}
                sx={{ width: 140 }}
              />
            </Stack>
          </Box>
        )}

        {loading && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 2, px: 1 }}>
            <CircularProgress size={18} />
            <Typography variant="body2" color="text.secondary">Searching…</Typography>
          </Box>
        )}

        {!loading && results.length === 0 && query.length >= 2 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2, px: 1 }}>
            No results
          </Typography>
        )}

        {!loading && results.length > 0 && filteredResults.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2, px: 1 }}>
            No results for selected tags. Clear filters or choose different tags.
          </Typography>
        )}

        {filteredResults.length > 0 && (
          <List disablePadding sx={{ overflowY: "auto", maxHeight: 340 }}>
            {filteredResults.map((r, i) => (
              <ListItemButton
                key={`${r.snomed_concept_id}-${i}`}
                selected={selectedResult?.snomed_concept_id === r.snomed_concept_id}
                onClick={() => handleResultClick(r)}
                sx={{ alignItems: "flex-start", gap: 1, py: 1 }}
              >
                <ListItemText
                  primary={r.term}
                  secondary={
                    <>
                      SNOMED: {r.snomed_concept_id}
                      {r.read_code && ` · Read: ${r.read_code}`}
                      {r.icd10 && ` · ICD-10: ${r.icd10}`}
                      {` · Score: ${Math.round((r.score ?? 0) * 100)}%`}
                    </>
                  }
                  primaryTypographyProps={{ variant: "body2", fontWeight: 500 }}
                  secondaryTypographyProps={{ variant: "caption", fontFamily: "monospace" }}
                />
                <Chip
                  label={parseSemanticTag(r.term, r.semantic_tag ?? null)}
                  size="small"
                  color="primary"
                  variant="outlined"
                  sx={{ mt: 0.5, flexShrink: 0 }}
                />
              </ListItemButton>
            ))}
          </List>
        )}
      </DialogContent>

      <DialogActions>
        <Button variant="text" onClick={onClose}>Cancel</Button>
        {captureValueUnit && (
          <Button
            variant="contained"
            disabled={!selectedResult}
            onClick={handleConfirm}
          >
            {confirmLabel}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
