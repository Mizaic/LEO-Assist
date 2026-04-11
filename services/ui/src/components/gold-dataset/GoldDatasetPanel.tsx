"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Pagination from "@mui/material/Pagination";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import MenuItem from "@mui/material/MenuItem";
import TableRow from "@mui/material/TableRow";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DownloadIcon from "@mui/icons-material/Download";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import LinkIcon from "@mui/icons-material/Link";
import NotInterestedIcon from "@mui/icons-material/NotInterested";
import SearchIcon from "@mui/icons-material/Search";
import SyncIcon from "@mui/icons-material/Sync";
import VerifiedIcon from "@mui/icons-material/Verified";
import { exportMedSpaCyTraining, fetchSurfaceForms, patchGoldLabelEntities, upsertSurfaceFormMapping } from "@/lib/api/legacy";
import type { TermSearchResult } from "@/lib/types";
import ConfirmDialog from "@/components/ConfirmDialog";
import TermSearch from "@/components/TermSearch";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CandidateStats {
  total: number;
  pending: number;
  processing: number;
  completed: number;
  failed: number;
}

interface GoldStats {
  total: number;
  avg_quality_score: number | null;
  high_quality: number;
}

interface Candidate {
  candidate_id: string;
  text: string;
  source: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface GoldLabel {
  label_id: string;
  text: string;
  entities_json: string | null;
  quality_score: number | null;
  source: string;
  verified_by: string | null;
  verified_at: string | null;
  candidate_id: string | null;
  updated_at: string;
}

interface Entity {
  text: string;
  label?: string;
  semantic_tag?: string;
  snomed_concept_id?: string;
  assertion?: string;
}

interface DeleteGoldLabelResult {
  label_id: string;
  candidate_id: string | null;
  candidate_reset: boolean;
  candidate_status: string | null;
}

interface DeleteTrainingCandidateResult {
  candidate_id: string;
  gold_labels_deleted: number;
  surface_form_tasks_deleted: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

function parseEntities(json: string | null): Entity[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    if (Array.isArray(parsed)) return parsed as Entity[];
    return [];
  } catch {
    return [];
  }
}

const ASSERTION_LABEL: Record<string, string> = {
  present:      "Present",
  absent:       "Absent",
  refuted:      "Refuted",
  possible:     "Possible",
  uncertain:    "Uncertain",
  historical:   "Historical",
  family:       "Family history",
  hypothetical: "Hypothetical",
};

const ENTITY_LABEL_OPTIONS = [
  "finding",
  "disorder",
  "procedure",
  "observable_entity",
  "situation",
  "event",
  "body_structure",
  "substance",
  "medicinal_product",
  "clinical_drug",
  "qualifier_value",
  "tumor_staging",
  "assessment_scale",
  "staging_scale",
  "regime_therapy",
  "record_artifact",
  "physical_object",
  "organism",
  "morphologic_abnormality",
  "occupation",
  "attribute",
  "environment",
  "product",
  "X_TEMPORAL",
  "X_DOSAGE",
  "X_FREQUENCY",
  "X_ROUTE",
] as const;

const ASSERTION_OPTIONS = [
  "present",
  "possible",
  "uncertain",
  "historical",
  "family",
  "absent",
  "refuted",
  "hypothetical",
  "planned",
  "declined",
  "cancelled",
] as const;

function formatAssertion(assertion: string | undefined): string {
  const key = (assertion ?? "present").toLowerCase().replace(/_/g, " ").trim();
  return ASSERTION_LABEL[key] ?? (key.charAt(0).toUpperCase() + key.slice(1));
}

/** Returns true for assertions that differ meaningfully from "present" */
function isNonPresent(assertion: string | undefined): boolean {
  const key = (assertion ?? "present").toLowerCase().trim();
  return key !== "present";
}

function assertionColor(
  assertion: string | undefined,
): "default" | "success" | "warning" | "info" | "error" {
  switch ((assertion ?? "present").toLowerCase()) {
    case "present":      return "success";
    case "possible":
    case "uncertain":    return "warning";
    case "historical":
    case "family":       return "info";
    case "absent":
    case "refuted":      return "error";
    case "hypothetical": return "warning";
    default:             return "default";
  }
}

/** Build a brief assertion summary line from a list of entities */
function assertionSummary(entities: Entity[]): string | null {
  const counts: Record<string, number> = {};
  for (const e of entities) {
    const key = formatAssertion(e.assertion);
    counts[key] = (counts[key] ?? 0) + 1;
  }
  const parts = Object.entries(counts)
    .sort(([a], [b]) => (a === "Present" ? -1 : b === "Present" ? 1 : 0))
    .map(([k, v]) => `${v} ${k.toLowerCase()}`);
  if (parts.length <= 1 && counts["Present"] === entities.length) return null;
  return parts.join(" · ");
}

function truncate(text: string, max = 140) {
  if (!text) return "—";
  return text.length > max ? text.slice(0, max) + "…" : text;
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function qualityColor(score: number | null): "success" | "warning" | "error" | "default" {
  if (score === null) return "default";
  if (score >= 0.8) return "success";
  if (score >= 0.5) return "warning";
  return "error";
}

function statusColor(status: string): "success" | "warning" | "error" | "info" | "default" {
  switch (status) {
    case "completed": return "success";
    case "pending": return "warning";
    case "processing": return "info";
    case "failed": return "error";
    default: return "default";
  }
}

function statusIcon(status: string) {
  switch (status) {
    case "completed": return <CheckCircleOutlineIcon sx={{ fontSize: 14 }} />;
    case "failed": return <ErrorOutlineIcon sx={{ fontSize: 14 }} />;
    case "processing": return <SyncIcon sx={{ fontSize: 14 }} />;
    default: return <HourglassEmptyIcon sx={{ fontSize: 14 }} />;
  }
}

// ---------------------------------------------------------------------------
// Stat tile
// ---------------------------------------------------------------------------

function StatTile({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <Box sx={{ p: 2, border: "1px solid", borderColor: "divider", borderRadius: 2, minWidth: 130, textAlign: "center" }}>
      <Typography variant="h5" sx={{ fontWeight: 700, color: color ?? "text.primary" }}>
        {value}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block">{label}</Typography>
      {sub && <Typography variant="caption" color="text.disabled" display="block">{sub}</Typography>}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Detail dialog
// ---------------------------------------------------------------------------

function DetailField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </Typography>
      <Box sx={{ mt: 0.25 }}>{children}</Box>
    </Box>
  );
}

function CandidateDetailDialog({
  item,
  onClose,
  onDelete,
  deleting,
  onEditTerms,
  openingLabelEditor,
  onMarkGold,
  markingGold,
}: {
  item: Candidate;
  onClose: () => void;
  onDelete: (candidateId: string) => void;
  deleting: boolean;
  onEditTerms: (candidateId: string) => void;
  openingLabelEditor: boolean;
  onMarkGold: (candidateId: string) => void;
  markingGold: boolean;
}) {
  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth scroll="paper">
      <DialogTitle sx={{ pr: 6 }}>
        Candidate
        <Typography component="span" variant="body2" sx={{ fontFamily: "monospace", color: "text.secondary", ml: 1 }}>
          {item.candidate_id}
        </Typography>
        <IconButton onClick={onClose} size="small" sx={{ position: "absolute", top: 12, right: 12 }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <DetailField label="Encounter text">
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {item.text || "—"}
          </Typography>
        </DetailField>
        <Divider sx={{ my: 2 }} />
        <Stack direction="row" flexWrap="wrap" spacing={3} useFlexGap>
          <DetailField label="Status">
            <Chip
              icon={statusIcon(item.status)}
              label={item.status}
              color={statusColor(item.status)}
              size="small"
              sx={{ fontWeight: 600, textTransform: "capitalize" }}
            />
          </DetailField>
          <DetailField label="Source">
            <Typography variant="body2">{item.source || "—"}</Typography>
          </DetailField>
          <DetailField label="Created">
            <Typography variant="body2">{formatDate(item.created_at)}</Typography>
          </DetailField>
          <DetailField label="Updated">
            <Typography variant="body2">{formatDate(item.updated_at)}</Typography>
          </DetailField>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button variant="text" onClick={onClose}>
          Close
        </Button>
        <Button
          variant="outlined"
          startIcon={openingLabelEditor ? <CircularProgress size={14} /> : <SearchIcon fontSize="small" />}
          disabled={deleting || openingLabelEditor || markingGold}
          onClick={() => onEditTerms(item.candidate_id)}
        >
          Edit terms and assertions
        </Button>
        <Button
          variant="contained"
          color="success"
          startIcon={markingGold ? <CircularProgress size={14} /> : <VerifiedIcon fontSize="small" />}
          disabled={deleting || openingLabelEditor || markingGold}
          onClick={() => onMarkGold(item.candidate_id)}
        >
          Mark as gold data
        </Button>
        <Button
          variant="contained"
          color="error"
          startIcon={deleting ? <CircularProgress size={14} /> : <DeleteOutlineIcon fontSize="small" />}
          disabled={deleting}
          onClick={() => onDelete(item.candidate_id)}
        >
          Delete candidate
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// State for the row being looked up: index into entities array
interface LookupTarget {
  entityIndex: number;
  entityText: string;
  entityLabel: string;
}

function GoldLabelDetailDialog({
  item,
  onClose,
  onEntitiesChanged,
}: {
  item: GoldLabel;
  onClose: () => void;
  onEntitiesChanged?: () => void;
}) {
  const [entities, setEntities] = useState<Entity[]>(() => parseEntities(item.entities_json));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [newEntityText, setNewEntityText] = useState("");
  const [newEntityLabel, setNewEntityLabel] = useState<(typeof ENTITY_LABEL_OPTIONS)[number]>("finding");
  const [newEntityAssertion, setNewEntityAssertion] = useState<(typeof ASSERTION_OPTIONS)[number]>("present");
  const [lookupTarget, setLookupTarget] = useState<LookupTarget | null>(null);

  async function persistEntities(next: Entity[], successMsg: string) {
    setSaving(true);
    setSaveError(null);
    setSaveMsg(null);
    try {
      await patchGoldLabelEntities(
        item.label_id,
        next.map((e) => ({
          text: e.text,
          label: e.label ?? "finding",
          assertion: e.assertion,
          snomed_concept_id: e.snomed_concept_id,
          semantic_tag: e.semantic_tag,
        })),
      );
      setEntities(next);
      setSaveMsg(successMsg);
      onEntitiesChanged?.();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save changes");
    } finally {
      setSaving(false);
    }
  }

  function handleRemoveEntity(idx: number) {
    const next = entities.filter((_, i) => i !== idx);
    void persistEntities(next, `Removed "${entities[idx].text}" from this label.`);
  }

  function handleUpdateEntityAssertion(idx: number, assertion: string) {
    const next = entities.map((entity, i) =>
      i === idx ? { ...entity, assertion } : entity,
    );
    void persistEntities(
      next,
      `Updated assertion for "${entities[idx].text}" to ${formatAssertion(assertion)}.`,
    );
  }

  function handleAddEntity() {
    const text = newEntityText.trim();
    if (!text) {
      setSaveError("Enter a term before adding it.");
      return;
    }
    const duplicate = entities.some(
      (entity) =>
        entity.text.trim().toLowerCase() === text.toLowerCase() &&
        (entity.label ?? "").trim().toLowerCase() === newEntityLabel.toLowerCase() &&
        (entity.assertion ?? "present").trim().toLowerCase() === newEntityAssertion.toLowerCase(),
    );
    if (duplicate) {
      setSaveError("This term is already in the label with the same type and assertion.");
      return;
    }
    const next = [
      ...entities,
      {
        text,
        label: newEntityLabel,
        assertion: newEntityAssertion,
      },
    ];
    setNewEntityText("");
    setSaveError(null);
    void persistEntities(next, `Added "${text}" to this label.`);
  }

  async function handleSnomedSelected(result: TermSearchResult, alsoFixSurfaceForm: boolean) {
    if (lookupTarget === null) return;
    const { entityIndex, entityText } = lookupTarget;
    setLookupTarget(null);

    const next = entities.map((e, i) =>
      i === entityIndex
        ? { ...e, snomed_concept_id: result.snomed_concept_id, semantic_tag: result.semantic_tag ?? e.semantic_tag }
        : e,
    );

    let surfaceFormNote = "";
    if (alsoFixSurfaceForm) {
      try {
        const normalized = entityText.toLowerCase().trim();
        const existing = await fetchSurfaceForms(normalized, result.snomed_concept_id, 1, 0);
        const mappingExists = existing.items.some(
          (item) =>
            item.normalized === normalized &&
            item.concept_id === result.snomed_concept_id,
        );
        if (mappingExists) {
          surfaceFormNote = " Surface form mapping already exists.";
        } else {
          await upsertSurfaceFormMapping(normalized, entityText, result.snomed_concept_id, {
            provenance: "manual_correction",
            source: "gold_label_editor",
          });
          surfaceFormNote = " Surface form mapping created.";
        }
      } catch {
        // Surface form check/write is non-blocking - entity save continues.
        surfaceFormNote = " Could not verify surface form mapping.";
      }
    }

    void persistEntities(
      next,
      `Updated SNOMED code to ${result.snomed_concept_id} - ${result.term}.${surfaceFormNote}`,
    );
  }

  const summary = assertionSummary(entities);

  return (
    <>
      <Dialog open onClose={onClose} maxWidth="md" fullWidth scroll="paper">
        <DialogTitle sx={{ pr: 6 }}>
          Verified gold label
          <Typography component="span" variant="body2" sx={{ fontFamily: "monospace", color: "text.secondary", ml: 1 }}>
            {item.label_id}
          </Typography>
          <IconButton onClick={onClose} size="small" sx={{ position: "absolute", top: 12, right: 12 }}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          {saveError && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setSaveError(null)}>
              {saveError}
            </Alert>
          )}
          {saveMsg && (
            <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSaveMsg(null)}>
              {saveMsg}
            </Alert>
          )}

          <DetailField label="Encounter text">
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {item.text || "—"}
            </Typography>
          </DetailField>

          <Divider sx={{ my: 2 }} />
          <DetailField label="Add term">
            <Stack direction={{ xs: "column", md: "row" }} spacing={1} useFlexGap>
              <TextField
                value={newEntityText}
                onChange={(event) => setNewEntityText(event.target.value)}
                label="Term"
                size="small"
                fullWidth
                placeholder="Add a term to this verified label"
                disabled={saving}
              />
              <TextField
                select
                label="Type"
                size="small"
                value={newEntityLabel}
                onChange={(event) => setNewEntityLabel(event.target.value as (typeof ENTITY_LABEL_OPTIONS)[number])}
                disabled={saving}
                sx={{ minWidth: 170 }}
              >
                {ENTITY_LABEL_OPTIONS.map((option) => (
                  <MenuItem key={option} value={option}>
                    {option}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Assertion"
                size="small"
                value={newEntityAssertion}
                onChange={(event) => setNewEntityAssertion(event.target.value as (typeof ASSERTION_OPTIONS)[number])}
                disabled={saving}
                sx={{ minWidth: 170 }}
              >
                {ASSERTION_OPTIONS.map((option) => (
                  <MenuItem key={option} value={option}>
                    {formatAssertion(option)}
                  </MenuItem>
                ))}
              </TextField>
              <Button variant="contained" size="small" onClick={handleAddEntity} disabled={saving || !newEntityText.trim()}>
                Add term
              </Button>
            </Stack>
          </DetailField>

          {entities.length > 0 && (
            <>
              <Divider sx={{ my: 2 }} />
              <DetailField label={`Entities (${entities.length})`}>
                {summary && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1, fontStyle: "italic" }}>
                    {summary}
                  </Typography>
                )}
                <Table size="small" sx={{ "& td, & th": { px: 1.25, py: 0.75 } }}>
                  <TableHead>
                    <TableRow sx={{ "& th": { fontWeight: 700, fontSize: "0.72rem", color: "text.secondary", textTransform: "uppercase", letterSpacing: "0.04em", borderBottom: "2px solid", borderColor: "divider" } }}>
                      <TableCell>Term</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Assertion</TableCell>
                      <TableCell>SNOMED CT</TableCell>
                      <TableCell sx={{ width: 80 }} />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {entities.map((e, i) => {
                      const nonPresent = isNonPresent(e.assertion);
                      const aColor = assertionColor(e.assertion);
                      const hasSnomed = !!e.snomed_concept_id;
                      return (
                        <TableRow
                          key={i}
                          sx={{
                            "&:last-child td": { border: 0 },
                            bgcolor: nonPresent ? `${aColor}.50` : "transparent",
                            "&:hover": { bgcolor: nonPresent ? `${aColor}.100` : "action.hover" },
                          }}
                        >
                          <TableCell>
                            <Typography variant="body2" sx={{ fontWeight: 500 }}>
                              {e.text}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption" color="primary.main" sx={{ fontWeight: 600 }}>
                              {e.label ?? e.semantic_tag ?? "—"}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <TextField
                              select
                              size="small"
                              value={(e.assertion ?? "present").toLowerCase()}
                              onChange={(event) =>
                                handleUpdateEntityAssertion(i, event.target.value)
                              }
                              disabled={saving}
                              sx={{
                                minWidth: 132,
                                "& .MuiInputBase-input": {
                                  py: 0.45,
                                  fontSize: "0.75rem",
                                  fontWeight: 600,
                                },
                              }}
                            >
                              {ASSERTION_OPTIONS.map((option) => (
                                <MenuItem key={option} value={option}>
                                  {formatAssertion(option)}
                                </MenuItem>
                              ))}
                            </TextField>
                          </TableCell>
                          <TableCell>
                            {hasSnomed ? (
                              <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
                                {e.snomed_concept_id}
                              </Typography>
                            ) : (
                              <Typography variant="caption" color="error.main" sx={{ fontStyle: "italic" }}>
                                No code
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell align="right">
                            <Stack direction="row" spacing={0.25} justifyContent="flex-end">
                              <Tooltip title={hasSnomed ? "Fix SNOMED code" : "Look up SNOMED code"}>
                                <span>
                                  <IconButton
                                    size="small"
                                    color={hasSnomed ? "default" : "warning"}
                                    disabled={saving}
                                    onClick={() =>
                                      setLookupTarget({
                                        entityIndex: i,
                                        entityText: e.text,
                                        entityLabel: e.label ?? e.semantic_tag ?? "",
                                      })
                                    }
                                  >
                                    {saving ? (
                                      <CircularProgress size={14} />
                                    ) : (
                                      <SearchIcon sx={{ fontSize: 16 }} />
                                    )}
                                  </IconButton>
                                </span>
                              </Tooltip>
                              <Tooltip title="Remove this entity from the label">
                                <span>
                                  <IconButton
                                    size="small"
                                    color="error"
                                    disabled={saving}
                                    onClick={() => handleRemoveEntity(i)}
                                  >
                                    <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                                  </IconButton>
                                </span>
                              </Tooltip>
                            </Stack>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </DetailField>
            </>
          )}

          <Divider sx={{ my: 2 }} />
          <Stack direction="row" flexWrap="wrap" spacing={3} useFlexGap>
            <DetailField label="Quality score">
              <Chip
                icon={<VerifiedIcon sx={{ fontSize: 14 }} />}
                label={item.quality_score !== null ? `${Math.round(item.quality_score * 100)}%` : "unscored"}
                color={qualityColor(item.quality_score)}
                size="small"
                sx={{ fontWeight: 700 }}
              />
            </DetailField>
            <DetailField label="Source">
              <Typography variant="body2">{item.source || "—"}</Typography>
            </DetailField>
            <DetailField label="Verified by">
              <Typography variant="body2">{item.verified_by || "—"}</Typography>
            </DetailField>
            <DetailField label="Verified at">
              <Typography variant="body2">{formatDate(item.verified_at)}</Typography>
            </DetailField>
            <DetailField label="Candidate ID">
              <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
                {item.candidate_id || "—"}
              </Typography>
            </DetailField>
            <DetailField label="Updated">
              <Typography variant="body2">{formatDate(item.updated_at)}</Typography>
            </DetailField>
          </Stack>
        </DialogContent>
      </Dialog>

      {lookupTarget && (
        <SnomedLookupDialog
          entityText={lookupTarget.entityText}
          entityLabel={lookupTarget.entityLabel}
          hasExistingCode={!!entities[lookupTarget.entityIndex]?.snomed_concept_id}
          onSelect={handleSnomedSelected}
          onClose={() => setLookupTarget(null)}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// SNOMED lookup dialog wrapper -- wraps TermSearch and adds "fix surface form"
// ---------------------------------------------------------------------------

function SnomedLookupDialog({
  entityText,
  entityLabel,
  hasExistingCode,
  onSelect,
  onClose,
}: {
  entityText: string;
  entityLabel: string;
  hasExistingCode: boolean;
  onSelect: (result: TermSearchResult, alsoFixSurfaceForm: boolean) => void;
  onClose: () => void;
}) {
  const [pendingResult, setPendingResult] = useState<TermSearchResult | null>(null);

  if (pendingResult) {
    return (
      <Dialog open onClose={() => setPendingResult(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Apply SNOMED code</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2" sx={{ mb: 1 }}>
            Selected: <strong>{pendingResult.term}</strong>
          </Typography>
          <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary", display: "block", mb: 2 }}>
            {pendingResult.snomed_concept_id}
          </Typography>
          {hasExistingCode && (
            <Alert severity="info" sx={{ mb: 2, py: 0.5 }}>
              This will replace the existing SNOMED code for &ldquo;{entityText}&rdquo;.
            </Alert>
          )}
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Would you also like to fix the surface form mapping in the terminology server? This helps the
            pipeline recognise &ldquo;{entityText}&rdquo; as this concept in future runs.
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              variant="contained"
              size="small"
              startIcon={<LinkIcon />}
              onClick={() => onSelect(pendingResult, true)}
            >
              Apply and fix surface form
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={() => onSelect(pendingResult, false)}
            >
              Apply code only
            </Button>
            <Button variant="text" size="small" onClick={() => setPendingResult(null)}>
              Back
            </Button>
          </Stack>
        </DialogContent>
      </Dialog>
    );
  }

  const typeLabel = entityLabel ? entityLabel.replace(/_/g, " ") : null;

  return (
    <TermSearch
      initialQuery={entityText}
      entityText={entityText}
      entityLabel={entityLabel}
      title={hasExistingCode ? "Fix SNOMED code" : "Find SNOMED code"}
      contextLabel={typeLabel ? `"${entityText}" · ${typeLabel}` : `"${entityText}"`}
      preventAutoClose
      onSelect={(result) => setPendingResult(result)}
      onClose={onClose}
      onCorrection={() => {}}
    />
  );
}

// ---------------------------------------------------------------------------
// Candidate row
// ---------------------------------------------------------------------------

function CandidateRow({ item, onClick }: { item: Candidate; onClick: () => void }) {
  return (
    <Card
      variant="outlined"
      onClick={onClick}
      sx={{ mb: 1.5, cursor: "pointer", transition: "box-shadow 0.15s", "&:hover": { boxShadow: 3 } }}
    >
      <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={2}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: "0.8rem", color: "text.secondary", mb: 0.5 }}>
              {item.candidate_id.slice(0, 12)}…
            </Typography>
            <Typography variant="body2" sx={{ wordBreak: "break-word" }}>
              {truncate(item.text)}
            </Typography>
          </Box>
          <Stack alignItems="flex-end" spacing={0.5} sx={{ flexShrink: 0 }}>
            <Chip
              icon={statusIcon(item.status)}
              label={item.status}
              color={statusColor(item.status)}
              size="small"
              sx={{ fontWeight: 600, textTransform: "capitalize" }}
            />
            {item.source && (
              <Chip label={item.source} size="small" variant="outlined" sx={{ fontSize: "0.7rem" }} />
            )}
            <Typography variant="caption" color="text.disabled">{formatDate(item.updated_at)}</Typography>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Gold label row
// ---------------------------------------------------------------------------

function GoldLabelRow({
  item,
  onClick,
  onReset,
  resetting,
}: {
  item: GoldLabel;
  onClick: () => void;
  onReset: () => void;
  resetting: boolean;
}) {
  const entities = parseEntities(item.entities_json);
  const shortId = item.label_id ? `${item.label_id.slice(0, 12)}…` : "—";

  return (
    <Card
      variant="outlined"
      onClick={onClick}
      sx={{ mb: 1.5, cursor: "pointer", transition: "box-shadow 0.15s", "&:hover": { boxShadow: 3 } }}
    >
      <CardContent sx={{ py: 1.5, "&:last-child": { pb: 1.5 } }}>
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={2}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: "0.8rem", color: "text.secondary", mb: 0.5 }}>
              {shortId}
            </Typography>
            <Typography variant="body2" sx={{ wordBreak: "break-word", mb: 1 }}>
              {truncate(item.text)}
            </Typography>
            {entities.length > 0 && (
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {entities.slice(0, 6).map((e, i) => {
                  const nonPresent = isNonPresent(e.assertion);
                  const tipParts = [e.label ?? e.semantic_tag, e.snomed_concept_id];
                  if (nonPresent) tipParts.push(formatAssertion(e.assertion));
                  return (
                    <Tooltip key={i} title={tipParts.filter(Boolean).join(" · ")}>
                      <Chip
                        label={e.text}
                        size="small"
                        sx={{
                          fontSize: "0.72rem",
                          bgcolor: nonPresent ? `${assertionColor(e.assertion)}.50` : "primary.50",
                          borderColor: nonPresent ? `${assertionColor(e.assertion)}.300` : "primary.200",
                          color: nonPresent ? `${assertionColor(e.assertion)}.dark` : undefined,
                          fontWeight: 500,
                          cursor: "default",
                          mb: 0.5,
                        }}
                        variant="outlined"
                      />
                    </Tooltip>
                  );
                })}
                {entities.length > 6 && (
                  <Chip label={`+${entities.length - 6} more`} size="small" variant="outlined" sx={{ fontSize: "0.72rem", mb: 0.5 }} />
                )}
              </Stack>
            )}
          </Box>
          <Stack alignItems="flex-end" spacing={0.5} sx={{ flexShrink: 0 }}>
            <Tooltip title="Delete this gold label and reset candidate to pending">
              <span>
                <IconButton
                  size="small"
                  color="error"
                  onClick={(event) => {
                    event.stopPropagation();
                    onReset();
                  }}
                  disabled={resetting}
                >
                  {resetting ? <CircularProgress size={14} /> : <DeleteOutlineIcon fontSize="small" />}
                </IconButton>
              </span>
            </Tooltip>
            <Chip
              icon={<VerifiedIcon sx={{ fontSize: 14 }} />}
              label={item.quality_score !== null ? `${Math.round(item.quality_score * 100)}%` : "verified"}
              color={qualityColor(item.quality_score)}
              size="small"
              sx={{ fontWeight: 700 }}
            />
            {item.source && (
              <Chip label={item.source} size="small" variant="outlined" sx={{ fontSize: "0.7rem" }} />
            )}
            <Typography variant="caption" color="text.disabled">{formatDate(item.verified_at ?? item.updated_at)}</Typography>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Skeleton list
// ---------------------------------------------------------------------------

function SkeletonList() {
  return (
    <>
      {[0, 1, 2, 3, 4].map((i) => (
        <Skeleton key={i} variant="rounded" height={80} sx={{ mb: 1.5 }} />
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;

export default function GoldDatasetPanel() {
  const [tab, setTab] = useState<"candidates" | "gold">("candidates");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(1);

  const [candidateStats, setCandidateStats] = useState<CandidateStats | null>(null);
  const [goldStats, setGoldStats] = useState<GoldStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);

  const [items, setItems] = useState<(Candidate | GoldLabel)[]>([]);
  const [total, setTotal] = useState(0);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [resettingLabelId, setResettingLabelId] = useState<string | null>(null);
  const [deletingCandidateId, setDeletingCandidateId] = useState<string | null>(null);
  const [confirmGoldLabel, setConfirmGoldLabel] = useState<GoldLabel | null>(null);
  const [confirmCandidateId, setConfirmCandidateId] = useState<string | null>(null);
  const [openingCandidateLabelId, setOpeningCandidateLabelId] = useState<string | null>(null);
  const [candidateGoldLabel, setCandidateGoldLabel] = useState<GoldLabel | null>(null);
  const [markingGoldCandidateId, setMarkingGoldCandidateId] = useState<string | null>(null);

  const [selectedItem, setSelectedItem] = useState<Candidate | GoldLabel | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce search input
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    setStatsError(null);
    try {
      const [cs, gs] = await Promise.all([
        jsonFetch<CandidateStats>("/api/training/candidates/stats"),
        jsonFetch<GoldStats>("/api/training/gold-labels/stats"),
      ]);
      setCandidateStats(cs);
      setGoldStats(gs);
    } catch (e) {
      setStatsError(e instanceof Error ? e.message : "Could not load stats");
    } finally {
      setStatsLoading(false);
    }
  }, []);

  // Load stats on mount
  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  // Load list when tab / page / search changes
  const loadList = useCallback(async () => {
    setListLoading(true);
    setListError(null);
    try {
      const skip = (page - 1) * PAGE_SIZE;
      if (tab === "candidates") {
        const url = `/api/training/candidates?page=${page}&page_size=${PAGE_SIZE}&exclude_completed=true${debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ""}`;
        const data = await jsonFetch<{ items: Candidate[]; total: number }>(url);
        setItems(data.items);
        setTotal(data.total);
      } else {
        const url = `/api/training/gold-labels?page=${page}&page_size=${PAGE_SIZE}${debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ""}`;
        const data = await jsonFetch<{ items: GoldLabel[]; total: number }>(url);
        setItems(data.items);
        setTotal(data.total);
      }
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Could not load records");
    } finally {
      setListLoading(false);
    }
  }, [tab, page, debouncedSearch]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  // Reset page when tab changes — also clear items to prevent rendering stale typed data
  const handleTabChange = (_: React.SyntheticEvent, val: "candidates" | "gold") => {
    setItems([]);
    setTotal(0);
    setTab(val);
    setPage(1);
    setSearch("");
  };

  async function handleExport() {
    setExporting(true);
    setExportMsg(null);
    setActionMsg(null);
    try {
      const result = await exportMedSpaCyTraining({ export_name: `gold_${new Date().toISOString().slice(0, 10)}` });
      setExportMsg(
        `Export complete — ${result.entity_count} entities, ${result.kb_count} KB entries from ${result.encounter_count} encounters. Saved to: ${result.export_path}`
      );
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  async function handleDeleteGoldLabel(item: GoldLabel) {
    if (!item.label_id || resettingLabelId) return;
    setResettingLabelId(item.label_id);
    setExportMsg(null);
    setActionMsg(null);
    setListError(null);
    try {
      const result = await jsonFetch<DeleteGoldLabelResult>(
        `/api/training/gold-labels/${encodeURIComponent(item.label_id)}`,
        { method: "DELETE" },
      );
      if (result.candidate_reset) {
        setActionMsg("Gold label deleted. Candidate reset to pending.");
      } else {
        setActionMsg("Gold label deleted. No linked candidate was found to reset.");
      }
      if (selectedItem && "label_id" in selectedItem && selectedItem.label_id === item.label_id) {
        setSelectedItem(null);
      }
      await Promise.all([loadList(), loadStats()]);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to delete gold label");
    } finally {
      setResettingLabelId(null);
    }
  }

  function requestDeleteGoldLabel(item: GoldLabel) {
    setConfirmGoldLabel(item);
  }

  function requestDeleteCandidate(candidateId: string) {
    if (!candidateId || deletingCandidateId) return;
    setConfirmCandidateId(candidateId);
  }

  async function handleDeleteCandidate(candidateId: string) {
    if (!candidateId || deletingCandidateId) return;
    setDeletingCandidateId(candidateId);
    setExportMsg(null);
    setActionMsg(null);
    setListError(null);
    try {
      const result = await jsonFetch<DeleteTrainingCandidateResult>(
        `/api/training/candidates/${encodeURIComponent(candidateId)}`,
        { method: "DELETE" },
      );
      setActionMsg(
        `Candidate deleted. Removed ${result.gold_labels_deleted} gold labels and ${result.surface_form_tasks_deleted} surface-form tasks.`,
      );
      if (selectedItem && "candidate_id" in selectedItem && selectedItem.candidate_id === candidateId) {
        setSelectedItem(null);
      }
      await Promise.all([loadList(), loadStats()]);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to delete candidate");
    } finally {
      setDeletingCandidateId(null);
    }
  }

  async function openCandidateLabelEditor(candidateId: string) {
    if (!candidateId || openingCandidateLabelId) return;
    setOpeningCandidateLabelId(candidateId);
    setListError(null);
    try {
      const label = await jsonFetch<GoldLabel>(
        `/api/training/gold-labels/by-candidate/${encodeURIComponent(candidateId)}/ensure`,
        { method: "POST" },
      );
      setCandidateGoldLabel(label);
    } catch (e) {
      setListError(
        e instanceof Error
          ? e.message
          : "Could not open candidate label editor.",
      );
    } finally {
      setOpeningCandidateLabelId(null);
    }
  }

  async function markCandidateAsGold(candidateId: string) {
    if (!candidateId || markingGoldCandidateId) return;
    setMarkingGoldCandidateId(candidateId);
    setActionMsg(null);
    setListError(null);
    try {
      const result = await jsonFetch<{ candidate_id: string; status: string; gold_label_id: string | null }>(
        `/api/training/candidates/${encodeURIComponent(candidateId)}/mark-completed`,
        { method: "POST" },
      );
      setActionMsg("Saved as gold data. Candidate status updated to completed.");
      if (selectedItem && "candidate_id" in selectedItem && selectedItem.candidate_id === candidateId) {
        setSelectedItem({ ...(selectedItem as Candidate), status: result.status });
      }
      await Promise.all([loadList(), loadStats()]);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Could not mark candidate as gold data");
    } finally {
      setMarkingGoldCandidateId(null);
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <Box sx={{ maxWidth: 1000, mx: "auto", py: 4, px: 3 }}>

      {/* Header */}
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" sx={{ mb: 3 }} flexWrap="wrap" spacing={2}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>Verification Examples</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Raw candidates processed by the pipeline, and the verified gold labels ready for training.
          </Typography>
        </Box>
        <Tooltip title="Export all verified gold labels as MedSpaCy training data">
          <Button
            variant="outlined"
            startIcon={exporting ? <CircularProgress size={14} /> : <DownloadIcon />}
            disabled={exporting || !goldStats || goldStats.total === 0}
            onClick={handleExport}
            size="small"
          >
            Export training data
          </Button>
        </Tooltip>
      </Stack>

      {/* Stats row */}
      {statsError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setStatsError(null)}>{statsError}</Alert>}
      <Stack direction="row" spacing={2} sx={{ mb: 3 }} flexWrap="wrap" useFlexGap>
        {statsLoading ? (
          [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} variant="rounded" width={130} height={76} />)
        ) : (
          <>
            <StatTile label="Candidates total" value={candidateStats?.total ?? 0} />
            <StatTile
              label="Completed"
              value={candidateStats?.completed ?? 0}
              color="success.main"
            />
            <StatTile
              label="Failed"
              value={candidateStats?.failed ?? 0}
              color={candidateStats?.failed ? "error.main" : undefined}
            />
            <Divider orientation="vertical" flexItem sx={{ display: { xs: "none", sm: "block" } }} />
            <StatTile
              label="Verified gold labels"
              value={goldStats?.total ?? 0}
              color="primary.main"
            />
            <StatTile
              label="Avg quality score"
              value={goldStats?.avg_quality_score !== null && goldStats?.avg_quality_score !== undefined
                ? `${Math.round((goldStats.avg_quality_score ?? 0) * 100)}%`
                : "—"}
              sub={goldStats && goldStats.total > 0 ? `${goldStats.high_quality} high quality` : undefined}
              color={goldStats?.avg_quality_score !== null && goldStats?.avg_quality_score !== undefined
                ? goldStats.avg_quality_score >= 0.8 ? "success.main" : goldStats.avg_quality_score >= 0.5 ? "warning.main" : "error.main"
                : undefined}
            />
          </>
        )}
      </Stack>

      {exportMsg && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setExportMsg(null)}>{exportMsg}</Alert>}
      {actionMsg && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setActionMsg(null)}>{actionMsg}</Alert>}

      {/* Tabs */}
      <Tabs value={tab} onChange={handleTabChange} sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}>
        <Tab
          value="candidates"
          label={
            <Stack direction="row" spacing={0.75} alignItems="center">
              <span>Candidates</span>
              {candidateStats && (
                <Chip label={candidateStats.total} size="small" sx={{ height: 18, fontSize: "0.7rem" }} />
              )}
            </Stack>
          }
        />
        <Tab
          value="gold"
          label={
            <Stack direction="row" spacing={0.75} alignItems="center">
              <span>Verified gold</span>
              {goldStats && (
                <Chip label={goldStats.total} size="small" color="primary" sx={{ height: 18, fontSize: "0.7rem" }} />
              )}
            </Stack>
          }
        />
      </Tabs>

      {/* Search */}
      <TextField
        size="small"
        placeholder={tab === "candidates" ? "Search candidate text…" : "Search gold label text…"}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        fullWidth
        sx={{ mb: 2 }}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          },
        }}
      />

      {/* List */}
      {listError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setListError(null)}>{listError}</Alert>}

      {listLoading ? (
        <SkeletonList />
      ) : items.length === 0 ? (
        <Box sx={{ py: 6, textAlign: "center" }}>
          <Typography color="text.secondary">
            {debouncedSearch
              ? `No ${tab === "candidates" ? "candidates" : "verified labels"} matching "${debouncedSearch}".`
              : tab === "candidates"
                ? "No training candidates yet. Run the pipeline to generate them."
                : "No verified gold labels yet. Complete candidates will appear here once the pipeline verifies them."}
          </Typography>
        </Box>
      ) : (
        <>
          {tab === "candidates"
            ? (items as Candidate[]).map((item, i) => (
                <CandidateRow key={item.candidate_id ?? `c-${i}`} item={item} onClick={() => setSelectedItem(item)} />
              ))
            : (items as GoldLabel[]).filter((item) => item.label_id).map((item, i) => (
                <GoldLabelRow
                  key={item.label_id ?? `g-${i}`}
                  item={item}
                  onClick={() => setSelectedItem(item)}
                  onReset={() => requestDeleteGoldLabel(item)}
                  resetting={resettingLabelId === item.label_id}
                />
              ))
          }
          {totalPages > 1 && (
            <Stack alignItems="center" sx={{ mt: 2 }}>
              <Pagination
                count={totalPages}
                page={page}
                onChange={(_, p) => setPage(p)}
                color="primary"
                size="small"
              />
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                {total.toLocaleString()} total · page {page} of {totalPages}
              </Typography>
            </Stack>
          )}
        </>
      )}

      {/* Detail dialog */}
      {selectedItem && tab === "candidates" && (
        <CandidateDetailDialog
          item={selectedItem as Candidate}
          onClose={() => setSelectedItem(null)}
          onDelete={requestDeleteCandidate}
          deleting={deletingCandidateId === (selectedItem as Candidate).candidate_id}
          onEditTerms={openCandidateLabelEditor}
          openingLabelEditor={openingCandidateLabelId === (selectedItem as Candidate).candidate_id}
          onMarkGold={markCandidateAsGold}
          markingGold={markingGoldCandidateId === (selectedItem as Candidate).candidate_id}
        />
      )}
      {selectedItem && tab === "gold" && (
        <GoldLabelDetailDialog
          item={selectedItem as GoldLabel}
          onClose={() => setSelectedItem(null)}
          onEntitiesChanged={() => void loadList()}
        />
      )}
      {confirmGoldLabel && (
        <ConfirmDialog
          title="Delete verified label?"
          body="This will permanently delete this verified gold label and reset its linked candidate to pending."
          confirmLabel="Delete label"
          variant="danger"
          onCancel={() => setConfirmGoldLabel(null)}
          onConfirm={() => {
            const item = confirmGoldLabel;
            setConfirmGoldLabel(null);
            if (item) {
              void handleDeleteGoldLabel(item);
            }
          }}
        />
      )}
      {confirmCandidateId && (
        <ConfirmDialog
          title="Delete training candidate?"
          body="This will permanently delete this candidate, its linked gold labels, and related surface-form tasks from Neo4j."
          confirmLabel="Delete candidate"
          variant="danger"
          onCancel={() => setConfirmCandidateId(null)}
          onConfirm={() => {
            const candidateId = confirmCandidateId;
            setConfirmCandidateId(null);
            if (candidateId) {
              void handleDeleteCandidate(candidateId);
            }
          }}
        />
      )}
      {candidateGoldLabel && (
        <GoldLabelDetailDialog
          item={candidateGoldLabel}
          onClose={() => setCandidateGoldLabel(null)}
          onEntitiesChanged={async () => {
            await Promise.all([loadList(), loadStats()]);
            if (selectedItem && "candidate_id" in selectedItem) {
              void openCandidateLabelEditor(selectedItem.candidate_id);
            }
          }}
        />
      )}
    </Box>
  );
}
