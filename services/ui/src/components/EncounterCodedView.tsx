"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { addCodedLink, fetchEncounter, inferEncounter } from "@/lib/api";
import type { CodedLink, Correction, EncounterSummary, TermSearchResult } from "@/lib/types";
import CodedLinksSection from "./CodedLinksSection";
import CorrectionsLog from "./CorrectionsLog";
import TermSearch from "./TermSearch";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

/** Fixed colors per semantic tag - same tag always same color */
const SEMANTIC_TAG_COLORS: Record<string, string> = {
  situation: "#e0e7ff",
  clinicalfinding: "#d1fae5",
  clinical_finding: "#d1fae5",
  disease: "#fecaca",
  disorder: "#fecaca",
  observableentity: "#fef3c7",
  observable_entity: "#fef3c7",
  observable: "#fef3c7",
  procedure: "#bfdbfe",
  substance: "#ddd6fe",
  medication: "#ddd6fe",
  snomedconcept: "#dbeafe",
  other: "#e2e8f0",
};

function colorForTag(tag: string | null | undefined): string {
  const key = (tag ?? "snomedconcept").toLowerCase().replace(/[^a-z0-9]/g, "");
  return SEMANTIC_TAG_COLORS[key] ?? SEMANTIC_TAG_COLORS.snomedconcept;
}

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
    const merged: { start: number; end: number; tag: string | null; count: number }[] = [];
    for (const s of spans) {
      if (merged.length && s.start <= merged[merged.length - 1].end) {
        merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, s.end);
        merged[merged.length - 1].count += 1;
      } else {
        merged.push({ ...s, count: 1 });
      }
    }
    if (merged.length === 0) return text;
    const parts: React.ReactNode[] = [];
    let i = 0;
    for (const { start, end, tag, count } of merged) {
      if (i < start) parts.push(text.slice(i, start));
      const bg = colorForTag(tag);
      parts.push(
        <Box
          component="mark"
          key={`${start}-${end}`}
          sx={{ background: bg, borderRadius: "2px", px: "2px", position: "relative", display: "inline" }}
        >
          {text.slice(start, end)}
          {count > 1 && (
            <Box
              component="span"
              sx={{
                position: "absolute",
                top: -8,
                right: -8,
                bgcolor: "#4f46e5",
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
              {count}
            </Box>
          )}
        </Box>
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
      .catch((e) =>
        setError(
          e instanceof Error ? e.message : "Could not load encounter.",
        ),
      )
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

  function handleTermSelected(result: TermSearchResult, modifiers?: { value?: string; unit?: string; reference_range?: string; interpretation?: string }, context?: { negated?: boolean; uncertain?: boolean; historical?: boolean }) {
    const mods = modifiers && (modifiers.value || modifiers.unit || modifiers.reference_range || modifiers.interpretation)
      ? { value: modifiers.value, unit: modifiers.unit, reference_range: modifiers.reference_range, interpretation: modifiers.interpretation }
      : undefined;
    const ctx = context && (context.negated || context.uncertain || context.historical) ? context : undefined;
    addCodedLink(patientId, encounterId, {
      concept_id: result.snomed_concept_id,
      term: result.term,
      read_code: result.read_code,
      evidence: pendingEvidence || result.term,
      modifiers: mods,
      context: ctx,
    })
      .then(() => {
        setRefreshTrigger((t) => t + 1);
        setCorrections((prev) => [
          { type: "add", text: result.term, detail: `Added SNOMED ${result.snomed_concept_id}`, time: new Date().toISOString() },
          ...prev,
        ]);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Could not add coded link."),
      )
      .finally(() => {
        setShowTermSearch(false);
        setTermSearchQuery("");
        setPendingEvidence("");
      });
  }

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 5 }}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  if (!encounter) return null;

  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "1fr 340px", height: "100vh", overflow: "hidden" }}>
      {/* Left column */}
      <Box sx={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Header */}
        <Paper
          square
          elevation={0}
          sx={{ px: 3, py: 2, borderBottom: 1, borderColor: "divider" }}
        >
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
              <Typography variant="h6" sx={{ fontFamily: "var(--font-heading)", fontWeight: 700 }}>
                Encounter: {encounterId.slice(0, 8)}…
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Patient {patientId} · {encounter.date || "no date"} · {encounter.coded_count ?? 0} coded
              </Typography>
            </Box>

            <Stack alignItems="flex-end" spacing={0.5}>
              <Stack direction="row" spacing={1}>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={handleRunInference}
                  disabled={inferring}
                  sx={{ textTransform: "none", fontWeight: 600 }}
                  color="success"
                >
                  {inferring ? "Running…" : "Run inference"}
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => {
                    setTermSearchQuery(selection?.text ?? "");
                    setPendingEvidence(selection?.text ?? "");
                    setShowTermSearch(true);
                    setSelection(null);
                  }}
                  sx={{ textTransform: "none", fontWeight: 600 }}
                >
                  {selection
                    ? `Code "${selection.text.slice(0, 20)}${selection.text.length > 20 ? "…" : ""}"`
                    : "+ Add code"}
                </Button>
              </Stack>
              {inferResult && (
                <Typography variant="caption" color="text.secondary">
                  {inferResult}
                </Typography>
              )}
            </Stack>
          </Stack>
        </Paper>

        {/* Text area */}
        <Box
          sx={{ flex: 1, overflowY: "auto", p: 3, bgcolor: "grey.50" }}
          onMouseUp={handleMouseUp}
          onClick={(e) => { if (e.target === e.currentTarget) setSelection(null); }}
        >
          <Paper
            ref={textRef}
            elevation={0}
            sx={{
              p: 3,
              fontSize: 15,
              lineHeight: 1.8,
              fontFamily: "var(--font-body)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              userSelect: "text",
              border: 1,
              borderColor: "divider",
              borderRadius: 3,
            }}
          >
            {highlightedText || "(No text)"}
          </Paper>

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
                Code selection
              </Button>
            </Box>
          )}
        </Box>
      </Box>

      {/* Right sidebar */}
      <Paper
        square
        elevation={0}
        sx={{
          borderLeft: 1,
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <CodedLinksSection
          patientId={patientId}
          encounterId={encounterId}
          onCorrection={(c) => setCorrections((prev) => [c, ...prev])}
          refreshTrigger={refreshTrigger}
          onLinksChange={setCodedLinks}
        />
        <Divider />
        <Box sx={{ flexShrink: 0, display: "flex", flexDirection: "column", minHeight: 0 }}>
          <Typography
            variant="subtitle2"
            sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: "divider", color: "text.primary" }}
          >
            Corrections ({corrections.length})
          </Typography>
          <CorrectionsLog corrections={corrections} />
        </Box>
      </Paper>

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
    </Box>
  );
}
