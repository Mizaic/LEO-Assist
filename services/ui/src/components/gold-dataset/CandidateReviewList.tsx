/**
 * CandidateReviewList -- Wave E Phase 2a-ii
 *
 * Renders a list of training-data candidates through the shared
 * @leo/design-system ReviewListCard primitive.
 *
 * Design decisions (per DI-LEO-AI-144):
 *   - Single primary action ("Mark gold") lives in the row actions
 *     slot. Edit and Delete are demoted to an overflow kebab menu --
 *     progressive disclosure so the quiet common case ("mark gold")
 *     dominates the visual weight.
 *   - Tone accent on the left edge reflects status: positive when the
 *     item is done, warning when codes are missing, neutral otherwise.
 *   - Density follows useDensity() from the DensityContext provider
 *     (airy by default, compact when the user flips the toggle).
 *   - Motion (stagger, layout morph on hover, reduced-motion fallback)
 *     is handled inside ReviewListCard itself.
 *
 * Supersedes the legacy components/gold-dataset/CandidateCard.tsx.
 */
"use client";

import { useMemo } from "react";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import {
  ReviewListCard,
  type ReviewListItem,
} from "@leo/design-system";

import { useDensity } from "@/context/DensityContext";

import type { Candidate, Entity } from "./goldDatasetTypes";
import { parseEntities, truncate } from "./goldDatasetUtils";
import RelationRow, { buildRelTriplets, hasMissingLinks } from "./RelationRow";
import {
  EntityChipView,
  makeEntityKey,
  useEntityChipMaps,
  type ChipMaps,
} from "./EntityChipView";
import { MarkGoldButton, RowMenu } from "./CandidateRowActions";

interface Props {
  items: Candidate[];
  onOpen: (candidateId: string) => void;
  onMarkGold: (candidateId: string) => void;
  onDelete: (candidateId: string) => void;
  openingLabelId: string | null;
  markingGoldId: string | null;
  deletingId: string | null;
}

function toneFor(
  candidate: Candidate,
  uncodedCount: number,
): ReviewListItem["tone"] {
  if (candidate.status === "completed") return "positive";
  if (uncodedCount > 0) return "warning";
  return "neutral";
}

function renderChips(
  entities: Entity[],
  uncodedCount: number,
  rareLabels: string[] | undefined,
  maps: ChipMaps,
) {
  if (entities.length === 0) return null;
  return (
    <>
      {entities.slice(0, 4).map((entity, index) => (
        <EntityChipView
          key={`${entity.text}-${index}`}
          entity={entity}
          hasSurface={maps.surface[makeEntityKey(entity)] ?? false}
          domainCount={maps.domain[makeEntityKey(entity)] ?? 0}
        />
      ))}
      {entities.length > 4 && (
        <Chip
          size="small"
          variant="outlined"
          label={`+${entities.length - 4} more`}
          sx={{ height: 22, fontSize: "0.7rem" }}
        />
      )}
      {uncodedCount > 0 && (
        <Chip
          size="small"
          color="warning"
          icon={<WarningAmberIcon sx={{ fontSize: "13px !important" }} />}
          label={`${uncodedCount} need${uncodedCount === 1 ? "s" : ""} a code`}
          sx={{ height: 22, fontSize: "0.72rem" }}
        />
      )}
      {rareLabels && rareLabels.length > 0 && (
        <Tooltip
          title={`Prioritised: these entity types have few gold examples - reviewing this record helps fill the gap (${rareLabels.join(", ")})`}
        >
          <Chip
            size="small"
            icon={<TrendingUpIcon sx={{ fontSize: "13px !important" }} />}
            label={`Rare: ${rareLabels.join(", ")}`}
            sx={{
              height: 20,
              fontSize: "0.68rem",
              bgcolor: "#F3E5F5",
              color: "#6A1B9A",
              border: "1px solid #CE93D8",
              "& .MuiChip-icon": { color: "#6A1B9A" },
            }}
          />
        </Tooltip>
      )}
    </>
  );
}

function buildItem(
  candidate: Candidate,
  handlers: Props,
  maps: ChipMaps,
): ReviewListItem {
  const entities = parseEntities(candidate.entities_json ?? null);
  const uncodedCount = entities.filter((e) => !e.snomed_concept_id).length;
  const relTriplets = buildRelTriplets(entities);
  const missingLinks = hasMissingLinks(entities);
  const isDone = candidate.status === "completed";
  const id = candidate.candidate_id;
  const busyMark = handlers.markingGoldId === id;
  const busyDelete = handlers.deletingId === id;
  const busyOpen = handlers.openingLabelId === id;
  const disabled = busyMark || busyDelete || busyOpen;

  return {
    id,
    title: truncate(candidate.text),
    chips: renderChips(
      entities,
      uncodedCount,
      candidate.rare_labels ?? undefined,
      maps,
    ),
    meta: <RelationRow triplets={relTriplets} missing={missingLinks} />,
    actions: (
      <>
        <MarkGoldButton
          candidateId={id}
          busy={busyMark}
          disabled={disabled || isDone}
          onClick={handlers.onMarkGold}
        />
        <RowMenu
          candidateId={id}
          disabled={disabled}
          deleting={busyDelete}
          onOpen={handlers.onOpen}
          onDelete={handlers.onDelete}
        />
      </>
    ),
    tone: toneFor(candidate, uncodedCount),
    onSelect: () => handlers.onOpen(id),
    selected: false,
  };
}

export default function CandidateReviewList(props: Props) {
  const { density } = useDensity();
  const listDensity = density === "compact" ? "compact" : "comfortable";

  const allEntities = useMemo(
    () => props.items.flatMap((c) => parseEntities(c.entities_json ?? null)),
    [props.items],
  );
  const maps = useEntityChipMaps(allEntities);

  const reviewItems: ReviewListItem[] = useMemo(
    () => props.items.map((c) => buildItem(c, props, maps)),
    [props, maps],
  );

  return (
    <ReviewListCard
      items={reviewItems}
      density={listDensity}
      emptyState="No sentences to review yet. Run the pipeline to get started."
    />
  );
}
