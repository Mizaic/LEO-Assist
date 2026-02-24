"use client";

import { useMemo, useEffect, useRef, useState } from "react";
import { searchTerms } from "@/lib/api";
import type { TermSearchResult, Correction } from "@/lib/types";

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

interface Props {
  onSelect: (result: TermSearchResult, modifiers?: { value?: string; unit?: string; reference_range?: string; interpretation?: string }) => void;
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
  const inputRef = useRef<HTMLInputElement>(null);
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
    inputRef.current?.focus();
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

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

  function handleChange(value: string) {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (value.trim().length < 2) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        setResults(await searchTerms(value));
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.3)",
        display: "flex",
        alignItems: "start",
        justifyContent: "center",
        paddingTop: 100,
        zIndex: 2000,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          borderRadius: 14,
          width: 560,
          maxHeight: "70vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
          animation: "cardIn 0.2s ease",
        }}
      >
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #e2e8f0" }}>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => handleChange(e.target.value)}
            placeholder="Search SNOMED terms…"
            style={{
              width: "100%",
              border: "none",
              outline: "none",
              fontSize: 16,
              fontFamily: "var(--font-body)",
            }}
          />
          {tags.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
              {tags.map((tag) => {
                const isSelected = selectedTags.has(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => toggleTag(tag)}
                    style={{
                      padding: "4px 10px",
                      borderRadius: 16,
                      border: `1px solid ${isSelected ? "#4f46e5" : "#e2e8f0"}`,
                      background: isSelected ? "#eef2ff" : "#fff",
                      color: isSelected ? "#4f46e5" : "#64748b",
                      fontSize: 12,
                      fontWeight: isSelected ? 600 : 500,
                      cursor: "pointer",
                    }}
                  >
                    {tag}
                  </button>
                );
              })}
              {selectedTags.size > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedTags(new Set())}
                  style={{
                    padding: "4px 10px",
                    borderRadius: 16,
                    border: "1px solid #e2e8f0",
                    background: "#fff",
                    color: "#64748b",
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  Clear
                </button>
              )}
            </div>
          )}
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          {loading && <p style={{ padding: 16, color: "#64748b", fontSize: 14 }}>Searching…</p>}
          {!loading && results.length === 0 && query.length >= 2 && (
            <p style={{ padding: 16, color: "#94a3b8", fontSize: 14 }}>No results</p>
          )}
          {!loading && results.length > 0 && filteredResults.length === 0 && (
            <p style={{ padding: 16, color: "#94a3b8", fontSize: 14 }}>
              No results for selected tags. Clear filters or choose different tags.
            </p>
          )}
          {filteredResults.map((r, i) => (
            <button
              key={`${r.snomed_concept_id}-${i}`}
              onClick={() => {
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
              }}
              style={{
                display: "block",
                width: "100%",
                padding: "12px 20px",
                textAlign: "left",
                border: "none",
                borderBottom: "1px solid #f1f5f9",
                background: selectedResult?.snomed_concept_id === r.snomed_concept_id ? "#eef2ff" : "transparent",
                cursor: "pointer",
                transition: "background 0.1s",
              }}
              onMouseEnter={(e) => {
                if (selectedResult?.snomed_concept_id !== r.snomed_concept_id) e.currentTarget.style.background = "#f8fafc";
              }}
              onMouseLeave={(e) => {
                if (selectedResult?.snomed_concept_id !== r.snomed_concept_id) e.currentTarget.style.background = "transparent";
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 500, color: "#0f172a" }}>{r.term}</div>
              <div style={{ fontSize: 12, color: "#64748b", fontFamily: "var(--font-mono)", marginTop: 2 }}>
                <span style={{ marginRight: 8, color: "#6366f1", fontWeight: 500 }}>
                  {parseSemanticTag(r.term, r.semantic_tag ?? null)}
                </span>
                SNOMED: {r.snomed_concept_id}
                {r.read_code && <span> · Read: {r.read_code}</span>}
                {r.icd10 && <span> · ICD-10: {r.icd10}</span>}
                <span> · Score: {Math.round(r.score * 100)}%</span>
              </div>
            </button>
          ))}
        </div>
        {captureValueUnit && selectedResult && (
          <div
            style={{
              padding: "16px 20px",
              borderTop: "1px solid #e2e8f0",
              background: "#f8fafc",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600, color: "#334155" }}>
              Add: {selectedResult.term}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                  Value:
                  <input
                    type="text"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    placeholder="e.g. 91 or &lt; 0.2"
                    style={{
                      width: 90,
                      padding: "6px 10px",
                      border: "1px solid #e2e8f0",
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                  Unit:
                  <input
                    type="text"
                    value={unit}
                    onChange={(e) => setUnit(e.target.value)}
                    placeholder="e.g. fL"
                    style={{
                      width: 100,
                      padding: "6px 10px",
                      border: "1px solid #e2e8f0",
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                  Ref range:
                  <input
                    type="text"
                    value={referenceRange}
                    onChange={(e) => setReferenceRange(e.target.value)}
                    placeholder="e.g. 80 - 99"
                    style={{
                      width: 110,
                      padding: "6px 10px",
                      border: "1px solid #e2e8f0",
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
                  Interpretation:
                  <input
                    type="text"
                    value={interpretation}
                    onChange={(e) => setInterpretation(e.target.value)}
                    placeholder="normal / low / high"
                    style={{
                      width: 100,
                      padding: "6px 10px",
                      border: "1px solid #e2e8f0",
                      borderRadius: 6,
                      fontSize: 13,
                    }}
                  />
                </label>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                onClick={() => {
                  const mods: { value?: string; unit?: string; reference_range?: string; interpretation?: string } = {};
                  if (value.trim()) mods.value = value.trim();
                  if (unit.trim()) mods.unit = unit.trim();
                  if (referenceRange.trim()) mods.reference_range = referenceRange.trim();
                  if (interpretation.trim()) mods.interpretation = interpretation.trim();
                  onSelect(selectedResult, Object.keys(mods).length ? mods : undefined);
                  onClose();
                }}
                style={{
                  padding: "8px 16px",
                  background: "#4f46e5",
                  color: "#fff",
                  border: "none",
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {confirmLabel}
              </button>
              <button
                type="button"
                onClick={() => setSelectedResult(null)}
                style={{
                  padding: "8px 16px",
                  background: "#fff",
                  color: "#64748b",
                  border: "1px solid #e2e8f0",
                  borderRadius: 8,
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
