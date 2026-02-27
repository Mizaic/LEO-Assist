"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TablePagination from "@mui/material/TablePagination";
import Paper from "@mui/material/Paper";
import IconButton from "@mui/material/IconButton";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Link from "@mui/material/Link";
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
import ListItemText from "@mui/material/ListItemText";
import ListItemButton from "@mui/material/ListItemButton";
import Divider from "@mui/material/Divider";
import SearchIcon from "@mui/icons-material/Search";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import InputAdornment from "@mui/material/InputAdornment";
import {
  fetchSurfaceForms,
  deleteSurfaceForm,
  fetchSurfaceFormDuplicates,
  deduplicateSurfaceForms,
  deleteSurfaceFormMapping,
  keepSurfaceFormMapping,
  upsertSurfaceFormMapping,
  searchTerms,
  type SurfaceFormItem,
  type SurfaceFormDuplicate,
} from "@/lib/api";

const PAGE_SIZE_OPTIONS = [25, 50, 100];

export default function SurfaceFormsPage() {
  const router = useRouter();

  const [searchInput, setSearchInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);

  const [items, setItems] = useState<SurfaceFormItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<SurfaceFormItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Duplicate audit
  const [duplicates, setDuplicates] = useState<SurfaceFormDuplicate[] | null>(null);
  const [duplicatesOpen, setDuplicatesOpen] = useState(false);
  const [duplicatesLoading, setDuplicatesLoading] = useState(false);
  const [deduping, setDeduping] = useState(false);
  const [dedupeResult, setDedupeResult] = useState<number | null>(null);
  // key = `${normalized}__${concept_id}`
  const [mappingActioning, setMappingActioning] = useState<string | null>(null);

  // Add-mapping panel state — key = normalized form currently open
  const [addMappingOpen, setAddMappingOpen] = useState<string | null>(null);
  const [addMappingQuery, setAddMappingQuery] = useState("");
  const [addMappingResults, setAddMappingResults] = useState<
    Array<{ snomed_concept_id: string; term: string; semantic_tag?: string }>
  >([]);
  const [addMappingSearching, setAddMappingSearching] = useState(false);
  const [addMappingAdding, setAddMappingAdding] = useState<string | null>(null);
  const addMappingDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (q: string, p: number, rpp: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchSurfaceForms(q || undefined, undefined, rpp, p * rpp);
      setItems(result.items);
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
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setPage(0);
      setQuery(value);
    }, 350);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteSurfaceForm(deleteTarget.normalized);
      setDeleteTarget(null);
      load(query, page, rowsPerPage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete surface form");
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

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

  // All confidences equal — auto-fix won't help, needs manual review
  const allSameConfidence = duplicates?.every((d) => {
    const confs = d.mappings.map((m) => m.confidence ?? 0);
    return confs.every((c) => c === confs[0]);
  }) ?? false;

  const openAddMapping = (normalized: string) => {
    setAddMappingOpen(normalized);
    setAddMappingQuery("");
    setAddMappingResults([]);
  };

  const handleAddMappingSearch = async (q: string, normalized: string) => {
    setAddMappingQuery(q);
    if (addMappingDebounce.current) clearTimeout(addMappingDebounce.current);
    if (q.trim().length < 2) { setAddMappingResults([]); return; }
    addMappingDebounce.current = setTimeout(async () => {
      setAddMappingSearching(true);
      try {
        setAddMappingResults(await searchTerms(q, 10));
      } catch { setAddMappingResults([]); }
      finally { setAddMappingSearching(false); }
    }, 300);
  };

  const handleAddMapping = async (
    normalized: string,
    form: string,
    conceptId: string,
  ) => {
    setAddMappingAdding(conceptId);
    try {
      await upsertSurfaceFormMapping(normalized, form, conceptId);
      setAddMappingOpen(null);
      setAddMappingQuery("");
      setAddMappingResults([]);
      await refreshDuplicates();
      load(query, page, rowsPerPage);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add mapping");
    } finally {
      setAddMappingAdding(null);
    }
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: "auto" }}>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link
          underline="hover"
          color="inherit"
          sx={{ cursor: "pointer" }}
          onClick={() => router.push("/settings")}
        >
          Settings
        </Link>
        <Typography color="text.primary">Surface Forms</Typography>
      </Breadcrumbs>

      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <IconButton size="small" onClick={() => router.push("/settings")}>
          <ArrowBackIcon fontSize="small" />
        </IconButton>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Surface Forms
        </Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Surface forms are text strings recognised by the NLP pipeline and mapped
        to SNOMED concepts. Remove spurious or over-broad mappings here.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2, flexWrap: "wrap" }}>
        <TextField
          size="small"
          placeholder="Search by surface form text…"
          value={searchInput}
          onChange={(e) => handleSearchChange(e.target.value)}
          sx={{ width: 360 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" color="action" />
              </InputAdornment>
            ),
          }}
        />
        <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
          {loading ? "Loading…" : `${total.toLocaleString()} surface form${total === 1 ? "" : "s"}`}
        </Typography>
        <Button
          size="small"
          startIcon={duplicatesLoading ? <CircularProgress size={14} /> : <WarningAmberIcon fontSize="small" />}
          onClick={handleAuditDuplicates}
          disabled={duplicatesLoading || deduping}
          color="warning"
          variant="outlined"
        >
          Audit duplicates
        </Button>
      </Box>

      {/* Dedupe result banner */}
      {dedupeResult !== null && (
        <Alert
          severity={dedupeResult > 0 ? "success" : "info"}
          sx={{ mb: 2 }}
          onClose={() => setDedupeResult(null)}
        >
          {dedupeResult > 0
            ? `Removed ${dedupeResult} duplicate mapping${dedupeResult === 1 ? "" : "s"}. Surface forms now have at most one concept mapping.`
            : "No duplicate mappings found — the graph is already clean."}
        </Alert>
      )}

      {/* Duplicate audit panel */}
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
                        {deduping ? <CircularProgress size={14} color="inherit" /> : "Fix all by confidence"}
                      </Button>
                    </Tooltip>
                  )}
                  <Button size="small" onClick={() => setDuplicatesOpen(false)}>
                    Close
                  </Button>
                </Box>
              </Box>

              {duplicates.length > 0 && allSameConfidence && (
                <Alert severity="warning" sx={{ mb: 1.5 }}>
                  All mappings have equal confidence — each surface form needs manual review. Use <strong>Keep</strong> to select the correct concept or <strong>Remove</strong> to delete individual mappings.
                </Alert>
              )}

              {duplicates.length > 0 && (
                <List dense sx={{ maxHeight: 480, overflow: "auto" }}>
                  {duplicates.map((d) => (
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
                        <Button
                          size="small"
                          startIcon={<AddCircleOutlineIcon fontSize="small" />}
                          onClick={() =>
                            addMappingOpen === d.normalized
                              ? setAddMappingOpen(null)
                              : openAddMapping(d.normalized)
                          }
                          sx={{ ml: "auto" }}
                        >
                          Add mapping
                        </Button>
                      </Box>

                      {/* Inline add-mapping search */}
                      <Collapse in={addMappingOpen === d.normalized}>
                        <Box sx={{ pl: 1, mb: 1 }}>
                          <TextField
                            size="small"
                            fullWidth
                            placeholder="Search SNOMED concept to add…"
                            value={addMappingQuery}
                            onChange={(e) => handleAddMappingSearch(e.target.value, d.normalized)}
                            InputProps={{
                              startAdornment: (
                                <InputAdornment position="start">
                                  {addMappingSearching
                                    ? <CircularProgress size={14} />
                                    : <SearchIcon fontSize="small" color="action" />}
                                </InputAdornment>
                              ),
                            }}
                          />
                          {addMappingResults.length > 0 && (
                            <Paper variant="outlined" sx={{ mt: 0.5, maxHeight: 180, overflow: "auto" }}>
                              <List dense disablePadding>
                                {addMappingResults.map((r, i) => (
                                  <Box key={r.snomed_concept_id}>
                                    {i > 0 && <Divider />}
                                    <ListItemButton
                                      onClick={() => handleAddMapping(d.normalized, d.form, r.snomed_concept_id)}
                                      disabled={!!addMappingAdding}
                                      sx={{ py: 0.5 }}
                                    >
                                      <ListItemText
                                        primary={r.term}
                                        secondary={
                                          r.semantic_tag
                                            ? `${r.snomed_concept_id} · ${r.semantic_tag}`
                                            : r.snomed_concept_id
                                        }
                                        primaryTypographyProps={{ variant: "body2" }}
                                        secondaryTypographyProps={{ variant: "caption" }}
                                      />
                                      {addMappingAdding === r.snomed_concept_id && (
                                        <CircularProgress size={14} sx={{ ml: 1 }} />
                                      )}
                                    </ListItemButton>
                                  </Box>
                                ))}
                              </List>
                            </Paper>
                          )}
                        </Box>
                      </Collapse>
                      {d.mappings.map((m) => {
                        const actionKey = `${d.normalized}__${m.concept_id}`;
                        const busy = mappingActioning === actionKey;
                        const anyBusy = !!mappingActioning;
                        return (
                          <Box
                            key={m.concept_id}
                            sx={{
                              display: "flex",
                              alignItems: "center",
                              gap: 1,
                              pl: 1,
                              mb: 0.5,
                              flexWrap: "wrap",
                            }}
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
                                  {busy && mappingActioning?.endsWith(`__${m.concept_id}`) ? (
                                    <CircularProgress size={12} color="inherit" />
                                  ) : "Keep"}
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
                                  {busy ? (
                                    <CircularProgress size={12} color="inherit" />
                                  ) : "Remove"}
                                </Button>
                              </span>
                            </Tooltip>
                          </Box>
                        );
                      })}
                    </ListItem>
                  ))}
                </List>
              )}
          </Paper>
        )}
      </Collapse>

      <Paper variant="outlined">
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 600, width: "22%" }}>Surface form</TableCell>
                <TableCell sx={{ fontWeight: 600, width: "34%" }}>Mapped concept</TableCell>
                <TableCell sx={{ fontWeight: 600, width: "10%" }}>Confidence</TableCell>
                <TableCell sx={{ fontWeight: 600, width: "10%" }}>Source</TableCell>
                <TableCell sx={{ fontWeight: 600, width: "10%" }}>Created by</TableCell>
                <TableCell sx={{ fontWeight: 600, width: "10%" }}>Last seen</TableCell>
                <TableCell sx={{ width: "4%" }} />
              </TableRow>
            </TableHead>
            <TableBody>
              {loading && items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <CircularProgress size={28} />
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <Typography variant="body2" color="text.secondary">
                      No surface forms found.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                items.flatMap((item) => [
                  <TableRow key={`${item.normalized}__${item.concept_id}`} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {item.form}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {item.normalized}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{item.concept_fsn}</Typography>
                      <Box sx={{ display: "flex", gap: 0.5, mt: 0.25, flexWrap: "wrap" }}>
                        <Typography variant="caption" color="text.secondary">
                          {item.concept_id}
                        </Typography>
                        {item.semantic_tag && (
                          <Chip
                            label={item.semantic_tag}
                            size="small"
                            variant="outlined"
                            sx={{ height: 16, fontSize: "0.6rem" }}
                          />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      {item.confidence != null ? (
                        <Typography variant="body2">
                          {(item.confidence * 100).toFixed(0)}%
                        </Typography>
                      ) : (
                        <Typography variant="caption" color="text.secondary">—</Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {item.source ?? "—"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {item.created_by ?? "—"}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {item.last_seen_at
                          ? new Date(item.last_seen_at).toLocaleDateString()
                          : "—"}
                      </Typography>
                    </TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                      <Tooltip title="Add / correct mapping">
                        <IconButton
                          size="small"
                          onClick={() =>
                            addMappingOpen === item.normalized
                              ? setAddMappingOpen(null)
                              : openAddMapping(item.normalized)
                          }
                        >
                          <AddCircleOutlineIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Delete surface form">
                        <IconButton
                          size="small"
                          onClick={() => setDeleteTarget(item)}
                          color="error"
                        >
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>,
                  <TableRow key={`${item.normalized}__${item.concept_id}__add`}>
                    <TableCell colSpan={7} sx={{ p: 0, borderBottom: addMappingOpen === item.normalized ? 1 : 0, borderColor: "divider" }}>
                      <Collapse in={addMappingOpen === item.normalized}>
                        <Box sx={{ p: 1.5, bgcolor: "action.hover" }}>
                          <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
                            Add / correct mapping for <strong>{item.form}</strong>
                          </Typography>
                          <TextField
                            size="small"
                            fullWidth
                            placeholder="Search SNOMED concept…"
                            value={addMappingOpen === item.normalized ? addMappingQuery : ""}
                            onChange={(e) => handleAddMappingSearch(e.target.value, item.normalized)}
                            InputProps={{
                              startAdornment: (
                                <InputAdornment position="start">
                                  {addMappingSearching
                                    ? <CircularProgress size={14} />
                                    : <SearchIcon fontSize="small" color="action" />}
                                </InputAdornment>
                              ),
                            }}
                          />
                          {addMappingResults.length > 0 && (
                            <Paper variant="outlined" sx={{ mt: 0.5, maxHeight: 180, overflow: "auto" }}>
                              <List dense disablePadding>
                                {addMappingResults.map((r, i) => (
                                  <Box key={r.snomed_concept_id}>
                                    {i > 0 && <Divider />}
                                    <ListItemButton
                                      onClick={() => handleAddMapping(item.normalized, item.form, r.snomed_concept_id)}
                                      disabled={!!addMappingAdding}
                                      sx={{ py: 0.5 }}
                                    >
                                      <ListItemText
                                        primary={r.term}
                                        secondary={r.semantic_tag ? `${r.snomed_concept_id} · ${r.semantic_tag}` : r.snomed_concept_id}
                                        primaryTypographyProps={{ variant: "body2" }}
                                        secondaryTypographyProps={{ variant: "caption" }}
                                      />
                                      {addMappingAdding === r.snomed_concept_id && (
                                        <CircularProgress size={14} sx={{ ml: 1 }} />
                                      )}
                                    </ListItemButton>
                                  </Box>
                                ))}
                              </List>
                            </Paper>
                          )}
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>,
                ])
              )}
            </TableBody>
          </Table>
        </TableContainer>
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
        />
      </Paper>

      {/* Delete confirmation */}
      <Dialog open={!!deleteTarget} onClose={() => !deleting && setDeleteTarget(null)}>
        <DialogTitle>Delete surface form?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will permanently remove{" "}
            <strong>&ldquo;{deleteTarget?.form}&rdquo;</strong> and its mapping
            to{" "}
            <strong>{deleteTarget?.concept_fsn}</strong>. The NLP pipeline will
            no longer recognise this text as that concept.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)} disabled={deleting}>
            Cancel
          </Button>
          <Button
            onClick={handleDelete}
            color="error"
            variant="contained"
            disabled={deleting}
          >
            {deleting ? <CircularProgress size={16} color="inherit" /> : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
