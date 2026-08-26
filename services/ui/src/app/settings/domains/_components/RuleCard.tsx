/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-F499E476
 *   DI: DI-C34A2990
 *   VT: VT-6ADE2398
 */
"use client";

import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { useEffect, useMemo, useRef, useState } from "react";

import { searchTerms } from "@/lib/api";
import type { CompletenessConceptGroup } from "@/lib/analyticsApi";
import { themeForTag } from "@/lib/nerAnnotation";

export type RuleConceptMeta = {
  term?: string;
  semantic_tag?: string;
};

type SnomedHit = {
  snomed_concept_id: string;
  term: string;
  semantic_tag?: string;
};

const SEARCH_DEBOUNCE_MS = 250;

function formatCategoryLabel(cat: string): string {
  return cat.replace(/_/g, " ");
}

function truncateTerm(term: string, max = 36): string {
  if (term.length <= max) return term;
  return `${term.slice(0, max - 1)}...`;
}

function chipTooltip(id: number, meta?: RuleConceptMeta): string {
  const parts: string[] = [];
  if (meta?.term) parts.push(meta.term);
  parts.push(`SNOMED ${id}`);
  if (meta?.semantic_tag) parts.push(formatCategoryLabel(meta.semantic_tag));
  return parts.join(" - ");
}

function SemanticCategoryChip({
  cat,
  canEdit,
  onDelete,
}: {
  cat: string;
  canEdit: boolean;
  onDelete?: () => void;
}) {
  const theme = themeForTag(cat);
  return (
    <Tooltip title={cat} arrow>
      <Chip
        label={formatCategoryLabel(cat)}
        size="small"
        onDelete={canEdit ? onDelete : undefined}
        sx={{
          height: 24,
          fontSize: "0.75rem",
          bgcolor: theme.bg,
          border: "1px solid",
          borderColor: theme.border,
          maxWidth: 220,
          "& .MuiChip-label": { overflow: "hidden", textOverflow: "ellipsis" },
        }}
      />
    </Tooltip>
  );
}

function SnomedConceptChip({
  id,
  meta,
  canEdit,
  onDelete,
}: {
  id: number;
  meta?: RuleConceptMeta;
  canEdit: boolean;
  onDelete?: () => void;
}) {
  const theme = themeForTag(meta?.semantic_tag);
  const label = meta?.term ? truncateTerm(meta.term) : String(id);
  return (
    <Tooltip title={chipTooltip(id, meta)} arrow>
      <Chip
        label={label}
        size="small"
        onDelete={canEdit ? onDelete : undefined}
        sx={{
          height: 24,
          fontSize: "0.75rem",
          bgcolor: theme.bg,
          border: "1px solid",
          borderColor: theme.border,
          maxWidth: 280,
          "& .MuiChip-label": { overflow: "hidden", textOverflow: "ellipsis" },
        }}
      />
    </Tooltip>
  );
}

function RuleSnomedSearch({
  idx,
  existingIds,
  semanticFilter,
  onAdd,
}: {
  idx: number;
  existingIds: number[];
  semanticFilter: string[];
  onAdd: (id: number, meta: RuleConceptMeta) => void;
}) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<SnomedHit[]>([]);
  const [loading, setLoading] = useState(false);
  const reqRef = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setOptions([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const handle = window.setTimeout(() => {
      const myReq = ++reqRef.current;
      void searchTerms(
        trimmed,
        15,
        semanticFilter.length > 0 ? semanticFilter : undefined,
      )
        .then((rows) => {
          if (myReq !== reqRef.current) return;
          setOptions(
            rows.filter((r) => !existingIds.includes(parseInt(r.snomed_concept_id, 10))),
          );
        })
        .catch(() => {
          if (myReq !== reqRef.current) return;
          setOptions([]);
        })
        .finally(() => {
          if (myReq !== reqRef.current) return;
          setLoading(false);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [query, semanticFilter, existingIds]);

  return (
    <Autocomplete
      size="small"
      fullWidth
      options={options}
      value={null}
      inputValue={query}
      onInputChange={(_, next) => setQuery(next)}
      onChange={(_, hit) => {
        if (!hit) return;
        const id = parseInt(hit.snomed_concept_id, 10);
        if (!Number.isFinite(id) || existingIds.includes(id)) return;
        onAdd(id, { term: hit.term, semantic_tag: hit.semantic_tag });
        setQuery("");
        setOptions([]);
      }}
      filterOptions={(opts) => opts}
      loading={loading}
      autoHighlight
      clearOnBlur
      getOptionLabel={(opt) => opt.term || opt.snomed_concept_id}
      isOptionEqualToValue={(a, b) => a.snomed_concept_id === b.snomed_concept_id}
      noOptionsText={
        query.trim().length < 2
          ? "Type at least 2 letters to search"
          : "No SNOMED terms match"
      }
      slotProps={{
        popper: { placement: "bottom-start" },
        paper: { sx: { minWidth: 320 } },
      }}
      renderOption={(props, hit) => {
        const { key: muiKey, ...liProps } = props as typeof props & { key?: string | number };
        const theme = themeForTag(hit.semantic_tag);
        return (
          <Box
            component="li"
            key={muiKey ?? hit.snomed_concept_id}
            {...liProps}
            sx={{ display: "block !important", py: 0.75 }}
          >
            <Typography variant="body2" sx={{ fontWeight: 500, lineHeight: 1.2 }}>
              {hit.term || "(no term)"}
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.25 }}>
              <Typography variant="caption" color="text.secondary">
                {hit.snomed_concept_id}
              </Typography>
              {hit.semantic_tag && (
                <Chip
                  label={formatCategoryLabel(hit.semantic_tag)}
                  size="small"
                  sx={{
                    height: 18,
                    fontSize: "0.65rem",
                    bgcolor: theme.bg,
                    border: "1px solid",
                    borderColor: theme.border,
                  }}
                />
              )}
            </Box>
          </Box>
        );
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          placeholder="Search SNOMED terms..."
          inputProps={{
            ...params.inputProps,
            "aria-label": `Search SNOMED terms for rule ${idx + 1}`,
          }}
          InputProps={{
            ...params.InputProps,
            endAdornment: (
              <>
                {loading ? (
                  <CircularProgress size={16} aria-label="Searching SNOMED terms" />
                ) : null}
                {params.InputProps.endAdornment}
              </>
            ),
          }}
        />
      )}
    />
  );
}

function kindSelectValue(group: CompletenessConceptGroup): string {
  const kind = String(group.kind || "");
  if (kind === "one_of" || kind === "n_of" || kind === "if_then") return kind;
  return group.required ? "required" : "optional";
}

function kindSelectPatch(value: string): Partial<CompletenessConceptGroup> {
  if (value === "optional") return { required: false, kind: "optional" };
  if (value === "required") return { required: true, kind: "mandatory" };
  return { required: true, kind: value };
}

export interface RuleCardProps {
  group: CompletenessConceptGroup;
  idx: number;
  canEdit: boolean;
  allSemanticTags: string[];
  conceptMeta: Record<number, RuleConceptMeta>;
  onRegisterConceptMeta: (id: number, meta: RuleConceptMeta) => void;
  onUpdate: (patch: Partial<CompletenessConceptGroup>) => void;
  onDelete: () => void;
}

export default function RuleCard({
  group,
  idx,
  canEdit,
  allSemanticTags,
  conceptMeta,
  onRegisterConceptMeta,
  onUpdate,
  onDelete,
}: RuleCardProps) {
  const [nameValue, setNameValue] = useState(group.name);

  const categoryOptions = useMemo(
    () => allSemanticTags.filter((t) => !group.semantic_categories.includes(t)),
    [allSemanticTags, group.semantic_categories],
  );

  const handleAddConcept = (id: number, meta: RuleConceptMeta) => {
    if (group.concept_ids.includes(id)) return;
    onRegisterConceptMeta(id, meta);
    onUpdate({ concept_ids: [...group.concept_ids, id] });
  };

  return (
    <Box
      sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1.5 }}
      data-testid={`rule-card-${idx}`}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        {canEdit ? (
          <TextField
            size="small"
            value={nameValue}
            onChange={(e) => setNameValue(e.target.value)}
            onBlur={() => {
              if (nameValue !== group.name) onUpdate({ name: nameValue });
            }}
            variant="standard"
            inputProps={{ "aria-label": `Rule ${idx + 1} name` }}
            sx={{ flex: 1, "& input": { fontWeight: 600, fontSize: "0.875rem" } }}
          />
        ) : (
          <Typography variant="subtitle2" sx={{ flex: 1 }}>
            {group.name}
          </Typography>
        )}

        <FormControl size="small" sx={{ minWidth: 110 }}>
          <Select
            value={kindSelectValue(group)}
            onChange={(e) => onUpdate(kindSelectPatch(e.target.value))}
            disabled={!canEdit}
            sx={{ fontSize: "0.75rem", height: 28 }}
          >
            <MenuItem value="required">Required</MenuItem>
            <MenuItem value="optional">Optional</MenuItem>
            <MenuItem value="one_of">1 of these</MenuItem>
            <MenuItem value="n_of">At least N</MenuItem>
            <MenuItem value="if_then">If-then</MenuItem>
          </Select>
        </FormControl>

        {canEdit && (
          <IconButton
            size="small"
            color="error"
            onClick={onDelete}
            aria-label={`Delete rule ${idx + 1}`}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        )}
      </Box>

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        <Box>
          <Typography variant="caption" color="text.secondary">
            SNOMED concepts
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}>
            {group.concept_ids.map((id) => (
              <SnomedConceptChip
                key={id}
                id={id}
                meta={conceptMeta[id]}
                canEdit={canEdit}
                onDelete={
                  canEdit
                    ? () => onUpdate({ concept_ids: group.concept_ids.filter((c) => c !== id) })
                    : undefined
                }
              />
            ))}
            {group.concept_ids.length === 0 && !canEdit && (
              <Typography variant="caption" color="text.secondary">
                None
              </Typography>
            )}
          </Box>
          {canEdit && (
            <Box sx={{ mt: 0.75 }}>
              <RuleSnomedSearch
                idx={idx}
                existingIds={group.concept_ids}
                semanticFilter={group.semantic_categories}
                onAdd={handleAddConcept}
              />
            </Box>
          )}
        </Box>

        <Box>
          <Typography variant="caption" color="text.secondary">
            Semantic categories
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5, alignItems: "center" }}>
            {group.semantic_categories.map((cat) => (
              <SemanticCategoryChip
                key={cat}
                cat={cat}
                canEdit={canEdit}
                onDelete={() =>
                  onUpdate({
                    semantic_categories: group.semantic_categories.filter((c) => c !== cat),
                  })
                }
              />
            ))}
            {canEdit && categoryOptions.length > 0 && (
              <Autocomplete
                size="small"
                options={categoryOptions}
                value={null}
                onChange={(_, v) => {
                  if (v) onUpdate({ semantic_categories: [...group.semantic_categories, v] });
                }}
                getOptionLabel={formatCategoryLabel}
                slotProps={{
                  popper: { placement: "bottom-start" },
                  paper: { sx: { minWidth: 280 } },
                }}
                sx={{ minWidth: 220, flex: 1, maxWidth: 360 }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    placeholder="Add category"
                    inputProps={{
                      ...params.inputProps,
                      "aria-label": `Add semantic category to rule ${idx + 1}`,
                    }}
                  />
                )}
                renderOption={(props, opt) => {
                  const { key: muiKey, ...liProps } = props as typeof props & {
                    key?: string | number;
                  };
                  const theme = themeForTag(opt);
                  return (
                    <Box
                      component="li"
                      key={muiKey ?? opt}
                      {...liProps}
                      sx={{ display: "flex", alignItems: "center", gap: 1 }}
                    >
                      <Box
                        sx={{
                          width: 10,
                          height: 10,
                          borderRadius: "50%",
                          bgcolor: theme.border,
                          flexShrink: 0,
                        }}
                      />
                      <Typography variant="body2">{formatCategoryLabel(opt)}</Typography>
                    </Box>
                  );
                }}
              />
            )}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
