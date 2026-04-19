"use client";

/**
 * Popover editor for the synonym set + exclusions on a CONCEPT chip.
 *
 * Implements UN-LEO-AI-093 / DI-LEO-AI-511. The editor lets a guideline
 * author:
 *   - add one or more equivalent SNOMED codes to a single chip (e.g.
 *     "Smoker", "Cigarette smoker", "Pipe smoker")
 *   - nominate which seed supplies the chip's preferred-term label
 *   - opt each seed in / out of descendant expansion (and override the
 *     per-rule distance_child default when needed)
 *   - exclude specific SNOMED codes that should NOT fire the rule, even
 *     if they would otherwise fall inside one of the seed closures
 *
 * The editor is intentionally headless of any concept search infra --
 * adding seeds and exclusions reuses ConceptSearchPanel via a small
 * inline search dialog so we do not duplicate the terminology lookup.
 *
 * Plain-English copy follows `health-literacy.mdc` (reading age 9-11).
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Radio from "@mui/material/Radio";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import HubIcon from "@mui/icons-material/Hub";
import BlockIcon from "@mui/icons-material/Block";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";

import ConceptSearchPanel from "./ConceptSearchPanel";
import { friendlyTerm } from "./copy";
import type {
  EditableLogicNode,
  LogicCriterion,
  LogicSeed,
  NodeUpdate,
} from "./types";

interface Props {
  node: EditableLogicNode;
  onUpdate: (u: NodeUpdate) => void;
}

/**
 * Trigger badge that opens the editor popover. We keep the badge
 * subtle (28px chip-ish button, neutral colour) so it does not
 * compete with the primary "Click to swap" affordance on the chip.
 *
 * The badge label adapts to the current state:
 *   - 0 extra seeds, 0 exclusions  -> "synonyms" (icon-only tooltip)
 *   - N>=1 extra seeds             -> "+N"
 *   - any exclusions               -> a "no-entry" icon is added
 */
export default function SynonymChipEditor({ node, onUpdate }: Props) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = Boolean(anchor);

  const criterion = node.criterion ?? ({} as LogicCriterion);
  const seeds = useMemo<LogicSeed[]>(() => {
    if (criterion.seeds && criterion.seeds.length > 0) return criterion.seeds;
    if (criterion.snomed_concept_id) {
      return [
        {
          snomed_concept_id: criterion.snomed_concept_id,
          preferred_term: criterion.preferred_term,
          semantic_tag: criterion.semantic_tag,
          include_descendants: true,
        },
      ];
    }
    return [];
  }, [criterion]);
  const excluded = criterion.excluded_concept_ids ?? [];
  const primaryId =
    criterion.primary_concept_id || seeds[0]?.snomed_concept_id || "";

  const extraSeedCount = Math.max(0, seeds.length - 1);
  const hasExclusions = excluded.length > 0;
  const isPopulated = extraSeedCount > 0 || hasExclusions;
  const friendlyChipLabel = friendlyTerm(criterion.preferred_term);
  const tooltip = !isPopulated
    ? `Add other codes that mean the same as "${friendlyChipLabel}", or block specific codes.`
    : `${seeds.length} code${seeds.length === 1 ? "" : "s"} on this chip${
        hasExclusions
          ? `, ${excluded.length} blocked code${excluded.length === 1 ? "" : "s"}`
          : ""
      }. Click to edit.`;
  const ariaLabel = `Edit synonyms and blocked codes for ${friendlyChipLabel}. ${
    isPopulated
      ? `${seeds.length} code${seeds.length === 1 ? "" : "s"} on this chip${
          hasExclusions
            ? `, ${excluded.length} blocked.`
            : "."
        }`
      : "No synonyms yet."
  }`;

  return (
    <>
      <Tooltip title={tooltip} arrow>
        {isPopulated ? (
          <ButtonBase
            onClick={(e) => setAnchor(e.currentTarget)}
            aria-label={ariaLabel}
            sx={{
              height: 22,
              borderRadius: "11px",
              px: 0.75,
              ml: 0.5,
              gap: 0.5,
              border: "1px solid",
              borderColor: hasExclusions ? "error.light" : "info.light",
              bgcolor: hasExclusions ? "error.50" : "info.50",
              color: hasExclusions ? "error.dark" : "info.dark",
              fontSize: "0.68rem",
              fontWeight: 700,
              lineHeight: 1,
              transition:
                "background-color 120ms ease, border-color 120ms ease",
              "&:hover": {
                bgcolor: hasExclusions ? "error.100" : "info.100",
              },
              "&:focus-visible": {
                outline: "2px solid",
                outlineColor: hasExclusions ? "error.main" : "info.main",
                outlineOffset: 1,
              },
            }}
          >
            {extraSeedCount > 0 && (
              <>
                <HubIcon sx={{ fontSize: 12 }} />
                <span>+{extraSeedCount}</span>
              </>
            )}
            {hasExclusions && (
              <>
                {extraSeedCount > 0 && (
                  <Box
                    aria-hidden
                    sx={{
                      width: 1,
                      height: 10,
                      bgcolor: "currentColor",
                      opacity: 0.35,
                    }}
                  />
                )}
                <BlockIcon sx={{ fontSize: 12 }} />
                <span>{excluded.length}</span>
              </>
            )}
          </ButtonBase>
        ) : (
          <IconButton
            size="small"
            onClick={(e) => setAnchor(e.currentTarget)}
            aria-label={ariaLabel}
            sx={{
              ml: 0.25,
              p: 0.25,
              color: "text.disabled",
              transition: "color 120ms ease, background-color 120ms ease",
              "&:hover": {
                color: "primary.main",
                bgcolor: "primary.50",
              },
              "&:focus-visible": {
                outline: "2px solid",
                outlineColor: "primary.main",
                outlineOffset: 1,
              },
            }}
          >
            <TuneRoundedIcon sx={{ fontSize: 14 }} />
          </IconButton>
        )}
      </Tooltip>
      <Popover
        open={open}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{
          paper: {
            elevation: 8,
            sx: {
              p: 2,
              width: 480,
              maxWidth: "90vw",
              borderRadius: 2,
              border: "1px solid",
              borderColor: "divider",
              mt: 0.5,
            },
          },
        }}
      >
        <SynonymEditorBody
          nodeId={node.node_id}
          seeds={seeds}
          excluded={excluded}
          primaryId={primaryId}
          chipLabel={friendlyTerm(criterion.preferred_term) || "this chip"}
          onUpdate={onUpdate}
        />
      </Popover>
    </>
  );
}

function SynonymEditorBody({
  nodeId,
  seeds,
  excluded,
  primaryId,
  chipLabel,
  onUpdate,
}: {
  nodeId: string;
  seeds: LogicSeed[];
  excluded: string[];
  primaryId: string;
  chipLabel: string;
  onUpdate: (u: NodeUpdate) => void;
}) {
  const [searchMode, setSearchMode] =
    useState<"none" | "add_seed" | "add_excluded">("none");

  return (
    <Stack spacing={2}>
      <Box>
        <Stack direction="row" alignItems="center" spacing={0.75}>
          <TuneRoundedIcon sx={{ fontSize: 18, color: "primary.main" }} />
          <Typography
            variant="subtitle1"
            sx={{ fontWeight: 700, lineHeight: 1.2 }}
          >
            Edit &ldquo;{chipLabel}&rdquo;
          </Typography>
        </Stack>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 0.5, lineHeight: 1.45 }}
        >
          Add other codes that mean the same thing, or block codes that
          should not fire this rule.
        </Typography>
      </Box>

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
            <SeedRow
              key={seed.snomed_concept_id}
              seed={seed}
              isPrimary={seed.snomed_concept_id === primaryId}
              canRemove={seeds.length > 1}
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
              onRemove={() =>
                onUpdate({
                  kind: "remove_seed",
                  nodeId,
                  conceptId: seed.snomed_concept_id,
                })
              }
            />
          ))}
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

      <Box>
        <Stack
          direction="row"
          alignItems="baseline"
          spacing={0.75}
          sx={{ mb: 0.5 }}
        >
          <BlockIcon sx={{ fontSize: 14, color: "error.main", alignSelf: "center" }} />
          <Typography variant="caption" sx={{ fontWeight: 700, color: "text.primary" }}>
            Blocked codes
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {excluded.length} total
          </Typography>
        </Stack>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mb: 0.75, lineHeight: 1.45 }}
        >
          These codes will not fire the rule, even if they sit under a
          chip code.
        </Typography>
        <Stack
          direction="row"
          spacing={0.5}
          sx={{ mt: 0.5, flexWrap: "wrap", rowGap: 0.5 }}
        >
          {excluded.length === 0 ? (
            <Box
              sx={{
                width: "100%",
                py: 0.75,
                px: 1,
                borderRadius: 1,
                border: "1px dashed",
                borderColor: "divider",
                color: "text.secondary",
              }}
            >
              <Typography variant="caption">
                Nothing blocked yet.
              </Typography>
            </Box>
          ) : (
            excluded.map((cid) => (
              <Chip
                key={cid}
                icon={<BlockIcon sx={{ fontSize: 12 }} />}
                label={`code ${cid}`}
                size="small"
                variant="outlined"
                color="error"
                onDelete={() =>
                  onUpdate({
                    kind: "remove_excluded",
                    nodeId,
                    conceptId: cid,
                  })
                }
                deleteIcon={<CloseIcon sx={{ fontSize: 13 }} />}
                sx={{
                  height: 24,
                  fontSize: "0.7rem",
                  bgcolor: "error.50",
                  borderColor: "error.light",
                  "& .MuiChip-icon": { color: "error.dark", ml: 0.5 },
                }}
              />
            ))
          )}
        </Stack>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          sx={{ mt: 1 }}
          alignItems={{ xs: "stretch", sm: "center" }}
        >
          <Button
            size="small"
            startIcon={<BlockIcon />}
            onClick={() => setSearchMode("add_excluded")}
            sx={{ textTransform: "none", fontWeight: 600 }}
          >
            Search a code to block
          </Button>
          <ManualBlockField
            onAdd={(cid) =>
              onUpdate({ kind: "add_excluded", nodeId, conceptId: cid })
            }
          />
        </Stack>
      </Box>

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
                    include_descendants: true,
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
  onPickPrimary,
  onToggleDescendants,
  onSetDistance,
  onRemove,
}: {
  seed: LogicSeed;
  isPrimary: boolean;
  canRemove: boolean;
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
          inputProps={{
            "aria-label": `Include descendants for ${friendly}`,
          }}
        />
      </Tooltip>
      {includeDescendants && (
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
            onSetDistance(Number.isFinite(n) ? n : null);
          }}
          inputProps={{
            min: 0,
            max: 12,
            "aria-label": `Descendant depth for ${friendly}`,
          }}
          sx={{ width: 64 }}
        />
      )}
      <Tooltip title={canRemove ? "Remove this code" : "A chip needs at least one code."} arrow>
        <span>
          <IconButton
            size="small"
            disabled={!canRemove}
            onClick={onRemove}
            aria-label={`Remove ${friendly} from this chip`}
          >
            <CloseIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </span>
      </Tooltip>
    </Stack>
  );
}

function ManualBlockField({ onAdd }: { onAdd: (conceptId: string) => void }) {
  const [value, setValue] = useState("");
  const trimmed = value.trim();
  const isNumeric = /^\d{4,18}$/.test(trimmed);
  return (
    <Stack direction="row" spacing={0.5} alignItems="center">
      <TextField
        size="small"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="paste SNOMED id"
        inputProps={{ "aria-label": "Block a SNOMED code by id" }}
        sx={{ width: 160 }}
      />
      <Button
        size="small"
        variant="outlined"
        disabled={!isNumeric}
        onClick={() => {
          onAdd(trimmed);
          setValue("");
        }}
      >
        Block
      </Button>
    </Stack>
  );
}
