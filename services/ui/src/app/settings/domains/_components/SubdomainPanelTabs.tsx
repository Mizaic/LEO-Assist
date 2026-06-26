/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2340F614
 *   Also implements: DO-F499E476
 *   DI: DI-4885D9FF, DI-C34A2990, DI-2C33BE30
 *   VT: VT-6ADE2398
 */
"use client";

import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DownloadIcon from "@mui/icons-material/Download";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { useCallback, useEffect, useMemo, useState } from "react";

import { searchTerms } from "@/lib/api";
import type {
  SubdomainDetail,
  CompletenessConceptGroup,
  DomainUseCase,
  SubdomainConcept,
} from "@/lib/analyticsApi";
import { fetchBenchmarkKeys } from "@/lib/analyticsApi";
import { ASSERTION_OPTIONS, MILESTONE_OPTIONS } from "./domainConstants";
import RuleCard, { type RuleConceptMeta } from "./RuleCard";
import SubdomainConceptSearchPanel from "./SubdomainConceptSearchPanel";

// -- Use-case display helpers -----------------------------------------------

const USE_CASE_LABELS: Record<DomainUseCase, string> = {
  extraction: "Targeted extraction",
  completeness: "Minimum dataset",
  analytics: "Population health analytics",
  episode_detection: "Episode detection",
};

const ALL_USE_CASES: DomainUseCase[] = [
  "extraction",
  "completeness",
  "analytics",
  "episode_detection",
];

// -- Overview tab -------------------------------------------------------------

interface OverviewTabProps {
  configSub: SubdomainDetail;
  allSemanticTags: string[];
  canEditDomains: boolean;
  submitting: boolean;
  onUpdate: (updates: {
    description?: string;
    milestone_type?: string;
    time_window_months?: number;
    semantic_tags?: string[];
    assertion_filter?: string[];
    use_cases?: DomainUseCase[];
  }) => Promise<void>;
  onClearSearch: () => void;
  onSaved: () => void;
}

export function OverviewTab({
  configSub,
  allSemanticTags,
  canEditDomains,
  submitting,
  onUpdate,
  onClearSearch,
  onSaved,
}: OverviewTabProps) {
  const [description, setDescription] = useState(configSub.description ?? "");
  const [useCases, setUseCases] = useState<DomainUseCase[]>(configSub.use_cases ?? []);
  const [milestoneType, setMilestoneType] = useState(configSub.milestone_type ?? "");
  const [timeWindow, setTimeWindow] = useState(
    configSub.time_window_months != null ? String(configSub.time_window_months) : "",
  );
  const [assertionFilter, setAssertionFilter] = useState(
    (configSub as { assertion_filter?: string[] }).assertion_filter ?? [],
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDescription(configSub.description ?? "");
    setUseCases(configSub.use_cases ?? []);
    setMilestoneType(configSub.milestone_type ?? "");
    setTimeWindow(
      configSub.time_window_months != null ? String(configSub.time_window_months) : "",
    );
    setAssertionFilter(
      (configSub as { assertion_filter?: string[] }).assertion_filter ?? [],
    );
  }, [configSub]);

  const showEpisodeFields = useCases.includes("episode_detection");

  const save = async () => {
    setSaving(true);
    try {
      await onUpdate({
        description,
        use_cases: useCases,
        milestone_type: showEpisodeFields ? milestoneType || undefined : undefined,
        time_window_months:
          showEpisodeFields && timeWindow ? parseInt(timeWindow, 10) : undefined,
        assertion_filter: assertionFilter,
      });
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <TextField
        size="small"
        label="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        disabled={!canEditDomains}
        multiline
        rows={2}
      />

      <Autocomplete
        multiple
        size="small"
        options={ALL_USE_CASES}
        value={useCases}
        getOptionLabel={(opt) => USE_CASE_LABELS[opt] ?? opt}
        onChange={(_, v) => {
          setUseCases(v as DomainUseCase[]);
          if (!v.includes("episode_detection")) {
            setMilestoneType("");
            setTimeWindow("");
            onClearSearch();
          }
        }}
        disabled={!canEditDomains}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Purpose"
            helperText="What is this subdomain used for?"
          />
        )}
      />

      {showEpisodeFields && (
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
          <FormControl size="small" sx={{ minWidth: 180, flex: 1 }}>
            <InputLabel id="milestone-label">Milestone type</InputLabel>
            <Select
              labelId="milestone-label"
              label="Milestone type"
              value={milestoneType}
              onChange={(e) => setMilestoneType(e.target.value)}
              disabled={!canEditDomains}
            >
              <MenuItem value="">
                <em>None</em>
              </MenuItem>
              {MILESTONE_OPTIONS.map((opt) => (
                <MenuItem key={opt} value={opt}>
                  {opt.replace(/_/g, " ")}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            type="number"
            label="Time window (months)"
            value={timeWindow}
            onChange={(e) => setTimeWindow(e.target.value)}
            sx={{ minWidth: 140 }}
            disabled={!canEditDomains}
          />
        </Box>
      )}

      <Autocomplete
        multiple
        size="small"
        options={[...ASSERTION_OPTIONS]}
        value={assertionFilter}
        onChange={(_, v) =>
          setAssertionFilter(v.filter((t): t is string => typeof t === "string"))
        }
        disabled={!canEditDomains}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Assertion filter"
            helperText="Leave blank to accept any assertion"
          />
        )}
      />

      {canEditDomains && (
        <Button
          variant="contained"
          size="small"
          onClick={() => void save()}
          disabled={saving || submitting}
          startIcon={saving ? <CircularProgress size={14} /> : null}
        >
          {saving ? "Saving..." : "Save overview"}
        </Button>
      )}
    </Box>
  );
}

// -- Concepts tab -------------------------------------------------------------

interface ConceptsTabProps {
  configSub: SubdomainDetail;
  canEditDomains: boolean;
  submitting: boolean;
  exportLoading: "concepts" | "expanded" | null;
  allSemanticTags: string[];
  benchmarkKeys: string[];
  onExport: (includeChildren: boolean) => void;
  onRemoveConcept: (conceptId: number) => void;
  searchPanelProps: React.ComponentProps<typeof SubdomainConceptSearchPanel>;
}

export function ConceptsTab({
  configSub,
  canEditDomains,
  submitting,
  exportLoading,
  allSemanticTags,
  benchmarkKeys,
  onExport,
  onRemoveConcept,
  searchPanelProps,
}: ConceptsTabProps) {
  const [activeFilter, setActiveFilter] = useState<string[]>([]);
  const isAnalytics = (configSub.use_cases ?? []).includes("analytics");

  const toggleTag = (tag: string) => {
    setActiveFilter((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  };

  const filteredConcepts =
    activeFilter.length === 0
      ? configSub.concepts
      : configSub.concepts.filter(
          (c) => c.semantic_tag && activeFilter.includes(c.semantic_tag),
        );

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {allSemanticTags.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 0.75, display: "block" }}>
            Filter by type
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
            {allSemanticTags.map((tag) => (
              <Chip
                key={tag}
                label={tag.replace(/_/g, " ")}
                size="small"
                variant={activeFilter.includes(tag) ? "filled" : "outlined"}
                color={activeFilter.includes(tag) ? "primary" : "default"}
                onClick={() => toggleTag(tag)}
                sx={{ height: 24, fontSize: "0.7rem", cursor: "pointer" }}
              />
            ))}
            {activeFilter.length > 0 && (
              <Chip
                label="Clear"
                size="small"
                variant="outlined"
                onClick={() => setActiveFilter([])}
                sx={{ height: 24, fontSize: "0.7rem" }}
              />
            )}
          </Box>
        </Box>
      )}

      {canEditDomains && (
        <SubdomainConceptSearchPanel
          {...searchPanelProps}
          activeTagFilter={activeFilter}
          isAnalytics={isAnalytics}
          benchmarkKeys={benchmarkKeys}
        />
      )}

      <Typography variant="subtitle2">
        Concepts ({filteredConcepts.length}
        {activeFilter.length > 0 ? ` of ${configSub.concepts.length}` : ""})
      </Typography>

      {filteredConcepts.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {configSub.concepts.length === 0
            ? canEditDomains
              ? "No concepts yet. Search above to add SNOMED codes."
              : "No concepts in this subdomain."
            : "No concepts match the current filter."}
        </Typography>
      ) : (
        <List
          dense
          sx={{ border: 1, borderColor: "divider", borderRadius: 1, maxHeight: 320, overflow: "auto" }}
        >
          {filteredConcepts.map((c) => (
            <ConceptListRow
              key={c.concept_id}
              concept={c}
              canEdit={canEditDomains}
              submitting={submitting}
              isAnalytics={isAnalytics}
              benchmarkKeys={benchmarkKeys}
              onRemove={() => onRemoveConcept(c.concept_id)}
            />
          ))}
        </List>
      )}

      <Box sx={{ display: "flex", gap: 1 }}>
        <Tooltip title="Download concept list (top-level codes only)">
          <span>
            <Button
              size="small"
              variant="outlined"
              startIcon={
                exportLoading === "concepts" ? (
                  <CircularProgress size={14} />
                ) : (
                  <DownloadIcon />
                )
              }
              onClick={() => onExport(false)}
              disabled={!!exportLoading || !configSub.concepts.length}
            >
              Export concepts
            </Button>
          </span>
        </Tooltip>
        <Tooltip title="Download with all IS_A descendants expanded">
          <span>
            <Button
              size="small"
              variant="outlined"
              startIcon={
                exportLoading === "expanded" ? (
                  <CircularProgress size={14} />
                ) : (
                  <DownloadIcon />
                )
              }
              onClick={() => onExport(true)}
              disabled={!!exportLoading || !configSub.concepts.length}
            >
              Export with variants
            </Button>
          </span>
        </Tooltip>
      </Box>
    </Box>
  );
}

// -- Concept list row with IS-A toggle ----------------------------------------

interface ConceptListRowProps {
  concept: SubdomainDetail["concepts"][number];
  canEdit: boolean;
  submitting: boolean;
  isAnalytics: boolean;
  benchmarkKeys: string[];
  onRemove: () => void;
}

function ConceptListRow({
  concept,
  canEdit,
  submitting,
  isAnalytics,
  benchmarkKeys,
  onRemove,
}: ConceptListRowProps) {
  const [open, setOpen] = useState(false);
  const hasVariants = (concept.child_count ?? 0) > 0;
  const bKey = concept.benchmark_key as string | undefined;

  return (
    <>
      <ListItem
        secondaryAction={
          canEdit ? (
            <IconButton
              size="small"
              onClick={onRemove}
              disabled={submitting}
              aria-label="Remove concept"
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          ) : undefined
        }
      >
        <ListItemText
          primary={concept.term}
          secondary={
            <Box component="span" sx={{ display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap" }}>
              <Typography component="span" variant="caption" color="text.secondary">
                {concept.concept_id}
              </Typography>
              {concept.semantic_tag && (
                <Chip
                  label={concept.semantic_tag.replace(/_/g, " ")}
                  size="small"
                  variant="outlined"
                  sx={{ height: 16, fontSize: "0.6rem" }}
                />
              )}
              {isAnalytics && bKey && (
                <Chip
                  label={`benchmark: ${bKey}`}
                  size="small"
                  color="success"
                  variant="outlined"
                  sx={{ height: 16, fontSize: "0.6rem" }}
                />
              )}
              {hasVariants && (
                <Chip
                  label={`+${concept.child_count} types`}
                  size="small"
                  color="info"
                  variant="outlined"
                  onClick={() => setOpen((o) => !o)}
                  deleteIcon={
                    <ExpandMoreIcon
                      sx={{
                        fontSize: "12px !important",
                        transform: open ? "rotate(180deg)" : "none",
                        transition: "transform 0.2s",
                      }}
                    />
                  }
                  onDelete={() => setOpen((o) => !o)}
                  sx={{ height: 16, fontSize: "0.6rem", cursor: "pointer" }}
                />
              )}
            </Box>
          }
        />
      </ListItem>
      {hasVariants && (
        <Collapse in={open}>
          <Box sx={{ pl: 2, pr: 1, pb: 1 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic" }}>
              IS-A subtypes are included automatically when the pipeline runs.
              Use "Export with variants" to see the full expanded list.
            </Typography>
          </Box>
        </Collapse>
      )}
    </>
  );
}

// -- Rules tab (CRUD) ---------------------------------------------------------

interface RulesTabProps {
  schema: CompletenessConceptGroup[];
  subdomainConcepts: SubdomainConcept[];
  canEditDomains: boolean;
  allSemanticTags: string[];
  useCases: DomainUseCase[];
  onSave: (schema: CompletenessConceptGroup[]) => Promise<void>;
}

function buildConceptMetaLookup(concepts: SubdomainConcept[]): Record<number, RuleConceptMeta> {
  const lookup: Record<number, RuleConceptMeta> = {};
  for (const concept of concepts) {
    lookup[concept.concept_id] = {
      term: concept.term || concept.preferred_term,
      semantic_tag: concept.semantic_tag,
    };
  }
  return lookup;
}

export function RulesTab({
  schema,
  subdomainConcepts,
  canEditDomains,
  allSemanticTags,
  useCases,
  onSave,
}: RulesTabProps) {
  const [groups, setGroups] = useState<CompletenessConceptGroup[]>(schema);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conceptMeta, setConceptMeta] = useState<Record<number, RuleConceptMeta>>(() =>
    buildConceptMetaLookup(subdomainConcepts),
  );

  const hasCompleteness = useCases.includes("completeness");

  useEffect(() => {
    setGroups(schema);
  }, [schema]);

  useEffect(() => {
    setConceptMeta((prev) => ({ ...buildConceptMetaLookup(subdomainConcepts), ...prev }));
  }, [subdomainConcepts]);

  const unresolvedConceptIds = useMemo(() => {
    const ids = new Set<number>();
    for (const group of groups) {
      for (const id of group.concept_ids) {
        if (!conceptMeta[id]?.term) ids.add(id);
      }
    }
    return [...ids];
  }, [groups, conceptMeta]);

  useEffect(() => {
    if (unresolvedConceptIds.length === 0) return;
    let cancelled = false;
    void (async () => {
      for (const id of unresolvedConceptIds) {
        try {
          const rows = await searchTerms(String(id), 10);
          const match =
            rows.find((row) => parseInt(row.snomed_concept_id, 10) === id) ?? rows[0];
          if (cancelled || !match?.term) continue;
          setConceptMeta((prev) => ({
            ...prev,
            [id]: { term: match.term, semantic_tag: match.semantic_tag },
          }));
        } catch {
          // Keep numeric fallback on the chip when lookup fails.
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [unresolvedConceptIds]);

  const persist = useCallback(
    async (next: CompletenessConceptGroup[]) => {
      setSaving(true);
      setSaveError(null);
      try {
        await onSave(next);
      } catch (e) {
        setSaveError(e instanceof Error ? e.message : "Failed to save rules");
      } finally {
        setSaving(false);
      }
    },
    [onSave],
  );

  const handleAddGroup = () => {
    const next: CompletenessConceptGroup[] = [
      ...groups,
      { name: "New rule", required: true, semantic_categories: [], concept_ids: [] },
    ];
    setGroups(next);
    void persist(next);
  };

  const handleUpdateGroup = (idx: number, patch: Partial<CompletenessConceptGroup>) => {
    const next = groups.map((g, i) => (i === idx ? { ...g, ...patch } : g));
    setGroups(next);
    void persist(next);
  };

  const handleDeleteGroup = (idx: number) => {
    const next = groups.filter((_, i) => i !== idx);
    setGroups(next);
    void persist(next);
  };

  if (!hasCompleteness) {
    return (
      <Alert severity="info">
        Add the "Minimum dataset" purpose on the Overview tab to define completeness rules for this subdomain.
      </Alert>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
      {saveError && (
        <Alert severity="error" onClose={() => setSaveError(null)}>
          {saveError}
        </Alert>
      )}

      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Typography variant="body2" color="text.secondary">
          {groups.length} rule{groups.length !== 1 ? "s" : ""} defined.
        </Typography>
        {saving && <CircularProgress size={14} />}
      </Box>

      {groups.map((group, idx) => (
        <RuleCard
          key={idx}
          group={group}
          idx={idx}
          canEdit={canEditDomains}
          allSemanticTags={allSemanticTags}
          conceptMeta={conceptMeta}
          onRegisterConceptMeta={(id, meta) =>
            setConceptMeta((prev) => ({ ...prev, [id]: { ...prev[id], ...meta } }))
          }
          onUpdate={(patch) => handleUpdateGroup(idx, patch)}
          onDelete={() => handleDeleteGroup(idx)}
        />
      ))}

      {canEditDomains && (
        <Button
          size="small"
          variant="outlined"
          startIcon={<AddIcon />}
          onClick={handleAddGroup}
          sx={{ alignSelf: "flex-start" }}
        >
          Add rule
        </Button>
      )}
    </Box>
  );
}
