"use client";

import type { Dispatch, SetStateAction } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputLabel from "@mui/material/InputLabel";
import FormControl from "@mui/material/FormControl";
import Autocomplete from "@mui/material/Autocomplete";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import CircularProgress from "@mui/material/CircularProgress";
import Tooltip from "@mui/material/Tooltip";
import DownloadIcon from "@mui/icons-material/Download";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import type { SubdomainDetail } from "@/lib/analyticsApi";
import { ASSERTION_OPTIONS, MILESTONE_OPTIONS } from "./domainConstants";
import SubdomainConceptSearchPanel from "./SubdomainConceptSearchPanel";

type SubdomainUpdatePayload = {
  description?: string;
  milestone_type?: string;
  time_window_months?: number;
  semantic_tags?: string[];
  assertion_filter?: string[];
};

export interface ConfigureSubdomainDialogProps {
  open: boolean;
  configSubmitting: boolean;
  configSub: SubdomainDetail | null;
  setConfigSub: Dispatch<SetStateAction<SubdomainDetail | null>>;
  canEditDomains: boolean;
  allSemanticTags: string[];
  onUpdateSubdomain: (updates: SubdomainUpdatePayload) => Promise<void>;
  onClearSearchResults: () => void;
  onDismiss: () => void;
  onCloseButton: () => void;
  onRemoveConcept: (conceptId: number) => void;
  exportLoading: "concepts" | "expanded" | null;
  onExport: (includeChildren: boolean) => void;
  searchPanelProps: React.ComponentProps<typeof SubdomainConceptSearchPanel>;
}

export default function ConfigureSubdomainDialog({
  open,
  configSubmitting,
  configSub,
  setConfigSub,
  canEditDomains,
  allSemanticTags,
  onUpdateSubdomain,
  onClearSearchResults,
  onDismiss,
  onCloseButton,
  onRemoveConcept,
  exportLoading,
  onExport,
  searchPanelProps,
}: ConfigureSubdomainDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={() => !configSubmitting && onDismiss()}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>
        Configure: {configSub?.name.replace(/_/g, " ") ?? "\u2026"}
      </DialogTitle>
      <DialogContent dividers>
        {!configSub ? (
          <Box sx={{ py: 4, display: "flex", justifyContent: "center" }}>
            <CircularProgress aria-label="Loading" />
          </Box>
        ) : (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <TextField
                size="small"
                label="Description"
                value={configSub.description}
                onChange={(e) =>
                  setConfigSub((p) =>
                    p ? { ...p, description: e.target.value } : null,
                  )
                }
                onBlur={() =>
                  onUpdateSubdomain({ description: configSub.description })
                }
                placeholder="Subdomain description"
                disabled={!canEditDomains}
              />
              <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
                <FormControl size="small" sx={{ minWidth: 180 }}>
                  <InputLabel id="milestone-type-label">Milestone type</InputLabel>
                  <Select
                    labelId="milestone-type-label"
                    label="Milestone type"
                    value={configSub.milestone_type ?? ""}
                    onChange={(e) => {
                      const val = e.target.value || undefined;
                      setConfigSub((p) =>
                        p ? { ...p, milestone_type: val } : null,
                      );
                      void onUpdateSubdomain({ milestone_type: val });
                    }}
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
                  value={configSub.time_window_months ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setConfigSub((p) =>
                      p
                        ? {
                            ...p,
                            time_window_months: v
                              ? parseInt(v, 10)
                              : undefined,
                          }
                        : null,
                    );
                  }}
                  onBlur={() =>
                    onUpdateSubdomain({
                      time_window_months: configSub.time_window_months,
                    })
                  }
                  placeholder="e.g. 12"
                  sx={{ minWidth: 140 }}
                  disabled={!canEditDomains}
                />
              </Box>
              <Autocomplete
                multiple
                size="small"
                options={allSemanticTags}
                value={configSub.semantic_tags}
                onChange={(_, v) => {
                  const tags = v.filter((t): t is string => typeof t === "string");
                  setConfigSub((p) => (p ? { ...p, semantic_tags: tags } : null));
                  void onUpdateSubdomain({ semantic_tags: tags });
                  onClearSearchResults();
                }}
                disabled={!canEditDomains}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Semantic tags (filters search)"
                    placeholder={
                      configSub.semantic_tags.length === 0
                        ? "Select tags to filter concepts"
                        : ""
                    }
                  />
                )}
              />
              <Autocomplete
                multiple
                size="small"
                options={[...ASSERTION_OPTIONS]}
                value={
                  (configSub as { assertion_filter?: string[] }).assertion_filter ??
                  []
                }
                onChange={(_, v) => {
                  const filter = v.filter((t): t is string => typeof t === "string");
                  setConfigSub(
                    (p) =>
                      p
                        ? ({
                            ...(p as object),
                            assertion_filter: filter,
                          } as SubdomainDetail)
                        : null,
                  );
                  void onUpdateSubdomain({ assertion_filter: filter });
                }}
                disabled={!canEditDomains}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Assertion filter"
                    placeholder="Leave blank to accept any assertion"
                    helperText="e.g. set to 'hypothetical' to only count suspected findings"
                  />
                )}
              />
            </Box>

            {canEditDomains && <SubdomainConceptSearchPanel {...searchPanelProps} />}

            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Concepts ({configSub.concepts.length})
              </Typography>
              {configSub.concepts.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  {canEditDomains
                    ? "No concepts yet. Search above to add SNOMED codes."
                    : "No concepts in this subdomain."}
                </Typography>
              ) : (
                <List
                  dense
                  sx={{
                    border: 1,
                    borderColor: "divider",
                    borderRadius: 1,
                    maxHeight: 300,
                    overflow: "auto",
                  }}
                >
                  {configSub.concepts.map((c) => (
                    <ListItem
                      key={c.concept_id}
                      secondaryAction={
                        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                          {c.child_count !== undefined && c.child_count > 0 && (
                            <Tooltip
                              title={`Covers ${c.child_count} child variant${c.child_count !== 1 ? "s" : ""} via IS_A hierarchy`}
                            >
                              <Chip
                                label={`+${c.child_count} variants`}
                                size="small"
                                color="info"
                                variant="outlined"
                                sx={{
                                  height: 20,
                                  fontSize: "0.65rem",
                                  cursor: "default",
                                }}
                              />
                            </Tooltip>
                          )}
                          {c.child_count === 0 && (
                            <Tooltip title="Leaf concept - no child variants">
                              <Chip
                                label="Specific"
                                size="small"
                                variant="outlined"
                                sx={{
                                  height: 20,
                                  fontSize: "0.65rem",
                                  cursor: "default",
                                  color: "text.secondary",
                                }}
                              />
                            </Tooltip>
                          )}
                          {canEditDomains && (
                            <IconButton
                              size="small"
                              onClick={() => onRemoveConcept(c.concept_id)}
                              disabled={configSubmitting}
                              aria-label="Remove concept"
                            >
                              <DeleteOutlineIcon />
                            </IconButton>
                          )}
                        </Box>
                      }
                    >
                      <ListItemText
                        primary={c.term}
                        secondary={
                          <Typography component="span" variant="caption">
                            {c.concept_id}
                            {c.benchmark_key && (
                              <>
                                {" \u00b7 "}
                                <Box
                                  component="span"
                                  sx={{ color: "primary.main" }}
                                >
                                  {c.benchmark_key}
                                </Box>
                              </>
                            )}
                            {c.guideline_synonyms &&
                              c.guideline_synonyms.length > 0 && (
                                <>
                                  {" \u00b7 Synonyms: "}
                                  {c.guideline_synonyms.join(", ")}
                                </>
                              )}
                          </Typography>
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              )}
            </Box>
          </Box>
        )}
      </DialogContent>
      <DialogActions sx={{ justifyContent: "space-between" }}>
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
                disabled={
                  !!exportLoading || configSubmitting || !configSub?.concepts.length
                }
              >
                Export concepts
              </Button>
            </span>
          </Tooltip>
          <Tooltip title="Download concept list with all IS_A descendants expanded (larger file)">
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
                disabled={
                  !!exportLoading || configSubmitting || !configSub?.concepts.length
                }
              >
                Export with variants
              </Button>
            </span>
          </Tooltip>
        </Box>
        <Button onClick={onCloseButton} disabled={configSubmitting}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
