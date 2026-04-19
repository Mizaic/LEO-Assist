/**
 * GoldLabelReviewList -- Wave E Phase 2a-iii
 *
 * Renders verified-gold and synthetic-gold rows through the shared
 * @leo/design-system ReviewListCard primitive so that the three
 * Training Data sub-tabs (Candidates / Verified gold / Synthetic) feel
 * like a single product instead of three different designs.
 *
 * Design decisions (per DI-LEO-AI-145):
 *   - Same EntityChipView as the candidate row so that the chip style,
 *     colour scheme, and surface-form / domain badges are identical
 *     across sub-tabs.
 *   - Single quiet QualityChip in the actions slot. Reset (destructive)
 *     hides behind the kebab so the row stays calm.
 *   - The whole row is the "Open" affordance via onSelect; clicking
 *     anywhere outside the kebab opens the detail dialog.
 *   - Tone accent on the left edge follows quality_score:
 *     positive >= 0.8, warning >= 0.5, danger < 0.5, neutral when null.
 *   - Density follows useDensity() (airy default, compact toggle).
 *
 * Supersedes the legacy components/gold-dataset/GoldLabelRow.tsx
 * (deleted in this changeset).
 */
"use client";

import { useMemo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";

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

import type { Entity, GoldLabel } from "./goldDatasetTypes";
import {
  assertionSummary,
  formatDate,
  parseEntities,
  truncate,
} from "./goldDatasetUtils";
import {
  EntityChipView,
  makeEntityKey,
  useEntityChipMaps,
  type ChipMaps,
} from "./EntityChipView";
import RelationRow, { buildRelTriplets, hasMissingLinks } from "./RelationRow";
import { GoldRowMenu, QualityChip } from "./GoldLabelRowActions";

interface Props {
  items: GoldLabel[];
  onOpen: (item: GoldLabel) => void;
  onReset: (item: GoldLabel) => void;
  resettingLabelId: string | null;
  /**
   * Reviewer's debounced search query (forwarded from
   * GoldDatasetPanel). When set, the row title highlights matched
   * terms and a "why this matched" chip row is rendered alongside
   * the existing entity chips so verified / synthetic gold rows
   * speak the same vocabulary as /care/encounters and the patient
   * drawer (DI-LEO-AI-523, UN-LEO-AI-096).
   */
  search?: string;
}

function toneFor(score: number | null): ReviewListItem["tone"] {
  if (score === null) return "neutral";
  if (score >= 0.8) return "positive";
  if (score >= 0.5) return "warning";
  return "danger";
}

function renderRationaleChips(
  labelId: string,
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
          key={`${labelId}-mr-${idx}-${term}`}
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
  maps: ChipMaps,
  labelId: string,
  rationale: MatchRationale,
  expandedTerms: string[],
) {
  const showRationale =
    expandedTerms.length > 0 && rationale.hitTerms.length > 0;
  if (entities.length === 0 && !showRationale) return null;
  return (
    <>
      {renderRationaleChips(labelId, rationale, expandedTerms)}
      {entities.slice(0, 5).map((entity, index) => (
        <EntityChipView
          key={`${entity.text}-${index}`}
          entity={entity}
          hasSurface={maps.surface[makeEntityKey(entity)] ?? false}
          domainCount={maps.domain[makeEntityKey(entity)] ?? 0}
        />
      ))}
      {entities.length > 5 && (
        <Chip
          size="small"
          variant="outlined"
          label={`+${entities.length - 5} more`}
          sx={{ height: 22, fontSize: "0.7rem" }}
        />
      )}
    </>
  );
}

function renderMeta(item: GoldLabel, entities: Entity[]) {
  const summary = assertionSummary(entities);
  const relTriplets = buildRelTriplets(entities);
  const missingLinks = hasMissingLinks(entities);
  const verifier = item.verified_by ? item.verified_by.split("@")[0] : null;
  const stamp = formatDate(item.verified_at ?? item.updated_at);
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.75 }}>
        {summary && (
          <Typography
            sx={{
              fontSize: "0.68rem",
              color: "text.secondary",
              fontStyle: "italic",
              lineHeight: 1.3,
            }}
          >
            {summary}
          </Typography>
        )}
        {summary && (verifier || stamp) && (
          <Box component="span" sx={{ color: "text.disabled", fontSize: "0.66rem" }}>
            -
          </Box>
        )}
        {verifier && (
          <Typography sx={{ fontSize: "0.68rem", color: "text.secondary" }}>
            {verifier}
          </Typography>
        )}
        {stamp && (
          <Typography sx={{ fontSize: "0.66rem", color: "text.disabled" }}>
            {stamp}
          </Typography>
        )}
      </Box>
      {(relTriplets.length > 0 || missingLinks) && (
        <RelationRow triplets={relTriplets} missing={missingLinks} />
      )}
    </Box>
  );
}

function buildItem(
  item: GoldLabel,
  handlers: Props,
  maps: ChipMaps,
  search: string | undefined,
  expandedTerms: string[],
): ReviewListItem {
  const entities = parseEntities(item.entities_json);
  const id = item.label_id;
  const resetting = handlers.resettingLabelId === id;
  const truncatedText = truncate(item.text);
  const matchRationale = computeMatchRationale(item.text, expandedTerms);
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
    chips: renderChips(entities, maps, id, matchRationale, expandedTerms),
    meta: renderMeta(item, entities),
    actions: (
      <>
        <QualityChip score={item.quality_score} />
        <GoldRowMenu
          labelId={id}
          resetting={resetting}
          disabled={resetting}
          onReset={() => handlers.onReset(item)}
        />
      </>
    ),
    tone: toneFor(item.quality_score),
    onSelect: () => handlers.onOpen(item),
    selected: false,
  };
}

export default function GoldLabelReviewList(props: Props) {
  const { density } = useDensity();
  const listDensity = density === "compact" ? "compact" : "comfortable";

  const allEntities = useMemo(
    () => props.items.flatMap((item) => parseEntities(item.entities_json)),
    [props.items],
  );
  const maps = useEntityChipMaps(allEntities);

  const expandedTerms = useMemo(
    () => expandSearchTerms(props.search),
    [props.search],
  );

  const reviewItems: ReviewListItem[] = useMemo(
    () =>
      props.items.map((item) =>
        buildItem(item, props, maps, props.search, expandedTerms),
      ),
    [props, maps, expandedTerms],
  );

  return (
    <ReviewListCard
      items={reviewItems}
      density={listDensity}
      emptyState="No verified examples yet. Mark sentences as gold and they will show up here."
    />
  );
}
