/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   DI: DI-340279C1
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CFA1ED55")
 */
"use client";

/**
 * Surface Forms -- Wave E Phase 3b chrome redesign
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes:
 *   - StatHero: concepts on this page / total concepts / total aliases.
 *   - FilterBar: search across alias/concept name/SNOMED/Read code.
 *   - ToolbarActions: Audit duplicates + Add SNOMED concept.
 *
 * The concept-group cards retain their bespoke alias-chip + inline
 * add-alias editor + AI-suggestion behaviour because no design-system
 * primitive captures that interaction shape; they are re-styled to
 * match the rest of Knowledge through the wrapping layout.
 *
 * Design Controls: DI-LEO-AI-147, DO-LEO-AI-143, VT-LEO-AI-145.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Paper from "@mui/material/Paper";
import IconButton from "@mui/material/IconButton";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Divider from "@mui/material/Divider";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import TablePagination from "@mui/material/TablePagination";
import SearchIcon from "@mui/icons-material/Search";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import InputAdornment from "@mui/material/InputAdornment";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import {
  FilterBar,
  StatHero,
  ToolbarActions,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";
import {
  fetchGroupedSurfaceForms,
  fetchSurfaceForms,
  fetchSurfaceFormDuplicates,
  deduplicateSurfaceForms,
  deleteSurfaceForm,
  deleteSurfaceFormMapping,
  keepSurfaceFormMapping,
  upsertSurfaceFormMapping,
  suggestAliases,
  searchTerms,
  type ConceptGroup,
  type GroupedSurfaceForm,
  type SurfaceFormDuplicate,
} from "@/lib/api";

const PAGE_SIZE_OPTIONS = [25, 50, 100];

/** Client-side normalisation matching the server's _normalize() function. */
function normalize(text: string): string {
  return [...text]
    .map((ch) => (/[a-zA-Z0-9]/.test(ch) ? ch.toLowerCase() : " "))
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}

type SnomedSearchResult = {
  snomed_concept_id: string;
  term: string;
  semantic_tag?: string;
  read_code?: string;
};

interface AliasConflict {
  concept_fsn: string;
  concept_id: string;
}

export default function SurfaceFormsPage() {
  // ── Search + pagination ───────────────────────────────────
  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);

  // ── Data ─────────────────────────────────────────────────
  const [groups, setGroups] = useState<ConceptGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Delete concept group ──────────────────────────────────
  const [deleteTarget, setDeleteTarget] = useState<ConceptGroup | null>(null);
  const [deleting, setDeleting] = useState(false);

  // ── Delete individual surface form ────────────────────────
  const [deletingAlias, setDeletingAlias] = useState<string | null>(null); // normalized

  // ── Add SNOMED concept panel ──────────────────────────────
  const [addConceptOpen, setAddConceptOpen] = useState(false);
  const [addConceptQuery, setAddConceptQuery] = useState("");
  const [addConceptResults, setAddConceptResults] = useState<SnomedSearchResult[]>([]);
  const [addConceptSearching, setAddConceptSearching] = useState(false);
  const [addConceptWarning, setAddConceptWarning] = useState<string | null>(null);
  const addConceptDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Add alias (surface form) to a concept ────────────────
  const [addAliasFor, setAddAliasFor] = useState<string | null>(null); // concept_id
  const [addAliasInput, setAddAliasInput] = useState("");
  const [aliasConflict, setAliasConflict] = useState<AliasConflict | null>(null);
  const [aliasAdding, setAliasAdding] = useState(false);
  const aliasConflictDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── LLM alias suggestions ─────────────────────────────────
  // concept_id -> string[] (loaded suggestions)
  const [suggestions, setSuggestions] = useState<Record<string, string[]>>({});
  // concept_id -> Set of normalized strings the user dismissed
  const [dismissed, setDismissed] = useState<Record<string, Set<string>>>({});
  const [suggestingFor, setSuggestingFor] = useState<string | null>(null);

  // ── Duplicate audit ───────────────────────────────────────
  const [duplicates, setDuplicates] = useState<SurfaceFormDuplicate[] | null>(null);
  const [duplicatesOpen, setDuplicatesOpen] = useState(false);
  const [duplicatesLoading, setDuplicatesLoading] = useState(false);
  const [deduping, setDeduping] = useState(false);
  const [dedupeResult, setDedupeResult] = useState<number | null>(null);
  const [mappingActioning, setMappingActioning] = useState<string | null>(null);

  const searchDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Scroll-to refs per concept ────────────────────────────
  const groupRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const load = useCallback(async (q: string, p: number, rpp: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchGroupedSurfaceForms(q || undefined, rpp, p * rpp);
      setGroups(result.items);
      setTotal(result.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load surface forms");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(query, page, rowsPerPage);
  }, [query, page, rowsPerPage, load]);

  const handleSearchChange = (value: string) => {
    setSearchInput(value);
    if (searchDebounce.current) clearTimeout(searchDebounce.current);
    searchDebounce.current = setTimeout(() => {
      setPage(0);
      setQuery(value);
    }, 350);
  };

  const totalAliases = groups.reduce((sum, g) => sum + g.surface_forms.length, 0);

  // ── LLM alias suggestions ─────────────────────────────────

  const handleSuggest = async (conceptId: string) => {
    setSuggestingFor(conceptId);
    try {
      const results = await suggestAliases(conceptId);
      setSuggestions((prev) => ({ ...prev, [conceptId]: results }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Suggestion failed");
    } finally {
      setSuggestingFor(null);
    }
  };

  const handleAcceptSuggestion = async (conceptId: string, form: string) => {
    const norm = normalize(form);
    try {
      await upsertSurfaceFormMapping(norm, form, conceptId, { source: "llm_suggestion" });
      // Remove from suggestions, refresh group
      setSuggestions((prev) => ({
        ...prev,
        [conceptId]: (prev[conceptId] ?? []).filter((s) => s !== form),
      }));
      load(query, page, rowsPerPage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add suggestion");
    }
  };

  const handleDismissSuggestion = (conceptId: string, form: string) => {
    const norm = normalize(form);
    setDismissed((prev) => {
      const existing = new Set(prev[conceptId]);
      existing.add(norm);
      return { ...prev, [conceptId]: existing };
    });
  };

  // ── Duplicate audit ───────────────────────────────────────

  const handleAuditDuplicates = async () => {
    setDuplicatesLoading(true);
    setDedupeResult(null);
    try {
      const results = await fetchSurfaceFormDuplicates();
      setDuplicates(results);
      setDuplicatesOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load duplicates");
    } finally {
      setDuplicatesLoading(false);
    }
  };

  const handleDeduplicate = async () => {
    setDeduping(true);
    try {
      const result = await deduplicateSurfaceForms();
      setDedupeResult(result.duplicates_removed);
      setDuplicates(null);
      load(query, page, rowsPerPage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Deduplication failed");
    } finally {
      setDeduping(false);
    }
  };

  const refreshDuplicates = async () => {
    try {
      const results = await fetchSurfaceFormDuplicates();
      setDuplicates(results);
      if (results.length === 0) setDuplicatesOpen(false);
    } catch { /* silent */ }
  };

  const handleRemoveMapping = async (normalized: string, conceptId: string) => {
    const key = `${normalized}__${conceptId}`;
    setMappingActioning(key);
    try {
      await deleteSurfaceFormMapping(normalized, conceptId);
      await refreshDuplicates();
      load(query, page, rowsPerPage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove mapping");
    } finally {
      setMappingActioning(null);
    }
  };

  const handleKeepMapping = async (normalized: string, conceptId: string) => {
    const key = `${normalized}__${conceptId}`;
    setMappingActioning(key);
    try {
      await keepSurfaceFormMapping(normalized, conceptId);
      await refreshDuplicates();
      load(query, page, rowsPerPage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update mapping");
    } finally {
      setMappingActioning(null);
    }
  };

  const allSameConfidence = duplicates?.every((d) => {
    const confs = d.mappings.map((m) => m.confidence ?? 0);
    return confs.every((c) => c === confs[0]);
  }) ?? false;

  // ── Add SNOMED concept ────────────────────────────────────

  const handleAddConceptSearch = (q: string) => {
    setAddConceptQuery(q);
    setAddConceptWarning(null);
    if (addConceptDebounce.current) clearTimeout(addConceptDebounce.current);
    if (q.trim().length < 2) { setAddConceptResults([]); return; }
    addConceptDebounce.current = setTimeout(async () => {
      setAddConceptSearching(true);
      try {
        setAddConceptResults(await searchTerms(q, 10));
      } catch { setAddConceptResults([]); }
      finally { setAddConceptSearching(false); }
    }, 300);
  };

  const handleSelectConcept = (result: SnomedSearchResult) => {
    const existing = groups.find((g) => g.concept_id === result.snomed_concept_id);
    if (existing) {
      setAddConceptWarning(
        `"${existing.concept_fsn}" already exists on this page. Scroll to it below.`,
      );
      // Scroll to the existing group
      setTimeout(() => {
        groupRefs.current[result.snomed_concept_id]?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 100);
      return;
    }
    // Add placeholder group at top and open its alias input
    const newGroup: ConceptGroup = {
      concept_id: result.snomed_concept_id,
      concept_fsn: result.term,
      semantic_tag: result.semantic_tag,
      read_code: result.read_code,
      surface_forms: [],
    };
    setGroups((prev) => [newGroup, ...prev]);
    setAddConceptOpen(false);
    setAddConceptQuery("");
    setAddConceptResults([]);
    setAddConceptWarning(null);
    setAddAliasFor(result.snomed_concept_id);
    setAddAliasInput("");
    setAliasConflict(null);
  };

  // ── Delete SNOMED concept group ───────────────────────────

  const handleDeleteGroup = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      for (const sf of deleteTarget.surface_forms) {
        await deleteSurfaceForm(sf.normalized);
      }
      // If placeholder (0 surface forms) just remove from local state
      setGroups((prev) => prev.filter((g) => g.concept_id !== deleteTarget.concept_id));
      setDeleteTarget(null);
      // Reload to sync server state
      load(query, page, rowsPerPage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete concept group");
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  // ── Delete individual surface form (alias) ────────────────

  const handleDeleteAlias = async (sf: GroupedSurfaceForm) => {
    setDeletingAlias(sf.normalized);
    try {
      await deleteSurfaceForm(sf.normalized);
      // Optimistic update
      setGroups((prev) =>
        prev
          .map((g) => ({
            ...g,
            surface_forms: g.surface_forms.filter((s) => s.normalized !== sf.normalized),
          }))
          // Remove group if it has no more aliases (it was a placeholder or last alias)
          .filter((g) => g.surface_forms.length > 0 || addAliasFor === g.concept_id),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove alias");
    } finally {
      setDeletingAlias(null);
    }
  };

  // ── Add alias ─────────────────────────────────────────────

  const openAddAlias = (conceptId: string) => {
    setAddAliasFor(conceptId);
    setAddAliasInput("");
    setAliasConflict(null);
  };

  const handleAliasInputChange = (value: string, targetConceptId: string) => {
    setAddAliasInput(value);
    setAliasConflict(null);

    if (aliasConflictDebounce.current) clearTimeout(aliasConflictDebounce.current);
    const norm = normalize(value);
    if (norm.length < 2) return;

    aliasConflictDebounce.current = setTimeout(async () => {
      // Check loaded groups first (fast, client-side)
      for (const g of groups) {
        if (g.concept_id === targetConceptId) continue;
        if (g.surface_forms.some((sf) => sf.normalized === norm)) {
          setAliasConflict({ concept_fsn: g.concept_fsn, concept_id: g.concept_id });
          return;
        }
      }
      // Also check server for matches outside current page
      try {
        const result = await fetchSurfaceForms(norm, undefined, 1, 0);
        const hit = result.items.find(
          (item) => item.normalized === norm && item.concept_id !== targetConceptId,
        );
        if (hit) {
          setAliasConflict({ concept_fsn: hit.concept_fsn, concept_id: hit.concept_id });
        }
      } catch { /* silent */ }
    }, 400);
  };

  const handleAddAlias = async (conceptId: string) => {
    const form = addAliasInput.trim();
    if (!form) return;
    const norm = normalize(form);

    // Check if already in this group
    const group = groups.find((g) => g.concept_id === conceptId);
    if (group?.surface_forms.some((sf) => sf.normalized === norm)) {
      setAddAliasFor(null);
      setAddAliasInput("");
      return;
    }

    setAliasAdding(true);
    try {
      await upsertSurfaceFormMapping(norm, form, conceptId);
      setAddAliasFor(null);
      setAddAliasInput("");
      setAliasConflict(null);
      load(query, page, rowsPerPage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add alias");
    } finally {
      setAliasAdding(false);
    }
  };

  const handleAliasKeyDown = (e: React.KeyboardEvent, conceptId: string) => {
    if (e.key === "Enter") { e.preventDefault(); handleAddAlias(conceptId); }
    if (e.key === "Escape") { setAddAliasFor(null); setAddAliasInput(""); setAliasConflict(null); }
  };

  const stats = useMemo<StatTile[]>(
    () => [
      {
        id: "concepts",
        label: "Concepts",
        value: total.toLocaleString(),
        hint: "Total SNOMED concepts mapped",
      },
      {
        id: "concepts-on-page",
        label: "On this page",
        value: groups.length.toLocaleString(),
        hint: query
          ? `Matches "${query}"`
          : "Showing the current page of concepts",
      },
      {
        id: "aliases",
        label: "Aliases on page",
        value: totalAliases.toLocaleString(),
        hint: "Surface-form text the pipeline recognises",
        tone: "positive",
      },
    ],
    [total, groups.length, totalAliases, query],
  );

  const toolbarActions: ToolbarAction[] = [
    {
      id: "audit-duplicates",
      label: duplicatesLoading ? "Auditing" : "Audit duplicates",
      icon: duplicatesLoading ? (
        <CircularProgress size={14} aria-label="Loading" />
      ) : (
        <WarningAmberIcon fontSize="small" />
      ),
      variant: "secondary",
      onClick: handleAuditDuplicates,
      disabled: duplicatesLoading || deduping,
      loading: duplicatesLoading,
    },
    {
      id: "add-concept",
      label: addConceptOpen ? "Cancel" : "Add SNOMED concept",
      icon: addConceptOpen ? undefined : (
        <AddCircleOutlineIcon fontSize="small" />
      ),
      variant: "primary",
      onClick: () => {
        setAddConceptOpen((o) => !o);
        setAddConceptQuery("");
        setAddConceptResults([]);
        setAddConceptWarning(null);
      },
    },
  ];

  return (
    <Box>
      <StatHero stats={stats} />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Box sx={{ mb: 2 }}>
        <FilterBar
          search={searchInput}
          onSearchChange={handleSearchChange}
          searchPlaceholder="Search by alias, concept name, SNOMED or Read code"
          aria-label="Search surface forms"
          trailing={<ToolbarActions actions={toolbarActions} />}
        />
        {loading ? (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 1 }}
          >
            Loading...
          </Typography>
        ) : null}
      </Box>

      {/* ── Deduplication result banner ──────────────────────── */}
      {dedupeResult !== null && (
        <Alert
          severity={dedupeResult > 0 ? "success" : "info"}
          sx={{ mb: 2 }}
          onClose={() => setDedupeResult(null)}
        >
          {dedupeResult > 0
            ? `Removed ${dedupeResult} duplicate mapping${dedupeResult === 1 ? "" : "s"}. Each surface form now has at most one concept mapping.`
            : "No duplicate mappings found — the graph is already clean."}
        </Alert>
      )}

      {/* ── Duplicate audit panel ────────────────────────────── */}
      <Collapse in={duplicatesOpen && !!duplicates}>
        {duplicates && (
          <Paper variant="outlined" sx={{ mb: 2, p: 2 }}>
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <WarningAmberIcon color="warning" fontSize="small" />
                <Typography variant="subtitle2">
                  {duplicates.length === 0
                    ? "No duplicates found — graph is clean."
                    : `${duplicates.length} surface form${duplicates.length === 1 ? "" : "s"} with multiple mappings`}
                </Typography>
              </Box>
              <Box sx={{ display: "flex", gap: 1 }}>
                {duplicates.length > 0 && !allSameConfidence && (
                  <Tooltip title="Keeps the highest-confidence mapping per surface form and removes the rest">
                    <Button
                      size="small"
                      variant="outlined"
                      color="warning"
                      onClick={handleDeduplicate}
                      disabled={deduping || !!mappingActioning}
                    >
                      {deduping ? <CircularProgress aria-label="Loading" size={14} color="inherit" /> : "Fix all by confidence"}
                    </Button>
                  </Tooltip>
                )}
                <Button size="small" onClick={() => setDuplicatesOpen(false)}>Close</Button>
              </Box>
            </Box>

            {duplicates.length > 0 && allSameConfidence && (
              <Alert severity="warning" sx={{ mb: 1.5 }}>
                All mappings have equal confidence — each surface form needs manual review. Use{" "}
                <strong>Keep</strong> to select the correct concept or <strong>Remove</strong> to
                delete individual mappings.
              </Alert>
            )}

            {duplicates.length > 0 && (
              <List dense sx={{ maxHeight: 480, overflow: "auto" }}>
                {duplicates.map((d) => {
                  const anyBusy = !!mappingActioning;
                  return (
                    <ListItem
                      key={d.normalized}
                      alignItems="flex-start"
                      sx={{ borderBottom: 1, borderColor: "divider", flexDirection: "column", pb: 1.5, pt: 1.5 }}
                    >
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1, flexWrap: "wrap" }}>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          {d.form}
                        </Typography>
                        <Chip
                          label={`${d.rel_count} mappings · ${d.concept_count} concept${d.concept_count === 1 ? "" : "s"}`}
                          size="small"
                          color={d.concept_count > 1 ? "error" : "warning"}
                          variant="outlined"
                        />
                      </Box>
                      {d.mappings.map((m) => {
                        const actionKey = `${d.normalized}__${m.concept_id}`;
                        const busy = mappingActioning === actionKey;
                        return (
                          <Box
                            key={m.concept_id}
                            sx={{ display: "flex", alignItems: "center", gap: 1, pl: 1, mb: 0.5, flexWrap: "wrap" }}
                          >
                            <Typography variant="caption" sx={{ flex: 1, color: "text.secondary" }}>
                              → <strong>{m.concept_fsn}</strong>{" "}
                              <span style={{ opacity: 0.7 }}>({m.concept_id})</span>
                              {m.confidence != null && ` · ${(m.confidence * 100).toFixed(0)}%`}
                            </Typography>
                            <Tooltip title={`Keep only this mapping — remove the other ${d.mappings.length - 1}`}>
                              <span>
                                <Button
                                  size="small"
                                  variant="contained"
                                  color="success"
                                  sx={{ minWidth: 60, py: 0.25 }}
                                  onClick={() => handleKeepMapping(d.normalized, m.concept_id)}
                                  disabled={anyBusy}
                                >
                                  {busy ? <CircularProgress aria-label="Loading" size={12} color="inherit" /> : "Keep"}
                                </Button>
                              </span>
                            </Tooltip>
                            <Tooltip title="Remove only this mapping">
                              <span>
                                <Button
                                  size="small"
                                  variant="outlined"
                                  color="error"
                                  sx={{ minWidth: 72, py: 0.25 }}
                                  onClick={() => handleRemoveMapping(d.normalized, m.concept_id)}
                                  disabled={anyBusy}
                                >
                                  {busy ? <CircularProgress aria-label="Loading" size={12} color="inherit" /> : "Remove"}
                                </Button>
                              </span>
                            </Tooltip>
                          </Box>
                        );
                      })}
                    </ListItem>
                  );
                })}
              </List>
            )}
          </Paper>
        )}
      </Collapse>

      {/* ── Add concept panel ────────────────────────────────── */}
      <Collapse in={addConceptOpen}>
        <Paper variant="outlined" sx={{ mb: 2, p: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Search for a SNOMED concept to add
          </Typography>
          {addConceptWarning && (
            <Alert severity="warning" sx={{ mb: 1.5 }} onClose={() => setAddConceptWarning(null)}>
              {addConceptWarning}
            </Alert>
          )}
          <TextField
            size="small"
            fullWidth
            autoFocus
            placeholder="Concept name, SNOMED code, or Read code…"
            value={addConceptQuery}
            onChange={(e) => handleAddConceptSearch(e.target.value)}
            aria-label="Search for SNOMED concept by name, code, or Read code"
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  {addConceptSearching
                    ? <CircularProgress aria-label="Loading" size={14} />
                    : <SearchIcon fontSize="small" color="action" />}
                </InputAdornment>
              ),
            }}
          />
          {addConceptResults.length > 0 && (
            <Paper variant="outlined" sx={{ mt: 0.5, maxHeight: 240, overflow: "auto" }}>
              <List dense disablePadding>
                {addConceptResults.map((r, i) => (
                  <Box key={r.snomed_concept_id}>
                    {i > 0 && <Divider />}
                    <ListItemButton onClick={() => handleSelectConcept(r)} sx={{ py: 0.75 }}>
                      <ListItemText
                        primary={r.term}
                        secondary={
                          <>
                            {r.snomed_concept_id}
                            {r.semantic_tag && ` · ${r.semantic_tag}`}
                          </>
                        }
                        primaryTypographyProps={{ variant: "body2" }}
                        secondaryTypographyProps={{ variant: "caption" }}
                      />
                    </ListItemButton>
                  </Box>
                ))}
              </List>
            </Paper>
          )}
        </Paper>
      </Collapse>

      {/* ── Concept groups ───────────────────────────────────── */}
      {loading && groups.length === 0 ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      ) : groups.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
          <Typography variant="body2" color="text.secondary">
            No surface forms found.
          </Typography>
        </Paper>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          {groups.map((group) => (
            <Paper
              key={group.concept_id}
              variant="outlined"
              ref={(el) => { groupRefs.current[group.concept_id] = el; }}
              sx={{ p: 2 }}
            >
              {/* Concept header */}
              <Box
                sx={{
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "space-between",
                  gap: 1,
                  mb: 1,
                }}
              >
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      {group.concept_fsn}
                    </Typography>
                    {group.semantic_tag && (
                      <Chip
                        label={group.semantic_tag}
                        size="small"
                        variant="outlined"
                        sx={{ height: 18, fontSize: "0.65rem" }}
                      />
                    )}
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    {group.concept_id}
                    {group.read_code && ` · Read: ${group.read_code}`}
                    {group.icd10 && ` · ICD-10: ${group.icd10}${group.icd10_term ? ` ${group.icd10_term}` : ""}`}
                    {group.opcs4 && ` · OPCS-4: ${group.opcs4}${group.opcs4_term ? ` ${group.opcs4_term}` : ""}`}
                  </Typography>
                </Box>
                <Box sx={{ display: "flex", gap: 0.5 }}>
                  <Tooltip title="Suggest more aliases using AI">
                    <span>
                      <IconButton
                        aria-label="Suggest more aliases using AI"
                        size="small"
                        color="primary"
                        onClick={() => handleSuggest(group.concept_id)}
                        disabled={suggestingFor === group.concept_id}
                      >
                        {suggestingFor === group.concept_id
                          ? <CircularProgress aria-label="Loading" size={16} />
                          : <AutoAwesomeIcon fontSize="small" />}
                      </IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title="Delete this concept and all its aliases">
                    <IconButton
                      aria-label="Delete this concept and all its aliases"
                      size="small"
                      color="error"
                      onClick={() => setDeleteTarget(group)}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>

              <Divider sx={{ mb: 1.5 }} />

              {/* Alias chips */}
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, alignItems: "center" }}>
                {group.surface_forms.map((sf) => (
                  <Chip
                    key={sf.normalized}
                    label={sf.form}
                    size="small"
                    variant="outlined"
                    onDelete={
                      deletingAlias === sf.normalized
                        ? undefined
                        : () => handleDeleteAlias(sf)
                    }
                    deleteIcon={
                      deletingAlias === sf.normalized
                        ? <CircularProgress aria-label="Loading" size={12} />
                        : undefined
                    }
                    title={`${sf.normalized}${sf.source ? ` · ${sf.source}` : ""}${sf.confidence != null ? ` · ${(sf.confidence * 100).toFixed(0)}%` : ""}`}
                  />
                ))}

                {/* LLM-suggested alias chips */}
                {(suggestions[group.concept_id] ?? [])
                  .filter((s) => !dismissed[group.concept_id]?.has(normalize(s)))
                  .map((s) => (
                    <Tooltip key={s} title="AI suggestion — Accept or Dismiss">
                      <Chip
                        label={s}
                        size="small"
                        color="primary"
                        variant="outlined"
                        icon={<AutoAwesomeIcon style={{ fontSize: 12 }} />}
                        sx={{ borderStyle: "dashed", opacity: 0.85 }}
                        onClick={() => handleAcceptSuggestion(group.concept_id, s)}
                        onDelete={() => handleDismissSuggestion(group.concept_id, s)}
                        deleteIcon={<CloseIcon style={{ fontSize: 12 }} />}
                      />
                    </Tooltip>
                  ))}

                {/* Inline add-alias input */}
                {addAliasFor === group.concept_id ? (
                  <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5, flex: "1 1 260px", minWidth: 200 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      <TextField
                        size="small"
                        autoFocus
                        placeholder="Type alias text, e.g. 2WW Breast Referral"
                        value={addAliasInput}
                        onChange={(e) => handleAliasInputChange(e.target.value, group.concept_id)}
                        onKeyDown={(e) => handleAliasKeyDown(e, group.concept_id)}
                        disabled={aliasAdding}
                        aria-label="Add alias for this concept"
                        sx={{ flex: 1 }}
                        inputProps={{ style: { fontSize: "0.8rem", padding: "4px 8px" } }}
                      />
                      <Tooltip title="Confirm (Enter)">
                        <span>
                          <IconButton
                            aria-label="Confirm add alias"
                            size="small"
                            color="primary"
                            onClick={() => handleAddAlias(group.concept_id)}
                            disabled={aliasAdding || !addAliasInput.trim()}
                          >
                            {aliasAdding ? <CircularProgress aria-label="Loading" size={14} /> : <CheckIcon fontSize="small" />}
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Tooltip title="Cancel (Esc)">
                        <IconButton
                          aria-label="Cancel add alias"
                          size="small"
                          onClick={() => { setAddAliasFor(null); setAddAliasInput(""); setAliasConflict(null); }}
                          disabled={aliasAdding}
                        >
                          <CloseIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                    {aliasConflict && (
                      <Alert severity="warning" sx={{ py: 0, fontSize: "0.75rem" }}>
                        <strong>&ldquo;{normalize(addAliasInput)}&rdquo;</strong> already maps to{" "}
                        <strong>{aliasConflict.concept_fsn}</strong> ({aliasConflict.concept_id}).
                        Saving will create a duplicate — audit duplicates to resolve.
                      </Alert>
                    )}
                  </Box>
                ) : (
                  <Chip
                    label="+ Add alias"
                    size="small"
                    variant="outlined"
                    color="primary"
                    onClick={() => openAddAlias(group.concept_id)}
                    sx={{ cursor: "pointer", borderStyle: "dashed" }}
                    icon={<AddCircleOutlineIcon style={{ fontSize: 14 }} />}
                  />
                )}
              </Box>
            </Paper>
          ))}
        </Box>
      )}

      {/* ── Pagination ───────────────────────────────────────── */}
      {total > PAGE_SIZE_OPTIONS[0] && (
        <TablePagination
          component="div"
          count={total}
          page={page}
          rowsPerPage={rowsPerPage}
          rowsPerPageOptions={PAGE_SIZE_OPTIONS}
          onPageChange={(_, p) => setPage(p)}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10));
            setPage(0);
          }}
          sx={{ mt: 1 }}
        />
      )}

      {/* ── Delete concept confirmation ───────────────────────── */}
      <Dialog open={!!deleteTarget} onClose={() => !deleting && setDeleteTarget(null)}>
        <DialogTitle>Delete concept group?</DialogTitle>
        <DialogContent>
          <DialogContentText component="div">
            <Typography variant="body2" sx={{ mb: 1 }}>
              This will permanently remove{" "}
              <strong>{deleteTarget?.concept_fsn}</strong> and all{" "}
              {deleteTarget?.surface_forms.length
                ? `${deleteTarget.surface_forms.length} alias${deleteTarget.surface_forms.length === 1 ? "" : "es"}`
                : "aliases"}{" "}
              mapped to it. The NLP pipeline will no longer recognise these terms.
            </Typography>
            {deleteTarget && deleteTarget.surface_forms.length > 0 && (
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 1 }}>
                {deleteTarget.surface_forms.map((sf) => (
                  <Chip key={sf.normalized} label={sf.form} size="small" variant="outlined" />
                ))}
              </Box>
            )}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)} disabled={deleting}>
            Cancel
          </Button>
          <Button
            onClick={handleDeleteGroup}
            color="error"
            variant="contained"
            disabled={deleting}
          >
            {deleting ? <CircularProgress aria-label="Loading" size={16} color="inherit" /> : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
