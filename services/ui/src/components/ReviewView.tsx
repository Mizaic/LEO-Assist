"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchTaskDetail, submitDecision } from "@/lib/api";
import type {
  Correction,
  EncounterCandidate,
  EncounterTerm,
  ReviewTaskDetail,
  TermContext,
  TermSearchResult,
} from "@/lib/types";
import CodedLinksSection from "./CodedLinksSection";
import EntityCard from "./EntityCard";
import EntitySidebar from "./EntitySidebar";
import TermSearch from "./TermSearch";
import SpanAdjustBanner from "./SpanAdjustBanner";
import ManualEntityBanner from "./ManualEntityBanner";
import CorrectionsLog from "./CorrectionsLog";

interface Props {
  taskId: string;
  patientId: string;
}

export default function ReviewView({ taskId, patientId }: Props) {
  const [detail, setDetail] = useState<ReviewTaskDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTermId, setSelectedTermId] = useState<string | null>(null);
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [showTermSearch, setShowTermSearch] = useState(false);
  const [reassignTargetId, setReassignTargetId] = useState<string | null>(null);
  const [spanAdjustId, setSpanAdjustId] = useState<string | null>(null);
  const [showManualAdd, setShowManualAdd] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [localCandidate, setLocalCandidate] = useState<EncounterCandidate | null>(null);
  const [reason, setReason] = useState("");
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    setLoading(true);
    fetchTaskDetail(taskId)
      .then((d) => {
        setDetail(d);
        setLocalCandidate(d.candidate);
      })
      .catch((e) =>
        setError(
          e instanceof Error
            ? e.message
            : "Could not load review task. It may have been completed. Return to the list.",
        ),
      )
      .finally(() => setLoading(false));
  }, [taskId]);

  const allTerms = useMemo(() => {
    if (!localCandidate) return [];
    return localCandidate.sentences.flatMap((s) => s.terms);
  }, [localCandidate]);

  const selectedTerm = useMemo(
    () => allTerms.find((t) => t.term_id === selectedTermId) ?? null,
    [allTerms, selectedTermId],
  );

  const addCorrection = useCallback((c: Correction) => setCorrections((prev) => [c, ...prev]), []);

  function handleEntityClick(term: EncounterTerm, event: React.MouseEvent) {
    setSelectedTermId(term.term_id);
    setPopoverPos({ top: event.clientY - 10, left: Math.min(event.clientX, window.innerWidth - 380) });
  }

  function closePopover() {
    setSelectedTermId(null);
    setPopoverPos(null);
  }

  function handleContextChange(termId: string, ctx: Partial<TermContext>) {
    if (!localCandidate) return;
    setLocalCandidate({
      ...localCandidate,
      sentences: localCandidate.sentences.map((s) => ({
        ...s,
        terms: s.terms.map((t) =>
          t.term_id === termId ? { ...t, context: { ...t.context, ...ctx } } : t,
        ),
      })),
    });
  }

  function handleRemoveTerm(termId: string) {
    if (!localCandidate) return;
    setLocalCandidate({
      ...localCandidate,
      sentences: localCandidate.sentences.map((s) => ({
        ...s,
        terms: s.terms.filter((t) => t.term_id !== termId),
      })),
    });
    closePopover();
  }

  function handleReassign(termId: string) {
    setReassignTargetId(termId);
    setShowTermSearch(true);
    closePopover();
  }

  function handleTermSelected(result: TermSearchResult) {
    if (!localCandidate || !reassignTargetId) return;
    setLocalCandidate({
      ...localCandidate,
      sentences: localCandidate.sentences.map((s) => ({
        ...s,
        terms: s.terms.map((t) =>
          t.term_id === reassignTargetId
            ? {
                ...t,
                coding: {
                  snomed_concept_id: result.snomed_concept_id,
                  snomed_term: result.term,
                  read_code: result.read_code,
                  score: result.score,
                  source: "manual_reassign",
                },
              }
            : t,
        ),
      })),
    });
    setReassignTargetId(null);
  }

  function handleSpanSave(termId: string, start: number, end: number, newText: string) {
    if (!localCandidate) return;
    setLocalCandidate({
      ...localCandidate,
      sentences: localCandidate.sentences.map((s) => ({
        ...s,
        terms: s.terms.map((t) =>
          t.term_id === termId
            ? { ...t, span_start: start, span_end: end, text: newText }
            : t,
        ),
      })),
    });
    setSpanAdjustId(null);
  }

  function handleManualAdd(text: string, start: number, end: number) {
    if (!localCandidate) return;
    const newTerm: EncounterTerm = {
      term_id: `t_manual_${Date.now()}`,
      text,
      span_start: start,
      span_end: end,
      context: { negated: false, uncertain: false, historical: false, subject: "patient", temporality: "present" },
      coding: { snomed_concept_id: undefined, snomed_term: undefined, read_code: undefined, score: 0, source: "manual" },
      evidence_text: text,
      extraction_method: "manual",
      extraction_confidence: 1.0,
    };
    const sentences = localCandidate.sentences.map((s) => {
      if (start >= s.start && start < s.end) {
        return { ...s, terms: [...s.terms, newTerm] };
      }
      return s;
    });
    setLocalCandidate({ ...localCandidate, sentences });
    setShowManualAdd(false);
  }

  function buildReason(action: string): string {
    if (action === "reject") return reason.trim();
    if (corrections.length > 0) return `${corrections.length} corrections applied`;
    return "Approved as-is";
  }

  async function handleDecision(action: string) {
    if (!detail) return;
    if (action === "reject" && reason.trim().length < 3) {
      setDecisionError("Reason is required for reject (min 3 characters).");
      return;
    }
    setDecisionError(null);
    setSubmitting(true);
    setError(null);
    try {
      await submitDecision(taskId, {
        action,
        reviewer: "current_user",
        reason: buildReason(action),
        edited_candidate: action === "edit" ? localCandidate : undefined,
      });
      setSubmitSuccess(true);
      setTimeout(() => router.push(`/patients/${patientId}`), 800);
    } catch (e: unknown) {
      setError(
        e instanceof Error
          ? e.message
          : "Submit failed. Your corrections are still in place. Try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (showTermSearch || showManualAdd || spanAdjustId) return;
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;

      switch (e.key.toLowerCase()) {
        case "a":
          handleDecision("approve");
          break;
        case "r":
          handleDecision("reject");
          break;
        case "c":
          handleDecision("edit");
          break;
        case "escape":
          closePopover();
          break;
        case "j": {
          const idx = allTerms.findIndex((t) => t.term_id === selectedTermId);
          const next = allTerms[idx + 1] ?? allTerms[0];
          if (next) setSelectedTermId(next.term_id);
          break;
        }
        case "k": {
          const idx = allTerms.findIndex((t) => t.term_id === selectedTermId);
          const prev = allTerms[idx - 1] ?? allTerms[allTerms.length - 1];
          if (prev) setSelectedTermId(prev.term_id);
          break;
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (loading) return <div style={{ padding: 40, color: "#64748b" }}>Loading review…</div>;
  if (error) return <div style={{ padding: 40, color: "#b91c1c" }}>{error}</div>;
  if (!detail || !localCandidate) return null;

  const fullText = localCandidate.deidentified_text;
  const spanAdjustTerm = allTerms.find((t) => t.term_id === spanAdjustId);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", height: "100vh", overflow: "hidden" }}>
      {/* Main area */}
      <div style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Header */}
        <div style={{
          padding: "16px 24px",
          borderBottom: "1px solid #e2e8f0",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#fff",
        }}>
          <div>
            <button
              onClick={() => router.push(`/patients/${patientId}`)}
              style={{ background: "none", border: "none", color: "#4f46e5", cursor: "pointer", fontSize: 13, padding: 0, marginBottom: 4 }}
            >
              ← Back to encounters
            </button>
            <h1 style={{ fontFamily: "var(--font-heading)", fontSize: 20, fontWeight: 700 }}>
              Review: {localCandidate.encounter_id}
            </h1>
            <span style={{ color: "#64748b", fontSize: 13 }}>
              Patient {patientId} · {localCandidate.date || "no date"} · {allTerms.length} entities
            </span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => setShowManualAdd(true)}
              style={{
                padding: "7px 14px",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                background: "#fff",
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              + Add entity
            </button>
          </div>
        </div>

        {/* Source text with highlights */}
        <div style={{ flex: 1, overflowY: "auto", padding: 24, background: "#f8fafc" }} onClick={closePopover}>
          <div style={{
            background: "#fff",
            borderRadius: 12,
            border: "1px solid #e2e8f0",
            padding: 24,
            fontSize: 15,
            lineHeight: 1.8,
            fontFamily: "var(--font-body)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}>
            {renderHighlightedText(fullText, allTerms, selectedTermId, handleEntityClick)}
          </div>
        </div>

        {/* Decision bar */}
        <div style={{
          padding: "12px 24px",
          borderTop: "1px solid #e2e8f0",
          background: "#fff",
          display: "flex",
          flexWrap: "wrap",
          gap: 10,
          alignItems: "center",
        }}>
          <div style={{ flex: 1, minWidth: 200, fontSize: 12, color: "#94a3b8" }}>
            <kbd style={{ background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, fontSize: 11 }}>A</kbd> Approve
            <kbd style={{ background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, fontSize: 11, marginLeft: 10 }}>R</kbd> Reject
            <kbd style={{ background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, fontSize: 11, marginLeft: 10 }}>C</kbd> Correct &amp; approve
            <kbd style={{ background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, fontSize: 11, marginLeft: 10 }}>J/K</kbd> Navigate
          </div>
          <input
            type="text"
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setDecisionError(null);
            }}
            placeholder="Reason (required for Reject)"
            style={{
              padding: "6px 12px",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              fontSize: 13,
              width: 220,
              fontFamily: "var(--font-body)",
            }}
          />
          <button onClick={() => handleDecision("reject")} disabled={submitting}
            style={{ padding: "8px 18px", borderRadius: 8, border: "1px solid #fecaca", background: "#fff", color: "#dc2626", fontWeight: 600, fontSize: 13, cursor: "pointer" }}>
            Reject
          </button>
          <button onClick={() => handleDecision("edit")} disabled={submitting}
            style={{ padding: "8px 18px", borderRadius: 8, border: "1px solid #e2e8f0", background: "#fff", color: "#475569", fontWeight: 600, fontSize: 13, cursor: "pointer" }}>
            Correct &amp; Approve
          </button>
          <button onClick={() => handleDecision("approve")} disabled={submitting}
            style={{ padding: "8px 18px", borderRadius: 8, border: "none", background: "#4f46e5", color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer" }}>
            Approve
          </button>
          {decisionError && (
            <span style={{ color: "#dc2626", fontSize: 12 }}>{decisionError}</span>
          )}
          {submitSuccess && (
            <span style={{ color: "#16a34a", fontSize: 13, fontWeight: 600 }}>
              Decision submitted
            </span>
          )}
        </div>
      </div>

      {/* Right sidebar */}
      <div style={{ borderLeft: "1px solid #e2e8f0", background: "#fff", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <EntitySidebar
          terms={allTerms}
          selectedId={selectedTermId}
          onSelect={(id) => setSelectedTermId(id)}
        />
        <CodedLinksSection
          patientId={patientId}
          encounterId={localCandidate.encounter_id}
          onCorrection={addCorrection}
        />
        <div style={{ borderTop: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "#334155", padding: "12px 16px", borderBottom: "1px solid #e2e8f0" }}>
            Corrections ({corrections.length})
          </h3>
          <CorrectionsLog corrections={corrections} />
        </div>
      </div>

      {/* Popover */}
      {selectedTerm && popoverPos && (
        <EntityCard
          term={selectedTerm}
          position={popoverPos}
          onClose={closePopover}
          onContextChange={handleContextChange}
          onReassign={handleReassign}
          onAdjustSpan={(id) => { setSpanAdjustId(id); closePopover(); }}
          onRemove={handleRemoveTerm}
          onCorrection={addCorrection}
        />
      )}

      {/* Modals/Banners */}
      {showTermSearch && (
        <TermSearch
          onSelect={handleTermSelected}
          onClose={() => { setShowTermSearch(false); setReassignTargetId(null); }}
          onCorrection={addCorrection}
        />
      )}
      {spanAdjustTerm && (
        <SpanAdjustBanner
          term={spanAdjustTerm}
          fullText={fullText}
          onSave={handleSpanSave}
          onCancel={() => setSpanAdjustId(null)}
          onCorrection={addCorrection}
        />
      )}
      {showManualAdd && (
        <ManualEntityBanner
          fullText={fullText}
          onAdd={handleManualAdd}
          onCancel={() => setShowManualAdd(false)}
          onCorrection={addCorrection}
        />
      )}
    </div>
  );
}

function renderHighlightedText(
  text: string,
  terms: EncounterTerm[],
  selectedId: string | null,
  onClick: (term: EncounterTerm, e: React.MouseEvent) => void,
) {
  if (terms.length === 0) return text;

  const sorted = [...terms].sort((a, b) => a.span_start - b.span_start);
  const parts: React.ReactNode[] = [];
  let cursor = 0;

  for (const term of sorted) {
    if (term.span_start > text.length || term.span_end > text.length) continue;
    if (term.span_start < cursor) continue;

    if (term.span_start > cursor) {
      parts.push(<span key={`t-${cursor}`}>{text.slice(cursor, term.span_start)}</span>);
    }

    const isSelected = term.term_id === selectedId;
    const hasContext = term.context.negated || term.context.uncertain || term.context.historical;
    const bg = isSelected ? "#c7d2fe" : hasContext ? "#fef3c7" : "#dbeafe";
    const border = isSelected ? "2px solid #4f46e5" : "none";

    parts.push(
      <mark
        key={term.term_id}
        onClick={(e) => { e.stopPropagation(); onClick(term, e); }}
        style={{
          background: bg,
          border,
          borderRadius: 4,
          padding: "1px 3px",
          cursor: "pointer",
          transition: "background 0.15s",
        }}
        title={`${term.text} — ${term.coding.snomed_concept_id || "unlinked"}`}
      >
        {text.slice(term.span_start, term.span_end)}
      </mark>,
    );
    cursor = term.span_end;
  }

  if (cursor < text.length) {
    parts.push(<span key="t-end">{text.slice(cursor)}</span>);
  }

  return <>{parts}</>;
}
