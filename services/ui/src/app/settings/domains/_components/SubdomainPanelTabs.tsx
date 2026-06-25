/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2340F614
 *   DI: DI-4885D9FF
 */
"use client";

import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
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

import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DownloadIcon from "@mui/icons-material/Download";

import { useState } from "react";

import type { SubdomainDetail, CompletenessConceptGroup } from "@/lib/analyticsApi";
import { ASSERTION_OPTIONS, MILESTONE_OPTIONS } from "./domainConstants";
import SubdomainConceptSearchPanel from "./SubdomainConceptSearchPanel";

// -- Overview tab --

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
  }) => Promise<void>;
  onClearSearch: () => void;
  onSaved: () => void;
}

export function OverviewTab({ configSub, allSemanticTags, canEditDomains, submitting, onUpdate, onClearSearch, onSaved }: OverviewTabProps) {
  const [description, setDescription] = useState(configSub.description ?? "");
  const [milestoneType, setMilestoneType] = useState(configSub.milestone_type ?? "");
  const [timeWindow, setTimeWindow] = useState(configSub.time_window_months != null ? String(configSub.time_window_months) : "");
  const [semanticTags, setSemanticTags] = useState(configSub.semantic_tags ?? []);
  const [assertionFilter, setAssertionFilter] = useState((configSub as { assertion_filter?: string[] }).assertion_filter ?? []);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await onUpdate({
        description,
        milestone_type: milestoneType || undefined,
        time_window_months: timeWindow ? parseInt(timeWindow, 10) : undefined,
        semantic_tags: semanticTags,
        assertion_filter: assertionFilter,
      });
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <TextField size="small" label="Description" value={description} onChange={(e) => setDescription(e.target.value)} disabled={!canEditDomains} multiline rows={2} />
      <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
        <FormControl size="small" sx={{ minWidth: 180, flex: 1 }}>
          <InputLabel id="milestone-label">Milestone type</InputLabel>
          <Select labelId="milestone-label" label="Milestone type" value={milestoneType} onChange={(e) => setMilestoneType(e.target.value)} disabled={!canEditDomains}>
            <MenuItem value=""><em>None</em></MenuItem>
            {MILESTONE_OPTIONS.map((opt) => <MenuItem key={opt} value={opt}>{opt.replace(/_/g, " ")}</MenuItem>)}
          </Select>
        </FormControl>
        <TextField size="small" type="number" label="Time window (months)" value={timeWindow} onChange={(e) => setTimeWindow(e.target.value)} sx={{ minWidth: 140 }} disabled={!canEditDomains} />
      </Box>
      <Autocomplete multiple size="small" options={allSemanticTags} value={semanticTags}
        onChange={(_, v) => { setSemanticTags(v.filter((t): t is string => typeof t === "string")); onClearSearch(); }}
        disabled={!canEditDomains}
        renderInput={(params) => <TextField {...params} label="Semantic tags" placeholder={semanticTags.length === 0 ? "Select tags to filter concepts" : ""} />}
      />
      <Autocomplete multiple size="small" options={[...ASSERTION_OPTIONS]} value={assertionFilter}
        onChange={(_, v) => setAssertionFilter(v.filter((t): t is string => typeof t === "string"))}
        disabled={!canEditDomains}
        renderInput={(params) => <TextField {...params} label="Assertion filter" helperText="Leave blank to accept any assertion" />}
      />
      {canEditDomains && (
        <Button variant="contained" size="small" onClick={() => void save()} disabled={saving || submitting} startIcon={saving ? <CircularProgress size={14} /> : null}>
          {saving ? "Saving..." : "Save overview"}
        </Button>
      )}
    </Box>
  );
}

// -- Concepts tab --

interface ConceptsTabProps {
  configSub: SubdomainDetail;
  canEditDomains: boolean;
  submitting: boolean;
  exportLoading: "concepts" | "expanded" | null;
  onExport: (includeChildren: boolean) => void;
  onRemoveConcept: (conceptId: number) => void;
  searchPanelProps: React.ComponentProps<typeof SubdomainConceptSearchPanel>;
}

export function ConceptsTab({ configSub, canEditDomains, submitting, exportLoading, onExport, onRemoveConcept, searchPanelProps }: ConceptsTabProps) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {canEditDomains && <SubdomainConceptSearchPanel {...searchPanelProps} />}
      <Typography variant="subtitle2">Concepts ({configSub.concepts.length})</Typography>
      {configSub.concepts.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {canEditDomains ? "No concepts yet. Search above to add SNOMED codes." : "No concepts in this subdomain."}
        </Typography>
      ) : (
        <List dense sx={{ border: 1, borderColor: "divider", borderRadius: 1, maxHeight: 320, overflow: "auto" }}>
          {configSub.concepts.map((c) => (
            <ListItem key={c.concept_id} secondaryAction={canEditDomains ? (
              <IconButton size="small" onClick={() => onRemoveConcept(c.concept_id)} disabled={submitting} aria-label="Remove concept">
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            ) : undefined}>
              <ListItemText
                primary={c.term}
                secondary={
                  <Typography component="span" variant="caption">
                    {c.concept_id}
                    {c.child_count != null && c.child_count > 0 && (
                      <Chip label={`+${c.child_count} variants`} size="small" color="info" variant="outlined" sx={{ ml: 0.5, height: 18, fontSize: "0.6rem" }} />
                    )}
                  </Typography>
                }
              />
            </ListItem>
          ))}
        </List>
      )}
      <Box sx={{ display: "flex", gap: 1 }}>
        <Tooltip title="Download concept list (top-level codes only)">
          <span>
            <Button size="small" variant="outlined" startIcon={exportLoading === "concepts" ? <CircularProgress size={14} /> : <DownloadIcon />} onClick={() => onExport(false)} disabled={!!exportLoading || !configSub.concepts.length}>
              Export concepts
            </Button>
          </span>
        </Tooltip>
        <Tooltip title="Download with all IS_A descendants expanded">
          <span>
            <Button size="small" variant="outlined" startIcon={exportLoading === "expanded" ? <CircularProgress size={14} /> : <DownloadIcon />} onClick={() => onExport(true)} disabled={!!exportLoading || !configSub.concepts.length}>
              Export with variants
            </Button>
          </span>
        </Tooltip>
      </Box>
    </Box>
  );
}

// -- Rules tab (display only) --

export function RulesTab({ schema }: { schema: CompletenessConceptGroup[] }) {
  if (schema.length === 0) {
    return <Alert severity="info">No completeness criteria defined for this subdomain.</Alert>;
  }
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
        {schema.length} completeness rule{schema.length !== 1 ? "s" : ""} defined.
      </Typography>
      {schema.map((group, idx) => (
        <Box key={idx} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="subtitle2">{group.name}</Typography>
            <Chip label={group.required ? "Required" : "Optional"} size="small" color={group.required ? "error" : "default"} variant="outlined" sx={{ height: 20, fontSize: "0.65rem" }} />
          </Box>
          {group.concept_ids.length > 0 && (
            <Typography variant="caption" color="text.secondary">SNOMED: {group.concept_ids.join(", ")}</Typography>
          )}
          {group.semantic_categories.length > 0 && (
            <Box sx={{ mt: 0.5, display: "flex", gap: 0.5, flexWrap: "wrap" }}>
              {group.semantic_categories.map((cat) => (
                <Chip key={cat} label={cat} size="small" variant="outlined" sx={{ height: 18, fontSize: "0.6rem" }} />
              ))}
            </Box>
          )}
        </Box>
      ))}
    </Box>
  );
}
