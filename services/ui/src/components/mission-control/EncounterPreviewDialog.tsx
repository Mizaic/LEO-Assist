"use client";

/**
 * EncounterPreviewDialog (DI-LEO-AI-212).
 *
 * Thin wrapper around the shared GoldLabelEditorDialog used on the
 * /care/encounters mission-control surface. It seeds a gold label from
 * the live encounter, mounts the shared editor in dual-save mode, and
 * surfaces the search match rationale (date, match type, rationale
 * chips) in the dialog header so reviewers retain the context that
 * brought them to this encounter.
 *
 * Saving the dialog
 *   - updates :DOCUMENTS coded links on the live encounter, and
 *   - mirrors a de-identified copy onto the linked GoldLabel for
 *     training (DI-LEO-AI-209/210).
 */

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
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

export default function EncounterPreviewDialog({
  item,
  onClose,
  onCodingChanged,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<GoldLabel | null>(null);
  const [context, setContext] =
    useState<DualSaveEncounterContext | null>(null);

  const reset = useCallback(() => {
    setTarget(null);
    setContext(null);
    setError(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!item) {
      reset();
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setTarget(null);
    setContext(null);
    void createGoldLabelFromEncounter({
      patient_id: item.patient_id,
      encounter_id: item.encounter_id,
    })
      .then((seed) => {
        if (cancelled) return;
        setContext({
          patient_id: item.patient_id,
          encounter_id: item.encounter_id,
          baseline_concept_ids: seed.baseline_concept_ids,
        });
        setTarget(seed.gold_label);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof Error
            ? err.message
            : "Could not open the encounter editor.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [item, reset]);

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
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Encounter detail</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <MatchRationaleHeader item={item} />
          {loading && (
            <Stack
              direction="row"
              spacing={1.5}
              alignItems="center"
              data-testid="encounter-preview-loading"
            >
              <CircularProgress size={20} />
              <Typography variant="body2" color="text.secondary">
                Preparing the editor for this encounter...
              </Typography>
            </Stack>
          )}
          {error && (
            <Typography
              variant="body2"
              color="error"
              data-testid="encounter-preview-error"
            >
              {error}
            </Typography>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
