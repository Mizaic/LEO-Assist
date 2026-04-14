import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import VerifiedIcon from "@mui/icons-material/Verified";
import type { Entity, GoldLabel } from "./goldDatasetTypes";
import { assertionColor, assertionSummary, entityLabelColour, formatDate, isNonPresent, parseEntities, truncate } from "./goldDatasetUtils";
import RelationRow, { buildRelTriplets, hasMissingLinks } from "./RelationRow";

function qualityColor(score: number | null): "success" | "warning" | "error" | "default" {
  if (score === null) return "default";
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  return "error";
}

function EntityPill({ entity }: { entity: Entity }) {
  const nonPresent = isNonPresent(entity.assertion);
  const assertColor = assertionColor(entity.assertion);
  const typeColour = entityLabelColour(entity.label ?? entity.semantic_tag);
  const labelName = (entity.label ?? entity.semantic_tag ?? "").replace(/_/g, " ");

  const tipParts = [entity.label ?? entity.semantic_tag];
  if (nonPresent) tipParts.push(entity.assertion ?? "");
  if (entity.body_site_term) tipParts.push(`Site: ${entity.body_site_term}`);
  if (entity.snomed_term) tipParts.push(`SNOMED: ${entity.snomed_term}`);

  // For non-present entities keep assertion coloring; for present ones use
  // a very light tint derived from the entity label colour.
  const bgStyle = nonPresent
    ? { bgcolor: `${assertColor}.50`, borderColor: `${assertColor}.200` }
    : { bgcolor: `${typeColour}18`, borderColor: `${typeColour}40` };

  return (
    <Tooltip title={tipParts.filter(Boolean).join(" - ")}>
      <Box
        sx={{
          display: "inline-flex",
          flexDirection: "column",
          alignItems: "flex-start",
          ...bgStyle,
          border: "1px solid",
          borderLeft: `3px solid ${typeColour}`,
          borderRadius: 1.5,
          px: 1,
          py: 0.5,
          cursor: "default",
          minWidth: 80,
          maxWidth: 180,
        }}
      >
        {labelName && (
          <Typography
            sx={{
              fontSize: "0.58rem",
              fontWeight: 700,
              color: typeColour,
              letterSpacing: 0.4,
              textTransform: "uppercase",
              lineHeight: 1.2,
              mb: 0.15,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              maxWidth: "100%",
            }}
          >
            {labelName}
          </Typography>
        )}
        <Typography
          sx={{
            fontSize: "0.75rem",
            fontWeight: 600,
            color: nonPresent ? `${assertColor}.dark` : "text.primary",
            lineHeight: 1.3,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: "100%",
          }}
        >
          {entity.text}
        </Typography>
        {entity.snomed_concept_id ? (
          <Typography
            sx={{
              fontSize: "0.62rem",
              color: "text.secondary",
              lineHeight: 1.3,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              maxWidth: "100%",
            }}
          >
            {entity.snomed_term || entity.text}
            <Box component="span" sx={{ fontFamily: "monospace", color: "text.disabled", ml: 0.5 }}>
              {entity.snomed_concept_id}
            </Box>
          </Typography>
        ) : (
          <Typography sx={{ fontSize: "0.62rem", color: "warning.main", fontStyle: "italic", lineHeight: 1.3 }}>
            no code
          </Typography>
        )}
      </Box>
    </Tooltip>
  );
}

interface Props {
  item: GoldLabel;
  onClick: () => void;
  onReset: () => void;
  resetting: boolean;
}

export default function GoldLabelRow({ item, onClick, onReset, resetting }: Props) {
  const entities = parseEntities(item.entities_json);
  const summary = assertionSummary(entities);
  const relTriplets = buildRelTriplets(entities);
  const missingLinks = hasMissingLinks(entities);

  return (
    <Box
      onClick={onClick}
      sx={{
        mb: 0.75,
        cursor: "pointer",
        border: "1px solid",
        borderColor: "success.light",
        borderLeft: "3px solid",
        borderLeftColor: "success.main",
        borderRadius: 1.5,
        px: 1.5,
        py: 1,
        bgcolor: "background.paper",
        transition: "box-shadow 0.12s",
        "&:hover": { boxShadow: "0 2px 8px rgba(0,0,0,0.10)", borderColor: "success.main" },
      }}
    >
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1.5}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {summary && (
            <Typography sx={{ fontSize: "0.7rem", color: "text.secondary", fontStyle: "italic", mb: 0.25 }}>
              {summary}
            </Typography>
          )}

          <Typography
            variant="body2"
            sx={{ wordBreak: "break-word", mb: entities.length > 0 ? 0.75 : 0, lineHeight: 1.5, color: "text.primary", fontWeight: 500 }}
          >
            {truncate(item.text)}
          </Typography>

            {entities.length > 0 && (
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {entities.slice(0, 6).map((entity, index) => (
                  <EntityPill key={`${entity.text}-${index}`} entity={entity} />
                ))}
                <RelationRow triplets={relTriplets} missing={missingLinks} />
                {entities.length > 6 && (
                  <Box
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      px: 0.75,
                      border: "1px solid",
                      borderColor: "divider",
                      borderRadius: 1.5,
                      bgcolor: "action.hover",
                    }}
                  >
                    <Typography sx={{ fontSize: "0.72rem", color: "text.secondary", fontWeight: 500 }}>
                      +{entities.length - 6} more
                    </Typography>
                  </Box>
                )}
              </Stack>
            )}
          </Box>

          <Stack alignItems="flex-end" spacing={0.5} sx={{ flexShrink: 0, minWidth: 96 }}>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <Chip
                icon={<VerifiedIcon sx={{ fontSize: "13px !important" }} />}
                label={item.quality_score !== null ? `${Math.round(item.quality_score * 100)}%` : "Verified"}
                color={qualityColor(item.quality_score)}
                size="small"
                sx={{ fontWeight: 700, fontSize: "0.72rem", height: 22 }}
              />
              <Tooltip title="Remove this gold label and put it back in the queue">
                <span>
                  <IconButton
                    size="small"
                    color="error"
                    onClick={(event) => {
                      event.stopPropagation();
                      onReset();
                    }}
                    disabled={resetting}
                    sx={{ p: 0.3 }}
                  >
                    {resetting ? <CircularProgress size={13} /> : <DeleteOutlineIcon sx={{ fontSize: 16 }} />}
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
            {item.verified_by && (
              <Typography sx={{ fontSize: "0.67rem", color: "text.secondary", textAlign: "right", lineHeight: 1.3 }}>
                {item.verified_by.split("@")[0]}
              </Typography>
            )}
            <Typography sx={{ fontSize: "0.64rem", color: "text.disabled", textAlign: "right", lineHeight: 1.3 }}>
              {formatDate(item.verified_at ?? item.updated_at)}
            </Typography>
          </Stack>
        </Stack>
    </Box>
  );
}
