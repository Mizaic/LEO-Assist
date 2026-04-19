"use client";

/**
 * EncounterPreviewDialog (DI-LEO-AI-223).
 *
 * Two-stage dialog used on the /care/encounters mission-control
 * surface:
 *
 *   1. Read-only preview (default). Shows the encounter date,
 *      patient id, search-match rationale chips and the full
 *      encounter text already returned by the search response. No
 *      API call is made on open, so the dialog is fast and works
 *      even if the reviewer cannot mount the gold editor (for
 *      example, when the patient is out of org scope).
 *
 *   2. Edit codes (explicit). When the reviewer clicks "Edit
 *      codes", the wrapper calls
 *      `createGoldLabelFromEncounter` (DI-LEO-AI-220) to seed a
 *      draft GoldLabel and then mounts the shared
 *      `GoldLabelEditorDialog` in dual-save mode (DI-LEO-AI-221).
 *      Saves still update :DOCUMENTS coded links on the live
 *      encounter and mirror a de-identified copy onto the linked
 *      GoldLabel.
 *
 * The match-rationale header (date, patient, match chips, "why
 * this matched your search") is shown in both stages, either
 * inline in the preview body or via the editor's `headerChrome`
 * slot.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import {
  GoldLabelEditorDialog,
  createGoldLabelFromEncounter,
  useDualSaveAdapter,
  type DualSaveEncounterContext,
  type GoldLabel,
} from "@/components/gold-editor";
import type { EncounterListItem } from "@/lib/missionControlApi";

interface Props {
  item: EncounterListItem | null;
  onClose: () => void;
  /** Free-text query the reviewer typed into the search box. Used
   *  alongside `item.match_rationale` to highlight hits in the
   *  encounter text. Optional -- omit on surfaces that don't have a
   *  query (e.g. when previewing from a deep link). */
  searchQuery?: string;
  /** Optional callback fired after a successful dual save so the host
   *  can refresh its list (e.g. updated coded counts). */
  onCodingChanged?: () => void;
}

function formatDateLong(dateStr: string | null): string {
  if (!dateStr) return "Unknown date";
  return new Date(dateStr).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function MatchRationaleHeader({
  item,
}: {
  item: EncounterListItem;
}) {
  return (
    <Stack spacing={1} data-testid="encounter-preview-rationale">
      <Typography variant="body2" color="text.secondary">
        {formatDateLong(item.encounter_date)} -- Patient{" "}
        <Box
          component="span"
          sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}
        >
          {item.patient_id}
        </Box>
      </Typography>
      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
        <Chip
          size="small"
          label={`ID: ${item.encounter_id}`}
          variant="outlined"
          sx={{ fontFamily: "monospace", fontSize: "0.72rem" }}
        />
        <Chip
          size="small"
          label={`Match: ${item.match_type}`}
          variant="outlined"
        />
        <Chip
          size="small"
          label={`${item.coded_count} coded term${
            item.coded_count !== 1 ? "s" : ""
          }`}
          color={item.coded_count > 0 ? "success" : "default"}
          variant={item.coded_count > 0 ? "filled" : "outlined"}
        />
      </Stack>
      {!!item.match_rationale?.length && (
        <Box>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 0.5 }}
          >
            Why this matched your search
          </Typography>
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {item.match_rationale.map((term, idx) => (
              <Chip
                key={`preview-${item.encounter_id}-mr-${idx}-${term}`}
                size="small"
                label={term}
                variant="outlined"
              />
            ))}
          </Stack>
        </Box>
      )}
    </Stack>
  );
}

// Tokens shorter than this are skipped so a stray "a" or "in" from
// the user's query does not paint the entire encounter yellow.
const MIN_HIGHLIGHT_LEN = 3;

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function collectHighlightTerms(
  searchQuery: string | undefined,
  rationale: string[] | undefined,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const push = (raw: string) => {
    const t = raw.trim();
    if (t.length < MIN_HIGHLIGHT_LEN) return;
    const key = t.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(t);
  };
  // Split the user's query on whitespace + common punctuation so
  // "breast cancer screening" highlights all three words.
  if (searchQuery) {
    for (const tok of searchQuery.split(/[\s,.;:/()\[\]"']+/)) push(tok);
  }
  if (rationale) for (const tok of rationale) push(tok);
  // Match longer terms first so "cancer screening" wins over "cancer".
  out.sort((a, b) => b.length - a.length);
  return out;
}

function HighlightedText({
  text,
  terms,
}: {
  text: string;
  terms: string[];
}) {
  if (!terms.length) return <>{text}</>;
  const pattern = new RegExp(
    `(${terms.map(escapeRegex).join("|")})`,
    "gi",
  );
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, idx) => {
        if (!part) return null;
        // Even indices are non-matches, odd indices are captured hits
        // (because the pattern is a single capturing group).
        if (idx % 2 === 1) {
          return (
            <Box
              key={`hl-${idx}`}
              component="mark"
              data-testid="encounter-preview-highlight"
              sx={{
                bgcolor: "#fef3c7",
                color: "inherit",
                px: 0.25,
                borderRadius: 0.5,
              }}
            >
              {part}
            </Box>
          );
        }
        return <span key={`hl-${idx}`}>{part}</span>;
      })}
    </>
  );
}

function EncounterTextBlock({
  text,
  terms,
}: {
  text: string | null;
  terms: string[];
}) {
  if (!text || !text.trim()) {
    return (
      <Typography
        variant="body2"
        color="text.secondary"
        data-testid="encounter-preview-empty"
      >
        This encounter has no text recorded.
      </Typography>
    );
  }
  return (
    <Box
      data-testid="encounter-preview-text"
      sx={{
        maxHeight: 360,
        overflowY: "auto",
        p: 1.5,
        borderRadius: 1,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.default",
        whiteSpace: "pre-wrap",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: "0.82rem",
        lineHeight: 1.5,
      }}
    >
      <HighlightedText text={text} terms={terms} />
    </Box>
  );
}

export default function EncounterPreviewDialog({
  item,
  onClose,
  searchQuery,
  onCodingChanged,
}: Props) {
  const highlightTerms = useMemo(
    () => collectHighlightTerms(searchQuery, item?.match_rationale),
    [searchQuery, item?.match_rationale],
  );
  // Edit-mode state: only set once the reviewer clicks "Edit codes".
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [target, setTarget] = useState<GoldLabel | null>(null);
  const [context, setContext] =
    useState<DualSaveEncounterContext | null>(null);

  const reset = useCallback(() => {
    setTarget(null);
    setContext(null);
    setEditError(null);
    setEditLoading(false);
  }, []);

  // Reset edit state whenever the host opens a different encounter
  // or closes the dialog. The preview itself does NOT trigger any
  // API call -- the encounter text is already on `item`.
  useEffect(() => {
    if (!item) reset();
  }, [item, reset]);

  const handleEditCodes = useCallback(() => {
    if (!item) return;
    setEditLoading(true);
    setEditError(null);
    void createGoldLabelFromEncounter({
      patient_id: item.patient_id,
      encounter_id: item.encounter_id,
    })
      .then((seed) => {
        setContext({
          patient_id: item.patient_id,
          encounter_id: item.encounter_id,
          baseline_concept_ids: seed.baseline_concept_ids,
        });
        setTarget(seed.gold_label);
      })
      .catch((err) => {
        setEditError(
          err instanceof Error
            ? err.message
            : "Could not open the codes editor for this encounter.",
        );
      })
      .finally(() => {
        setEditLoading(false);
      });
  }, [item]);

  const dualSaver = useDualSaveAdapter({
    labelId: target?.label_id ?? "",
    context: context ?? {
      patient_id: item?.patient_id ?? "",
      encounter_id: item?.encounter_id ?? "",
      baseline_concept_ids: [],
    },
    onSynced: () => {
      onCodingChanged?.();
    },
  });

  if (!item) return null;

  if (target && context) {
    return (
      <GoldLabelEditorDialog
        item={target}
        onClose={() => {
          reset();
          onClose();
        }}
        saveMode="dual"
        entitySaver={dualSaver}
        onAfterSave={() => {
          onCodingChanged?.();
        }}
        headerChrome={<MatchRationaleHeader item={item} />}
      />
    );
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Encounter detail</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <MatchRationaleHeader item={item} />
          <Divider flexItem />
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ textTransform: "uppercase", letterSpacing: 0.4 }}
          >
            Encounter text
          </Typography>
          <EncounterTextBlock text={item.text} terms={highlightTerms} />
          {editError && (
            <Typography
              variant="body2"
              color="error"
              data-testid="encounter-preview-error"
            >
              {editError}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        <Button
          onClick={handleEditCodes}
          variant="contained"
          disabled={editLoading}
          startIcon={
            editLoading ? (
              <CircularProgress size={16} aria-label="Loading" />
            ) : undefined
          }
          data-testid="encounter-preview-edit-codes"
        >
          {editLoading ? "Opening editor..." : "Edit codes"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
