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
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import {
  ReviewListCard,
  type ReviewListItem,
} from "@leo/design-system";

import { useDensity } from "@/context/DensityContext";
import {
  HighlightedText,
  collectHighlightTerms,
} from "@/components/mission-control/HighlightedText";
import {
  computeMatchRationale,
  expandSearchTerms,
  type MatchRationale,
} from "@/components/mission-control/encounterRelevance";

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
  /**
   * Reviewer's debounced search query (forwarded from
   * GoldDatasetPanel). When set, the row title highlights matched
   * terms and a "why this matched" chip row is rendered alongside
   * the existing entity / status chips so the dry-run queue speaks
   * the same vocabulary as the /care/encounters host search and the
   * /care/patients drawer (DI-LEO-AI-523, UN-LEO-AI-096).
   */
  search?: string;
}

function toneFor(
  candidate: Candidate,
  uncodedCount: number,
): ReviewListItem["tone"] {
  if (candidate.status === "completed") return "positive";
  if (uncodedCount > 0) return "warning";
  return "neutral";
}

function renderRationaleChips(
  candidateId: string,
  rationale: MatchRationale,
  expandedTerms: string[],
) {
  if (expandedTerms.length === 0 || rationale.hitTerms.length === 0) return null;
  return (
    <Box
      data-testid="candidate-row-match-rationale"
      sx={{
        display: "flex",
        gap: 0.5,
        flexWrap: "wrap",
        alignItems: "center",
      }}
    >
      {rationale.hitTerms.slice(0, 4).map((term, idx) => (
        <Chip
          key={`${candidateId}-mr-${idx}-${term}`}
          size="small"
          label={term}
          variant="outlined"
          data-testid="candidate-row-match-rationale-chip"
          sx={{ height: 20, fontSize: "0.65rem" }}
        />
      ))}
    </Box>
  );
}

function renderChips(
  entities: Entity[],
  uncodedCount: number,
  rareLabels: string[] | undefined,
  maps: ChipMaps,
  isAISuggested: boolean,
  candidateId: string,
  rationale: MatchRationale,
  expandedTerms: string[],
) {
  const showRationale =
    expandedTerms.length > 0 && rationale.hitTerms.length > 0;
  if (entities.length === 0 && !isAISuggested && !showRationale) return null;
  return (
    <>
      {renderRationaleChips(candidateId, rationale, expandedTerms)}
      {/* -- AI first-pass row badge (DI-LEO-AI-209 / R-LEO-AI-197) -- */}
      {/* Surface AI provenance at the row level so reviewers can spot */}
      {/* pre-done candidates without opening the detail dialog. */}
      {isAISuggested && (
        <Tooltip title="AI first-pass proposed these entities. Confirm before approving.">
          <Chip
            size="small"
            label="AI suggested"
            color="info"
            data-testid="ai-suggested-chip"
            sx={{
              height: 20,
              fontSize: "0.68rem",
              fontWeight: 600,
              letterSpacing: "0.02em",
            }}
          />
        </Tooltip>
      )}
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
  search: string | undefined,
  expandedTerms: string[],
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
  const truncatedText = truncate(candidate.text);
  const matchRationale = computeMatchRationale(candidate.text, expandedTerms);
  const highlightTerms = collectHighlightTerms(
    search,
    matchRationale.hitTerms,
  );

  return {
    id,
    title:
      highlightTerms.length > 0 ? (
        <HighlightedText
          text={truncatedText}
          terms={highlightTerms}
          testId="candidate-row-highlight"
        />
      ) : (
        truncatedText
      ),
    chips: renderChips(
      entities,
      uncodedCount,
      candidate.rare_labels ?? undefined,
      maps,
      !!candidate.ai_first_pass_run_id,
      id,
      matchRationale,
      expandedTerms,
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

  const expandedTerms = useMemo(
    () => expandSearchTerms(props.search),
    [props.search],
  );

  const reviewItems: ReviewListItem[] = useMemo(
    () =>
      props.items.map((c) => buildItem(c, props, maps, props.search, expandedTerms)),
    [props, maps, expandedTerms],
  );

  return (
    <ReviewListCard
      items={reviewItems}
      density={listDensity}
      emptyState="No sentences to review yet. Run the pipeline to get started."
    />
  );
}
