import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import BookmarkIcon from "@mui/icons-material/Bookmark";
import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditNoteIcon from "@mui/icons-material/EditNote";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { fetchSurfaceForms } from "@/lib/api/legacy";
import { fetchConceptSubdomainMemberships } from "@/lib/analyticsApi";
import type { Candidate, Entity } from "./goldDatasetTypes";
import { entityLabelColour, parseEntities, truncate } from "./goldDatasetUtils";
import RelationRow, { buildRelTriplets, hasMissingLinks } from "./RelationRow";

interface Props {
  item: Candidate;
  onClick: () => void;
  onMarkGold: (candidateId: string) => void;
  onDelete: (candidateId: string) => void;
  openingLabelEditor: boolean;
  markingGold: boolean;
  deleting: boolean;
}

function EntityChip({
  text,
  snomedTerm,
  snomedId,
  hasSurface,
  domainCount,
  entityLabel,
}: {
  text: string;
  snomedTerm: string | null;
  snomedId: string | null;
  hasSurface: boolean;
  domainCount: number;
  entityLabel: string;
}) {
  const labelColour = entityLabelColour(entityLabel);
  const displayLabel = snomedTerm || text || "Unknown term";
  const labelName = entityLabel ? entityLabel.replace(/_/g, " ") : "";
  const tip = snomedId
    ? `${displayLabel} (${snomedId})${labelName ? ` [${labelName}]` : ""}${hasSurface ? " - matched surface form" : " - no surface form yet"}${domainCount > 0 ? ` - in ${domainCount} domain(s)` : ""}`
    : `${text}${labelName ? ` [${labelName}]` : ""} - needs a code`;
  return (
    <Tooltip title={tip}>
      <Chip
        size="small"
        color={snomedId ? "primary" : "warning"}
        variant={snomedId ? "outlined" : "filled"}
        icon={
          snomedId ? (
            domainCount > 0 ? (
              <BookmarkIcon sx={{ fontSize: "13px !important" }} />
            ) : (
              <BookmarkBorderIcon sx={{ fontSize: "13px !important" }} />
            )
          ) : (
            <WarningAmberIcon sx={{ fontSize: "13px !important" }} />
          )
        }
        label={displayLabel}
        sx={{
          maxWidth: 200,
          height: 22,
          fontSize: "0.72rem",
          borderLeft: `3px solid ${labelColour}`,
          "& .MuiChip-label": {
            overflow: "hidden",
            textOverflow: "ellipsis",
            px: 0.75,
          },
          opacity: hasSurface || !snomedId ? 1 : 0.75,
        }}
      />
    </Tooltip>
  );
}

export default function CandidateCard({
  item,
  onClick,
  onMarkGold,
  onDelete,
  openingLabelEditor,
  markingGold,
  deleting,
}: Props) {
  const entities = useMemo(() => parseEntities(item.entities_json ?? null), [item.entities_json]);
  const [surfaceMap, setSurfaceMap] = useState<Record<string, boolean>>({});
  const [domainMap, setDomainMap] = useState<Record<string, number>>({});

  useEffect(() => {
    let cancelled = false;
    const coded = entities
      .filter((entity) => entity.snomed_concept_id)
      .map((entity) => ({
        key: `${entity.snomed_concept_id}::${(entity.text || "").toLowerCase().trim()}`,
        conceptId: String(entity.snomed_concept_id),
        text: String(entity.text || "").trim(),
      }));
    if (!coded.length) {
      setSurfaceMap({});
      setDomainMap({});
      return () => undefined;
    }
    async function load() {
      const surfaceNext: Record<string, boolean> = {};
      const domainNext: Record<string, number> = {};
      await Promise.all(
        coded.map(async (row) => {
          try {
            const memberships = await fetchConceptSubdomainMemberships(row.conceptId);
            domainNext[row.key] = memberships.filter((m) => m.is_member).length;
          } catch {
            domainNext[row.key] = 0;
          }
          try {
            const normalized = row.text.toLowerCase();
            if (!normalized) {
              surfaceNext[row.key] = false;
              return;
            }
            const result = await fetchSurfaceForms(normalized, row.conceptId, 1, 0);
            surfaceNext[row.key] = Boolean(result.items?.length);
          } catch {
            surfaceNext[row.key] = false;
          }
        }),
      );
      if (cancelled) return;
      setSurfaceMap(surfaceNext);
      setDomainMap(domainNext);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [entities]);

  const uncodedCount = entities.filter((entity) => !entity.snomed_concept_id).length;
  const isDone = item.status === "completed";
  const relTriplets = useMemo(() => buildRelTriplets(entities), [entities]);
  const missingLinks = useMemo(() => hasMissingLinks(entities), [entities]);

  return (
    <Box
      onClick={onClick}
      sx={{
        mb: 0.75,
        cursor: "pointer",
        border: "1px solid",
        borderColor: isDone ? "success.light" : "divider",
        borderLeft: "3px solid",
        borderLeftColor: isDone ? "success.main" : uncodedCount > 0 ? "warning.main" : "primary.light",
        borderRadius: 1.5,
        px: 1.5,
        py: 1,
        bgcolor: "background.paper",
        transition: "box-shadow 0.12s, border-color 0.12s",
        "&:hover": {
          boxShadow: "0 2px 8px rgba(0,0,0,0.10)",
          borderColor: isDone ? "success.main" : "primary.light",
        },
      }}
    >
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1.5}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="body2"
            sx={{ wordBreak: "break-word", lineHeight: 1.5, fontWeight: 500, color: "text.primary" }}
          >
            {truncate(item.text)}
          </Typography>

          {entities.length > 0 ? (
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
              {entities.slice(0, 4).map((entity, index) => {
                const key = `${entity.snomed_concept_id}::${(entity.text || "").toLowerCase().trim()}`;
                return (
                  <EntityChip
                    key={`${entity.text}-${index}`}
                    text={entity.text || ""}
                    snomedTerm={entity.snomed_term || null}
                    snomedId={entity.snomed_concept_id || null}
                    hasSurface={surfaceMap[key] ?? false}
                    domainCount={domainMap[key] ?? 0}
                    entityLabel={entity.label || entity.semantic_tag || ""}
                  />
                );
              })}
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
            </Stack>
          ) : (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              No terms found yet.
            </Typography>
          )}

          <RelationRow triplets={relTriplets} missing={missingLinks} />

          {item.rare_labels && item.rare_labels.length > 0 && (
            <Tooltip
              title={`Prioritised: these entity types have few gold examples — reviewing this record helps fill the gap (${item.rare_labels.join(", ")})`}
            >
              <Stack
                direction="row"
                spacing={0.5}
                flexWrap="wrap"
                useFlexGap
                sx={{ mt: 0.5 }}
              >
                <Chip
                  size="small"
                  icon={<TrendingUpIcon sx={{ fontSize: "13px !important" }} />}
                  label={`Rare: ${item.rare_labels.join(", ")}`}
                  sx={{
                    height: 20,
                    fontSize: "0.68rem",
                    bgcolor: "#f3e5f5",
                    color: "#6a1b9a",
                    border: "1px solid #ce93d8",
                    "& .MuiChip-icon": { color: "#6a1b9a" },
                    "& .MuiChip-label": { px: 0.75 },
                  }}
                />
              </Stack>
            </Tooltip>
          )}
        </Box>

        <Stack alignItems="flex-end" spacing={0.5} sx={{ flexShrink: 0 }}>
          {isDone ? (
            <Chip
              icon={<CheckCircleIcon sx={{ fontSize: "13px !important" }} />}
              label="Done"
              color="success"
              size="small"
              sx={{ height: 22, fontWeight: 600, fontSize: "0.72rem" }}
            />
          ) : (
            <Chip
              label="Needs review"
              color="warning"
              size="small"
              sx={{ height: 22, fontWeight: 600, fontSize: "0.72rem" }}
            />
          )}

          <Stack direction="row" spacing={0.5} sx={{ mt: 0.25 }}>
            <Tooltip title="Open to edit codes and terms">
              <span>
                <IconButton
                  size="small"
                  color="primary"
                  onClick={(event) => {
                    event.stopPropagation();
                    onClick();
                  }}
                  disabled={openingLabelEditor || markingGold || deleting}
                  sx={{
                    border: "1px solid",
                    borderColor: "primary.light",
                    borderRadius: 1,
                    p: 0.4,
                  }}
                >
                  {openingLabelEditor ? (
                    <CircularProgress size={12} />
                  ) : (
                    <EditNoteIcon sx={{ fontSize: 16 }} />
                  )}
                </IconButton>
              </span>
            </Tooltip>
            <Button
              size="small"
              variant="contained"
              color="success"
              onClick={(event) => {
                event.stopPropagation();
                onMarkGold(item.candidate_id);
              }}
              disabled={openingLabelEditor || markingGold || deleting}
              startIcon={markingGold ? <CircularProgress size={11} color="inherit" /> : undefined}
              sx={{ minWidth: 82, height: 28, fontSize: "0.72rem", px: 1 }}
            >
              Mark gold
            </Button>
            <Tooltip title="Remove this item">
              <span>
                <IconButton
                  size="small"
                  color="error"
                  onClick={(event) => {
                    event.stopPropagation();
                    onDelete(item.candidate_id);
                  }}
                  disabled={openingLabelEditor || markingGold || deleting}
                  sx={{
                    border: "1px solid",
                    borderColor: "error.light",
                    borderRadius: 1,
                    p: 0.4,
                  }}
                >
                  {deleting ? (
                    <CircularProgress size={12} />
                  ) : (
                    <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                  )}
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
        </Stack>
      </Stack>
    </Box>
  );
}
