/**
 * EncounterListPanel -- encounter list with text preview and viewer.
 *
 * Left: scrollable encounter list with date, type badge, text preview,
 *       coded-term count chip.
 * Right: full encounter text with coded terms highlighted, plus linked SBAR.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CodeIcon from "@mui/icons-material/Code";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import type { EncounterRow, EncounterDetail } from "@/lib/patientEprApi";
import {
  fetchEprEncounters,
  fetchEprEncounterDetail,
} from "@/lib/patientEprApi";
import { encounterTypeLabel } from "./clinicalLabels";

const TYPE_COLORS: Record<string, string> = {
  "GP Consultation": "#1E40AF",
  "GP referral": "#1E40AF",
  Diagnosis: "#9D174D",
  Symptoms: "#B45309",
  Outpatient: "#047857",
  Inpatient: "#9D174D",
  "A&E": "#B45309",
  "Clinical note": "#475569",
};

function typeColor(t: string): string {
  return TYPE_COLORS[t] ?? "#475569";
}

function fmt(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

function EncounterListItem({
  enc,
  selected,
  onSelect,
}: {
  enc: EncounterRow;
  selected: boolean;
  onSelect: () => void;
}) {
  const label = encounterTypeLabel(enc.encounter_id, enc.encounter_type);
  const color = typeColor(label);
  return (
    <Box
      component="button"
      onClick={onSelect}
      sx={{
        display: "block",
        width: "100%",
        textAlign: "left",
        border: "none",
        borderBottom: "1px solid #E2E8F0",
        p: "12px 16px",
        bgcolor: selected ? "#EFF6FF" : "transparent",
        cursor: "pointer",
        "&:hover": { bgcolor: selected ? "#EFF6FF" : "#F8FAFC" },
        transition: "background 0.12s",
      }}
      aria-pressed={selected}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
        <Typography variant="caption" color="text.secondary">
          {fmt(enc.encounter_date)}
        </Typography>
        {enc.coded_count > 0 && (
          <Stack direction="row" spacing={0.5} alignItems="center">
            <CodeIcon sx={{ fontSize: 11, color: "#64748B" }} />
            <Typography variant="caption" color="text.secondary">
              {enc.coded_count}
            </Typography>
          </Stack>
        )}
      </Stack>
      <Chip
        label={label}
        size="small"
        sx={{
          my: 0.5,
          height: 18,
          fontSize: 10,
          bgcolor: `${color}18`,
          color,
        }}
      />
      {enc.specialty && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          {enc.specialty}
        </Typography>
      )}
      {enc.text_preview && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            display: "block",
            mt: 0.5,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          &ldquo;{enc.text_preview}&rdquo;
        </Typography>
      )}
    </Box>
  );
}

const ASSERTION_COLORS: Record<string, { bg: string; color: string }> = {
  present: { bg: "#DCFCE7", color: "#15803D" },
  negated: { bg: "#FEE2E2", color: "#B91C1C" },
  suspected: { bg: "#FEF3C7", color: "#92400E" },
  historical: { bg: "#F1F5F9", color: "#475569" },
};

const ENTITY_GROUP: Record<string, string> = {
  disorder: "Conditions",
  disease: "Conditions",
  finding: "Findings",
  situation: "Situations",
  observable: "Observations",
  procedure: "Procedures",
  medication: "Medications",
  concept: "Other",
};

function assertionStyle(a: string | null) {
  const key = (a ?? "present").toLowerCase();
  return ASSERTION_COLORS[key] ?? ASSERTION_COLORS.present;
}

function highlightTerms(text: string, terms: EncounterDetail["coded_terms"]): React.ReactNode {
  if (!terms.length) return text;
  const displays = terms.map((t) => t.display).filter(Boolean) as string[];
  if (!displays.length) return text;
  const pattern = displays
    .sort((a, b) => b.length - a.length)
    .map((d) => d.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  const regex = new RegExp(`(${pattern})`, "gi");
  const parts = text.split(regex);
  return parts.map((part, i) => {
    const term = terms.find((t) => t.display?.toLowerCase() === part.toLowerCase());
    if (!term) return part;
    const tip = [
      `${term.system ?? "SNOMED"}: ${term.code_id ?? ""}`,
      term.assertion ? `Assertion: ${term.assertion}` : null,
      term.confidence != null ? `Confidence: ${Math.round(term.confidence * 100)}%` : null,
      term.evidence ? `evidence: "${term.evidence}"` : null,
      term.evidence_sentence ? `evidence_sentence: "${term.evidence_sentence}"` : null,
    ].filter(Boolean).join(" | ");
    return (
      <Tooltip key={i} title={tip} arrow>
        <mark
          style={{
            background: "#DBEAFE",
            color: "#1E40AF",
            borderRadius: 2,
            padding: "0 2px",
            fontWeight: 500,
            cursor: "help",
          }}
        >
          {part}
        </mark>
      </Tooltip>
    );
  });
}

function EncounterViewer({
  patientId,
  encounterId,
}: {
  patientId: string;
  encounterId: string;
}) {
  const [detail, setDetail] = useState<EncounterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sbarOpen, setSbarOpen] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchEprEncounterDetail(patientId, encounterId)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load encounter."))
      .finally(() => setLoading(false));
  }, [patientId, encounterId]);

  if (loading) {
    return (
      <Stack spacing={1.5} sx={{ p: 2 }}>
        <Skeleton height={24} width={220} />
        <Skeleton height={300} variant="rounded" />
      </Stack>
    );
  }

  if (error || !detail) {
    return (
      <Alert severity="error" sx={{ m: 2 }}>
        {error ?? "Encounter not found."}
      </Alert>
    );
  }

  const label = encounterTypeLabel(detail.encounter_id, detail.encounter_type);

  return (
    <Box sx={{ p: 2, height: "100%", overflowY: "auto" }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <Chip
          label={label}
          size="small"
          sx={{ bgcolor: `${typeColor(label)}18`, color: typeColor(label) }}
        />
        <Typography variant="caption" color="text.secondary">
          {fmt(detail.encounter_date)}
          {detail.specialty ? `  \u00B7  ${detail.specialty}` : ""}
        </Typography>
      </Stack>

      <Divider sx={{ mb: 2 }} />

      <Typography
        variant="body2"
        sx={{ lineHeight: 1.8, whiteSpace: "pre-wrap", wordBreak: "break-word" }}
      >
        {highlightTerms(detail.full_text || "No clinical text available.", detail.coded_terms)}
      </Typography>

      {detail.coded_terms.length > 0 && (
        <>
          <Divider sx={{ my: 2 }} />
          <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ mb: 1.25, display: "block" }}>
            CODED TERMS ({detail.coded_terms.length})
          </Typography>
          {(() => {
            const grouped = detail.coded_terms.reduce<Record<string, typeof detail.coded_terms>>(
              (acc, t) => {
                const g = ENTITY_GROUP[t.system === "SNOMED" ? "concept" : "concept"] ?? "Other";
                // group by assertion first, then type
                const key = ENTITY_GROUP["concept"] ?? "Other";
                if (!acc[key]) acc[key] = [];
                acc[key].push(t);
                return acc;
              },
              {}
            );
            return (
              <Stack spacing={1.25}>
                {detail.coded_terms.map((t, i) => {
                  const style = assertionStyle(t.assertion);
                  const tipLines = [
                    t.code_id ? `${t.system}: ${t.code_id}` : null,
                    t.confidence != null ? `Confidence: ${Math.round(t.confidence * 100)}%` : null,
                    t.evidence ? `evidence: "${t.evidence}"` : null,
                    t.evidence_sentence ? `evidence_sentence: "${t.evidence_sentence}"` : null,
                    t.value != null ? `Value: ${t.value}${t.unit ? " " + t.unit : ""}` : null,
                  ].filter(Boolean).join(" | ");
                  return (
                    <Tooltip key={i} title={tipLines || undefined} arrow placement="top">
                      <Stack direction="row" spacing={0.75} alignItems="center" component="span">
                        <Chip
                          label={t.display ?? t.code_id}
                          size="small"
                          sx={{ bgcolor: style.bg, color: style.color, fontSize: 11, fontWeight: 500 }}
                        />
                        {t.assertion && t.assertion !== "present" && (
                          <Chip
                            label={t.assertion}
                            size="small"
                            sx={{ height: 16, fontSize: 10, bgcolor: style.bg, color: style.color, border: `1px solid ${style.color}40` }}
                          />
                        )}
                        {t.confidence != null && (
                          <Typography variant="caption" color="text.secondary" fontSize={10}>
                            {Math.round(t.confidence * 100)}%
                          </Typography>
                        )}
                      </Stack>
                    </Tooltip>
                  );
                })}
              </Stack>
            );
          })()}
        </>
      )}

      <Divider sx={{ my: 2 }} />

      <Box
        component="button"
        onClick={() => setSbarOpen((v) => !v)}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          border: "none",
          background: "none",
          cursor: "pointer",
          p: 0,
          color: "#1E40AF",
          fontWeight: 600,
          fontSize: 13,
        }}
      >
        {sbarOpen ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
        SBAR summary
        <Chip label="auto-generated" size="small" sx={{ height: 16, fontSize: 9 }} />
      </Box>
      <Collapse in={sbarOpen}>
        <Alert severity="info" sx={{ mt: 1, fontSize: 13 }}>
          SBAR for this encounter is available in the Documents tab when linked to a referral.
        </Alert>
      </Collapse>
    </Box>
  );
}

interface Props {
  patientId: string;
  initialEncounterId?: string;
  scopeEpisodeIds?: string[];
}

export function EncounterListPanel({ patientId, initialEncounterId, scopeEpisodeIds }: Props) {
  const [encounters, setEncounters] = useState<EncounterRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(initialEncounterId ?? null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    setLoading(true);
    fetchEprEncounters(patientId)
      .then((rows) => {
        const filtered = scopeEpisodeIds
          ? rows.filter((r) => !r.episode_id || scopeEpisodeIds.includes(r.episode_id))
          : rows;
        setEncounters(filtered);
        if (!selectedId && filtered.length) setSelectedId(filtered[0].encounter_id);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load encounters."))
      .finally(() => setLoading(false));
  }, [patientId, scopeEpisodeIds]);

  const filtered = search
    ? encounters.filter(
        (e) =>
          e.encounter_type.toLowerCase().includes(search.toLowerCase()) ||
          (e.text_preview ?? "").toLowerCase().includes(search.toLowerCase()) ||
          (e.specialty ?? "").toLowerCase().includes(search.toLowerCase())
      )
    : encounters;

  if (loading) {
    return (
      <Stack spacing={1.5}>
        {[1, 2, 3].map((i) => <Skeleton key={i} variant="rounded" height={80} />)}
      </Stack>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  return (
    <Box sx={{ display: "flex", gap: 0, border: "1px solid #E2E8F0", borderRadius: "10px", overflow: "hidden", height: "calc(100vh - 260px)", minHeight: 400 }}>
      {/* List panel */}
      <Box sx={{ width: 280, flexShrink: 0, borderRight: "1px solid #E2E8F0", display: "flex", flexDirection: "column" }}>
        <Box sx={{ p: 1.5, borderBottom: "1px solid #E2E8F0" }}>
          <TextField
            size="small"
            placeholder="Search encounters..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            fullWidth
            InputProps={{ startAdornment: <MedicalServicesOutlinedIcon sx={{ mr: 0.5, fontSize: 16, color: "#94A3B8" }} /> }}
          />
        </Box>
        <Box sx={{ flex: 1, overflowY: "auto" }}>
          {filtered.length === 0 ? (
            <Alert severity="info" sx={{ m: 1.5, fontSize: 12 }}>No encounters match.</Alert>
          ) : (
            filtered.map((enc) => (
              <EncounterListItem
                key={enc.encounter_id}
                enc={enc}
                selected={selectedId === enc.encounter_id}
                onSelect={() => setSelectedId(enc.encounter_id)}
              />
            ))
          )}
        </Box>
      </Box>

      {/* Viewer panel */}
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {selectedId ? (
          <EncounterViewer patientId={patientId} encounterId={selectedId} />
        ) : (
          <Box sx={{ p: 3, color: "#94A3B8", textAlign: "center", mt: 4 }}>
            <MedicalServicesOutlinedIcon sx={{ fontSize: 40, mb: 1 }} />
            <Typography variant="body2">Select an encounter to view the full record.</Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}
