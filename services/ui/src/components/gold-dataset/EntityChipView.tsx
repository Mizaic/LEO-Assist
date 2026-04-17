/**
 * EntityChipView -- presentational chip for a single extracted entity
 * and the async hook that resolves surface-form + subdomain membership
 * counts for each chip. Used by CandidateReviewList.
 */
"use client";

import { useEffect, useState } from "react";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import BookmarkIcon from "@mui/icons-material/Bookmark";
import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

import { fetchSurfaceForms } from "@/lib/api/legacy";
import { fetchConceptSubdomainMemberships } from "@/lib/analyticsApi";

import type { Entity } from "./goldDatasetTypes";
import { entityLabelColour } from "./goldDatasetUtils";

export interface ChipMaps {
  surface: Record<string, boolean>;
  domain: Record<string, number>;
}

export function makeEntityKey(entity: Entity): string {
  const code = entity.snomed_concept_id ?? "";
  const text = (entity.text || "").toLowerCase().trim();
  return `${code}::${text}`;
}

export function useEntityChipMaps(allEntities: Entity[]): ChipMaps {
  const [maps, setMaps] = useState<ChipMaps>({ surface: {}, domain: {} });

  useEffect(() => {
    let cancelled = false;
    const coded = allEntities
      .filter((entity) => entity.snomed_concept_id)
      .map((entity) => ({
        key: makeEntityKey(entity),
        conceptId: String(entity.snomed_concept_id),
        text: String(entity.text || "").trim(),
      }));
    if (coded.length === 0) {
      setMaps({ surface: {}, domain: {} });
      return () => undefined;
    }
    async function load() {
      const surface: Record<string, boolean> = {};
      const domain: Record<string, number> = {};
      await Promise.all(
        coded.map(async (row) => {
          try {
            const memberships = await fetchConceptSubdomainMemberships(
              row.conceptId,
            );
            domain[row.key] = memberships.filter((m) => m.is_member).length;
          } catch {
            domain[row.key] = 0;
          }
          try {
            const normalized = row.text.toLowerCase();
            if (!normalized) {
              surface[row.key] = false;
              return;
            }
            const result = await fetchSurfaceForms(
              normalized,
              row.conceptId,
              1,
              0,
            );
            surface[row.key] = Boolean(result.items?.length);
          } catch {
            surface[row.key] = false;
          }
        }),
      );
      if (cancelled) return;
      setMaps({ surface, domain });
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [allEntities]);

  return maps;
}

export function EntityChipView({
  entity,
  hasSurface,
  domainCount,
}: {
  entity: Entity;
  hasSurface: boolean;
  domainCount: number;
}) {
  const snomedId = entity.snomed_concept_id ?? null;
  const label = entity.snomed_term || entity.text || "Unknown term";
  const labelName = (entity.label || entity.semantic_tag || "").replace(
    /_/g,
    " ",
  );
  const accent = entityLabelColour(entity.label || entity.semantic_tag || "");
  const tip = snomedId
    ? `${label} (${snomedId})${labelName ? ` [${labelName}]` : ""}${hasSurface ? " - matched surface form" : " - no surface form yet"}${domainCount > 0 ? ` - in ${domainCount} domain(s)` : ""}`
    : `${entity.text}${labelName ? ` [${labelName}]` : ""} - needs a code`;
  const icon = snomedId
    ? domainCount > 0
      ? <BookmarkIcon sx={{ fontSize: "13px !important" }} />
      : <BookmarkBorderIcon sx={{ fontSize: "13px !important" }} />
    : <WarningAmberIcon sx={{ fontSize: "13px !important" }} />;
  return (
    <Tooltip title={tip}>
      <Chip
        size="small"
        variant={snomedId ? "outlined" : "filled"}
        color={snomedId ? "primary" : "warning"}
        icon={icon}
        label={label}
        sx={{
          maxWidth: 200,
          height: 22,
          fontSize: "0.72rem",
          borderLeft: `3px solid ${accent}`,
          "& .MuiChip-label": {
            overflow: "hidden",
            textOverflow: "ellipsis",
            px: 0.75,
          },
        }}
      />
    </Tooltip>
  );
}
