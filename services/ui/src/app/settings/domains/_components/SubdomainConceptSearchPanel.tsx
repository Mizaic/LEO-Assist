"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Chip from "@mui/material/Chip";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Collapse from "@mui/material/Collapse";
import Tooltip from "@mui/material/Tooltip";
import SearchIcon from "@mui/icons-material/Search";
import AccountTreeIcon from "@mui/icons-material/AccountTree";

export type SnomedSearchHit = {
  snomed_concept_id: string;
  term: string;
  semantic_tag?: string;
  child_count?: number;
};

export type DescendantPreviewRow = {
  snomed_concept_id: string;
  term: string;
  semantic_tag?: string;
  surface_form_count: number;
  surface_forms: string[];
};

export interface SubdomainConceptSearchPanelProps {
  activeTags: string[];
  searchQuery: string;
  onSearchQueryChange: (q: string) => void;
  searchResults: SnomedSearchHit[];
  searchLoading: boolean;
  configSubmitting: boolean;
  existingConceptIds: Set<number>;
  descendantPreview: {
    parentId: string;
    parentTerm: string;
    results: DescendantPreviewRow[];
  } | null;
  descendantLoading: string | null;
  descendantListOpen: boolean;
  onToggleDescendantList: () => void;
  pendingConcept: { conceptId: number; term: string } | null;
  addBenchmarkKey: string;
  onAddBenchmarkKeyChange: (k: string) => void;
  onStartAddConcept: (conceptId: number, term: string) => void;
  onCancelPending: () => void;
  onFetchDescendants: (conceptId: string, term: string) => void;
  onClearDescendantPreview: () => void;
  onConfirmAddConcept: (
    conceptId: number,
    term: string,
    benchmarkKey?: string,
  ) => void;
  onConfirmDescendants: () => void;
}

export default function SubdomainConceptSearchPanel({
  activeTags,
  searchQuery,
  onSearchQueryChange,
  searchResults,
  searchLoading,
  configSubmitting,
  existingConceptIds,
  descendantPreview,
  descendantLoading,
  descendantListOpen,
  onToggleDescendantList,
  pendingConcept,
  addBenchmarkKey,
  onAddBenchmarkKeyChange,
  onStartAddConcept,
  onCancelPending,
  onFetchDescendants,
  onClearDescendantPreview,
  onConfirmAddConcept,
  onConfirmDescendants,
}: SubdomainConceptSearchPanelProps) {
  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Add SNOMED concept
      </Typography>
      {activeTags.length > 0 && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ mb: 1, display: "block" }}
        >
          Filtering by: {activeTags.join(", ")}
        </Typography>
      )}
      <TextField
        size="small"
        fullWidth
        placeholder="Search SNOMED terms\u2026"
        value={searchQuery}
        onChange={(e) => onSearchQueryChange(e.target.value)}
        InputProps={{
          startAdornment: (
            <SearchIcon sx={{ mr: 1, color: "text.secondary" }} />
          ),
        }}
      />
      {searchLoading && (
        <Box sx={{ py: 1 }}>
          <CircularProgress aria-label="Loading" size={24} />
        </Box>
      )}
      {searchResults.length > 0 && (
        <List dense sx={{ mt: 1, maxHeight: 220, overflow: "auto" }}>
          {searchResults.map((r, i) => {
            const cid = parseInt(r.snomed_concept_id, 10);
            const alreadyAdded = existingConceptIds.has(cid);
            const isLoadingDescendants = descendantLoading === r.snomed_concept_id;
            const childCount = r.child_count ?? 0;
            const isBroad = childCount > 5;
            return (
              <ListItem
                key={`${r.snomed_concept_id}-${i}`}
                secondaryAction={
                  !alreadyAdded ? (
                    <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
                      <Button
                        size="small"
                        onClick={() => onStartAddConcept(cid, r.term)}
                        disabled={configSubmitting || isLoadingDescendants}
                      >
                        Add
                      </Button>
                      <Tooltip
                        title={
                          isBroad
                            ? `Preview ${childCount} variants this concept covers (IS_A hierarchy)`
                            : "Preview IS_A variants"
                        }
                      >
                        <span>
                          <IconButton
                            aria-label="Preview coverage via IS_A hierarchy"
                            size="small"
                            onClick={() =>
                              onFetchDescendants(r.snomed_concept_id, r.term)
                            }
                            disabled={configSubmitting || !!descendantLoading}
                            color={isBroad ? "primary" : "default"}
                          >
                            {isLoadingDescendants ? (
                              <CircularProgress aria-label="Loading" size={16} />
                            ) : (
                              <AccountTreeIcon fontSize="small" />
                            )}
                          </IconButton>
                        </span>
                      </Tooltip>
                    </Box>
                  ) : undefined
                }
              >
                <ListItemText
                  primary={
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      <span>{r.term}</span>
                      {isBroad && (
                        <Tooltip
                          title={`Broad concept - covers ~${childCount} child variants via IS_A. Use the tree icon to confirm coverage before adding.`}
                        >
                          <Chip
                            label={`~${childCount} variants`}
                            size="small"
                            color="primary"
                            variant="outlined"
                            sx={{
                              height: 18,
                              fontSize: "0.65rem",
                              cursor: "help",
                            }}
                          />
                        </Tooltip>
                      )}
                      {childCount === 0 && (
                        <Chip
                          label="Specific"
                          size="small"
                          variant="outlined"
                          sx={{
                            height: 18,
                            fontSize: "0.65rem",
                            color: "text.secondary",
                          }}
                        />
                      )}
                    </Box>
                  }
                  secondary={
                    r.semantic_tag
                      ? `${r.snomed_concept_id} \u00b7 ${r.semantic_tag}`
                      : r.snomed_concept_id
                  }
                />
                {alreadyAdded && (
                  <Chip label="Added" size="small" color="success" sx={{ ml: 1 }} />
                )}
              </ListItem>
            );
          })}
        </List>
      )}

      {pendingConcept && (
        <Box
          sx={{
            mt: 1,
            p: 1.5,
            border: 1,
            borderColor: "primary.light",
            borderRadius: 1,
            bgcolor: "background.paper",
          }}
        >
          <Typography variant="body2" sx={{ mb: 1 }}>
            Adding: <strong>{pendingConcept.term}</strong>
          </Typography>
          <TextField
            size="small"
            fullWidth
            label="Benchmark key (optional)"
            placeholder="e.g. comorbidity_hypertension_pct"
            value={addBenchmarkKey}
            onChange={(e) => onAddBenchmarkKeyChange(e.target.value)}
            helperText="Links this concept to the 2018 NCDA benchmark. Leave blank if not applicable."
            sx={{ mb: 1 }}
          />
          <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end" }}>
            <Button
              size="small"
              onClick={onCancelPending}
              disabled={configSubmitting}
            >
              Cancel
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={() =>
                onConfirmAddConcept(
                  pendingConcept.conceptId,
                  pendingConcept.term,
                  addBenchmarkKey || undefined,
                )
              }
              disabled={configSubmitting}
            >
              {configSubmitting ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                "Confirm"
              )}
            </Button>
          </Box>
        </Box>
      )}

      {descendantPreview && (
        <DescendantPreviewBlock
          preview={descendantPreview}
          descendantListOpen={descendantListOpen}
          onToggleList={onToggleDescendantList}
          onClear={onClearDescendantPreview}
          onConfirm={onConfirmDescendants}
          addBenchmarkKey={addBenchmarkKey}
          onAddBenchmarkKeyChange={onAddBenchmarkKeyChange}
          configSubmitting={configSubmitting}
          existingConceptIds={existingConceptIds}
        />
      )}
    </Box>
  );
}

function DescendantPreviewBlock({
  preview,
  descendantListOpen,
  onToggleList,
  onClear,
  onConfirm,
  addBenchmarkKey,
  onAddBenchmarkKeyChange,
  configSubmitting,
  existingConceptIds,
}: {
  preview: {
    parentId: string;
    parentTerm: string;
    results: DescendantPreviewRow[];
  };
  descendantListOpen: boolean;
  onToggleList: () => void;
  onClear: () => void;
  onConfirm: () => void;
  addBenchmarkKey: string;
  onAddBenchmarkKeyChange: (k: string) => void;
  configSubmitting: boolean;
  existingConceptIds: Set<number>;
}) {
  const coverageCount = preview.results.length;
  const visibleResults = preview.results;
  return (
    <Box sx={{ mt: 1 }}>
      <Alert
        severity="info"
        action={
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <Button size="small" color="inherit" onClick={onToggleList}>
              {descendantListOpen ? "Hide variants" : "Preview variants"}
            </Button>
            <Button
              size="small"
              color="inherit"
              onClick={onClear}
              disabled={configSubmitting}
            >
              Cancel
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={onConfirm}
              disabled={
                configSubmitting ||
                existingConceptIds.has(parseInt(preview.parentId, 10))
              }
            >
              {configSubmitting ? (
                <CircularProgress aria-label="Loading" size={16} color="inherit" />
              ) : (
                `Add "${preview.parentTerm}"`
              )}
            </Button>
          </Box>
        }
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
          <span>
            <strong>{preview.parentTerm}</strong> covers{" "}
            <strong>{coverageCount}</strong> variant
            {coverageCount !== 1 ? "s" : ""} via IS_A hierarchy. Only the parent
            concept is stored - variants are matched automatically at query time.
          </span>
          <TextField
            size="small"
            label="Benchmark key (optional)"
            placeholder="e.g. comorbidity_hypertension_pct"
            value={addBenchmarkKey}
            onChange={(e) => onAddBenchmarkKeyChange(e.target.value)}
            sx={{ minWidth: 280 }}
          />
        </Box>
      </Alert>
      <Collapse in={descendantListOpen}>
        <List
          dense
          sx={{
            border: 1,
            borderColor: "info.light",
            borderTop: 0,
            borderRadius: "0 0 4px 4px",
            maxHeight: 240,
            overflow: "auto",
            bgcolor: "background.paper",
          }}
        >
          {visibleResults.map((d, i) => (
            <ListItem key={`${d.snomed_concept_id}-${i}`}>
              <ListItemText
                primary={d.term}
                secondary={
                  d.semantic_tag
                    ? `${d.snomed_concept_id} \u00b7 ${d.semantic_tag}`
                    : d.snomed_concept_id
                }
              />
            </ListItem>
          ))}
          {visibleResults.length === 0 && (
            <ListItem>
              <ListItemText secondary="No variants found." />
            </ListItem>
          )}
        </List>
      </Collapse>
    </Box>
  );
}
