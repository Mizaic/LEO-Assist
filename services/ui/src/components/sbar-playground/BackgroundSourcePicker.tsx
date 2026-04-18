"use client";

/**
 * BackgroundSourcePicker -- patient-scoped picker for SBAR Background
 * sources (Encounters and DocumentReferences with nested Chunks).
 *
 * The picker reuses the same patient-record browsing capability as the
 * Mission Control patient drawer (DI-LEO-AI-179 + DI-LEO-AI-213): the
 * sticky histogram timeline scrubber, the focus-band brush as the only
 * spatial filter, the Coded-only switch, and the free-text search
 * field. The two surfaces share `EncounterTimelineScrubber` and
 * `applyCommonFilters` so behaviour stays in lock-step.
 *
 * The picker differs from Mission Control in three ways:
 *   1. It is a SELECTION surface -- every row carries a checkbox and
 *      there are no Edit-codes / Reset-and-recode actions.
 *   2. The flat feed is mixed: encounters AND DocumentReferences
 *      sorted by date in the same list. A chip filter narrows the
 *      feed to a single record kind.
 *   3. DocumentReference rows expand inline to reveal child :Chunk
 *      checkboxes -- selecting any chunk under a document drops the
 *      parent DocumentReference from the emitted payload (the
 *      orchestrator treats chunks as a more precise replacement).
 *
 * Design Controls: DI-LEO-AI-232, DI-LEO-AI-179, DI-LEO-AI-213,
 * R-LEO-AI-185, R-LEO-AI-211.
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import Alert from "@mui/material/Alert";
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
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
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
import EncounterTimelineScrubber from "@/components/mission-control/EncounterTimelineScrubber";
import { applyCommonFilters } from "@/components/mission-control/encounterFilters";
import { shortDate } from "@/components/mission-control/encounterTextUtils";

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

type RecordKind = "encounter" | "document";
type KindFilter = "all" | RecordKind;

interface UnifiedRecord {
  /** Namespaced id used for de-dup and the scrubber jump callback. */
  scrubberId: string;
  /** The Neo4j node id used in the emitted payload. */
  realId: string;
  kind: RecordKind;
  date: string;
  text: string | null;
  /** For encounters: coded_count. For documents: chunk_count. The
   *  scrubber treats a non-zero count as "coded" for the Coded-only
   *  switch -- in the picker context that means "has structured
   *  content (codes for encounters, chunks for documents)". */
  countForCodedFilter: number;
  encounter?: PatientFinderEncounter;
  document?: PatientFinderDocumentReference;
}

// -- Component ------------------------------------------------------------

const SCRUBBER_ENCOUNTER_PREFIX = "enc:";
const SCRUBBER_DOCUMENT_PREFIX = "doc:";

export function BackgroundSourcePicker({
  open,
  patientId,
  initialSelected,
  onClose,
  onConfirm,
  density = "compact",
}: BackgroundSourcePickerProps) {
  const [selectedEncounterIds, setSelectedEncounterIds] = useState<
    Set<string>
  >(new Set());
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [selectedChunks, setSelectedChunks] = useState<
    Map<string, { parent: string }>
  >(new Map());

  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [codedOnly, setCodedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [timelineRange, setTimelineRange] = useState<
    { fromMs: number; toMs: number } | null
  >(null);
  const [expandedDocIds, setExpandedDocIds] = useState<Set<string>>(new Set());
  const [focusedScrubberId, setFocusedScrubberId] = useState<string | null>(
    null,
  );

  const [encounters, setEncounters] = useState<PatientFinderEncounter[]>([]);
  const [documents, setDocuments] = useState<PatientFinderDocumentReference[]>(
    [],
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});

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
    setKindFilter("all");
    setCodedOnly(false);
    setSearch("");
    setTimelineRange(null);
    setExpandedDocIds(new Set());
    setFocusedScrubberId(null);
  }, [open, initialSelected]);

  // Load the patient's encounters + documents in parallel when the
  // dialog opens. Both endpoints return a short text snippet so the
  // picker can run free-text search client-side.
  useEffect(() => {
    if (!open || !patientId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      listPatientEncounters(patientId, 500),
      listPatientDocumentReferences(patientId, 500),
    ])
      .then(([enc, docs]) => {
        if (cancelled) return;
        setEncounters(enc);
        setDocuments(docs);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof Error
            ? err.message
            : "Could not load this patient's records.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, patientId]);

  const records = useMemo<UnifiedRecord[]>(() => {
    const out: UnifiedRecord[] = [];
    for (const e of encounters) {
      out.push({
        scrubberId: SCRUBBER_ENCOUNTER_PREFIX + e.id,
        realId: e.id,
        kind: "encounter",
        date: e.date ?? "",
        text: e.text ?? null,
        countForCodedFilter: e.coded_count ?? 0,
        encounter: e,
      });
    }
    for (const d of documents) {
      out.push({
        scrubberId: SCRUBBER_DOCUMENT_PREFIX + d.id,
        realId: d.id,
        kind: "document",
        date: d.date ?? "",
        text: d.text ?? null,
        countForCodedFilter: d.chunk_count ?? 0,
        document: d,
      });
    }
    return out;
  }, [encounters, documents]);

  // Records reshaped for the EncounterTimelineScrubber primitive.
  // The scrubber only cares about (encounter_id, date, text,
  // coded_count) -- we pass the namespaced scrubberId so the click
  // callback can route back to the correct row.
  const scrubberRecords = useMemo(
    () =>
      records.map((r) => ({
        encounter_id: r.scrubberId,
        date: r.date,
        text: r.text,
        coded_count: r.countForCodedFilter,
      })),
    [records],
  );

  const filteredRecords = useMemo(() => {
    const filtered = applyCommonFilters(
      records.map((r) => ({
        encounter_id: r.scrubberId,
        date: r.date,
        text: r.text ?? "",
        coded_count: r.countForCodedFilter,
        _ref: r,
      })),
      { codedOnly, search, timelineRange },
    );
    const byKind =
      kindFilter === "all"
        ? filtered
        : filtered.filter((r) => r._ref.kind === kindFilter);
    return byKind
      .map((r) => r._ref)
      .sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
  }, [records, codedOnly, search, timelineRange, kindFilter]);

  const totalSelected =
    selectedEncounterIds.size + selectedDocIds.size + selectedChunks.size;

  // "Select all" only acts on what is CURRENTLY visible after the
  // kind / search / brush / Coded-only filter, so the reviewer's
  // mental model matches what they can see. Chunks are not bulk-
  // selected: they are a more granular cut and the reviewer is
  // expected to expand a letter and pick chunks deliberately.
  const visibleEncounterIds = useMemo(
    () =>
      filteredRecords
        .filter((r) => r.kind === "encounter")
        .map((r) => r.realId),
    [filteredRecords],
  );
  const visibleDocIds = useMemo(
    () =>
      filteredRecords
        .filter((r) => r.kind === "document")
        .map((r) => r.realId),
    [filteredRecords],
  );
  const visibleAlreadySelected =
    visibleEncounterIds.every((id) => selectedEncounterIds.has(id)) &&
    visibleDocIds.every((id) => selectedDocIds.has(id)) &&
    (visibleEncounterIds.length + visibleDocIds.length) > 0;

  const onSelectAllVisible = useCallback(() => {
    setSelectedEncounterIds((prev) => {
      const next = new Set(prev);
      for (const id of visibleEncounterIds) next.add(id);
      return next;
    });
    setSelectedDocIds((prev) => {
      const next = new Set(prev);
      for (const id of visibleDocIds) next.add(id);
      return next;
    });
  }, [visibleEncounterIds, visibleDocIds]);

  const onClearAllSelections = useCallback(() => {
    setSelectedEncounterIds(new Set());
    setSelectedDocIds(new Set());
    setSelectedChunks(new Map());
  }, []);

  const onConfirmClick = useCallback(() => {
    const out: SelectedBackgroundSource[] = [];
    for (const id of selectedEncounterIds) {
      out.push({ type: "encounter", id });
    }
    // "Chunks drop parent": if any chunk under a document is selected,
    // we emit the chunks and drop the parent DocumentReference even
    // if the user also ticked the document-level checkbox.
    const docsWithChunks = new Set<string>();
    for (const meta of selectedChunks.values()) {
      docsWithChunks.add(meta.parent);
    }
    for (const id of selectedDocIds) {
      if (docsWithChunks.has(id)) continue;
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

  const onJumpToRecord = useCallback((scrubberId: string) => {
    setSearch("");
    setCodedOnly(false);
    setTimelineRange(null);
    if (scrubberId.startsWith(SCRUBBER_DOCUMENT_PREFIX)) {
      const realId = scrubberId.slice(SCRUBBER_DOCUMENT_PREFIX.length);
      setExpandedDocIds((prev) => {
        const next = new Set(prev);
        next.add(realId);
        return next;
      });
    }
    setFocusedScrubberId(scrubberId);
  }, []);

  useEffect(() => {
    if (!focusedScrubberId) return;
    const node = rowRefs.current[focusedScrubberId];
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    const t = window.setTimeout(() => setFocusedScrubberId(null), 2200);
    return () => window.clearTimeout(t);
  }, [focusedScrubberId, filteredRecords.length]);

  const handleTimelineRangeChange = useCallback(
    (fromMs: number | null, toMs: number | null) => {
      setTimelineRange(
        fromMs == null || toMs == null ? null : { fromMs, toMs },
      );
    },
    [],
  );

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
        Add records to the SBAR
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
      <Divider />
      <DialogContent
        sx={{ display: "flex", flexDirection: "column", gap: 1.5, pt: 2 }}
      >
        <Typography variant="caption" color="text.secondary">
          Pick the encounters and letters you want LEO to summarise.
          Drag the focus band on the timeline to narrow by date,
          search the text, and tick the records you need.
        </Typography>

        {error && <Alert severity="error">{error}</Alert>}
        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
            <CircularProgress size={24} aria-label="Loading patient records" />
          </Box>
        )}

        {!loading && !error && records.length === 0 && (
          <Alert severity="info">
            No encounters or letters on file for this patient yet.
          </Alert>
        )}

        {!loading && !error && records.length > 0 && (
          <>
            <EncounterTimelineScrubber
              encounters={scrubberRecords}
              linkedEncounterIds={EMPTY_LINKED_SET}
              episodeFrom={null}
              episodeTo={null}
              activeEncounterId={focusedScrubberId}
              onJumpToEncounter={onJumpToRecord}
              visibleFromMs={timelineRange?.fromMs ?? null}
              visibleToMs={timelineRange?.toMs ?? null}
              onVisibleRangeChange={handleTimelineRangeChange}
            />

            {timelineRange && (
              <Alert
                severity="info"
                variant="outlined"
                data-testid="background-source-picker-range-banner"
                sx={{ py: 0.25 }}
                action={
                  <Button
                    size="small"
                    color="inherit"
                    onClick={() => setTimelineRange(null)}
                  >
                    Clear
                  </Button>
                }
              >
                Records filtered to{" "}
                {shortDate(new Date(timelineRange.fromMs).toISOString())} -{" "}
                {shortDate(new Date(timelineRange.toMs).toISOString())}
              </Alert>
            )}

            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={1.5}
              alignItems={{ xs: "stretch", sm: "center" }}
            >
              <ToggleButtonGroup
                size="small"
                exclusive
                value={kindFilter}
                onChange={(_e, v) => v && setKindFilter(v as KindFilter)}
                aria-label="Filter records by kind"
                data-testid="background-source-picker-kind-toggle"
              >
                <ToggleButton value="all" data-testid="kind-toggle-all">
                  All ({records.length})
                </ToggleButton>
                <ToggleButton
                  value="encounter"
                  data-testid="kind-toggle-encounters"
                >
                  Encounters ({encounters.length})
                </ToggleButton>
                <ToggleButton
                  value="document"
                  data-testid="kind-toggle-documents"
                >
                  Letters ({documents.length})
                </ToggleButton>
              </ToggleButtonGroup>
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={codedOnly}
                    onChange={(_, v) => setCodedOnly(v)}
                    data-testid="background-source-picker-coded-only"
                  />
                }
                label={
                  <Typography variant="caption">
                    Coded or with chunks only
                  </Typography>
                }
              />
            </Stack>

            <TextField
              size="small"
              fullWidth
              label="Search text in shown records"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="background-source-picker-search"
            />

            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              data-testid="background-source-picker-bulk-actions"
            >
              <Typography variant="caption" color="text.secondary">
                {filteredRecords.length} record
                {filteredRecords.length === 1 ? "" : "s"} shown
              </Typography>
              <Box sx={{ flexGrow: 1 }} />
              <Button
                size="small"
                disabled={
                  filteredRecords.length === 0 || visibleAlreadySelected
                }
                onClick={onSelectAllVisible}
                data-testid="background-source-picker-select-all"
              >
                Select all shown
              </Button>
              <Button
                size="small"
                color="inherit"
                disabled={totalSelected === 0}
                onClick={onClearAllSelections}
                data-testid="background-source-picker-clear-selection"
              >
                Clear selection
              </Button>
            </Stack>

            {filteredRecords.length === 0 ? (
              <Alert severity="info">
                No records match this filter. Drag the focus band wider, or
                clear "Coded only" / search.
              </Alert>
            ) : (
              <Box
                sx={{
                  display: "flex",
                  flexDirection: "column",
                  gap: density === "compact" ? 0.5 : 1,
                }}
              >
                {filteredRecords.map((rec) =>
                  rec.kind === "encounter" ? (
                    <EncounterRow
                      key={rec.scrubberId}
                      ref={(node) => {
                        rowRefs.current[rec.scrubberId] = node;
                      }}
                      rec={rec}
                      isFocused={focusedScrubberId === rec.scrubberId}
                      checked={selectedEncounterIds.has(rec.realId)}
                      onToggle={() =>
                        setSelectedEncounterIds((prev) =>
                          toggleSet(prev, rec.realId),
                        )
                      }
                    />
                  ) : (
                    <DocumentRow
                      key={rec.scrubberId}
                      ref={(node) => {
                        rowRefs.current[rec.scrubberId] = node;
                      }}
                      rec={rec}
                      isFocused={focusedScrubberId === rec.scrubberId}
                      isExpanded={expandedDocIds.has(rec.realId)}
                      onToggleExpanded={() =>
                        setExpandedDocIds((prev) =>
                          toggleSet(prev, rec.realId),
                        )
                      }
                      checked={selectedDocIds.has(rec.realId)}
                      onToggleDoc={() =>
                        setSelectedDocIds((prev) =>
                          toggleSet(prev, rec.realId),
                        )
                      }
                      selectedChunks={selectedChunks}
                      onToggleChunk={(chunkId) =>
                        setSelectedChunks((prev) =>
                          toggleChunk(prev, chunkId, rec.realId),
                        )
                      }
                      density={density}
                    />
                  ),
                )}
              </Box>
            )}
          </>
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

const EMPTY_LINKED_SET: Set<string> = new Set();

// -- Row primitives -------------------------------------------------------

interface EncounterRowProps {
  rec: UnifiedRecord;
  isFocused: boolean;
  checked: boolean;
  onToggle: () => void;
}

const EncounterRow = withRowRef<EncounterRowProps>(function EncounterRow({
  rec,
  isFocused,
  checked,
  onToggle,
  forwardedRef,
}) {
  const e = rec.encounter!;
  return (
    <RowShell
      ref={forwardedRef}
      scrubberId={rec.scrubberId}
      isFocused={isFocused}
      onClick={onToggle}
      testId={`background-source-encounter-${rec.realId}`}
    >
      <Checkbox
        edge="start"
        checked={checked}
        tabIndex={-1}
        disableRipple
        inputProps={{ "aria-label": `Select encounter ${rec.realId}` }}
      />
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="body2" fontWeight={600}>
            {shortDate(rec.date) || "(no date)"}
          </Typography>
          <Chip size="small" label="Encounter" color="default" />
          {e.encounter_type && (
            <Chip size="small" variant="outlined" label={e.encounter_type} />
          )}
          <Chip
            size="small"
            variant="outlined"
            label={`${e.coded_count} codes`}
          />
        </Stack>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={oneLine}
        >
          {e.top_concept || rec.text || "No top SNOMED concept"}
        </Typography>
      </Box>
    </RowShell>
  );
});

interface DocumentRowProps {
  rec: UnifiedRecord;
  isFocused: boolean;
  isExpanded: boolean;
  onToggleExpanded: () => void;
  checked: boolean;
  onToggleDoc: () => void;
  selectedChunks: Map<string, { parent: string }>;
  onToggleChunk: (chunkId: string) => void;
  density: "compact" | "comfortable";
}

const DocumentRow = withRowRef<DocumentRowProps>(function DocumentRow({
  rec,
  isFocused,
  isExpanded,
  onToggleExpanded,
  checked,
  onToggleDoc,
  selectedChunks,
  onToggleChunk,
  density,
  forwardedRef,
}) {
  const d = rec.document!;
  return (
    <Box
      ref={forwardedRef}
      data-row-id={rec.scrubberId}
      sx={{
        border: "1px solid",
        borderColor: isFocused ? "primary.main" : "divider",
        borderRadius: 1,
        transition: "border-color 0.25s ease",
      }}
    >
      <RowShell
        scrubberId={rec.scrubberId}
        isFocused={isFocused}
        onClick={onToggleDoc}
        testId={`background-source-doc-${rec.realId}`}
        flat
      >
        <Checkbox
          edge="start"
          checked={checked}
          tabIndex={-1}
          disableRipple
          inputProps={{ "aria-label": `Select document ${rec.realId}` }}
        />
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            flexWrap="wrap"
          >
            <Typography variant="body2" fontWeight={600}>
              {shortDate(rec.date) || "(no date)"}
            </Typography>
            <Chip size="small" label="Letter" color="secondary" />
            {d.document_type && (
              <Chip size="small" variant="outlined" label={d.document_type} />
            )}
            {d.source && (
              <Chip size="small" variant="outlined" label={d.source} />
            )}
            <Chip
              size="small"
              variant="outlined"
              label={`${d.chunk_count} chunks`}
            />
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={oneLine}>
            {rec.text || `Document id: ${rec.realId}`}
          </Typography>
        </Box>
        {d.chunk_count > 0 && (
          <IconButton
            size="small"
            edge="end"
            aria-label={
              isExpanded
                ? `Hide chunks for ${rec.realId}`
                : `Show chunks for ${rec.realId}`
            }
            onClick={(e) => {
              e.stopPropagation();
              onToggleExpanded();
            }}
            data-testid={`background-source-doc-toggle-${rec.realId}`}
          >
            {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        )}
      </RowShell>
      <Collapse in={isExpanded} unmountOnExit>
        <ChunkList
          documentReferenceId={rec.realId}
          selectedChunks={selectedChunks}
          onToggleChunk={onToggleChunk}
          density={density}
        />
      </Collapse>
    </Box>
  );
});

interface RowShellProps {
  scrubberId: string;
  isFocused: boolean;
  onClick: () => void;
  testId: string;
  flat?: boolean;
  children: ReactNode;
}

const RowShell = forwardRefAdapter<RowShellProps>(function RowShell(
  { scrubberId, isFocused, onClick, testId, flat, children, forwardedRef },
) {
  return (
    <Box
      ref={forwardedRef}
      data-row-id={scrubberId}
      data-testid={testId}
      onClick={onClick}
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1,
        px: 1,
        py: 0.5,
        cursor: "pointer",
        borderRadius: flat ? 0 : 1,
        border: flat ? "none" : "1px solid",
        borderColor: isFocused ? "primary.main" : "divider",
        transition: "border-color 0.25s ease",
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      {children}
    </Box>
  );
});

function ChunkList({
  documentReferenceId,
  selectedChunks,
  onToggleChunk,
  density,
}: {
  documentReferenceId: string;
  selectedChunks: Map<string, { parent: string }>;
  onToggleChunk: (chunkId: string) => void;
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
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Could not load chunks.",
        );
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
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        gap: density === "compact" ? 0.25 : 0.5,
        pl: 5,
        pr: 1,
        pb: 1,
      }}
    >
      {rows.map((c) => {
        const checked = selectedChunks.has(c.id);
        return (
          <Box
            key={c.id}
            data-testid={`background-source-chunk-${c.id}`}
            onClick={() => onToggleChunk(c.id)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
              cursor: "pointer",
              borderRadius: 0.5,
              px: 0.5,
              py: 0.25,
              "&:hover": { bgcolor: "action.hover" },
            }}
          >
            <Checkbox
              size="small"
              edge="start"
              checked={checked}
              tabIndex={-1}
              disableRipple
              inputProps={{ "aria-label": `Select chunk ${c.id}` }}
            />
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Typography variant="caption" fontWeight={600}>
                Chunk {c.ordinal + 1}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={oneLine}>
                {c.preview || "(no preview)"}
              </Typography>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

// -- Style helpers --------------------------------------------------------

const oneLine = {
  display: "block",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
} as const;

// -- ref-forwarding adapters ---------------------------------------------
//
// React's `forwardRef` plus generic prop types is awkward, so we wrap
// each row type with a tiny adapter that injects `forwardedRef` as a
// regular prop. Avoids `as any` casts at the call sites.

function forwardRefAdapter<P extends { forwardedRef?: React.Ref<HTMLDivElement> }>(
  Component: (props: P) => JSX.Element,
) {
  return forwardRef<HTMLDivElement, Omit<P, "forwardedRef">>((props, ref) =>
    Component({ ...(props as P), forwardedRef: ref }),
  );
}

function withRowRef<P>(
  Component: (props: P & { forwardedRef?: React.Ref<HTMLDivElement> }) => JSX.Element,
) {
  return forwardRef<HTMLDivElement, P>((props, ref) =>
    Component({ ...props, forwardedRef: ref } as P & {
      forwardedRef?: React.Ref<HTMLDivElement>;
    }),
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
