/**
 * Encounter text reader with coded-term highlights.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { color } from "@leo/design-system";
import type { EncounterDetail } from "@/lib/patientEprApi";
import { fetchEprEncounterDetail } from "@/lib/patientEprApi";
import { encounterTypeLabel } from "./clinicalLabels";

const TYPE_TINT: Record<string, string> = {
  "GP Consultation": color.brand.primaryHover,
  "GP referral": color.brand.primaryHover,
  Diagnosis: color.status.danger,
  Symptoms: color.status.warning,
  Outpatient: color.status.success,
  Inpatient: color.status.danger,
  "A&E": color.status.warning,
  "Clinical note": color.status.neutral,
};

export function encounterTypeTint(label: string): string {
  return TYPE_TINT[label] ?? color.status.neutral;
}

export function formatEncounterDate(iso: string | null): string {
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

const ASSERTION_TINT: Record<string, { bg: string; fg: string }> = {
  present: { bg: color.surface.alt, fg: color.status.success },
  negated: { bg: color.surface.alt, fg: color.status.danger },
  suspected: { bg: color.surface.alt, fg: color.status.warning },
  historical: { bg: color.surface.alt, fg: color.status.neutral },
};

function assertionTint(assertion: string | null) {
  const key = (assertion ?? "present").toLowerCase();
  return ASSERTION_TINT[key] ?? ASSERTION_TINT.present;
}

function highlightTerms(
  text: string,
  terms: EncounterDetail["coded_terms"],
): React.ReactNode {
  if (!terms.length) return text;
  const displays = terms.map((t) => t.display).filter(Boolean) as string[];
  if (!displays.length) return text;
  const pattern = displays
    .sort((a, b) => b.length - a.length)
    .map((d) => d.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  const parts = text.split(new RegExp(`(${pattern})`, "gi"));
  return parts.map((part, i) => {
    const term = terms.find((t) => t.display?.toLowerCase() === part.toLowerCase());
    if (!term) return part;
    const tip = [
      `${term.system ?? "SNOMED"}: ${term.code_id ?? ""}`,
      term.assertion ? `Assertion: ${term.assertion}` : null,
      term.confidence != null
        ? `Confidence: ${Math.round(term.confidence * 100)}%`
        : null,
    ]
      .filter(Boolean)
      .join(" | ");
    return (
      <Tooltip key={i} title={tip} arrow>
        <mark
          style={{
            background: color.surface.alt,
            color: color.brand.primaryHover,
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

function ViewerHeader({ detail }: { detail: EncounterDetail }) {
  const label = encounterTypeLabel(detail.encounter_id, detail.encounter_type);
  const tint = encounterTypeTint(label);
  const dateLine = [
    formatEncounterDate(detail.encounter_date),
    detail.specialty,
  ]
    .filter(Boolean)
    .join(" -- ");
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
      <Chip
        label={label}
        size="small"
        sx={{ bgcolor: `${tint}18`, color: tint, height: 24 }}
      />
      <Typography variant="caption" sx={{ color: color.text.caption }}>
        {dateLine}
      </Typography>
    </Stack>
  );
}

function CodedTermRow({
  term,
}: {
  term: EncounterDetail["coded_terms"][number];
}) {
  const tint = assertionTint(term.assertion);
  const tip = [
    term.code_id ? `${term.system}: ${term.code_id}` : null,
    term.confidence != null
      ? `Confidence: ${Math.round(term.confidence * 100)}%`
      : null,
    term.value != null
      ? `Value: ${term.value}${term.unit ? " " + term.unit : ""}`
      : null,
  ]
    .filter(Boolean)
    .join(" | ");
  return (
    <Tooltip title={tip || undefined} arrow placement="top">
      <Stack direction="row" spacing={0.75} alignItems="center" component="span">
        <Chip
          label={term.display ?? term.code_id}
          size="small"
          sx={{
            bgcolor: tint.bg,
            color: tint.fg,
            fontSize: 12,
            fontWeight: 500,
            height: 24,
          }}
        />
        {term.assertion && term.assertion !== "present" && (
          <Chip
            label={term.assertion}
            size="small"
            sx={{
              height: 24,
              fontSize: 11,
              bgcolor: tint.bg,
              color: tint.fg,
            }}
          />
        )}
        {term.confidence != null && (
          <Typography variant="caption" sx={{ color: color.text.caption }}>
            {Math.round(term.confidence * 100)}%
          </Typography>
        )}
      </Stack>
    </Tooltip>
  );
}

function SbarHint() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Box
        component="button"
        type="button"
        onClick={() => setOpen((v) => !v)}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          border: "none",
          background: "none",
          cursor: "pointer",
          p: 0,
          color: color.brand.primaryHover,
          fontWeight: 600,
          fontSize: 13,
        }}
      >
        {open ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
        SBAR summary
        <Chip label="auto-generated" size="small" sx={{ height: 24, fontSize: 11 }} />
      </Box>
      <Collapse in={open}>
        <Alert severity="info" sx={{ mt: 1, fontSize: 13 }}>
          SBAR for this encounter is available in the Documents tab when linked
          to a referral.
        </Alert>
      </Collapse>
    </>
  );
}

export function EncounterViewer({
  patientId,
  encounterId,
}: {
  patientId: string;
  encounterId: string;
}) {
  const [detail, setDetail] = useState<EncounterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchEprEncounterDetail(patientId, encounterId)
      .then(setDetail)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load encounter."),
      )
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

  return (
    <Box sx={{ p: 2, height: "100%", overflowY: "auto" }}>
      <ViewerHeader detail={detail} />
      <Divider sx={{ mb: 2 }} />
      <Typography
        variant="body2"
        sx={{ lineHeight: 1.8, whiteSpace: "pre-wrap", wordBreak: "break-word" }}
      >
        {highlightTerms(
          detail.full_text || "No clinical text available.",
          detail.coded_terms,
        )}
      </Typography>
      {detail.coded_terms.length > 0 && (
        <>
          <Divider sx={{ my: 2 }} />
          <Typography
            variant="caption"
            fontWeight={700}
            sx={{ mb: 1.25, display: "block", color: color.text.caption }}
          >
            Coded terms ({detail.coded_terms.length})
          </Typography>
          <Stack spacing={1.25}>
            {detail.coded_terms.map((term, i) => (
              <CodedTermRow key={`${term.code_id ?? "term"}-${i}`} term={term} />
            ))}
          </Stack>
        </>
      )}
      <Divider sx={{ my: 2 }} />
      <SbarHint />
    </Box>
  );
}
