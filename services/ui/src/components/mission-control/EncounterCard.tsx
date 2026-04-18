"use client";

import { forwardRef, useState, useCallback } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import ExpandMore from "@mui/icons-material/ExpandMore";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import type { CodedLink } from "@/lib/types";
import CodesPanel from "./EncounterCodesPanel";
import { highlightSearchMatches } from "./encounterTextUtils";
import {
  GoldLabelEditorDialog,
  createGoldLabelFromEncounter,
  useDualSaveAdapter,
  type GoldLabel,
  type DualSaveEncounterContext,
} from "@/components/gold-editor";

export interface EncounterCardData {
  encounter_id: string;
  date: string;
  text: string | null;
  coded_count: number;
}

interface EncounterCardProps {
  enc: EncounterCardData;
  patientId: string;
  search: string;
  isExpanded: boolean;
  isFocused: boolean;
  isLinkedToEpisode?: boolean;
  isResetting: boolean;
  codingLoading: boolean;
  codingLinks: CodedLink[];
  codingError: string | undefined;
  onToggle: () => void;
  onRequestReset: () => void;
  /** Called after the editor dialog successfully syncs live coded
   *  links and the gold mirror, so the parent can refresh its cached
   *  view of :DOCUMENTS for this encounter (DI-LEO-AI-220/221). */
  onCodingChanged?: () => void;
}

// LONG FUNCTION: layout-dense card with collapse panel and inline
// action row; splitting further would scatter related markup with no
// clarity gain.
const EncounterCard = forwardRef<HTMLDivElement, EncounterCardProps>(
  function EncounterCard(props, ref) {
    const {
      enc,
      patientId,
      search,
      isExpanded,
      isFocused,
      isLinkedToEpisode = false,
      isResetting,
      codingLoading,
      codingLinks,
      codingError,
      onToggle,
      onRequestReset,
      onCodingChanged,
    } = props;
    const encounterKey = String(enc.encounter_id);

    // Inline shared editor state (DI-LEO-AI-220/221) -- replaces the
    // legacy /care/patients/.../encounters/.../ deep-link page so the
    // reviewer never loses their place in the patient timeline.
    const [openingEditor, setOpeningEditor] = useState(false);
    const [editorError, setEditorError] = useState<string | null>(null);
    const [editorTarget, setEditorTarget] = useState<GoldLabel | null>(null);
    const [editorContext, setEditorContext] =
      useState<DualSaveEncounterContext | null>(null);

    const openEditor = useCallback(async () => {
      setOpeningEditor(true);
      setEditorError(null);
      try {
        const seed = await createGoldLabelFromEncounter({
          patient_id: patientId,
          encounter_id: encounterKey,
        });
        setEditorContext({
          patient_id: patientId,
          encounter_id: encounterKey,
          baseline_concept_ids: seed.baseline_concept_ids,
        });
        setEditorTarget(seed.gold_label);
      } catch (err) {
        setEditorError(
          err instanceof Error
            ? err.message
            : "Could not open the encounter editor.",
        );
      } finally {
        setOpeningEditor(false);
      }
    }, [patientId, encounterKey]);

    // Hook must be called unconditionally; passes a placeholder context
    // when the dialog is closed to keep the hook order stable.
    const dualSaver = useDualSaveAdapter({
      labelId: editorTarget?.label_id ?? "",
      context: editorContext ?? {
        patient_id: patientId,
        encounter_id: encounterKey,
        baseline_concept_ids: [],
      },
      onSynced: () => {
        onCodingChanged?.();
      },
    });

    return (
      <Box
        ref={ref}
        data-encounter-card-id={encounterKey}
        data-linked-to-episode={isLinkedToEpisode ? "true" : "false"}
        sx={{
          position: "relative",
          mb: 1.5,
          border: "2px solid",
          borderColor: isFocused ? "primary.main" : "divider",
          borderRadius: "6px",
          transition: "border-color 0.25s ease",
          overflow: "hidden",
        }}
      >
        {isLinkedToEpisode && (
          <Box
            aria-hidden="true"
            data-testid="encounter-linked-accent"
            sx={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: 3,
              bgcolor: "#2563eb",
            }}
          />
        )}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            px: 1,
            py: 0.5,
            flexWrap: "wrap",
            cursor: "pointer",
            userSelect: "none",
            "&:hover": { bgcolor: "action.hover" },
          }}
          onClick={onToggle}
        >
          <IconButton
            size="small"
            aria-label={isExpanded ? "Collapse encounter" : "Expand encounter"}
            sx={{
              p: 0.25,
              transition: "transform 0.2s ease",
              transform: isExpanded ? "rotate(0deg)" : "rotate(-90deg)",
            }}
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
          >
            <ExpandMore fontSize="small" />
          </IconButton>

          <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>
            {enc.date?.slice(0, 10) ?? "--"}
            {!isExpanded && enc.coded_count > 0 && (
              <Typography component="span" variant="caption" color="text.disabled" sx={{ ml: 1 }}>
                &middot; {enc.coded_count} coded {enc.coded_count === 1 ? "concept" : "concepts"}
              </Typography>
            )}
          </Typography>
          {isLinkedToEpisode && (
            <Chip
              size="small"
              label="In episode"
              data-testid="encounter-in-episode-chip"
              sx={{
                height: 20,
                fontSize: "0.65rem",
                bgcolor: "#DBEAFE",
                color: "#1E40AF",
                fontWeight: 600,
              }}
            />
          )}

          <Box
            sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}
            onClick={(e) => e.stopPropagation()}
          >
            {isExpanded && (
              <Typography variant="caption" color="text.secondary">
                {enc.coded_count} coded {enc.coded_count === 1 ? "concept" : "concepts"}
              </Typography>
            )}
            <Button
              size="small"
              variant="outlined"
              data-testid="encounter-card-edit-codes"
              disabled={openingEditor}
              onClick={openEditor}
            >
              {openingEditor ? "Opening..." : "Edit codes"}
            </Button>
            <Button
              size="small"
              color="error"
              variant="outlined"
              disabled={isResetting}
              onClick={onRequestReset}
            >
              {isResetting ? "Resetting..." : "Reset and recode"}
            </Button>
          </Box>
        </Box>

        {editorError && (
          <Box sx={{ px: 1, pb: 0.5 }}>
            <Typography
              variant="caption"
              color="error"
              data-testid="encounter-card-editor-error"
            >
              {editorError}
            </Typography>
          </Box>
        )}

        {editorTarget && editorContext && (
          <GoldLabelEditorDialog
            item={editorTarget}
            onClose={() => {
              setEditorTarget(null);
              setEditorContext(null);
            }}
            saveMode="dual"
            entitySaver={dualSaver}
            onAfterSave={() => {
              onCodingChanged?.();
            }}
          />
        )}

        <Collapse in={isExpanded} unmountOnExit>
          <Box sx={{ px: 1, pb: 1 }}>
            <CodesPanel
              enc={enc}
              codingLoading={codingLoading}
              codingLinks={codingLinks}
              codingError={codingError}
            />
            <Box
              sx={{
                bgcolor: "grey.50",
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
                p: 1.5,
                fontFamily: "inherit",
                fontSize: "0.8rem",
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                color: enc.text ? "text.primary" : "text.disabled",
                fontStyle: enc.text ? "normal" : "italic",
              }}
            >
              {enc.text
                ? highlightSearchMatches(enc.text, search)
                : "No text available for this encounter."}
            </Box>
          </Box>
        </Collapse>
      </Box>
    );
  }
);

export default EncounterCard;
