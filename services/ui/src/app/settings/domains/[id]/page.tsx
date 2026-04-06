"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputLabel from "@mui/material/InputLabel";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import Autocomplete from "@mui/material/Autocomplete";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Collapse from "@mui/material/Collapse";
import Tooltip from "@mui/material/Tooltip";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Link from "@mui/material/Link";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import AddIcon from "@mui/icons-material/Add";
import SettingsIcon from "@mui/icons-material/Settings";
import SearchIcon from "@mui/icons-material/Search";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import DownloadIcon from "@mui/icons-material/Download";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import {
  fetchDomain,
  updateDomain,
  createSubdomain,
  fetchSubdomain,
  updateSubdomain,
  addConceptToSubdomain,
  removeConceptFromSubdomain,
  exportSubdomain,
  type DomainDetail,
  type SubdomainSummary,
  type SubdomainDetail,
} from "@/lib/analyticsApi";
import { searchTerms, fetchSemanticTags, fetchDescendants } from "@/lib/api";

const MILESTONE_OPTIONS = [
  "referral",
  "diagnosis",
  "treatment_start",
  "specialist_visit",
] as const;

const ASSERTION_OPTIONS = [
  "present",
  "absent",
  "refuted",
  "possible",
  "historical",
  "planned",
  "hypothetical",
  "family",
  "declined",
  "cancelled",
] as const;

export default function DomainDetailPage() {
  const params = useParams();
  const domainId = params.id as string;
  const router = useRouter();

  const [domain, setDomain] = useState<DomainDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create subdomain dialog
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [createSubmitting, setCreateSubmitting] = useState(false);

  // Configure subdomain dialog
  const [configSub, setConfigSub] = useState<SubdomainDetail | null>(null);
  const [configOpen, setConfigOpen] = useState(false);
  const [configSubmitting, setConfigSubmitting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<
    Array<{ snomed_concept_id: string; term: string; semantic_tag?: string }>
  >([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Descendant preview state (tree icon = "coverage preview", adds parent only)
  const [descendantPreview, setDescendantPreview] = useState<{
    parentId: string;
    parentTerm: string;
    results: Array<{ snomed_concept_id: string; term: string; semantic_tag?: string; surface_form_count: number; surface_forms: string[] }>;
  } | null>(null);
  const [descendantLoading, setDescendantLoading] = useState<string | null>(null);
  const [descendantListOpen, setDescendantListOpen] = useState(false);
  const [exportLoading, setExportLoading] = useState<"concepts" | "expanded" | null>(null);

  // Benchmark key capture: when user clicks "Add" on a search result we first
  // ask for an optional benchmark_key before confirming the add.
  const [pendingConcept, setPendingConcept] = useState<{ conceptId: number; term: string } | null>(null);
  const [addBenchmarkKey, setAddBenchmarkKey] = useState("");

  // Available SNOMED semantic tags (fetched once)
  const [allSemanticTags, setAllSemanticTags] = useState<string[]>([]);

  useEffect(() => {
    fetchSemanticTags()
      .then(setAllSemanticTags)
      .catch(() => {});
  }, []);

  const loadDomain = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDomain(await fetchDomain(domainId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load domain");
    } finally {
      setLoading(false);
    }
  }, [domainId]);

  useEffect(() => {
    loadDomain();
  }, [loadDomain]);

  // Debounced SNOMED search (filtered by the subdomain's semantic tags)
  const activeTags = configSub?.semantic_tags ?? [];

  const handleSearch = useCallback(async () => {
    const q = searchQuery.trim();
    if (q.length < 2) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    try {
      const tags = activeTags.length > 0 ? activeTags : undefined;
      setSearchResults(await searchTerms(q, 15, tags));
    } catch {
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }, [searchQuery, activeTags]);

  useEffect(() => {
    const t = setTimeout(handleSearch, 300);
    return () => clearTimeout(t);
  }, [searchQuery, handleSearch]);

  const handleCreateSubdomain = async () => {
    if (!createName.trim()) return;
    setCreateSubmitting(true);
    try {
      await createSubdomain(domainId, createName.trim(), {
        description: createDesc.trim() || undefined,
      });
      setCreateOpen(false);
      setCreateName("");
      setCreateDesc("");
      loadDomain();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create subdomain");
    } finally {
      setCreateSubmitting(false);
    }
  };

  const openConfig = async (sub: SubdomainSummary) => {
    setConfigSub(null);
    setConfigOpen(true);
    setSearchQuery("");
    setSearchResults([]);
    setDescendantPreview(null);
    setDescendantLoading(null);
    setDescendantListOpen(false);
    setPendingConcept(null);
    setAddBenchmarkKey("");
    try {
      setConfigSub(await fetchSubdomain(domainId, sub.name));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load subdomain");
      setConfigOpen(false);
    }
  };

  const handleAddConcept = async (conceptId: number, term: string, benchmarkKey?: string) => {
    if (!configSub) return;
    setConfigSubmitting(true);
    try {
      const updated = await addConceptToSubdomain(
        domainId,
        configSub.name,
        conceptId,
        term,
        [],
        benchmarkKey || undefined,
      );
      setConfigSub(updated);
      setSearchQuery("");
      setSearchResults([]);
      setPendingConcept(null);
      setAddBenchmarkKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add concept");
    } finally {
      setConfigSubmitting(false);
    }
  };

  const handleRemoveConcept = async (conceptId: number) => {
    if (!configSub) return;
    setConfigSubmitting(true);
    try {
      setConfigSub(
        await removeConceptFromSubdomain(domainId, configSub.name, conceptId),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove concept");
    } finally {
      setConfigSubmitting(false);
    }
  };

  const handleUpdateSubdomain = async (updates: {
    description?: string;
    milestone_type?: string;
    time_window_months?: number;
    semantic_tags?: string[];
    assertion_filter?: string[];
  }) => {
    if (!configSub) return;
    setConfigSubmitting(true);
    try {
      const updated = await updateSubdomain(domainId, configSub.name, updates);
      setConfigSub((prev) =>
        prev ? { ...prev, ...updated, concepts: prev.concepts } : null,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update subdomain");
    } finally {
      setConfigSubmitting(false);
    }
  };

  const handleFetchDescendants = async (conceptId: string, term: string) => {
    if (!configSub) return;
    setDescendantLoading(conceptId);
    setDescendantPreview(null);
    try {
      const tags = activeTags.length > 0 ? activeTags : undefined;
      const results = await fetchDescendants(conceptId, 3, tags);
      setDescendantPreview({ parentId: conceptId, parentTerm: term, results });
    } catch {
      setError("Failed to fetch descendants");
    } finally {
      setDescendantLoading(null);
    }
  };

  // Adds only the parent concept (descendants are expanded at query time via IS_A)
  const handleConfirmDescendants = async () => {
    if (!configSub || !descendantPreview) return;
    setConfigSubmitting(true);
    try {
      const updated = await addConceptToSubdomain(
        domainId,
        configSub.name,
        parseInt(descendantPreview.parentId, 10),
        descendantPreview.parentTerm,
        [],
        addBenchmarkKey || undefined,
      );
      setConfigSub(updated);
      setDescendantPreview(null);
      setDescendantListOpen(false);
      setSearchQuery("");
      setSearchResults([]);
      setAddBenchmarkKey("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add concept");
    } finally {
      setConfigSubmitting(false);
    }
  };

  const handleExport = async (includeChildren: boolean) => {
    if (!configSub) return;
    setExportLoading(includeChildren ? "expanded" : "concepts");
    try {
      const data = await exportSubdomain(domainId, configSub.name, includeChildren);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = includeChildren
        ? `${configSub.name}-expanded.json`
        : `${configSub.name}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExportLoading(null);
    }
  };

  const existingConceptIds = new Set(
    configSub?.concepts.map((c) => c.concept_id) ?? [],
  );

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      {/* Breadcrumbs */}
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link
          underline="hover"
          color="inherit"
          sx={{ cursor: "pointer" }}
          onClick={() => router.push("/settings")}
        >
          Settings
        </Link>
        <Link
          underline="hover"
          color="inherit"
          sx={{ cursor: "pointer" }}
          onClick={() => router.push("/settings/domains")}
        >
          Domains
        </Link>
        <Typography color="text.primary">
          {domain?.name ?? domainId}
        </Typography>
      </Breadcrumbs>

      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <IconButton
          aria-label="Back to domains"
          onClick={() => router.push("/settings/domains")}
          size="small"
        >
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          {domain?.name ?? "Loading\u2026"}
        </Typography>
      </Box>
      {domain?.description && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {domain.description}
        </Typography>
      )}

      {domain && (
        <Box sx={{ mb: 3 }}>
          <Tooltip title="When on, this domain's subdomains are used by the episode detector to identify cancer pathway milestones.">
            <FormControlLabel
              control={
                <Switch
                  checked={domain.episode_detector ?? false}
                  onChange={async (e) => {
                    const val = e.target.checked;
                    setDomain((d) => d ? { ...d, episode_detector: val } : d);
                    try {
                      await updateDomain(domainId, { episode_detector: val });
                    } catch {
                      setDomain((d) => d ? { ...d, episode_detector: !val } : d);
                      setError("Could not update episode detector setting.");
                    }
                  }}
                  size="small"
                />
              }
              label={
                <Typography variant="body2" color="text.secondary">
                  Episode detector config
                </Typography>
              }
            />
          </Tooltip>
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      ) : domain ? (
        <>
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              mb: 2,
            }}
          >
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              Subdomains ({domain.subdomains.length})
            </Typography>
            <Button
              variant="contained"
              size="small"
              startIcon={<AddIcon />}
              onClick={() => setCreateOpen(true)}
            >
              Create subdomain
            </Button>
          </Box>

          {domain.subdomains.length === 0 ? (
            <Typography
              color="text.secondary"
              sx={{ py: 4, textAlign: "center" }}
            >
              No subdomains yet. Create one to start adding SNOMED concepts.
            </Typography>
          ) : (
            <List disablePadding>
              {domain.subdomains.map((sub) => (
                <Card key={sub.name} sx={{ mb: 1 }}>
                  <CardContent
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 2,
                      py: 1.5,
                      "&:last-child": { pb: 1.5 },
                    }}
                  >
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        {sub.name.replace(/_/g, " ")}
                      </Typography>
                      {sub.description && (
                        <Typography variant="body2" color="text.secondary">
                          {sub.description}
                        </Typography>
                      )}
                      <Box
                        sx={{
                          mt: 0.5,
                          display: "flex",
                          gap: 0.5,
                          flexWrap: "wrap",
                        }}
                      >
                        <Chip
                          label={`${sub.concept_count} concept${sub.concept_count !== 1 ? "s" : ""}`}
                          size="small"
                        />
                        {(sub.descendant_count ?? 0) > 0 && (
                          <Tooltip title="Additional codes matched automatically via IS_A hierarchy">
                            <Chip
                              label={`+${sub.descendant_count} variants`}
                              size="small"
                              color="info"
                              variant="outlined"
                            />
                          </Tooltip>
                        )}
                        {sub.milestone_type && (
                          <Chip
                            label={sub.milestone_type}
                            size="small"
                            variant="outlined"
                          />
                        )}
                        {sub.semantic_tags.map((t) => (
                          <Chip
                            key={t}
                            label={t}
                            size="small"
                            variant="outlined"
                            color="info"
                          />
                        ))}
                      </Box>
                    </Box>
                    <IconButton
                      onClick={() => openConfig(sub)}
                      aria-label={`Configure ${sub.name}`}
                      size="small"
                    >
                      <SettingsIcon />
                    </IconButton>
                  </CardContent>
                </Card>
              ))}
            </List>
          )}
        </>
      ) : null}

      {/* Create subdomain dialog */}
      <Dialog
        open={createOpen}
        onClose={() => !createSubmitting && setCreateOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create subdomain</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Subdomain name"
            placeholder="e.g. cancer types"
            fullWidth
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            helperText="Spaces will be converted to underscores."
          />
          <TextField
            margin="dense"
            label="Description"
            placeholder="Optional description"
            fullWidth
            multiline
            rows={2}
            value={createDesc}
            onChange={(e) => setCreateDesc(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setCreateOpen(false)}
            disabled={createSubmitting}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleCreateSubdomain}
            disabled={!createName.trim() || createSubmitting}
          >
            {createSubmitting ? "Creating\u2026" : "Create"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Configure subdomain dialog */}
      <Dialog
        open={configOpen}
        onClose={() => !configSubmitting && setConfigOpen(false)}
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
              {/* Metadata */}
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
                    handleUpdateSubdomain({
                      description: configSub.description,
                    })
                  }
                  placeholder="Subdomain description"
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
                        setConfigSub((p) => p ? { ...p, milestone_type: val } : null);
                        handleUpdateSubdomain({ milestone_type: val });
                      }}
                    >
                      <MenuItem value=""><em>None</em></MenuItem>
                      {MILESTONE_OPTIONS.map((opt) => (
                        <MenuItem key={opt} value={opt}>{opt.replace(/_/g, " ")}</MenuItem>
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
                      handleUpdateSubdomain({
                        time_window_months: configSub.time_window_months,
                      })
                    }
                    placeholder="e.g. 12"
                    sx={{ minWidth: 140 }}
                  />
                </Box>
                <Autocomplete
                  multiple
                  size="small"
                  options={allSemanticTags}
                  value={configSub.semantic_tags}
                  onChange={(_, v) => {
                    const tags = v.filter(
                      (t): t is string => typeof t === "string",
                    );
                    setConfigSub((p) =>
                      p ? { ...p, semantic_tags: tags } : null,
                    );
                    handleUpdateSubdomain({ semantic_tags: tags });
                    setSearchResults([]);
                  }}
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
                  value={(configSub as { assertion_filter?: string[] }).assertion_filter ?? []}
                  onChange={(_, v) => {
                    const filter = v.filter((t): t is string => typeof t === "string");
                    setConfigSub((p) =>
                      p ? { ...(p as object), assertion_filter: filter } as typeof p : null,
                    );
                    handleUpdateSubdomain({ assertion_filter: filter } as Parameters<typeof handleUpdateSubdomain>[0]);
                  }}
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

              {/* SNOMED search */}
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
                  onChange={(e) => setSearchQuery(e.target.value)}
                  InputProps={{
                    startAdornment: (
                      <SearchIcon
                        sx={{ mr: 1, color: "text.secondary" }}
                      />
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
                      const childCount = (r as { child_count?: number }).child_count ?? 0;
                      const isBroad = childCount > 5;
                      return (
                        <ListItem
                          key={`${r.snomed_concept_id}-${i}`}
                          secondaryAction={
                            !alreadyAdded ? (
                              <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
                                <Button
                                  size="small"
                                  onClick={() => {
                                    setPendingConcept({ conceptId: cid, term: r.term });
                                    setAddBenchmarkKey("");
                                    setDescendantPreview(null);
                                  }}
                                  disabled={configSubmitting || isLoadingDescendants}
                                >
                                  Add
                                </Button>
                                <Tooltip title={isBroad ? `Preview ${childCount} variants this concept covers (IS_A hierarchy)` : "Preview IS_A variants"}>
                                  <span>
                                    <IconButton
                                      aria-label="Preview coverage via IS_A hierarchy"
                                      size="small"
                                      onClick={() =>
                                        handleFetchDescendants(r.snomed_concept_id, r.term)
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
                                  <Tooltip title={`Broad concept — covers ~${childCount} child variants via IS_A. Use the tree icon to confirm coverage before adding.`}>
                                    <Chip
                                      label={`~${childCount} variants`}
                                      size="small"
                                      color="primary"
                                      variant="outlined"
                                      sx={{ height: 18, fontSize: "0.65rem", cursor: "help" }}
                                    />
                                  </Tooltip>
                                )}
                                {childCount === 0 && (
                                  <Chip
                                    label="Specific"
                                    size="small"
                                    variant="outlined"
                                    sx={{ height: 18, fontSize: "0.65rem", color: "text.secondary" }}
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
                            <Chip
                              label="Added"
                              size="small"
                              color="success"
                              sx={{ ml: 1 }}
                            />
                          )}
                        </ListItem>
                      );
                    })}
                  </List>
                )}

                {/* Pending add — benchmark key capture */}
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
                      onChange={(e) => setAddBenchmarkKey(e.target.value)}
                      helperText="Links this concept to the 2018 NCDA benchmark. Leave blank if not applicable."
                      sx={{ mb: 1 }}
                    />
                    <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end" }}>
                      <Button
                        size="small"
                        onClick={() => {
                          setPendingConcept(null);
                          setAddBenchmarkKey("");
                        }}
                        disabled={configSubmitting}
                      >
                        Cancel
                      </Button>
                      <Button
                        size="small"
                        variant="contained"
                        onClick={() =>
                          handleAddConcept(
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

                {/* Descendant coverage preview — adds parent only, children expanded at query time */}
                {descendantPreview && (() => {
                  const coverageCount = descendantPreview.results.length;
                  const visibleResults = descendantPreview.results;
                  return (
                    <Box sx={{ mt: 1 }}>
                      <Alert
                        severity="info"
                        action={
                          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                            <Button
                              size="small"
                              color="inherit"
                              onClick={() => setDescendantListOpen((o) => !o)}
                            >
                              {descendantListOpen ? "Hide variants" : "Preview variants"}
                            </Button>
                            <Button
                              size="small"
                              color="inherit"
                              onClick={() => {
                                setDescendantPreview(null);
                                setDescendantListOpen(false);
                              }}
                              disabled={configSubmitting}
                            >
                              Cancel
                            </Button>
                            <Button
                              size="small"
                              variant="contained"
                              onClick={handleConfirmDescendants}
                              disabled={configSubmitting || existingConceptIds.has(parseInt(descendantPreview.parentId, 10))}
                            >
                              {configSubmitting ? (
                                <CircularProgress aria-label="Loading" size={16} color="inherit" />
                              ) : (
                                `Add "${descendantPreview.parentTerm}"`
                              )}
                            </Button>
                          </Box>
                        }
                      >
                        <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                          <span>
                            <strong>{descendantPreview.parentTerm}</strong> covers{" "}
                            <strong>{coverageCount}</strong> variant
                            {coverageCount !== 1 ? "s" : ""} via IS_A hierarchy.
                            Only the parent concept is stored — variants are matched automatically at query time.
                          </span>
                          <TextField
                            size="small"
                            label="Benchmark key (optional)"
                            placeholder="e.g. comorbidity_hypertension_pct"
                            value={addBenchmarkKey}
                            onChange={(e) => setAddBenchmarkKey(e.target.value)}
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
                })()}
              </Box>

              {/* Concepts in subdomain */}
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Concepts ({configSub.concepts.length})
                </Typography>
                {configSub.concepts.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No concepts yet. Search above to add SNOMED codes.
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
                              <Tooltip title={`Covers ${c.child_count} child variant${c.child_count !== 1 ? "s" : ""} via IS_A hierarchy`}>
                                <Chip
                                  label={`+${c.child_count} variants`}
                                  size="small"
                                  color="info"
                                  variant="outlined"
                                  sx={{ height: 20, fontSize: "0.65rem", cursor: "default" }}
                                />
                              </Tooltip>
                            )}
                            {c.child_count === 0 && (
                              <Tooltip title="Leaf concept — no child variants">
                                <Chip
                                  label="Specific"
                                  size="small"
                                  variant="outlined"
                                  sx={{ height: 20, fontSize: "0.65rem", cursor: "default", color: "text.secondary" }}
                                />
                              </Tooltip>
                            )}
                            <IconButton
                              size="small"
                              onClick={() => handleRemoveConcept(c.concept_id)}
                              disabled={configSubmitting}
                              aria-label="Remove concept"
                            >
                              <DeleteOutlineIcon />
                            </IconButton>
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
                                  <span style={{ color: "#1976d2" }}>{c.benchmark_key}</span>
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
                  onClick={() => handleExport(false)}
                  disabled={!!exportLoading || configSubmitting || !configSub?.concepts.length}
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
                  onClick={() => handleExport(true)}
                  disabled={!!exportLoading || configSubmitting || !configSub?.concepts.length}
                >
                  Export with variants
                </Button>
              </span>
            </Tooltip>
          </Box>
          <Button
            onClick={() => {
              setConfigOpen(false);
              loadDomain();
            }}
            disabled={configSubmitting}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
