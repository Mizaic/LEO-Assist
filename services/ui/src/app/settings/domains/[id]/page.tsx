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
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Link from "@mui/material/Link";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import AddIcon from "@mui/icons-material/Add";
import SettingsIcon from "@mui/icons-material/Settings";
import SearchIcon from "@mui/icons-material/Search";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import {
  fetchDomain,
  createSubdomain,
  fetchSubdomain,
  updateSubdomain,
  addConceptToSubdomain,
  removeConceptFromSubdomain,
  type DomainDetail,
  type SubdomainSummary,
  type SubdomainDetail,
} from "@/lib/analyticsApi";
import { searchTerms, fetchSemanticTags } from "@/lib/api";

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
    try {
      setConfigSub(await fetchSubdomain(domainId, sub.name));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load subdomain");
      setConfigOpen(false);
    }
  };

  const handleAddConcept = async (conceptId: number, term: string) => {
    if (!configSub) return;
    setConfigSubmitting(true);
    try {
      const updated = await addConceptToSubdomain(
        domainId,
        configSub.name,
        conceptId,
        term,
      );
      setConfigSub(updated);
      setSearchQuery("");
      setSearchResults([]);
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
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          {domain.description}
        </Typography>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
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
              <CircularProgress />
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
                  <TextField
                    size="small"
                    label="Milestone type"
                    value={configSub.milestone_type ?? ""}
                    onChange={(e) =>
                      setConfigSub((p) =>
                        p
                          ? {
                              ...p,
                              milestone_type: e.target.value || undefined,
                            }
                          : null,
                      )
                    }
                    onBlur={() =>
                      handleUpdateSubdomain({
                        milestone_type: configSub.milestone_type,
                      })
                    }
                    placeholder="e.g. referral"
                    sx={{ minWidth: 140 }}
                  />
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
                    <CircularProgress size={24} />
                  </Box>
                )}
                {searchResults.length > 0 && (
                  <List dense sx={{ mt: 1, maxHeight: 220, overflow: "auto" }}>
                    {searchResults.map((r) => {
                      const cid = parseInt(r.snomed_concept_id, 10);
                      const alreadyAdded = existingConceptIds.has(cid);
                      return (
                        <ListItem
                          key={r.snomed_concept_id}
                          secondaryAction={
                            !alreadyAdded ? (
                              <Button
                                size="small"
                                onClick={() => handleAddConcept(cid, r.term)}
                                disabled={configSubmitting}
                              >
                                Add
                              </Button>
                            ) : undefined
                          }
                        >
                          <ListItemText
                            primary={r.term}
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
                          <IconButton
                            size="small"
                            onClick={() =>
                              handleRemoveConcept(c.concept_id)
                            }
                            disabled={configSubmitting}
                            aria-label="Remove concept"
                          >
                            <DeleteOutlineIcon />
                          </IconButton>
                        }
                      >
                        <ListItemText
                          primary={c.term}
                          secondary={
                            <Typography component="span" variant="caption">
                              {c.concept_id}
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
        <DialogActions>
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
