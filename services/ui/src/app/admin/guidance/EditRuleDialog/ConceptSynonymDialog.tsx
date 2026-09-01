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
 * Controlled dialog for managing the synonym set + exclusions on a
 * CONCEPT leaf's criterion (UN-LEO-AI-093 / DI-LEO-AI-511): add one or
 * more equivalent SNOMED codes, nominate which supplies the chip's
 * label, opt each in/out of descendant expansion (with its own
 * depth), remove a code, or block a specific descendant.
 *
 * Extracted out of `SynonymChipEditor.tsx` so it can be opened from
 * anywhere a caller already has a target `node_id`, not only from
 * that component's own trigger badge. The highlight-to-build wizard's
 * Step 1 / Step 3 "edit an existing pick" flow has no chip UI of its
 * own to hang a badge off -- clicking an already-resolved row there
 * needs to open straight into add/remove, not a single-pick override.
 * `SynonymChipEditor` still owns the trigger badge and renders this
 * dialog internally, so the Advanced/Sentence editor's own chip keeps
 * working unchanged.
 *
 * Dialog, not Popover (R-LEO-AI-509 / DI-512 v3): the body grows and
 * shrinks as the author adds seeds, opens the descendants list, or
 * starts a search. A chip-anchored Popover repositions on every
 * content change and overflows a bounded host; a small centred Dialog
 * stays put and scrolls internally instead.
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Radio from "@mui/material/Radio";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import HubIcon from "@mui/icons-material/Hub";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";

import BlockedCodesPanel from "./BlockedCodesPanel";
import SoftChecksPanel from "./SoftChecksPanel";
import ConceptSearchPanel from "./ConceptSearchPanel";
import ObservationEditDialogBody from "./ObservationEditDialogBody";
import SeedDescendantsList from "./SeedDescendantsList";
import { friendlyTerm, SYNONYM_OBSERVATION_EDIT } from "./copy";
import { isLikelyObservableSeed } from "./observableHit";
import type {
  EditableLogicNode,
  LogicCriterion,
  LogicSeed,
  NodeUpdate,
} from "./types";

/**
 * Normalises a criterion (legacy single-seed OR synonym-set shape)
 * into the seeds/excluded/primary triple every consumer here needs.
 * Exported so `SynonymChipEditor`'s trigger badge can derive the same
 * counts without duplicating this promotion logic.
 */
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
  /** The CONCEPT leaf being edited. Null renders nothing -- callers
   *  that open this dialog by node_id alone (e.g. the highlight
   *  wizard) may briefly have no match while the tree updates. */
  node: EditableLogicNode | null;
  onUpdate: (u: NodeUpdate) => void;
  onClose: () => void;
  /**
   * When set (highlight wizard), the reviewer can undo a mistaken
   * pick: removing the last code -- or clicking "Remove this match"
   * -- deletes the whole CONCEPT leaf so the Step 3 row becomes
   * unresolved again. The Advanced/Sentence chip editor omits this
   * and keeps requiring at least one code on the chip.
   */
  onClearMatch?: () => void;
}

export default function ConceptSynonymDialog({
  open,
  node,
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
          <ObservationEditDialogBody
            node={node}
            primarySeed={primarySeed}
            onUpdate={onUpdate}
          />
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
  // Wizard: clearing the last code undoes the whole match. Chip editor:
  // keep at least one seed so the leaf never becomes empty.
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
                    // Default new synonyms to "exact code only". The author
                    // opts in to descendant expansion per-seed via the
                    // toggle so it is never on for a code they have not
                    // reviewed yet.
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

function SeedRow({
  seed,
  isPrimary,
  canRemove,
  removeClearsMatch = false,
  onPickPrimary,
  onToggleDescendants,
  onSetDistance,
  onRemove,
}: {
  seed: LogicSeed;
  isPrimary: boolean;
  canRemove: boolean;
  /** True when this X undoes the whole wizard match, not just one synonym. */
  removeClearsMatch?: boolean;
  onPickPrimary: () => void;
  onToggleDescendants: () => void;
  onSetDistance: (d: number | null) => void;
  onRemove: () => void;
}) {
  const includeDescendants = seed.include_descendants ?? true;
  const friendly = friendlyTerm(seed.preferred_term);
  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="center"
      sx={{
        px: 0.75,
        py: 0.5,
        borderRadius: 1,
        bgcolor: isPrimary ? "primary.50" : "background.paper",
        border: "1px solid",
        borderColor: isPrimary ? "primary.100" : "transparent",
        transition: "background-color 120ms ease, border-color 120ms ease",
      }}
    >
      <Tooltip title="Use as the chip label" arrow>
        <Radio
          size="small"
          checked={isPrimary}
          onChange={onPickPrimary}
          inputProps={{ "aria-label": `Use ${friendly} as the chip label` }}
          sx={{ p: 0.25 }}
        />
      </Tooltip>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <Typography
            variant="body2"
            sx={{
              fontWeight: isPrimary ? 700 : 500,
              lineHeight: 1.25,
              color: isPrimary ? "primary.dark" : "text.primary",
            }}
            noWrap
          >
            {friendly}
          </Typography>
          {isPrimary && (
            <Box
              component="span"
              sx={{
                fontSize: "0.6rem",
                fontWeight: 700,
                letterSpacing: 0.5,
                px: 0.5,
                py: "1px",
                borderRadius: 0.5,
                color: "primary.contrastText",
                bgcolor: "primary.main",
                textTransform: "uppercase",
              }}
              aria-hidden
            >
              Label
            </Box>
          )}
        </Stack>
        <Typography variant="caption" color="text.secondary">
          code {seed.snomed_concept_id}
          {seed.semantic_tag ? ` -- ${seed.semantic_tag}` : ""}
        </Typography>
      </Box>
      <Tooltip
        title={
          includeDescendants
            ? "Also matches more specific codes (descendants). Click to switch off."
            : "Only matches this exact code. Click to also include more specific codes."
        }
        arrow
      >
        <Switch
          size="small"
          checked={includeDescendants}
          onChange={onToggleDescendants}
          // NOT `inputProps` here: MUI's own Switch hardcodes
          // `slotProps.input = { role: 'switch' }` internally, and
          // that spread runs AFTER (i.e. wins over) the legacy
          // `inputProps` -> `slotProps.input` translation one layer
          // down in SwitchBase -- so an aria-label passed via
          // `inputProps` is silently dropped, leaving the switch with
          // no accessible name at all. Passing `slotProps.input`
          // ourselves is the only way to actually label this control,
          // but Switch's own default entirely REPLACES rather than
          // merges when we do -- so `role: "switch"` must be repeated
          // here too, or the control silently reverts to the browser's
          // default (implicit "checkbox") role.
          slotProps={{
            input: {
              role: "switch",
              "aria-label": `Include descendants for ${friendly}`,
            },
          }}
        />
      </Tooltip>
      {includeDescendants && (
        <Tooltip title="How many levels of more specific codes to include. Minimum is 1." arrow>
          <TextField
            size="small"
            type="number"
            value={seed.distance_child ?? ""}
            placeholder="depth"
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === "") {
                onSetDistance(null);
                return;
              }
              const n = Number(raw);
              if (!Number.isFinite(n)) {
                onSetDistance(null);
                return;
              }
              // Depth 0 with the toggle on would match nothing beyond the
              // exact code -- the same as switching the toggle off -- so
              // we never let the author land on a value below 1.
              onSetDistance(Math.max(1, Math.floor(n)));
            }}
            inputProps={{
              min: 1,
              max: 12,
              "aria-label": `Descendant depth for ${friendly}, minimum 1`,
            }}
            sx={{ width: 64 }}
          />
        </Tooltip>
      )}
      <Tooltip
        title={
          !canRemove
            ? "A chip needs at least one code."
            : removeClearsMatch
              ? "Remove this match so you can pick a different code."
              : "Remove this code"
        }
        arrow
      >
        <span>
          <IconButton
            size="small"
            disabled={!canRemove}
            onClick={onRemove}
            aria-label={
              removeClearsMatch
                ? `Remove match for ${friendly}`
                : `Remove ${friendly} from this chip`
            }
          >
            <CloseIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </span>
      </Tooltip>
    </Stack>
  );
}
