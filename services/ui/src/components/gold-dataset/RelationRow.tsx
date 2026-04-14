/**
 * Shared relation-summary row used by CandidateCard and GoldLabelRow.
 *
 * Renders compact source -> [rel type] -> target triplets from entity
 * relations, plus a "No links" warning when linkable entity pairs exist
 * but no relation has been set.
 */
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import LinkOffIcon from "@mui/icons-material/LinkOff";
import type { Entity } from "./goldDatasetTypes";
import { entityLabelColour, truncate } from "./goldDatasetUtils";

export const REL_TYPE_LABEL: Record<string, string> = {
  finding_site: "site",
  procedure_site: "site",
  interprets: "interprets",
  qualifies: "qualifies",
  associated_finding: "associated",
  component_of: "component of",
};

// All entity types that can be the SOURCE of any relation in policy.
const LINKABLE_SOURCE_LABELS = new Set([
  "finding",
  "disorder",
  "situation",
  "procedure",
  "qualifier_value",
  "observable_entity",
]);

// All entity types that can be the TARGET of any relation in policy.
const LINKABLE_TARGET_LABELS = new Set([
  "body_structure",
  "body structure",
  "observable_entity",
  "procedure",
  "finding",
  "disorder",
]);

export interface RelTriplet {
  sourceText: string;
  sourceLabel: string;
  relType: string;
  targetText: string;
  targetLabel: string;
}

export function buildRelTriplets(entities: Entity[]): RelTriplet[] {
  const triplets: RelTriplet[] = [];
  for (const entity of entities) {
    for (const rel of entity.relations ?? []) {
      const target = entities[rel.target_idx];
      if (!target) continue;
      triplets.push({
        sourceText: entity.text,
        sourceLabel: entity.label ?? entity.semantic_tag ?? "",
        relType: rel.type,
        targetText: target.text,
        targetLabel: target.label ?? target.semantic_tag ?? "",
      });
    }
  }
  return triplets;
}

export function hasMissingLinks(entities: Entity[]): boolean {
  for (const entity of entities) {
    const srcLabel = (entity.label ?? entity.semantic_tag ?? "")
      .toLowerCase()
      .replace(/ /g, "_");
    if (!LINKABLE_SOURCE_LABELS.has(srcLabel)) continue;
    if ((entity.relations ?? []).length > 0) continue;
    const hasPotentialTarget = entities.some((other) => {
      const tgtLabel = (other.label ?? other.semantic_tag ?? "")
        .toLowerCase()
        .replace(/ /g, "_");
      return LINKABLE_TARGET_LABELS.has(tgtLabel);
    });
    if (hasPotentialTarget) return true;
  }
  return false;
}

interface Props {
  triplets: RelTriplet[];
  missing: boolean;
}

export default function RelationRow({ triplets, missing }: Props) {
  if (triplets.length === 0 && !missing) return null;
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
      {triplets.slice(0, 3).map((t, i) => (
        <Tooltip
          key={i}
          title={`${t.sourceText} \u2192 ${REL_TYPE_LABEL[t.relType] ?? t.relType} \u2192 ${t.targetText}`}
        >
          <Box
            component="span"
            sx={{
              display: "inline-flex",
              alignItems: "center",
              gap: "2px",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1,
              px: 0.6,
              py: "1px",
              fontSize: "0.68rem",
              color: "text.secondary",
              bgcolor: "grey.50",
              whiteSpace: "nowrap",
            }}
          >
            <Box
              component="span"
              sx={{
                maxWidth: 80,
                overflow: "hidden",
                textOverflow: "ellipsis",
                color: entityLabelColour(t.sourceLabel),
                fontWeight: 600,
              }}
            >
              {truncate(t.sourceText, 22)}
            </Box>
            <Box component="span" sx={{ color: "text.disabled", mx: "2px" }}>
              {"\u2192"}
            </Box>
            <Box
              component="span"
              sx={{
                px: 0.4,
                borderRadius: 0.5,
                bgcolor: "grey.200",
                fontSize: "0.63rem",
                color: "text.secondary",
              }}
            >
              {REL_TYPE_LABEL[t.relType] ?? t.relType}
            </Box>
            <Box component="span" sx={{ color: "text.disabled", mx: "2px" }}>
              {"\u2192"}
            </Box>
            <Box
              component="span"
              sx={{
                maxWidth: 80,
                overflow: "hidden",
                textOverflow: "ellipsis",
                color: entityLabelColour(t.targetLabel),
                fontWeight: 600,
              }}
            >
              {truncate(t.targetText, 22)}
            </Box>
          </Box>
        </Tooltip>
      ))}
      {triplets.length > 3 && (
        <Typography variant="caption" color="text.disabled" sx={{ alignSelf: "center" }}>
          +{triplets.length - 3} more
        </Typography>
      )}
      {missing && (
        <Tooltip title="One or more terms could be linked (body site, observable, procedure, or another finding) but have no relation set">
          <Chip
            size="small"
            icon={<LinkOffIcon sx={{ fontSize: "13px !important" }} />}
            label="No links"
            sx={{
              height: 20,
              fontSize: "0.68rem",
              bgcolor: "#fff3e0",
              color: "#e65100",
              border: "1px solid #ffcc80",
              "& .MuiChip-icon": { color: "#e65100" },
              "& .MuiChip-label": { px: 0.75 },
            }}
          />
        </Tooltip>
      )}
    </Stack>
  );
}
