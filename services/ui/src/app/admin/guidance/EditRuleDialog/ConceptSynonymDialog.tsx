/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Controlled dialog for managing the synonym set, exclusions, soft checks,
 * and linked guideline wording on a CONCEPT or OBSERVATION leaf.
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import HubIcon from "@mui/icons-material/Hub";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";

import BlockedCodesPanel from "./BlockedCodesPanel";
import SoftChecksPanel from "./SoftChecksPanel";
import SourceWordingPanel from "./SourceWordingPanel";
import ConceptSearchPanel from "./ConceptSearchPanel";
import ObservationEditDialogBody from "./ObservationEditDialogBody";
import SeedDescendantsList from "./SeedDescendantsList";
import SeedRow from "./SeedRow";
import { friendlyTerm, SYNONYM_OBSERVATION_EDIT } from "./copy";
import { isLikelyObservableSeed } from "./observableHit";
import type {
  EditableLogicNode,
  LogicCriterion,
  LogicSeed,
  NodeUpdate,
} from "./types";

export function deriveSynonymEditorState(criterion: LogicCriterion | undefined): {
  seeds: LogicSeed[];
  excluded: string[];
  primaryId: string;
} {
  const c = criterion ?? ({} as LogicCriterion);
  const seeds: LogicSeed[] =
    c.seeds && c.seeds.length > 0
      ? c.seeds
      : c.snomed_concept_id
        ? [
            {
              snomed_concept_id: c.snomed_concept_id,
              preferred_term: c.preferred_term,
              semantic_tag: c.semantic_tag,
              include_descendants: true,
            },
          ]
        : [];
  const excluded = c.excluded_concept_ids ?? [];
  const primaryId = c.primary_concept_id || seeds[0]?.snomed_concept_id || "";
  return { seeds, excluded, primaryId };
}

interface Props {
  open: boolean;
  node: EditableLogicNode | null;
  /** Optional NICE recommendation text for editing linked guideline wording. */
  recommendationText?: string | null;
  onUpdate: (u: NodeUpdate) => void;
  onClose: () => void;
  onClearMatch?: () => void;
}

export default function ConceptSynonymDialog({
  open,
  node,
  recommendationText,
  onUpdate,
  onClose,
  onClearMatch,
}: Props) {
  const criterion = node?.criterion;
  const { seeds, excluded, primaryId } = useMemo(
    () => deriveSynonymEditorState(criterion),
    [criterion],
  );
  const primarySeed = seeds.find((s) => s.snomed_concept_id === primaryId) ?? seeds[0];
  const isObservationLeaf = node?.kind === "OBSERVATION";
  const showObservableThreshold =
    isObservationLeaf ||
    (!!primarySeed && isLikelyObservableSeed(primarySeed));
  const chipLabel = isObservationLeaf
    ? friendlyTerm(node?.observation?.observable_term) || "this reading"
    : friendlyTerm(criterion?.preferred_term) || "this chip";
  const subtitle = isObservationLeaf
    ? SYNONYM_OBSERVATION_EDIT.dialogSubtitleObservation
    : showObservableThreshold
      ? SYNONYM_OBSERVATION_EDIT.dialogSubtitleObservableConcept
      : "Add other codes that mean the same thing, or block codes that should not fire this rule.";
  const trimmedQuote = recommendationText?.trim() || "";

  if (!node) return null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      scroll="paper"
      aria-labelledby={`synonym-editor-title-${node.node_id}`}
      PaperProps={{
        elevation: 12,
        sx: {
          borderRadius: 2,
          border: "1px solid",
          borderColor: "divider",
          maxHeight: "85vh",
        },
      }}
    >
      <DialogTitle
        id={`synonym-editor-title-${node.node_id}`}
        sx={{
          display: "flex",
          alignItems: "flex-start",
          gap: 1,
          pr: 1.5,
          py: 1.5,
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <TuneRoundedIcon sx={{ fontSize: 20, color: "primary.main", mt: 0.25 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            component="span"
            variant="subtitle1"
            sx={{ fontWeight: 700, lineHeight: 1.2, display: "block" }}
          >
            Edit &ldquo;{chipLabel}&rdquo;
          </Typography>
          <Typography
            component="span"
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.25, lineHeight: 1.45 }}
          >
            {subtitle}
          </Typography>
        </Box>
        <Tooltip title="Close (ESC)">
          <IconButton
            onClick={onClose}
            size="small"
            aria-label="Close synonym editor"
            sx={{ color: "text.secondary" }}
          >
            <CloseIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </DialogTitle>
      <DialogContent dividers sx={{ p: 2 }}>
        {isObservationLeaf ? (
          <Stack spacing={2}>
            <ObservationEditDialogBody
              node={node}
              primarySeed={primarySeed}
              onUpdate={onUpdate}
            />
            {trimmedQuote && (
              <SourceWordingPanel
                node={node}
                recommendationText={trimmedQuote}
                onUpdate={onUpdate}
              />
            )}
          </Stack>
        ) : (
          <Stack spacing={2}>
            <SynonymEditorBody
              nodeId={node.node_id}
              seeds={seeds}
              excluded={excluded}
              primaryId={primaryId}
              chipLabel={chipLabel}
              softQualifiers={criterion?.soft_qualifiers ?? []}
              onUpdate={onUpdate}
              onClearMatch={onClearMatch}
            />
            {trimmedQuote && (
              <SourceWordingPanel
                node={node}
                recommendationText={trimmedQuote}
                onUpdate={onUpdate}
              />
            )}
            {showObservableThreshold && (
              <ObservationEditDialogBody
                node={node}
                primarySeed={primarySeed}
                onUpdate={onUpdate}
              />
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions
        sx={{
          px: 2,
          py: 1.25,
          justifyContent: onClearMatch ? "space-between" : "flex-end",
        }}
      >
        {onClearMatch && (
          <Button
            onClick={onClearMatch}
            color="error"
            sx={{ textTransform: "none", fontWeight: 600 }}
          >
            Remove this match
          </Button>
        )}
        <Button
          onClick={onClose}
          variant="contained"
          color="primary"
          sx={{ textTransform: "none", fontWeight: 700, minWidth: 96 }}
        >
          Done
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function SynonymEditorBody({
  nodeId,
  seeds,
  excluded,
  primaryId,
  chipLabel,
  softQualifiers,
  onUpdate,
  onClearMatch,
}: {
  nodeId: string;
  seeds: LogicSeed[];
  excluded: string[];
  primaryId: string;
  chipLabel: string;
  softQualifiers: import("./types").SoftQualifierSpec[];
  onUpdate: (u: NodeUpdate) => void;
  onClearMatch?: () => void;
}) {
  const [searchMode, setSearchMode] =
    useState<"none" | "add_seed" | "add_excluded">("none");
  const canRemoveLast = !!onClearMatch;

  return (
    <Stack spacing={2}>
      <Box>
        <Stack
          direction="row"
          alignItems="baseline"
          spacing={0.75}
          sx={{ mb: 0.75 }}
        >
          <HubIcon sx={{ fontSize: 14, color: "info.main", alignSelf: "center" }} />
          <Typography variant="caption" sx={{ fontWeight: 700, color: "text.primary" }}>
            Codes on this chip
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {seeds.length} total
          </Typography>
        </Stack>
        <Stack
          spacing={0.25}
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1.5,
            p: 0.5,
            bgcolor: "grey.50",
          }}
        >
          {seeds.map((seed) => (
            <Box key={seed.snomed_concept_id}>
              <SeedRow
                seed={seed}
                isPrimary={seed.snomed_concept_id === primaryId}
                canRemove={seeds.length > 1 || canRemoveLast}
                removeClearsMatch={seeds.length === 1 && canRemoveLast}
                onPickPrimary={() =>
                  onUpdate({
                    kind: "set_primary_seed",
                    nodeId,
                    conceptId: seed.snomed_concept_id,
                  })
                }
                onToggleDescendants={() =>
                  onUpdate({
                    kind: "toggle_include_descendants",
                    nodeId,
                    conceptId: seed.snomed_concept_id,
                  })
                }
                onSetDistance={(d) =>
                  onUpdate({
                    kind: "set_seed_distance",
                    nodeId,
                    conceptId: seed.snomed_concept_id,
                    distance: d,
                  })
                }
                onRemove={() => {
                  if (seeds.length === 1 && onClearMatch) {
                    onClearMatch();
                    return;
                  }
                  onUpdate({
                    kind: "remove_seed",
                    nodeId,
                    conceptId: seed.snomed_concept_id,
                  });
                }}
              />
              <Box sx={{ pl: 4.25, pr: 0.5, pb: 0.5 }}>
                <SeedDescendantsList
                  seedConceptId={seed.snomed_concept_id}
                  seedTerm={seed.preferred_term ?? ""}
                  includeDescendants={seed.include_descendants ?? true}
                  depth={Math.max(1, seed.distance_child ?? 3)}
                  excludedIds={excluded}
                  onBlock={(cid) =>
                    onUpdate({
                      kind: "add_excluded",
                      nodeId,
                      conceptId: cid,
                    })
                  }
                  onUnblock={(cid) =>
                    onUpdate({
                      kind: "remove_excluded",
                      nodeId,
                      conceptId: cid,
                    })
                  }
                />
              </Box>
            </Box>
          ))}
          {seeds.length === 0 && (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ p: 1, fontStyle: "italic" }}
            >
              No codes yet -- search below to add the first one.
            </Typography>
          )}
        </Stack>
        <Button
          size="small"
          startIcon={<AddIcon />}
          onClick={() => setSearchMode("add_seed")}
          sx={{ mt: 1, textTransform: "none", fontWeight: 600 }}
        >
          Add another code that means the same
        </Button>
      </Box>

      <BlockedCodesPanel
        nodeId={nodeId}
        excluded={excluded}
        onUpdate={onUpdate}
        onRequestSearch={() => setSearchMode("add_excluded")}
      />
      <SoftChecksPanel
        nodeId={nodeId}
        qualifiers={softQualifiers}
        onUpdate={onUpdate}
      />

      {searchMode !== "none" && (
        <Box
          sx={{
            mt: 0.5,
            p: 1.25,
            borderRadius: 1.5,
            bgcolor: "primary.50",
            border: "1px solid",
            borderColor: "primary.100",
          }}
        >
          <ConceptSearchPanel
            mode={searchMode === "add_seed" ? "add" : "replace"}
            focusLabel={
              searchMode === "add_seed"
                ? `Add a synonym to "${chipLabel}"`
                : `Block a code under "${chipLabel}"`
            }
            initialQuery=""
            onPick={(criterion: LogicCriterion) => {
              if (searchMode === "add_seed") {
                onUpdate({
                  kind: "add_seed",
                  nodeId,
                  seed: {
                    snomed_concept_id: criterion.snomed_concept_id,
                    preferred_term: criterion.preferred_term,
                    semantic_tag: criterion.semantic_tag,
                    include_descendants: false,
                  },
                });
              } else {
                onUpdate({
                  kind: "add_excluded",
                  nodeId,
                  conceptId: criterion.snomed_concept_id,
                });
              }
              setSearchMode("none");
            }}
          />
          <Button
            size="small"
            onClick={() => setSearchMode("none")}
            sx={{ mt: 0.5, textTransform: "none", fontWeight: 600 }}
          >
            Cancel
          </Button>
        </Box>
      )}
    </Stack>
  );
}
