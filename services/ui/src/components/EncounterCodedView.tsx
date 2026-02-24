"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { addCodedLink, fetchEncounter, inferEncounter } from "@/lib/api";
import type { CodedLink, Correction, EncounterSummary, TermSearchResult } from "@/lib/types";
import CodedLinksSection from "./CodedLinksSection";

/** Fixed colors per semantic tag - same tag always same color */
const SEMANTIC_TAG_COLORS: Record<string, string> = {
  situation: "#e0e7ff",       // indigo-100
  clinicalfinding: "#d1fae5", // green-100
  clinical_finding: "#d1fae5",
  disease: "#fecaca",         // red-100
  disorder: "#fecaca",
  observableentity: "#fef3c7", // amber-100
  observable_entity: "#fef3c7",
  observable: "#fef3c7",
  procedure: "#bfdbfe",       // blue-100
  substance: "#ddd6fe",      // violet-100
  medication: "#ddd6fe",
  snomedconcept: "#dbeafe",   // blue-100 (default)
  other: "#e2e8f0",          // slate-200
};

function colorForTag(tag: string | null | undefined): string {
  const key = (tag ?? "snomedconcept").toLowerCase().replace(/[^a-z0-9]/g, "");
  return SEMANTIC_TAG_COLORS[key] ?? SEMANTIC_TAG_COLORS.snomedconcept;
}
import CorrectionsLog from "./CorrectionsLog";
import TermSearch from "./TermSearch";

interface Props {
  patientId: string;
  encounterId: string;
}

export default function EncounterCodedView({ patientId, encounterId }: Props) {
  const [encounter, setEncounter] = useState<EncounterSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [selection, setSelection] = useState<{ text: string; rect: DOMRect } | null>(null);
  const [showTermSearch, setShowTermSearch] = useState(false);
  const [termSearchQuery, setTermSearchQuery] = useState("");
  const [pendingEvidence, setPendingEvidence] = useState("");
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [codedLinks, setCodedLinks] = useState<CodedLink[]>([]);
  const [inferring, setInferring] = useState(false);
  const [inferResult, setInferResult] = useState<string | null>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  async function handleRunInference() {
    setInferring(true);
    setInferResult(null);
    try {
      const result = await inferEncounter(patientId, encounterId, true);
      if (result.entities.length > 0) {
        setInferResult(`${result.entities.length} entities inferred`);
      } else {
        setInferResult(result.message ?? "No entities (model not yet built)");
      }
      setRefreshTrigger((t) => t + 1);
    } catch (e) {
      setInferResult(e instanceof Error ? e.message : "Inference failed");
    } finally {
      setInferring(false);
    }
  }

  const highlightedText = useMemo(() => {
    const text = encounter?.text ?? "";
    if (!text || codedLinks.length === 0) return text;
    const spans: { start: number; end: number; tag: string | null }[] = [];
    const textLower = text.toLowerCase();
    for (const link of codedLinks) {
      const tag = link.semantic_tag ?? null;
      const evidence = (link.evidence || "").trim();
      const term = (link.term || "").trim();
      const candidates: string[] = [];
      if (evidence) candidates.push(evidence);
      if (term && term !== evidence) candidates.push(term);
      const termShort = term.split(/\s*[-–—(]\s*/)[0]?.trim();
      if (termShort && termShort.length >= 3 && !candidates.includes(termShort)) candidates.push(termShort);
      let found = false;
      for (const needle of candidates) {
        if (!needle || needle.length < 2) continue;
        let pos = 0;
        while ((pos = text.indexOf(needle, pos)) !== -1) {
          spans.push({ start: pos, end: pos + needle.length, tag });
          pos += needle.length;
          found = true;
        }
        if (found) break;
        pos = 0;
        const needleLower = needle.toLowerCase();
        while ((pos = textLower.indexOf(needleLower, pos)) !== -1) {
          spans.push({ start: pos, end: pos + needle.length, tag });
          pos += needle.length;
          found = true;
        }
        if (found) break;
      }
    }
    spans.sort((a, b) => a.start - b.start);
    const merged: { start: number; end: number; tag: string | null }[] = [];
    for (const s of spans) {
      if (merged.length && s.start <= merged[merged.length - 1].end) {
        merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, s.end);
      } else {
        merged.push({ ...s });
      }
    }
    if (merged.length === 0) return text;
    const parts: React.ReactNode[] = [];
    let i = 0;
    for (const { start, end, tag } of merged) {
      if (i < start) parts.push(text.slice(i, start));
      const bg = colorForTag(tag);
      parts.push(
        <mark key={`${start}-${end}`} style={{ background: bg, borderRadius: 2, padding: "0 2px" }}>
          {text.slice(start, end)}
        </mark>
      );
      i = end;
    }
    if (i < text.length) parts.push(text.slice(i));
    return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : parts;
  }, [encounter?.text, codedLinks]);

  useEffect(() => {
    setLoading(true);
    fetchEncounter(patientId, encounterId)
      .then(setEncounter)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [patientId, encounterId]);

  const handleMouseUp = useCallback(() => {
    const sel = window.getSelection();
    const text = sel?.toString().trim();
    if (!text || text.length < 2) {
      setSelection(null);
      return;
    }
    const range = sel?.getRangeAt(0);
    const rect = range?.getBoundingClientRect();
    if (rect) {
      setSelection({ text, rect });
    }
  }, []);

  function openCodeWithSelection() {
    setTermSearchQuery(selection?.text ?? "");
    setPendingEvidence(selection?.text ?? "");
    setShowTermSearch(true);
    setSelection(null);
  }

  function handleTermSelected(result: TermSearchResult, modifiers?: { value?: string; unit?: string; reference_range?: string; interpretation?: string }) {
    const mods = modifiers && (modifiers.value || modifiers.unit || modifiers.reference_range || modifiers.interpretation)
      ? { value: modifiers.value, unit: modifiers.unit, reference_range: modifiers.reference_range, interpretation: modifiers.interpretation }
      : undefined;
    addCodedLink(patientId, encounterId, {
      concept_id: result.snomed_concept_id,
      term: result.term,
      read_code: result.read_code,
      evidence: pendingEvidence || result.term,
      modifiers: mods,
    })
      .then(() => {
        setRefreshTrigger((t) => t + 1);
        setCorrections((prev) => [
          { type: "add", text: result.term, detail: `Added SNOMED ${result.snomed_concept_id}`, time: new Date().toISOString() },
          ...prev,
        ]);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to add"))
      .finally(() => {
        setShowTermSearch(false);
        setTermSearchQuery("");
        setPendingEvidence("");
      });
  }

  if (loading) return <div style={{ padding: 40, color: "#64748b" }}>Loading encounter…</div>;
  if (error) return <div style={{ padding: 40, color: "#b91c1c" }}>{error}</div>;
  if (!encounter) return null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", height: "100vh", overflow: "hidden" }}>
      <div style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{
          padding: "16px 24px",
          borderBottom: "1px solid #e2e8f0",
          background: "#fff",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}>
          <div>
            <button
              onClick={() => router.push(`/patients/${patientId}`)}
              style={{ background: "none", border: "none", color: "#4f46e5", cursor: "pointer", fontSize: 13, padding: 0, marginBottom: 4 }}
            >
              ← Back to encounters
            </button>
            <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 20, fontWeight: 700 }}>
              Encounter: {encounterId.slice(0, 8)}…
            </h1>
            <span style={{ color: "#64748b", fontSize: 13 }}>
              Patient {patientId} · {encounter.date || "no date"} · {(encounter.coded_count ?? 0)} coded
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={handleRunInference}
                disabled={inferring}
                style={{
                  padding: "8px 16px",
                  border: "1px solid #16a34a",
                  borderRadius: 8,
                  background: "#fff",
                  color: "#16a34a",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: inferring ? "not-allowed" : "pointer",
                }}
              >
                {inferring ? "Running…" : "Run inference"}
              </button>
              <button
                onClick={() => {
                  setTermSearchQuery(selection?.text ?? "");
                  setPendingEvidence(selection?.text ?? "");
                  setShowTermSearch(true);
                  setSelection(null);
                }}
                style={{
                  padding: "8px 16px",
                  border: "1px solid #4f46e5",
                  borderRadius: 8,
                  background: "#fff",
                  color: "#4f46e5",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {selection ? `Code "${selection.text.slice(0, 20)}${selection.text.length > 20 ? "…" : ""}"` : "+ Add code"}
              </button>
            </div>
            {inferResult && (
              <span style={{ fontSize: 12, color: "#64748b" }}>{inferResult}</span>
            )}
          </div>
        </div>

        <div
          style={{ flex: 1, overflowY: "auto", padding: 24, background: "#f8fafc" }}
          onMouseUp={handleMouseUp}
          onClick={(e) => { if (e.target === e.currentTarget) setSelection(null); }}
        >
          <div
            ref={textRef}
            style={{
              background: "#fff",
              borderRadius: 12,
              border: "1px solid #e2e8f0",
              padding: 24,
              fontSize: 15,
              lineHeight: 1.8,
              fontFamily: "var(--font-body)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              userSelect: "text",
            }}
          >
            {highlightedText || "(No text)"}
          </div>

          {selection && (
            <div
              style={{
                position: "fixed",
                top: selection.rect.top - 40,
                left: selection.rect.left,
                zIndex: 1000,
              }}
            >
              <button
                onClick={openCodeWithSelection}
                style={{
                  padding: "6px 12px",
                  border: "none",
                  borderRadius: 6,
                  background: "#4f46e5",
                  color: "#fff",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                  boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
                }}
              >
                Code selection
              </button>
            </div>
          )}
        </div>
      </div>

      <div style={{ borderLeft: "1px solid #e2e8f0", background: "#fff", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <CodedLinksSection
          patientId={patientId}
          encounterId={encounterId}
          onCorrection={(c) => setCorrections((prev) => [c, ...prev])}
          refreshTrigger={refreshTrigger}
          onLinksChange={setCodedLinks}
        />
        <div style={{ borderTop: "1px solid #e2e8f0", flexShrink: 0, display: "flex", flexDirection: "column", minHeight: 0 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "#334155", padding: "12px 16px", borderBottom: "1px solid #e2e8f0" }}>
            Corrections ({corrections.length})
          </h3>
          <CorrectionsLog corrections={corrections} />
        </div>
      </div>

      {showTermSearch && (
        <TermSearch
          initialQuery={termSearchQuery}
          initialEvidence={pendingEvidence}
          captureValueUnit
          onSelect={handleTermSelected}
          onClose={() => { setShowTermSearch(false); setTermSearchQuery(""); setPendingEvidence(""); }}
          onCorrection={(c) => setCorrections((prev) => [c, ...prev])}
        />
      )}
    </div>
  );
}
