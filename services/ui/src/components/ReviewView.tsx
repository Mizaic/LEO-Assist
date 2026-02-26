"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import AddIcon from "@mui/icons-material/Add";
import ReplayIcon from "@mui/icons-material/Replay";
import { addCodedLink, fetchTaskDetail, fetchTasks, submitDecision } from "@/lib/api";
import { usePipeline } from "@/context/PipelineContext";
import ConfirmDialog from "./ConfirmDialog";
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
  const [selection, setSelection] = useState<{ text: string; rect: DOMRect } | null>(null);
  const [codeSearchOpen, setCodeSearchOpen] = useState(false);
  const [codeSearchQuery, setCodeSearchQuery] = useState("");
  const [pendingEvidence, setPendingEvidence] = useState("");
  const [pendingSpan, setPendingSpan] = useState<{ start: number; end: number } | null>(null);
  const [refreshCodedLinks, setRefreshCodedLinks] = useState(0);
  const [confirmRerun, setConfirmRerun] = useState(false);
  const router = useRouter();
  const pipeline = usePipeline();
  const prevRunning = useRef(pipeline.running);

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

  useEffect(() => {
    if (prevRunning.current && !pipeline.running && !pipeline.error) {
      router.push(`/patients/${patientId}`);
    }
    prevRunning.current = pipeline.running;
  }, [pipeline.running, pipeline.error, patientId, router]);

  function handleResetRerun() {
    if (!localCandidate) return;
    setConfirmRerun(false);
    pipeline.start({
      patientIds: [patientId],
      encounterId: localCandidate.encounter_id,
    });
  }

  const allTerms = useMemo(() => {
    if (!localCandidate) return [];
    return localCandidate.sentences.flatMap((s) => s.terms);
  }, [localCandidate]);

  const selectedTerm = useMemo(
    () => allTerms.find((t) => t.term_id === selectedTermId) ?? null,
    [allTerms, selectedTermId],
  );

  const selectedTermGroup = useMemo(() => {
    if (!selectedTerm) return [];
    const sorted = [...allTerms].sort((a, b) => a.span_start - b.span_start);
    const groups: EncounterTerm[][] = [];
    for (const t of sorted) {
      const last = groups[groups.length - 1];
      if (last) {
        const lastEnd = Math.max(...last.map((g) => g.span_end));
        if (t.span_start < lastEnd) { last.push(t); continue; }
      }
      groups.push([t]);
    }
    return groups.find((g) => g.some((t) => t.term_id === selectedTermId)) ?? [];
  }, [allTerms, selectedTerm, selectedTermId]);

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
    const selText = selection?.text ?? "";
    setCodeSearchQuery(selText);
    setPendingEvidence(selText);
    if (selText && localCandidate) {
      const full = localCandidate.deidentified_text;
      const idx = full.indexOf(selText);
      if (idx >= 0) {
        setPendingSpan({ start: idx, end: idx + selText.length });
      } else {
        const idxLower = full.toLowerCase().indexOf(selText.toLowerCase());
        setPendingSpan(idxLower >= 0 ? { start: idxLower, end: idxLower + selText.length } : null);
      }
    } else {
      setPendingSpan(null);
    }
    setCodeSearchOpen(true);
    setSelection(null);
  }

  function handleCodeTermSelected(result: TermSearchResult, modifiers?: { value?: string; unit?: string; reference_range?: string; interpretation?: string }, context?: { negated?: boolean; uncertain?: boolean; historical?: boolean }) {
    if (!localCandidate) return;
    const mods = modifiers && (modifiers.value || modifiers.unit || modifiers.reference_range || modifiers.interpretation)
      ? { value: modifiers.value, unit: modifiers.unit, reference_range: modifiers.reference_range, interpretation: modifiers.interpretation }
      : undefined;
    const ctx = context && (context.negated || context.uncertain || context.historical) ? context : undefined;

    if (pendingSpan) {
      const newTerm: EncounterTerm = {
        term_id: `t_code_${Date.now()}`,
        text: pendingEvidence,
        span_start: pendingSpan.start,
        span_end: pendingSpan.end,
        context: {
          negated: context?.negated ?? false,
          uncertain: context?.uncertain ?? false,
          historical: context?.historical ?? false,
          subject: "patient",
          temporality: "present",
        },
        coding: {
          snomed_concept_id: result.snomed_concept_id,
          snomed_term: result.term,
          read_code: result.read_code,
          score: result.score ?? 0.95,
          source: "manual_code_selection",
        },
        evidence_text: pendingEvidence,
        extraction_method: "manual_code_selection",
        extraction_confidence: 0.95,
      };
      const sentences = localCandidate.sentences.map((s) => {
        if (pendingSpan.start >= s.start && pendingSpan.start < s.end) {
          return { ...s, terms: [...s.terms, newTerm] };
        }
        return s;
      });
      const added = sentences.some((s) => s.terms.includes(newTerm));
      if (!added && sentences.length > 0) {
        sentences[sentences.length - 1] = {
          ...sentences[sentences.length - 1],
          terms: [...sentences[sentences.length - 1].terms, newTerm],
        };
      }
      setLocalCandidate({ ...localCandidate, sentences });
    }

    addCodedLink(patientId, localCandidate.encounter_id, {
      concept_id: result.snomed_concept_id,
      term: result.term,
      read_code: result.read_code,
      evidence: pendingEvidence || result.term,
      modifiers: mods,
      context: ctx,
    })
      .then(() => {
        setRefreshCodedLinks((t) => t + 1);
        addCorrection({
          type: "add",
          text: result.term,
          detail: `Added SNOMED ${result.snomed_concept_id}`,
          time: new Date().toISOString(),
        });
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Could not add clinical code."),
      )
      .finally(() => {
        setCodeSearchOpen(false);
        setCodeSearchQuery("");
        setPendingEvidence("");
        setPendingSpan(null);
      });
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

  async function handleDecision(action: string, goNext = false) {
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

      if (goNext) {
        const pending = await fetchTasks("pending", patientId);
        const next = pending.find((t) => t.task_id !== taskId);
        if (next) {
          router.replace(`/patients/${patientId}/encounters/${next.task_id}`);
          return;
        }
      }
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

      switch (e.key) {
        case "a":
          handleDecision(corrections.length > 0 ? "edit" : "approve", true);
          break;
        case "A":
          handleDecision(corrections.length > 0 ? "edit" : "approve");
          break;
        case "r":
        case "R":
          handleDecision("reject");
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

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error && !detail) {
    return (
      <Box sx={{ p: 5 }}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  if (!detail || !localCandidate) return null;

  const fullText = localCandidate.deidentified_text;
  const spanAdjustTerm = allTerms.find((t) => t.term_id === spanAdjustId);

  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "1fr 340px", height: "100vh", overflow: "hidden" }}>
      {/* Left column */}
      <Paper
        square
        elevation={0}
        sx={{ display: "flex", flexDirection: "column", overflow: "hidden" }}
      >
        {/* Header */}
        <Box sx={{ px: 3, py: 2, borderBottom: 1, borderColor: "divider", bgcolor: "background.paper" }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Box>
              <Button
                variant="text"
                size="small"
                startIcon={<ArrowBackIcon />}
                onClick={() => router.push(`/patients/${patientId}`)}
                sx={{ mb: 0.5, textTransform: "none" }}
              >
                Back to encounters
              </Button>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                Review: {localCandidate.encounter_id}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Patient {patientId} · {localCandidate.date || "no date"} · {allTerms.length} clinical terms
                {(() => {
                  try {
                    const usage = localCandidate.llm_usage_json
                      ? JSON.parse(localCandidate.llm_usage_json)
                      : null;
                    if (!usage) return null;
                    const tokens = usage.total_tokens?.toLocaleString() ?? "?";
                    const cost = typeof usage.cost_usd === "number"
                      ? ` · $${usage.cost_usd.toFixed(4)}`
                      : "";
                    return ` · ${tokens} tokens${cost}`;
                  } catch {
                    return null;
                  }
                })()}
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip label="A Approve" size="small" variant="outlined" />
              <Chip label="R Reject" size="small" variant="outlined" />
              <Chip label="C Correct" size="small" variant="outlined" />
              <Chip label="J/K Navigate" size="small" variant="outlined" />
              <Button
                variant="outlined"
                size="small"
                startIcon={<AddIcon />}
                onClick={() => setShowManualAdd(true)}
                sx={{ textTransform: "none" }}
              >
                Add clinical term
              </Button>
              <Button
                variant="outlined"
                size="small"
                color="warning"
                startIcon={<ReplayIcon />}
                onClick={() => setConfirmRerun(true)}
                disabled={pipeline.running}
                sx={{ textTransform: "none" }}
              >
                {pipeline.running ? "Running…" : "Reset & Re-run"}
              </Button>
            </Stack>
          </Stack>
        </Box>

        {/* Source text with highlights */}
        <Box
          sx={{ flex: 1, overflowY: "auto", p: 3, bgcolor: "grey.50" }}
          onClick={(e) => { if (e.target === e.currentTarget) { closePopover(); setSelection(null); } }}
          onMouseUp={handleMouseUp}
        >
          <Box
            sx={{
              bgcolor: "background.paper",
              borderRadius: 3,
              border: 1,
              borderColor: "divider",
              p: 3,
              fontSize: 15,
              lineHeight: 1.8,
              fontFamily: "var(--font-body)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              userSelect: "text",
            }}
          >
            {renderHighlightedText(fullText, allTerms, selectedTermId, handleEntityClick)}
          </Box>

          {selection && (
            <Box
              sx={{
                position: "fixed",
                top: selection.rect.top - 40,
                left: selection.rect.left,
                zIndex: 1000,
              }}
            >
              <Button
                variant="contained"
                size="small"
                onClick={openCodeWithSelection}
                sx={{
                  textTransform: "none",
                  fontWeight: 600,
                  fontSize: 12,
                  boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
                }}
              >
                Assign code
              </Button>
            </Box>
          )}
        </Box>

        {/* Decision bar */}
        <Divider />
        <Stack
          direction="row"
          spacing={1}
          sx={{ px: 3, py: 1.5, bgcolor: "background.paper", alignItems: "center", flexWrap: "wrap" }}
        >
          <TextField
            size="small"
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setDecisionError(null);
            }}
            placeholder="Reason (required for Reject)"
            sx={{ width: 240 }}
          />
          <Button
            variant="contained"
            color="error"
            startIcon={<CloseIcon />}
            disabled={submitting}
            onClick={() => handleDecision("reject")}
            sx={{ textTransform: "none", fontWeight: 600 }}
          >
            Reject
          </Button>
          <Button
            variant="outlined"
            color="success"
            startIcon={<CheckIcon />}
            disabled={submitting}
            onClick={() => handleDecision(corrections.length > 0 ? "edit" : "approve")}
            sx={{ textTransform: "none", fontWeight: 600 }}
          >
            Approve
          </Button>
          <Button
            variant="contained"
            color="success"
            startIcon={<CheckIcon />}
            disabled={submitting}
            onClick={() => handleDecision(corrections.length > 0 ? "edit" : "approve", true)}
            sx={{ textTransform: "none", fontWeight: 600 }}
          >
            {corrections.length > 0
              ? `Approve & Next (${corrections.length})`
              : "Approve & Next"}
          </Button>
          {decisionError && (
            <Typography variant="caption" color="error">
              {decisionError}
            </Typography>
          )}
          {submitSuccess && (
            <Typography variant="caption" color="success.main" sx={{ fontWeight: 600 }}>
              Decision submitted
            </Typography>
          )}
          {error && (
            <Alert severity="error" sx={{ py: 0, flex: 1 }}>
              {error}
            </Alert>
          )}
        </Stack>
      </Paper>

      {/* Right sidebar */}
      <Paper
        square
        elevation={0}
        sx={{ borderLeft: 1, borderColor: "divider", display: "flex", flexDirection: "column", overflow: "hidden" }}
      >
        <EntitySidebar
          terms={allTerms}
          selectedId={selectedTermId}
          onSelect={(id) => setSelectedTermId(id)}
          onRemove={handleRemoveTerm}
          onCorrection={addCorrection}
        />
        <Divider />
        <CodedLinksSection
          patientId={patientId}
          encounterId={localCandidate.encounter_id}
          onCorrection={addCorrection}
          refreshTrigger={refreshCodedLinks}
        />
        <Divider />
        <Box sx={{ flex: 1, overflow: "auto" }}>
          <Typography
            variant="subtitle2"
            sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: "divider", color: "text.primary" }}
          >
            Corrections ({corrections.length})
          </Typography>
          <CorrectionsLog corrections={corrections} />
        </Box>
      </Paper>

      {/* Popover */}
      {selectedTerm && popoverPos && (
        <EntityCard
          term={selectedTerm}
          group={selectedTermGroup}
          position={popoverPos}
          onClose={closePopover}
          onContextChange={handleContextChange}
          onReassign={handleReassign}
          onAdjustSpan={(id) => { setSpanAdjustId(id); closePopover(); }}
          onRemove={handleRemoveTerm}
          onCorrection={addCorrection}
          onSelectGroupTerm={(id) => setSelectedTermId(id)}
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
      {codeSearchOpen && (
        <TermSearch
          initialQuery={codeSearchQuery}
          initialEvidence={pendingEvidence}
          captureValueUnit
          onSelect={handleCodeTermSelected}
          onClose={() => { setCodeSearchOpen(false); setCodeSearchQuery(""); setPendingEvidence(""); }}
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

      {confirmRerun && (
        <ConfirmDialog
          title="Reset & re-run this encounter?"
          body="This will delete all clinical codes and review data for this encounter, then re-process to generate fresh candidates."
          confirmLabel="Reset & Re-run"
          variant="danger"
          onConfirm={handleResetRerun}
          onCancel={() => setConfirmRerun(false)}
        />
      )}
    </Box>
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

  // Group overlapping/identical spans together
  const groups: EncounterTerm[][] = [];
  for (const term of sorted) {
    if (term.span_start > text.length || term.span_end > text.length) continue;
    const last = groups[groups.length - 1];
    if (last) {
      const lastEnd = Math.max(...last.map((t) => t.span_end));
      if (term.span_start < lastEnd) {
        last.push(term);
        continue;
      }
    }
    groups.push([term]);
  }

  const parts: React.ReactNode[] = [];
  let cursor = 0;

  for (const group of groups) {
    const spanStart = Math.min(...group.map((t) => t.span_start));
    const spanEnd = Math.max(...group.map((t) => t.span_end));

    if (spanStart > cursor) {
      parts.push(<span key={`t-${cursor}`}>{text.slice(cursor, spanStart)}</span>);
    }

    const anySelected = group.some((t) => t.term_id === selectedId);
    const hasContext = group.some(
      (t) => t.context.negated || t.context.uncertain || t.context.historical,
    );
    const bg = anySelected ? "#c7d2fe" : hasContext ? "#fef3c7" : "#dbeafe";
    const border = anySelected ? "2px solid #4f46e5" : "none";
    const primary = group.find((t) => t.term_id === selectedId) ?? group[0];
    const tooltip = group
      .map((t) => `${t.text} — ${t.coding.snomed_concept_id || "unlinked"}`)
      .join("\n");

    parts.push(
      <mark
        key={`g-${spanStart}-${spanEnd}`}
        onClick={(e) => { e.stopPropagation(); onClick(primary, e); }}
        style={{
          background: bg,
          border,
          borderRadius: 4,
          padding: "1px 3px",
          cursor: "pointer",
          transition: "background 0.15s",
          position: "relative",
        }}
        title={tooltip}
      >
        {text.slice(spanStart, spanEnd)}
        {group.length > 1 && (
          <span
            style={{
              position: "absolute",
              top: -8,
              right: -8,
              background: "#4f46e5",
              color: "#fff",
              borderRadius: "50%",
              width: 16,
              height: 16,
              fontSize: 10,
              fontWeight: 700,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              lineHeight: 1,
              pointerEvents: "none",
            }}
          >
            {group.length}
          </span>
        )}
      </mark>,
    );
    cursor = spanEnd;
  }

  if (cursor < text.length) {
    parts.push(<span key="t-end">{text.slice(cursor)}</span>);
  }

  return <>{parts}</>;
}
