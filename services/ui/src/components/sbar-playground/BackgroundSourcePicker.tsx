"use client";

/**
 * BackgroundSourcePicker -- patient-scoped picker for SBAR Background
 * sources (Encounters and DocumentReferences with nested Chunks).
 *
 * Design Controls: DI-LEO-AI-232.
 *
 * Tabs:
 *   - Encounters: chronological list, multi-select.
 *   - Documents:  DocumentReference list. Each row expands to reveal
 *                 child :Chunk nodes with their own checkboxes -- chunk
 *                 selection is nested inside the parent document, never
 *                 a separate tab.
 *
 * Emits a list of SelectedBackgroundSource via onConfirm. Each entry
 * is one of:
 *   { type: "encounter",          id }
 *   { type: "document_reference", id }
 *   { type: "chunk",              id, parentDocumentReferenceId }
 *
 * Selecting a DocumentReference itself sends the whole document; picking
 * any chunks under it sends only those chunks (the parent is implicitly
 * dropped).
 */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import {
  listDocumentReferenceChunks,
  listPatientDocumentReferences,
  listPatientEncounters,
  type PatientFinderChunk,
  type PatientFinderDocumentReference,
  type PatientFinderEncounter,
} from "@/lib/analyticsApi";

// -- Types ----------------------------------------------------------------

export type SelectedBackgroundSource =
  | { type: "encounter"; id: string }
  | { type: "document_reference"; id: string }
  | { type: "chunk"; id: string; parentDocumentReferenceId: string };

export interface BackgroundSourcePickerProps {
  open: boolean;
  patientId: string;
  /** Sources currently selected, so the dialog can pre-tick. */
  initialSelected?: SelectedBackgroundSource[];
  onClose: () => void;
  onConfirm: (sources: SelectedBackgroundSource[]) => void;
  density?: "compact" | "comfortable";
}

type PickerTab = "encounters" | "documents";

// -- Component ------------------------------------------------------------

export function BackgroundSourcePicker({
  open,
  patientId,
  initialSelected,
  onClose,
  onConfirm,
  density = "compact",
}: BackgroundSourcePickerProps) {
  const [tab, setTab] = useState<PickerTab>("encounters");
  const [selectedEncounterIds, setSelectedEncounterIds] = useState<
    Set<string>
  >(new Set());
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [selectedChunks, setSelectedChunks] = useState<
    Map<string, { parent: string }>
  >(new Map());

  // Hydrate selection state from props on open.
  useEffect(() => {
    if (!open) return;
    const enc = new Set<string>();
    const docs = new Set<string>();
    const chunks = new Map<string, { parent: string }>();
    for (const s of initialSelected ?? []) {
      if (s.type === "encounter") enc.add(s.id);
      else if (s.type === "document_reference") docs.add(s.id);
      else if (s.type === "chunk") {
        chunks.set(s.id, { parent: s.parentDocumentReferenceId });
      }
    }
    setSelectedEncounterIds(enc);
    setSelectedDocIds(docs);
    setSelectedChunks(chunks);
    setTab("encounters");
  }, [open, initialSelected]);

  const totalSelected =
    selectedEncounterIds.size + selectedDocIds.size + selectedChunks.size;

  const onConfirmClick = useCallback(() => {
    const out: SelectedBackgroundSource[] = [];
    for (const id of selectedEncounterIds) {
      out.push({ type: "encounter", id });
    }
    for (const id of selectedDocIds) {
      out.push({ type: "document_reference", id });
    }
    for (const [id, meta] of selectedChunks) {
      out.push({
        type: "chunk",
        id,
        parentDocumentReferenceId: meta.parent,
      });
    }
    onConfirm(out);
  }, [selectedEncounterIds, selectedDocIds, selectedChunks, onConfirm]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      data-testid="background-source-picker"
      aria-labelledby="background-source-picker-title"
    >
      <DialogTitle
        id="background-source-picker-title"
        sx={{ display: "flex", alignItems: "center", gap: 1 }}
      >
        Add an encounter or letter
        <Box sx={{ flexGrow: 1 }} />
        <Chip
          size="small"
          color={totalSelected > 0 ? "primary" : "default"}
          label={`${totalSelected} picked`}
          data-testid="background-source-picker-count"
        />
        <IconButton
          size="small"
          onClick={onClose}
          aria-label="Close background source picker"
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <Tabs
        value={tab}
        onChange={(_e, v) => setTab(v as PickerTab)}
        aria-label="Background source picker tabs"
        sx={{ px: 2 }}
      >
        <Tab
          label="Encounters"
          value="encounters"
          data-testid="background-source-picker-tab-encounters"
        />
        <Tab
          label="Letters and documents"
          value="documents"
          data-testid="background-source-picker-tab-documents"
        />
      </Tabs>
      <Divider />
      <DialogContent>
        {tab === "encounters" && (
          <EncountersPanel
            patientId={patientId}
            selected={selectedEncounterIds}
            onToggle={(id) =>
              setSelectedEncounterIds((prev) => toggleSet(prev, id))
            }
            density={density}
          />
        )}
        {tab === "documents" && (
          <DocumentsPanel
            patientId={patientId}
            selectedDocIds={selectedDocIds}
            selectedChunks={selectedChunks}
            onToggleDoc={(id) =>
              setSelectedDocIds((prev) => toggleSet(prev, id))
            }
            onToggleChunk={(chunkId, parentId) =>
              setSelectedChunks((prev) => toggleChunk(prev, chunkId, parentId))
            }
            density={density}
          />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={onConfirmClick}
          disabled={totalSelected === 0}
          data-testid="background-source-picker-confirm"
        >
          Add {totalSelected > 0 ? totalSelected : ""}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// -- Encounters panel -----------------------------------------------------

function EncountersPanel({
  patientId,
  selected,
  onToggle,
  density,
}: {
  patientId: string;
  selected: Set<string>;
  onToggle: (id: string) => void;
  density: "compact" | "comfortable";
}) {
  const [rows, setRows] = useState<PatientFinderEncounter[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listPatientEncounters(patientId, 100)
      .then((r) => {
        if (!cancelled) setRows(r);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load encounters.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  if (loading) return <Loading />;
  if (error) return <ErrorText>{error}</ErrorText>;
  if (rows.length === 0) {
    return (
      <Empty>
        No encounters found for this patient. Try a different patient or
        widen the time range.
      </Empty>
    );
  }
  return (
    <List dense={density === "compact"} disablePadding>
      {rows.map((e) => {
        const checked = selected.has(e.id);
        return (
          <ListItem key={e.id} disablePadding>
            <ListItemButton
              onClick={() => onToggle(e.id)}
              data-testid={`background-source-encounter-${e.id}`}
            >
              <ListItemIcon>
                <Checkbox
                  edge="start"
                  checked={checked}
                  tabIndex={-1}
                  disableRipple
                  inputProps={{
                    "aria-label": `Select encounter ${e.id}`,
                  }}
                />
              </ListItemIcon>
              <ListItemText
                primary={
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2" fontWeight={600}>
                      {e.date || "(no date)"}
                    </Typography>
                    {e.encounter_type && (
                      <Chip
                        size="small"
                        variant="outlined"
                        label={e.encounter_type}
                      />
                    )}
                    <Chip
                      size="small"
                      variant="outlined"
                      label={`${e.coded_count} codes`}
                    />
                  </Stack>
                }
                secondary={e.top_concept || "No top SNOMED concept"}
              />
            </ListItemButton>
          </ListItem>
        );
      })}
    </List>
  );
}

// -- Documents panel ------------------------------------------------------

function DocumentsPanel({
  patientId,
  selectedDocIds,
  selectedChunks,
  onToggleDoc,
  onToggleChunk,
  density,
}: {
  patientId: string;
  selectedDocIds: Set<string>;
  selectedChunks: Map<string, { parent: string }>;
  onToggleDoc: (id: string) => void;
  onToggleChunk: (chunkId: string, parentId: string) => void;
  density: "compact" | "comfortable";
}) {
  const [rows, setRows] = useState<PatientFinderDocumentReference[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listPatientDocumentReferences(patientId, 100)
      .then((r) => {
        if (!cancelled) setRows(r);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load documents for this patient.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  if (loading) return <Loading />;
  if (error) return <ErrorText>{error}</ErrorText>;
  if (rows.length === 0) {
    return (
      <Empty>
        No letters or documents on file for this patient. Pick another
        patient or check that documents have been uploaded.
      </Empty>
    );
  }
  return (
    <List dense={density === "compact"} disablePadding>
      {rows.map((d) => {
        const isOpen = expanded.has(d.id);
        const isChecked = selectedDocIds.has(d.id);
        return (
          <Box key={d.id}>
            <ListItem
              disablePadding
              secondaryAction={
                d.chunk_count > 0 ? (
                  <IconButton
                    edge="end"
                    aria-label={
                      isOpen
                        ? `Hide chunks for ${d.id}`
                        : `Show chunks for ${d.id}`
                    }
                    onClick={() =>
                      setExpanded((prev) => toggleSet(prev, d.id))
                    }
                    data-testid={`background-source-doc-toggle-${d.id}`}
                  >
                    {isOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  </IconButton>
                ) : null
              }
            >
              <ListItemButton
                onClick={() => onToggleDoc(d.id)}
                data-testid={`background-source-doc-${d.id}`}
              >
                <ListItemIcon>
                  <Checkbox
                    edge="start"
                    checked={isChecked}
                    tabIndex={-1}
                    disableRipple
                    inputProps={{
                      "aria-label": `Select document ${d.id}`,
                    }}
                  />
                </ListItemIcon>
                <ListItemText
                  primary={
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography variant="body2" fontWeight={600}>
                        {d.date || "(no date)"}
                      </Typography>
                      {d.document_type && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={d.document_type}
                        />
                      )}
                      {d.source && (
                        <Chip
                          size="small"
                          variant="outlined"
                          label={d.source}
                        />
                      )}
                      <Chip
                        size="small"
                        variant="outlined"
                        label={`${d.chunk_count} chunks`}
                      />
                    </Stack>
                  }
                  secondary={`Document id: ${d.id}`}
                />
              </ListItemButton>
            </ListItem>
            <Collapse in={isOpen} unmountOnExit>
              <ChunkList
                documentReferenceId={d.id}
                selectedChunks={selectedChunks}
                onToggleChunk={onToggleChunk}
                density={density}
              />
            </Collapse>
          </Box>
        );
      })}
    </List>
  );
}

function ChunkList({
  documentReferenceId,
  selectedChunks,
  onToggleChunk,
  density,
}: {
  documentReferenceId: string;
  selectedChunks: Map<string, { parent: string }>;
  onToggleChunk: (chunkId: string, parentId: string) => void;
  density: "compact" | "comfortable";
}) {
  const [rows, setRows] = useState<PatientFinderChunk[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listDocumentReferenceChunks(documentReferenceId, 500)
      .then((r) => {
        if (!cancelled) setRows(r);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load chunks.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [documentReferenceId]);

  if (loading) {
    return (
      <Box sx={{ pl: 6, py: 1 }}>
        <CircularProgress size={16} />
      </Box>
    );
  }
  if (error) {
    return (
      <Typography
        variant="body2"
        color="error"
        sx={{ pl: 6, py: 1 }}
        data-testid={`background-source-chunks-error-${documentReferenceId}`}
      >
        {error}
      </Typography>
    );
  }
  if (rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ pl: 6, py: 1 }}>
        No chunks under this document.
      </Typography>
    );
  }
  return (
    <List dense={density === "compact"} disablePadding sx={{ pl: 4 }}>
      {rows.map((c) => {
        const checked = selectedChunks.has(c.id);
        return (
          <ListItem key={c.id} disablePadding>
            <ListItemButton
              onClick={() => onToggleChunk(c.id, documentReferenceId)}
              data-testid={`background-source-chunk-${c.id}`}
            >
              <ListItemIcon>
                <Checkbox
                  edge="start"
                  checked={checked}
                  tabIndex={-1}
                  disableRipple
                  inputProps={{ "aria-label": `Select chunk ${c.id}` }}
                />
              </ListItemIcon>
              <ListItemText
                primary={`Chunk ${c.ordinal + 1}`}
                secondary={c.preview || "(no preview)"}
              />
            </ListItemButton>
          </ListItem>
        );
      })}
    </List>
  );
}

// -- Helpers --------------------------------------------------------------

function toggleSet(prev: Set<string>, id: string): Set<string> {
  const next = new Set(prev);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

function toggleChunk(
  prev: Map<string, { parent: string }>,
  chunkId: string,
  parentId: string,
): Map<string, { parent: string }> {
  const next = new Map(prev);
  if (next.has(chunkId)) next.delete(chunkId);
  else next.set(chunkId, { parent: parentId });
  return next;
}

function Loading() {
  return (
    <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
      <CircularProgress size={24} />
    </Box>
  );
}

function ErrorText({ children }: { children: ReactNode }) {
  return (
    <Typography color="error" variant="body2">
      {children}
    </Typography>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return (
    <Typography variant="body2" color="text.secondary">
      {children}
    </Typography>
  );
}
