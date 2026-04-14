"use client";

import { useMemo } from "react";
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
  constructs?: Array<{
    id: string;
    display_name: string;
    description?: string;
    logic: "ALL" | "ANY";
    roles: Array<{ role: string; concept_ids: number[]; required: boolean }>;
  }>;
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
  const conceptOptions = useMemo(
    () =>
      (configSub?.concepts ?? []).map((concept) => ({
        label: `${concept.term} (${concept.concept_id})`,
        conceptId: concept.concept_id,
      })),
    [configSub],
  );

  const updateConstructs = (
    next: Array<{
      id: string;
      display_name: string;
      description?: string;
      logic: "ALL" | "ANY";
      roles: Array<{ role: string; concept_ids: number[]; required: boolean }>;
    }>,
  ) => {
    setConfigSub((prev) =>
      prev ? { ...prev, constructs: next, construct_count: next.length } : null,
    );
    void onUpdateSubdomain({ constructs: next });
  };

  const constructs = configSub?.constructs ?? [];

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

            <Box>
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  mb: 1,
                }}
              >
                <Typography variant="subtitle2">
                  Code groups ({constructs.length})
                </Typography>
                {canEditDomains && (
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      const nextId = `cg_${constructs.length + 1}`;
                      updateConstructs([
                        ...constructs,
                        {
                          id: nextId,
                          display_name: "New code group",
                          description: "",
                          logic: "ALL",
                          roles: [],
                        },
                      ]);
                    }}
                  >
                    Add code group
                  </Button>
                )}
              </Box>
              {constructs.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  Code groups let you match multi-code clinical constructs.
                </Typography>
              ) : (
                <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  {constructs.map((construct, constructIdx) => (
                    <Box
                      key={`${construct.id}-${constructIdx}`}
                      sx={{
                        border: "1px solid",
                        borderColor: "divider",
                        borderRadius: 1,
                        p: 1.25,
                        bgcolor: "background.paper",
                      }}
                    >
                      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 1 }}>
                        <TextField
                          size="small"
                          label="Group name"
                          value={construct.display_name}
                          onChange={(event) => {
                            const next = constructs.map((item, idx) =>
                              idx === constructIdx
                                ? { ...item, display_name: event.target.value }
                                : item,
                            );
                            updateConstructs(next);
                          }}
                          sx={{ minWidth: 220, flex: 1 }}
                          disabled={!canEditDomains}
                        />
                        <TextField
                          size="small"
                          label="Group ID"
                          value={construct.id}
                          onChange={(event) => {
                            const next = constructs.map((item, idx) =>
                              idx === constructIdx
                                ? { ...item, id: event.target.value }
                                : item,
                            );
                            updateConstructs(next);
                          }}
                          sx={{ minWidth: 170 }}
                          disabled={!canEditDomains}
                        />
                        <FormControl size="small" sx={{ minWidth: 120 }}>
                          <InputLabel id={`construct-logic-${constructIdx}`}>
                            Match rule
                          </InputLabel>
                          <Select
                            labelId={`construct-logic-${constructIdx}`}
                            label="Match rule"
                            value={construct.logic ?? "ALL"}
                            onChange={(event) => {
                              const value =
                                String(event.target.value).toUpperCase() === "ANY"
                                  ? "ANY"
                                  : "ALL";
                              const next = constructs.map((item, idx) =>
                                idx === constructIdx
                                  ? { ...item, logic: value as "ALL" | "ANY" }
                                  : item,
                              );
                              updateConstructs(next);
                            }}
                            disabled={!canEditDomains}
                          >
                            <MenuItem value="ALL">All roles</MenuItem>
                            <MenuItem value="ANY">Any role</MenuItem>
                          </Select>
                        </FormControl>
                        {canEditDomains && (
                          <Tooltip title="Delete this code group">
                            <span>
                              <IconButton
                                color="error"
                                size="small"
                                onClick={() => {
                                  const next = constructs.filter(
                                    (_, idx) => idx !== constructIdx,
                                  );
                                  updateConstructs(next);
                                }}
                              >
                                <DeleteOutlineIcon />
                              </IconButton>
                            </span>
                          </Tooltip>
                        )}
                      </Box>
                      <TextField
                        size="small"
                        label="Description"
                        value={construct.description ?? ""}
                        onChange={(event) => {
                          const next = constructs.map((item, idx) =>
                            idx === constructIdx
                              ? { ...item, description: event.target.value }
                              : item,
                          );
                          updateConstructs(next);
                        }}
                        fullWidth
                        disabled={!canEditDomains}
                      />
                      <Box sx={{ mt: 1, display: "flex", flexDirection: "column", gap: 1 }}>
                        {construct.roles.map((role, roleIdx) => (
                          <Box
                            key={`${role.role}-${roleIdx}`}
                            sx={{
                              display: "flex",
                              gap: 1,
                              flexWrap: "wrap",
                              alignItems: "center",
                            }}
                          >
                            <TextField
                              size="small"
                              label="Role"
                              value={role.role}
                              onChange={(event) => {
                                const next = constructs.map((item, idx) =>
                                  idx !== constructIdx
                                    ? item
                                    : {
                                        ...item,
                                        roles: item.roles.map((r, i) =>
                                          i === roleIdx
                                            ? { ...r, role: event.target.value }
                                            : r,
                                        ),
                                      },
                                );
                                updateConstructs(next);
                              }}
                              sx={{ minWidth: 150 }}
                              disabled={!canEditDomains}
                            />
                            <Autocomplete
                              multiple
                              size="small"
                              options={conceptOptions}
                              getOptionLabel={(option) => option.label}
                              value={conceptOptions.filter((option) =>
                                role.concept_ids.includes(option.conceptId),
                              )}
                              onChange={(_, values) => {
                                const next = constructs.map((item, idx) =>
                                  idx !== constructIdx
                                    ? item
                                    : {
                                        ...item,
                                        roles: item.roles.map((r, i) =>
                                          i === roleIdx
                                            ? {
                                                ...r,
                                                concept_ids: values.map(
                                                  (value) => value.conceptId,
                                                ),
                                              }
                                            : r,
                                        ),
                                      },
                                );
                                updateConstructs(next);
                              }}
                              renderInput={(params) => (
                                <TextField
                                  {...params}
                                  label="Concepts in role"
                                  placeholder="Select concepts"
                                />
                              )}
                              sx={{ minWidth: 280, flex: 1 }}
                              disabled={!canEditDomains}
                            />
                            <FormControl size="small" sx={{ minWidth: 120 }}>
                              <InputLabel id={`required-${constructIdx}-${roleIdx}`}>
                                Required
                              </InputLabel>
                              <Select
                                labelId={`required-${constructIdx}-${roleIdx}`}
                                label="Required"
                                value={role.required ? "yes" : "no"}
                                onChange={(event) => {
                                  const required = event.target.value === "yes";
                                  const next = constructs.map((item, idx) =>
                                    idx !== constructIdx
                                      ? item
                                      : {
                                          ...item,
                                          roles: item.roles.map((r, i) =>
                                            i === roleIdx ? { ...r, required } : r,
                                          ),
                                        },
                                  );
                                  updateConstructs(next);
                                }}
                                disabled={!canEditDomains}
                              >
                                <MenuItem value="yes">Yes</MenuItem>
                                <MenuItem value="no">No</MenuItem>
                              </Select>
                            </FormControl>
                            {canEditDomains && (
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => {
                                  const next = constructs.map((item, idx) =>
                                    idx !== constructIdx
                                      ? item
                                      : {
                                          ...item,
                                          roles: item.roles.filter(
                                            (_, i) => i !== roleIdx,
                                          ),
                                        },
                                  );
                                  updateConstructs(next);
                                }}
                              >
                                <DeleteOutlineIcon fontSize="small" />
                              </IconButton>
                            )}
                          </Box>
                        ))}
                        {canEditDomains && (
                          <Button
                            size="small"
                            variant="text"
                            onClick={() => {
                              const next = constructs.map((item, idx) =>
                                idx !== constructIdx
                                  ? item
                                  : {
                                      ...item,
                                      roles: [
                                        ...item.roles,
                                        {
                                          role: "condition",
                                          concept_ids: [],
                                          required: true,
                                        },
                                      ],
                                    },
                              );
                              updateConstructs(next);
                            }}
                          >
                            Add role
                          </Button>
                        )}
                      </Box>
                    </Box>
                  ))}
                </Box>
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
