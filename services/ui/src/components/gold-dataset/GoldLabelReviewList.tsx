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
}

function toneFor(score: number | null): ReviewListItem["tone"] {
  if (score === null) return "neutral";
  if (score >= 0.8) return "positive";
  if (score >= 0.5) return "warning";
  return "danger";
}

function renderChips(entities: Entity[], maps: ChipMaps) {
  if (entities.length === 0) return null;
  return (
    <>
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

function buildItem(item: GoldLabel, handlers: Props, maps: ChipMaps): ReviewListItem {
  const entities = parseEntities(item.entities_json);
  const id = item.label_id;
  const resetting = handlers.resettingLabelId === id;
  return {
    id,
    title: truncate(item.text),
    chips: renderChips(entities, maps),
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

  const reviewItems: ReviewListItem[] = useMemo(
    () => props.items.map((item) => buildItem(item, props, maps)),
    [props, maps],
  );

  return (
    <ReviewListCard
      items={reviewItems}
      density={listDensity}
      emptyState="No verified examples yet. Mark sentences as gold and they will show up here."
    />
  );
}
