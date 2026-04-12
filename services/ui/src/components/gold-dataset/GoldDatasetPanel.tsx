"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Checkbox from "@mui/material/Checkbox";
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
import LinearProgress from "@mui/material/LinearProgress";
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
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Popover from "@mui/material/Popover";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import BookmarkIcon from "@mui/icons-material/Bookmark";
import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DownloadIcon from "@mui/icons-material/Download";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import LinkIcon from "@mui/icons-material/Link";
import NotInterestedIcon from "@mui/icons-material/NotInterested";
import SearchIcon from "@mui/icons-material/Search";
import SyncIcon from "@mui/icons-material/Sync";
import VerifiedIcon from "@mui/icons-material/Verified";
import { createEncounterSuppressRule, createSuppressRule, exportMedSpaCyTraining, fetchSurfaceForms, patchGoldLabelEntities, searchTerms, upsertSurfaceFormMapping } from "@/lib/api/legacy";
import {
  addConceptToSubdomain,
  fetchConceptSubdomainMemberships,
  type SubdomainMembershipItem,
} from "@/lib/analyticsApi";
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

interface SyntheticTagCount {
  semantic_tag: string;
  covered_surface_forms: number;
}

interface SyntheticTagOption {
  semantic_tag: string;
  total_surface_forms: number;
}

interface SyntheticStats {
  total_surface_forms: number;
  covered_surface_forms: number;
  synthetic_gold_labels: number;
  tag_breakdown: SyntheticTagCount[];
  tag_options: SyntheticTagOption[];
}

interface ValuesetOption {
  id: string;
  title: string;
  concept_count: number;
  sf_count: number;
  no_sf_count: number;
  derivable_count: number;
}

interface Candidate {
  candidate_id: string;
  text: string;
  entities_json?: string | null;
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
  snomed_term?: string;
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

interface CandidateDedupeGroupEntry {
  candidate_id: string;
  status: string | null;
  source: string | null;
  updated_at: string | null;
  text_preview: string;
  similarity?: number;
}

interface CandidateDedupeGroup {
  canonical: CandidateDedupeGroupEntry;
  duplicates: CandidateDedupeGroupEntry[];
}

interface CandidateDedupePreview {
  candidate_pool_size: number;
  group_count: number;
  duplicate_count: number;
  similarity_threshold: number;
  groups: CandidateDedupeGroup[];
}

interface CandidateDedupeApplyResult {
  candidate_pool_size: number;
  duplicates_marked: number;
  group_count: number;
  run_id: string | null;
  similarity_threshold: number;
  message?: string;
}

interface SyntheticGenerateResult {
  forms_processed?: number;
  forms_zero_written?: number;
  candidates_written?: number;
  gold_labels_written?: number;
  skipped_phi?: number;
  skipped_no_match?: number;
  skipped_non_evidence?: number;
  skipped_speculative?: number;
  skipped_semantic_mismatch?: number;
  skipped_planned_observable?: number;
  skipped_observable_no_value?: number;
  skipped_empty?: number;
  errors?: string[];
}

interface SyntheticQueueResult {
  queued: boolean;
  estimated_forms: number;
  queued_batches: number;
}

interface SyntheticDeleteResult {
  deleted_gold_labels: number;
  deleted_candidates: number;
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
  if (!res.ok) {
    let message = `${res.status}`;
    try {
      const payload = (await res.json()) as { detail?: unknown; message?: string };
      if (typeof payload.message === "string" && payload.message.trim()) {
        message = payload.message.trim();
      } else if (typeof payload.detail === "string" && payload.detail.trim()) {
        message = payload.detail.trim();
      } else if (Array.isArray(payload.detail) && payload.detail.length) {
        const first = payload.detail[0] as { msg?: string } | string;
        if (typeof first === "string" && first.trim()) {
          message = first.trim();
        } else if (
          typeof first === "object" &&
          first !== null &&
          typeof first.msg === "string" &&
          first.msg.trim()
        ) {
          message = first.msg.trim();
        }
      }
    } catch {
      // Keep status-only message fallback.
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

function parseEntities(json: string | null): Entity[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    if (Array.isArray(parsed)) {
      return parsed
        .filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object")
        .map((entry) => {
          const coding = (entry.coding && typeof entry.coding === "object"
            ? (entry.coding as Record<string, unknown>)
            : {}) as Record<string, unknown>;
          const snomedConceptId = String(
            entry.snomed_concept_id ?? entry.concept_id ?? coding.snomed_concept_id ?? "",
          ).trim();
          const snomedTerm = String(
            entry.snomed_term ?? entry.term ?? entry.preferred_term ?? coding.snomed_term ?? "",
          ).trim();
          const text = String(entry.text ?? "").trim();
          return {
            ...entry,
            text,
            snomed_concept_id: snomedConceptId || undefined,
            snomed_term: snomedTerm || undefined,
          } as Entity;
        });
    }
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

function buildSyntheticRunSummary(result: SyntheticGenerateResult): string {
  const forms = result.forms_processed ?? 0;
  const labels = result.gold_labels_written ?? 0;
  const parts: string[] = [
    `Synthetic generation complete: ${labels} labels from ${forms} forms.`,
  ];
  if ((result.forms_zero_written ?? 0) > 0) {
    parts.push(`No accepted outputs for ${result.forms_zero_written} form(s).`);
  }
  const skips: Array<[string, number | undefined]> = [
    ["speculative", result.skipped_speculative],
    ["non-evidence", result.skipped_non_evidence],
    ["semantic mismatch", result.skipped_semantic_mismatch],
    ["planned observable", result.skipped_planned_observable],
    ["observable without value", result.skipped_observable_no_value],
    ["no span match", result.skipped_no_match],
    ["phi", result.skipped_phi],
    ["empty", result.skipped_empty],
  ];
  const used = skips
    .filter(([, count]) => typeof count === "number" && count > 0)
    .map(([label, count]) => `${label}: ${count}`);
  if (used.length > 0) {
    parts.push(`Filtered: ${used.join(", ")}.`);
  }
  if ((result.errors?.length ?? 0) > 0) {
    parts.push(`Errors: ${result.errors?.length}.`);
  }
  return parts.join(" ");
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

// State for the row being looked up: index into entities array
interface LookupTarget {
  entityIndex: number;
  entityText: string;
  entityLabel: string;
}

function normaliseLookupTag(raw: string): string | null {
  const tag = String(raw ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s/-]+/g, "_");
  if (!tag) return null;
  if (tag === "observable") return "observable_entity";
  if (tag === "observation") return "observable_entity";
  return tag;
}

// ---------------------------------------------------------------------------
// Delete candidate dialog -- with optional entity suppression
// ---------------------------------------------------------------------------

function DeleteCandidateDialog({
  target,
  onCancel,
  onConfirm,
}: {
  target: { id: string; text: string; entities: Entity[] };
  onCancel: () => void;
  onConfirm: (suppressEncounterText: boolean) => void;
}) {
  const [suppressChecked, setSuppressChecked] = useState(false);

  return (
    <Dialog open onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ color: "error.main" }}>Delete training candidate?</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" sx={{ mb: 1.5 }}>
          This will permanently delete this candidate, its linked gold labels, and related surface-form tasks from Neo4j.
        </Typography>
        {target.text && (
          <Box sx={{ bgcolor: "action.hover", borderRadius: 1, px: 1.5, py: 1, mb: 2, borderLeft: "3px solid", borderColor: "divider" }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.25 }}>
              Encounter text
            </Typography>
            <Typography variant="body2" sx={{ fontStyle: "italic" }}>
              {target.text}
            </Typography>
          </Box>
        )}
        <Divider sx={{ mb: 1.5 }} />
        <FormControlLabel
          control={
            <Checkbox
              checked={suppressChecked}
              onChange={(e) => setSuppressChecked(e.target.checked)}
              size="small"
              disabled={!target.text.trim()}
            />
          }
          label={
            <Typography variant="body2" fontWeight={600}>
              Suppress this encounter text from future pipeline runs
            </Typography>
          }
        />
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", ml: 3.5 }}>
          Creates a context-pattern suppress rule. Any entities extracted from matching encounter text will be removed in the post-processing step.
        </Typography>
      </DialogContent>
      <DialogActions sx={{ px: 2, pb: 2 }}>
        <Button variant="outlined" size="small" onClick={onCancel}>Cancel</Button>
        <Button
          variant="contained"
          color="error"
          size="small"
          onClick={() => onConfirm(suppressChecked)}
        >
          {suppressChecked ? "Delete and suppress encounter" : "Delete candidate"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function GoldLabelDetailDialog({
  item,
  onClose,
  onEntitiesChanged,
  onMarkGold,
  markingGold,
}: {
  item: GoldLabel;
  onClose: () => void;
  onEntitiesChanged?: () => void;
  onMarkGold?: () => void;
  markingGold?: boolean;
}) {
  const [entities, setEntities] = useState<Entity[]>(() => parseEntities(item.entities_json));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [newEntityText, setNewEntityText] = useState("");
  const [newEntityLabel, setNewEntityLabel] = useState<(typeof ENTITY_LABEL_OPTIONS)[number]>("finding");
  const [newEntityAssertion, setNewEntityAssertion] = useState<(typeof ASSERTION_OPTIONS)[number]>("present");
  const [lookupTarget, setLookupTarget] = useState<LookupTarget | null>(null);
  const [termDrafts, setTermDrafts] = useState<Record<number, string>>({});
  const [suppressingIndex, setSuppressingIndex] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<Record<number, TermSearchResult | null>>({});
  const [searchingAll, setSearchingAll] = useState(false);

  const pendingSuggestionCount = Object.values(suggestions).filter(Boolean).length;

  async function handleAutoCodeAll() {
    setSearchingAll(true);
    setSaveError(null);
    setSaveMsg(null);
    const targets = entities
      .map((e, i) => ({ i, e }))
      .filter(({ e }) => !e.snomed_concept_id && e.text?.trim());
    const results = await Promise.allSettled(
      targets.map(async ({ i, e }) => {
        const rows = await searchTerms(e.text, 1, e.label ? [e.label] : undefined);
        return { i, result: rows[0] ?? null };
      }),
    );
    const next: Record<number, TermSearchResult | null> = {};
    for (const r of results) {
      if (r.status === "fulfilled") {
        next[r.value.i] = r.value.result as TermSearchResult | null;
      }
    }
    setSuggestions(next);
    setSearchingAll(false);
  }

  function handleDismissSuggestion(idx: number) {
    setSuggestions((prev) => {
      const next = { ...prev };
      delete next[idx];
      return next;
    });
  }

  async function handleAcceptSuggestion(idx: number) {
    const suggestion = suggestions[idx];
    if (!suggestion) return;
    const next = entities.map((e, i) =>
      i === idx
        ? { ...e, snomed_concept_id: suggestion.snomed_concept_id, snomed_term: suggestion.term, semantic_tag: suggestion.semantic_tag ?? e.semantic_tag }
        : e,
    );
    const ok = await persistEntities(next, `Code applied: ${suggestion.snomed_concept_id} - ${suggestion.term}`);
    if (ok) handleDismissSuggestion(idx);
  }

  async function handleAcceptAllSuggestions() {
    const entries = Object.entries(suggestions).filter(([, v]) => v !== null) as [string, TermSearchResult][];
    if (!entries.length) return;
    const next = entities.map((e, i) => {
      const suggestion = suggestions[i];
      return suggestion ? { ...e, snomed_concept_id: suggestion.snomed_concept_id, snomed_term: suggestion.term, semantic_tag: suggestion.semantic_tag ?? e.semantic_tag } : e;
    });
    const ok = await persistEntities(next, `${entries.length} code(s) applied from auto-search.`);
    if (ok) setSuggestions({});
  }

  async function handleSuppressEntity(idx: number) {
    const entity = entities[idx];
    if (!entity?.text || suppressingIndex !== null) return;
    setSuppressingIndex(idx);
    setSaveError(null);
    setSaveMsg(null);
    try {
      await createSuppressRule(
        entity.text,
        entity.label ?? undefined,
        `Suppressed from gold label editor (label: ${item.label_id})`,
      );
      setSaveMsg(`"${entity.text}" added to pipeline suppress list.`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not create suppress rule");
    } finally {
      setSuppressingIndex(null);
    }
  }

  // -- Subdomain membership popover ----------------------------------------

  const [conceptSubdomainCounts, setConceptSubdomainCounts] = useState<Record<string, number>>({});
  const [domainPopover, setDomainPopover] = useState<{
    anchor: HTMLElement;
    conceptId: string;
    conceptTerm: string;
  } | null>(null);
  const [popoverItems, setPopoverItems] = useState<SubdomainMembershipItem[]>([]);
  const [popoverLoading, setPopoverLoading] = useState(false);
  const [savingSubdomain, setSavingSubdomain] = useState<string | null>(null);

  useEffect(() => {
    const coded = entities.filter((e) => e.snomed_concept_id);
    const toLoad = coded.filter((e) => !(e.snomed_concept_id! in conceptSubdomainCounts));
    if (!toLoad.length) return;
    void Promise.all(
      toLoad.map(async (e) => {
        try {
          const items = await fetchConceptSubdomainMemberships(e.snomed_concept_id!);
          const count = items.filter((m) => m.is_member).length;
          setConceptSubdomainCounts((prev) => ({ ...prev, [e.snomed_concept_id!]: count }));
        } catch {
          // non-blocking
        }
      }),
    );
  }, [entities]);

  async function handleOpenDomainPopover(anchor: HTMLElement, conceptId: string, conceptTerm: string) {
    setDomainPopover({ anchor, conceptId, conceptTerm });
    setPopoverLoading(true);
    setPopoverItems([]);
    try {
      const items = await fetchConceptSubdomainMemberships(conceptId);
      setPopoverItems(items);
      const count = items.filter((m) => m.is_member).length;
      setConceptSubdomainCounts((prev) => ({ ...prev, [conceptId]: count }));
    } catch {
      setPopoverItems([]);
    } finally {
      setPopoverLoading(false);
    }
  }

  async function handleAddToSubdomain(item_: SubdomainMembershipItem, conceptId: string, conceptTerm: string) {
    const key = `${item_.domain_id}::${item_.subdomain_name}`;
    setSavingSubdomain(key);
    try {
      await addConceptToSubdomain(item_.domain_id, item_.subdomain_name, Number(conceptId), conceptTerm);
      setPopoverItems((prev) =>
        prev.map((m) => (m.domain_id === item_.domain_id && m.subdomain_name === item_.subdomain_name ? { ...m, is_member: true } : m)),
      );
      setConceptSubdomainCounts((prev) => ({ ...prev, [conceptId]: (prev[conceptId] ?? 0) + 1 }));
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not add to subdomain");
    } finally {
      setSavingSubdomain(null);
    }
  }

  async function persistEntities(next: Entity[], successMsg: string): Promise<boolean> {
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
          snomed_term: e.snomed_term,
          semantic_tag: e.semantic_tag,
        })),
      );
      setEntities(next);
      setTermDrafts({});
      setSaveMsg(successMsg);
      onEntitiesChanged?.();
      return true;
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save changes");
      return false;
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

  function isDuplicateEntity(candidate: Entity, idxToIgnore: number): boolean {
    return entities.some((entity, idx) => {
      if (idx === idxToIgnore) return false;
      return (
        entity.text.trim().toLowerCase() === candidate.text.trim().toLowerCase() &&
        (entity.label ?? "").trim().toLowerCase() === (candidate.label ?? "").trim().toLowerCase() &&
        (entity.assertion ?? "present").trim().toLowerCase() === (candidate.assertion ?? "present").trim().toLowerCase()
      );
    });
  }

  function handleUpdateEntityType(idx: number, label: string) {
    const current = entities[idx];
    if (!current) return;
    const nextEntity = { ...current, label };
    if (isDuplicateEntity(nextEntity, idx)) {
      setSaveError("This term already exists with the same type and assertion.");
      return;
    }
    const next = entities.map((entity, i) => (i === idx ? nextEntity : entity));
    void persistEntities(next, `Updated type for "${current.text}" to ${label}.`);
  }

  async function handleCommitEntityTerm(idx: number) {
    const current = entities[idx];
    if (!current) return;
    const draft = (termDrafts[idx] ?? current.text).trim();
    if (!draft) {
      setSaveError("Term cannot be empty.");
      return;
    }
    if (draft === current.text.trim()) {
      setTermDrafts((prev) => {
        const next = { ...prev };
        delete next[idx];
        return next;
      });
      return;
    }
    const nextEntity = { ...current, text: draft };
    if (isDuplicateEntity(nextEntity, idx)) {
      setSaveError("This term already exists with the same type and assertion.");
      return;
    }
    const next = entities.map((entity, i) => (i === idx ? nextEntity : entity));
    const saved = await persistEntities(next, `Updated term to "${draft}".`);
    if (saved) {
      setTermDrafts((prev) => {
        const updated = { ...prev };
        delete updated[idx];
        return updated;
      });
    }
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

  async function handleSnomedSelected(
    result: TermSearchResult,
    alsoFixSurfaceForm: boolean,
    addToSubdomains: string[] = [],
  ) {
    if (lookupTarget === null) return;
    const { entityIndex, entityText } = lookupTarget;
    setLookupTarget(null);

    const next = entities.map((e, i) =>
      i === entityIndex
        ? {
            ...e,
            snomed_concept_id: result.snomed_concept_id,
            snomed_term: result.term ?? e.snomed_term,
            semantic_tag: result.semantic_tag ?? e.semantic_tag,
          }
        : e,
    );

    let surfaceFormNote = "";
    let subdomainNote = "";
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

    if (addToSubdomains.length > 0) {
      let added = 0;
      let skipped = 0;
      let failed = 0;
      const conceptId = Number(result.snomed_concept_id);
      for (const key of addToSubdomains) {
        const [domainId, subdomainName] = key.split("::");
        if (!domainId || !subdomainName || !Number.isFinite(conceptId)) {
          failed += 1;
          continue;
        }
        try {
          await addConceptToSubdomain(
            domainId,
            subdomainName,
            conceptId,
            result.term || entityText,
          );
          added += 1;
        } catch (err) {
          const message = err instanceof Error ? err.message.toLowerCase() : "";
          if (message.includes("already")) {
            skipped += 1;
          } else {
            failed += 1;
          }
        }
      }
      if (added > 0 || skipped > 0 || failed > 0) {
        subdomainNote = ` Domain updates - added ${added}, already present ${skipped}, failed ${failed}.`;
      }
    }

    void persistEntities(
      next,
      `Updated SNOMED code to ${result.snomed_concept_id} - ${result.term}.${surfaceFormNote}${subdomainNote}`,
    );
  }

  const summary = assertionSummary(entities);

  return (
    <>
      <Dialog open onClose={onClose} maxWidth="xl" fullWidth scroll="paper">
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
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={searchingAll ? <CircularProgress size={12} color="inherit" /> : <SearchIcon sx={{ fontSize: 15 }} />}
                    disabled={searchingAll || saving}
                    onClick={() => void handleAutoCodeAll()}
                  >
                    Search all
                  </Button>
                  {pendingSuggestionCount > 0 && (
                    <Button
                      variant="contained"
                      color="warning"
                      size="small"
                      startIcon={saving ? <CircularProgress size={12} color="inherit" /> : <CheckCircleOutlineIcon sx={{ fontSize: 15 }} />}
                      disabled={saving}
                      onClick={() => void handleAcceptAllSuggestions()}
                    >
                      Accept all ({pendingSuggestionCount})
                    </Button>
                  )}
                </Stack>
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
                            <TextField
                              size="small"
                              value={termDrafts[i] ?? e.text}
                              onChange={(event) =>
                                setTermDrafts((prev) => ({ ...prev, [i]: event.target.value }))
                              }
                              onBlur={() => {
                                void handleCommitEntityTerm(i);
                              }}
                              onKeyDown={(event) => {
                                if (event.key === "Enter") {
                                  event.preventDefault();
                                  const input = event.currentTarget.querySelector("input");
                                  input?.blur();
                                }
                              }}
                              disabled={saving}
                              sx={{
                                minWidth: 260,
                                "& .MuiInputBase-input": {
                                  py: 0.45,
                                  fontSize: "0.85rem",
                                  fontWeight: 500,
                                },
                              }}
                            />
                          </TableCell>
                          <TableCell>
                            <TextField
                              select
                              size="small"
                              value={e.label ?? "finding"}
                              onChange={(event) => handleUpdateEntityType(i, event.target.value)}
                              disabled={saving}
                              sx={{
                                minWidth: 170,
                                "& .MuiInputBase-input": {
                                  py: 0.45,
                                  fontSize: "0.75rem",
                                  fontWeight: 600,
                                  color: "primary.main",
                                },
                              }}
                            >
                              {ENTITY_LABEL_OPTIONS.map((option) => (
                                <MenuItem key={option} value={option}>
                                  {option}
                                </MenuItem>
                              ))}
                            </TextField>
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
                              <Stack spacing={0.25}>
                                {e.snomed_term && (
                                  <Typography variant="caption" sx={{ fontWeight: 600, color: "text.primary", lineHeight: 1.3 }}>
                                    {e.snomed_term}
                                  </Typography>
                                )}
                                <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
                                  {e.snomed_concept_id}
                                </Typography>
                              </Stack>
                            ) : suggestions[i] !== undefined ? (
                              suggestions[i] === null ? (
                                <Typography variant="caption" color="text.disabled" sx={{ fontStyle: "italic" }}>
                                  No match found
                                </Typography>
                              ) : (
                                <Stack direction="row" spacing={0.5} alignItems="flex-start">
                                  <Stack spacing={0.1}>
                                    <Typography variant="caption" sx={{ fontWeight: 600, color: "warning.dark", lineHeight: 1.3 }}>
                                      {suggestions[i]!.term}
                                    </Typography>
                                    <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
                                      {suggestions[i]!.snomed_concept_id}
                                    </Typography>
                                  </Stack>
                                  <Tooltip title="Accept this code">
                                    <span>
                                      <IconButton size="small" color="success" disabled={saving} onClick={() => void handleAcceptSuggestion(i)}>
                                        <CheckCircleOutlineIcon sx={{ fontSize: 15 }} />
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                  <Tooltip title="Dismiss suggestion">
                                    <span>
                                      <IconButton size="small" onClick={() => handleDismissSuggestion(i)}>
                                        <CloseIcon sx={{ fontSize: 15 }} />
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                </Stack>
                              )
                            ) : searchingAll ? (
                              <CircularProgress size={12} />
                            ) : (
                              <Typography variant="caption" color="error.main" sx={{ fontStyle: "italic" }}>
                                No code
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell align="right">
                            <Stack direction="row" spacing={0.25} justifyContent="flex-end" alignItems="center">
                              {hasSnomed && (() => {
                                const count = conceptSubdomainCounts[e.snomed_concept_id!];
                                const loaded = e.snomed_concept_id! in conceptSubdomainCounts;
                                return (
                                  <Tooltip title={loaded ? (count > 0 ? `In ${count} subdomain${count === 1 ? "" : "s"} -- click to manage` : "Not in any subdomain -- click to add") : "Check subdomains"}>
                                    <span>
                                      <IconButton
                                        size="small"
                                        color={loaded && count > 0 ? "success" : "default"}
                                        disabled={saving}
                                        onClick={(ev) => void handleOpenDomainPopover(ev.currentTarget, e.snomed_concept_id!, e.snomed_term ?? e.text)}
                                      >
                                        {loaded ? (count > 0 ? <BookmarkIcon sx={{ fontSize: 16 }} /> : <BookmarkBorderIcon sx={{ fontSize: 16, color: "warning.main" }} />) : <BookmarkBorderIcon sx={{ fontSize: 16 }} />}
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                );
                              })()}
                              <Tooltip title={hasSnomed ? "Fix SNOMED code" : "Look up SNOMED code"}>
                                <span>
                                  <IconButton
                                    size="small"
                                    color={hasSnomed ? "default" : "warning"}
                                    disabled={saving || suppressingIndex !== null}
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
                              <Tooltip title="Add to pipeline suppress list -- this text will be ignored in future runs">
                                <span>
                                  <IconButton
                                    size="small"
                                    color="warning"
                                    disabled={saving || suppressingIndex !== null}
                                    onClick={() => void handleSuppressEntity(i)}
                                  >
                                    {suppressingIndex === i ? (
                                      <CircularProgress size={14} />
                                    ) : (
                                      <NotInterestedIcon sx={{ fontSize: 16 }} />
                                    )}
                                  </IconButton>
                                </span>
                              </Tooltip>
                              <Tooltip title="Remove this entity from the label">
                                <span>
                                  <IconButton
                                    size="small"
                                    color="error"
                                    disabled={saving || suppressingIndex !== null}
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
        <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
          {onMarkGold && (
            <Button
              variant="contained"
              color="success"
              size="small"
              startIcon={markingGold ? <CircularProgress size={14} color="inherit" /> : <VerifiedIcon />}
              disabled={markingGold || saving}
              onClick={onMarkGold}
            >
              Mark as gold
            </Button>
          )}
          <Button variant="outlined" size="small" onClick={onClose} disabled={saving || markingGold}>
            Close
          </Button>
        </DialogActions>
      </Dialog>

      <Popover
        open={Boolean(domainPopover)}
        anchorEl={domainPopover?.anchor ?? null}
        onClose={() => setDomainPopover(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        PaperProps={{ sx: { p: 2, minWidth: 320, maxWidth: 420, maxHeight: 480, overflowY: "auto" } }}
      >
        {domainPopover && (
          <>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              Subdomain membership
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5, fontFamily: "monospace" }}>
              {domainPopover.conceptId} — {domainPopover.conceptTerm}
            </Typography>
            {popoverLoading ? (
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={14} />
                <Typography variant="caption">Loading...</Typography>
              </Stack>
            ) : popoverItems.length === 0 ? (
              <Typography variant="caption" color="text.secondary">No subdomains found.</Typography>
            ) : (
              (() => {
                const domains = Array.from(new Map(popoverItems.map((m) => [m.domain_id, m.domain_name])).entries());
                return (
                  <Stack spacing={1.5}>
                    {domains.map(([domainId, domainName]) => {
                      const subs = popoverItems.filter((m) => m.domain_id === domainId);
                      return (
                        <Box key={domainId}>
                          <Typography variant="caption" sx={{ fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "text.secondary", display: "block", mb: 0.5 }}>
                            {domainName}
                          </Typography>
                          <Stack spacing={0.5}>
                            {subs.map((m) => {
                              const key = `${m.domain_id}::${m.subdomain_name}`;
                              const isSaving = savingSubdomain === key;
                              return (
                                <Stack key={key} direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
                                  <Typography variant="body2" sx={{ fontSize: "0.8rem" }}>
                                    {m.subdomain_label}
                                  </Typography>
                                  {m.is_member ? (
                                    <Chip label="In" color="success" size="small" sx={{ height: 20, fontSize: "0.7rem" }} />
                                  ) : (
                                    <Tooltip title={`Add to ${m.subdomain_label}`}>
                                      <span>
                                        <IconButton
                                          size="small"
                                          color="primary"
                                          disabled={isSaving || !!savingSubdomain}
                                          onClick={() => void handleAddToSubdomain(m, domainPopover.conceptId, domainPopover.conceptTerm)}
                                        >
                                          {isSaving ? <CircularProgress size={14} /> : <AddCircleOutlineIcon sx={{ fontSize: 16 }} />}
                                        </IconButton>
                                      </span>
                                    </Tooltip>
                                  )}
                                </Stack>
                              );
                            })}
                          </Stack>
                        </Box>
                      );
                    })}
                  </Stack>
                );
              })()
            )}
          </>
        )}
      </Popover>

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
  onSelect: (
    result: TermSearchResult,
    alsoFixSurfaceForm: boolean,
    addToSubdomains?: string[],
  ) => void;
  onClose: () => void;
}) {
  interface SubdomainOption {
    key: string;
    domainId: string;
    domainName: string;
    subdomainName: string;
    subdomainLabel: string;
  }

  const [pendingResult, setPendingResult] = useState<TermSearchResult | null>(null);
  const [membershipLoading, setMembershipLoading] = useState(false);
  const [membershipError, setMembershipError] = useState("");
  const [subdomainOptions, setSubdomainOptions] = useState<SubdomainOption[]>([]);
  const [existingMembership, setExistingMembership] = useState<string[]>([]);
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const [selectedDomainId, setSelectedDomainId] = useState<string>("");
  const [applying, setApplying] = useState<"surface" | "code" | null>(null);
  const hintTag = normaliseLookupTag(entityLabel);

  useEffect(() => {
    if (!pendingResult) return;
    const conceptId = String(pendingResult.snomed_concept_id || "").trim();
    if (!conceptId) return;

    let cancelled = false;
    async function loadMemberships() {
      setMembershipLoading(true);
      setMembershipError("");
      setSelectedTargets([]);
      setSelectedDomainId("");
      try {
        const memberships = await fetchConceptSubdomainMemberships(conceptId);
        if (cancelled) return;
        const options: SubdomainOption[] = memberships.map((m) => ({
          key: `${m.domain_id}::${m.subdomain_name}`,
          domainId: m.domain_id,
          domainName: m.domain_name,
          subdomainName: m.subdomain_name,
          subdomainLabel: m.subdomain_label,
        }));
        setSubdomainOptions(options);
        setExistingMembership(
          memberships.filter((m) => m.is_member).map((m) => `${m.domain_id}::${m.subdomain_name}`),
        );
      } catch {
        if (cancelled) return;
        setMembershipError("Could not load domain/subdomain memberships.");
      } finally {
        if (!cancelled) setMembershipLoading(false);
      }
    }
    void loadMemberships();
    return () => {
      cancelled = true;
    };
  }, [pendingResult]);

  if (pendingResult) {
    const existingOptions = subdomainOptions.filter((opt) =>
      existingMembership.includes(opt.key),
    );
    return (
      <Dialog open onClose={() => setPendingResult(null)} maxWidth="md" fullWidth>
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
          {membershipLoading ? (
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
              <CircularProgress size={14} />
              <Typography variant="caption" color="text.secondary">
                Checking where this code is already used...
              </Typography>
            </Stack>
          ) : (
            <Stack spacing={1.25} sx={{ mb: 2 }}>
              {existingOptions.length > 0 && (
                <Tooltip
                  arrow
                  placement="top-start"
                  title={
                    <Box sx={{ py: 0.5 }}>
                      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                        Already in domain/subdomain
                      </Typography>
                      <Stack spacing={0.5}>
                        {existingOptions.slice(0, 8).map((opt) => (
                          <Typography key={opt.key} variant="caption">
                            {opt.domainName} - {opt.subdomainLabel}
                          </Typography>
                        ))}
                        {existingOptions.length > 8 && (
                          <Typography variant="caption">
                            +{existingOptions.length - 8} more
                          </Typography>
                        )}
                      </Stack>
                    </Box>
                  }
                >
                  <Chip
                    color="success"
                    variant="outlined"
                    label={`Already in ${existingOptions.length} subdomain${existingOptions.length === 1 ? "" : "s"}`}
                    sx={{ width: "fit-content" }}
                  />
                </Tooltip>
              )}
              <TextField
                select
                size="small"
                label="Step 1: choose domain"
                value={selectedDomainId}
                onChange={(e) => {
                  setSelectedDomainId(e.target.value);
                  setSelectedTargets([]);
                }}
                fullWidth
              >
                <MenuItem value="">-- select a domain --</MenuItem>
                {Array.from(
                  new Map(
                    subdomainOptions.map((o) => [o.domainId, o.domainName]),
                  ).entries(),
                ).map(([id, name]) => (
                  <MenuItem key={id} value={id}>{name}</MenuItem>
                ))}
              </TextField>
              {selectedDomainId && (
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                    Step 2: choose subdomains
                  </Typography>
                  <Box
                    sx={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
                      gap: 0,
                    }}
                  >
                    {subdomainOptions
                      .filter((o) => o.domainId === selectedDomainId)
                      .sort((a, b) => a.subdomainLabel.localeCompare(b.subdomainLabel))
                      .map((opt) => {
                        const alreadyIn = existingMembership.includes(opt.key);
                        const checked = selectedTargets.includes(opt.key);
                        return (
                          <FormControlLabel
                            key={opt.key}
                            disabled={alreadyIn}
                            sx={{ mr: 0, pr: 1 }}
                            control={
                              <Checkbox
                                size="small"
                                checked={checked || alreadyIn}
                                onChange={(e) => {
                                  setSelectedTargets((prev) =>
                                    e.target.checked
                                      ? [...prev, opt.key]
                                      : prev.filter((k) => k !== opt.key),
                                  );
                                }}
                              />
                            }
                            label={
                              <Typography variant="body2">
                                {opt.subdomainLabel}
                                {alreadyIn && (
                                  <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
                                    ✓
                                  </Typography>
                                )}
                              </Typography>
                            }
                          />
                        );
                      })}
                  </Box>
                </Box>
              )}
              {membershipError && (
                <Alert severity="warning" sx={{ py: 0.25 }}>
                  <Typography variant="caption">{membershipError}</Typography>
                </Alert>
              )}
            </Stack>
          )}
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
            <Button
              variant="contained"
              size="small"
              startIcon={applying === "surface" ? <CircularProgress size={14} color="inherit" /> : <LinkIcon />}
              disabled={applying !== null}
              onClick={async () => {
                setApplying("surface");
                try {
                  await onSelect(pendingResult, true, selectedTargets);
                } finally {
                  setApplying(null);
                }
              }}
            >
              Apply and fix surface form
            </Button>
            <Button
              variant="outlined"
              size="small"
              disabled={applying !== null}
              startIcon={applying === "code" ? <CircularProgress size={14} color="inherit" /> : undefined}
              onClick={async () => {
                setApplying("code");
                try {
                  await onSelect(pendingResult, false, selectedTargets);
                } finally {
                  setApplying(null);
                }
              }}
            >
              Apply code only
            </Button>
            <Button
              variant="text"
              size="small"
              disabled={applying !== null}
              onClick={() => setPendingResult(null)}
            >
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
      hintTags={hintTag ? [hintTag] : undefined}
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

function CandidateRow({
  item,
  onClick,
  onMarkGold,
  onDelete,
  openingLabelEditor,
  markingGold,
  deleting,
}: {
  item: Candidate;
  onClick: () => void;
  onMarkGold: (candidateId: string) => void;
  onDelete: (candidateId: string) => void;
  openingLabelEditor: boolean;
  markingGold: boolean;
  deleting: boolean;
}) {
  const codedEntities = parseEntities(item.entities_json ?? null).filter(
    (entity) => !!entity.snomed_concept_id,
  );
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
            {codedEntities.length > 0 ? (
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                {codedEntities.slice(0, 2).map((entity, index) => (
                  <Tooltip
                    key={`${entity.snomed_concept_id}-${index}`}
                    title={`${entity.snomed_term || entity.text || "Preferred term not available"} (${entity.snomed_concept_id})`}
                  >
                    <Chip
                      size="small"
                      color="primary"
                      variant="outlined"
                      label={`${entity.snomed_term || entity.text || "Term"} - ${entity.snomed_concept_id}`}
                      sx={{ maxWidth: 460, "& .MuiChip-label": { overflow: "hidden", textOverflow: "ellipsis" } }}
                    />
                  </Tooltip>
                ))}
                {codedEntities.length > 2 && (
                  <Chip
                    size="small"
                    variant="outlined"
                    label={`+${codedEntities.length - 2} more`}
                  />
                )}
              </Stack>
            ) : (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                No assigned code yet.
              </Typography>
            )}
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              Click row to edit terms and codes.
            </Typography>
            {openingLabelEditor && (
              <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
                <CircularProgress size={12} />
                <Typography variant="caption" color="text.secondary">
                  Opening editor...
                </Typography>
              </Stack>
            )}
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
            <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }}>
              <Button
                size="small"
                variant="contained"
                color="success"
                onClick={(event) => {
                  event.stopPropagation();
                  onMarkGold(item.candidate_id);
                }}
                disabled={openingLabelEditor || markingGold || deleting}
                startIcon={
                  markingGold ? <CircularProgress size={12} color="inherit" /> : undefined
                }
                sx={{ minWidth: 98 }}
              >
                Mark gold
              </Button>
              <IconButton
                size="small"
                color="error"
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(item.candidate_id);
                }}
                disabled={openingLabelEditor || markingGold || deleting}
                sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1.25 }}
              >
                {deleting ? (
                  <CircularProgress size={12} />
                ) : (
                  <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                )}
              </IconButton>
            </Stack>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Gold label row
// ---------------------------------------------------------------------------

function EntityPill({ entity }: { entity: Entity }) {
  const nonPresent = isNonPresent(entity.assertion);
  const color = assertionColor(entity.assertion);
  const tipParts = [entity.label ?? entity.semantic_tag];
  if (nonPresent) tipParts.push(formatAssertion(entity.assertion));
  if (entity.snomed_term) tipParts.push(`SNOMED: ${entity.snomed_term}`);

  return (
    <Tooltip title={tipParts.filter(Boolean).join(" · ")}>
      <Box
        sx={{
          display: "inline-flex",
          flexDirection: "column",
          alignItems: "flex-start",
          bgcolor: nonPresent ? `${color}.50` : "primary.50",
          border: "1px solid",
          borderColor: nonPresent ? `${color}.200` : "primary.100",
          borderRadius: 1.5,
          px: 1,
          py: 0.5,
          cursor: "default",
          minWidth: 80,
          maxWidth: 180,
        }}
      >
        <Typography
          sx={{
            fontSize: "0.75rem",
            fontWeight: 600,
            color: nonPresent ? `${color}.dark` : "primary.dark",
            lineHeight: 1.3,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: "100%",
          }}
        >
          {entity.text}
        </Typography>
        {entity.snomed_concept_id ? (
          <Typography
            sx={{
              fontSize: "0.62rem",
              color: "text.secondary",
              lineHeight: 1.3,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              maxWidth: "100%",
            }}
          >
            {entity.snomed_term || entity.text}
            <Box component="span" sx={{ fontFamily: "monospace", color: "text.disabled", ml: 0.5 }}>
              {entity.snomed_concept_id}
            </Box>
          </Typography>
        ) : (
          <Typography sx={{ fontSize: "0.62rem", color: "warning.main", fontStyle: "italic", lineHeight: 1.3 }}>
            no code
          </Typography>
        )}
      </Box>
    </Tooltip>
  );
}

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
  const shortId = item.label_id ? item.label_id.slice(0, 15) : "—";
  const summary = assertionSummary(entities);

  return (
    <Card
      variant="outlined"
      onClick={onClick}
      sx={{
        mb: 1.5,
        cursor: "pointer",
        transition: "all 0.15s ease",
        borderLeft: "3px solid",
        borderLeftColor: "success.main",
        "&:hover": { boxShadow: 4, borderLeftColor: "success.dark" },
      }}
    >
      <CardContent sx={{ py: 1.75, px: 2, "&:last-child": { pb: 1.75 } }}>
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={2}>
          {/* Left: text content + entity pills */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
              <Typography
                sx={{ fontFamily: "monospace", fontSize: "0.7rem", color: "text.disabled", letterSpacing: "0.01em" }}
              >
                {shortId}
              </Typography>
              {summary && (
                <Typography sx={{ fontSize: "0.7rem", color: "text.secondary", fontStyle: "italic" }}>
                  {summary}
                </Typography>
              )}
            </Stack>

            <Typography
              variant="body2"
              sx={{ wordBreak: "break-word", mb: entities.length > 0 ? 1.25 : 0, lineHeight: 1.55, color: "text.primary" }}
            >
              {truncate(item.text)}
            </Typography>

            {entities.length > 0 && (
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                {entities.slice(0, 6).map((e, i) => (
                  <EntityPill key={i} entity={e} />
                ))}
                {entities.length > 6 && (
                  <Box
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      px: 1,
                      py: 0.5,
                      border: "1px solid",
                      borderColor: "divider",
                      borderRadius: 1.5,
                      bgcolor: "action.hover",
                    }}
                  >
                    <Typography sx={{ fontSize: "0.72rem", color: "text.secondary", fontWeight: 500 }}>
                      +{entities.length - 6} more
                    </Typography>
                  </Box>
                )}
              </Stack>
            )}
          </Box>

          {/* Right: actions + meta */}
          <Stack alignItems="flex-end" spacing={0.75} sx={{ flexShrink: 0, minWidth: 112 }}>
            <Tooltip title="Delete this gold label and reset candidate to pending">
              <span>
                <IconButton
                  size="small"
                  color="error"
                  onClick={(event) => { event.stopPropagation(); onReset(); }}
                  disabled={resetting}
                  sx={{ mb: 0.25 }}
                >
                  {resetting ? <CircularProgress size={14} /> : <DeleteOutlineIcon sx={{ fontSize: 17 }} />}
                </IconButton>
              </span>
            </Tooltip>
            <Chip
              icon={<VerifiedIcon sx={{ fontSize: 13 }} />}
              label={item.quality_score !== null ? `${Math.round(item.quality_score * 100)}%` : "verified"}
              color={qualityColor(item.quality_score)}
              size="small"
              sx={{ fontWeight: 700, fontSize: "0.72rem" }}
            />
            {item.verified_by && (
              <Typography sx={{ fontSize: "0.68rem", color: "text.secondary", textAlign: "right", lineHeight: 1.3 }}>
                {item.verified_by}
              </Typography>
            )}
            <Typography sx={{ fontSize: "0.65rem", color: "text.disabled", textAlign: "right", lineHeight: 1.3 }}>
              {formatDate(item.verified_at ?? item.updated_at)}
            </Typography>
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
const DEDUPE_MIN_THRESHOLD = 0.5;
const DEDUPE_MAX_THRESHOLD = 0.99;
const DEDUPE_MIN_CANDIDATES = 50;
const DEDUPE_MAX_CANDIDATES = 3000;

function clampNumber(
  value: number,
  min: number,
  max: number,
  fallback: number,
): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

export default function GoldDatasetPanel() {
  const [tab, setTab] = useState<"candidates" | "gold" | "synthetic">("candidates");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [page, setPage] = useState(1);

  const [candidateStats, setCandidateStats] = useState<CandidateStats | null>(null);
  const [goldStats, setGoldStats] = useState<GoldStats | null>(null);
  const [syntheticStats, setSyntheticStats] = useState<SyntheticStats | null>(null);
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
  const [deleteCandidateTarget, setDeleteCandidateTarget] = useState<{
    id: string;
    text: string;
    entities: Entity[];
  } | null>(null);
  const [openingCandidateLabelId, setOpeningCandidateLabelId] = useState<string | null>(null);
  const [candidateGoldLabel, setCandidateGoldLabel] = useState<GoldLabel | null>(null);
  const [markingGoldCandidateId, setMarkingGoldCandidateId] = useState<string | null>(null);
  const [dedupeDialogOpen, setDedupeDialogOpen] = useState(false);
  const [dedupeStatus, setDedupeStatus] = useState("completed");
  const [dedupeThreshold, setDedupeThreshold] = useState(0.9);
  const [dedupeMaxCandidates, setDedupeMaxCandidates] = useState(1200);
  const [dedupePreviewLoading, setDedupePreviewLoading] = useState(false);
  const [dedupeApplyLoading, setDedupeApplyLoading] = useState(false);
  const [dedupePreview, setDedupePreview] = useState<CandidateDedupePreview | null>(
    null,
  );
  const [expandedDedupeGroup, setExpandedDedupeGroup] = useState<string | false>(false);
  const [syntheticDialogOpen, setSyntheticDialogOpen] = useState(false);
  const [generatingSynthetic, setGeneratingSynthetic] = useState(false);
  const [syntheticMode, setSyntheticMode] = useState<"inline" | "queue">("inline");
  const [syntheticLimit, setSyntheticLimit] = useState(50);
  const [selectedSyntheticTags, setSelectedSyntheticTags] = useState<string[]>([]);
  const [selectedValuesetIds, setSelectedValuesetIds] = useState<string[]>([]);
  const [availableValuesets, setAvailableValuesets] = useState<ValuesetOption[]>([]);
  const [useDerivedForms, setUseDerivedForms] = useState(false);
  const [purgingSynthetic, setPurgingSynthetic] = useState(false);

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
      const [cs, gs, ss] = await Promise.all([
        jsonFetch<CandidateStats>("/api/training/candidates/stats"),
        jsonFetch<GoldStats>("/api/training/gold-labels/stats"),
        jsonFetch<SyntheticStats>("/api/training/synthetic-gold/stats"),
      ]);
      setCandidateStats(cs);
      setGoldStats(gs);
      setSyntheticStats(ss);
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

  // Load valueset options once when the synthetic dialog is first opened
  useEffect(() => {
    if (!syntheticDialogOpen || availableValuesets.length > 0) return;
    jsonFetch<{ valuesets: ValuesetOption[] }>("/api/training/synthetic-gold/valuesets")
      .then((data) => setAvailableValuesets(data.valuesets ?? []))
      .catch(() => { /* non-critical — dialog still usable without valueset list */ });
  }, [syntheticDialogOpen, availableValuesets.length]);

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
      } else if (tab === "gold") {
        const url = `/api/training/gold-labels?page=${page}&page_size=${PAGE_SIZE}${debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ""}`;
        const data = await jsonFetch<{ items: GoldLabel[]; total: number }>(url);
        setItems(data.items);
        setTotal(data.total);
      } else {
        const url = `/api/training/gold-labels?page=${page}&page_size=${PAGE_SIZE}&source=synthetic_llm${debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ""}`;
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
  const handleTabChange = (_: React.SyntheticEvent, val: "candidates" | "gold" | "synthetic") => {
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

  async function handleGenerateSynthetic() {
    if (generatingSynthetic) return;
    setGeneratingSynthetic(true);
    setListError(null);
    setActionMsg(null);
    try {
      const payload = {
        limit: syntheticMode === "inline" ? Math.min(syntheticLimit, 50) : Math.min(syntheticLimit, 500),
        sentences_per_form: 10,
        semantic_tags: selectedSyntheticTags.length ? selectedSyntheticTags : null,
        valueset_ids: selectedValuesetIds.length ? selectedValuesetIds : null,
        use_derived_forms: useDerivedForms,
      };
      if (syntheticMode === "inline") {
        const result = await jsonFetch<SyntheticGenerateResult>(
          "/api/training/synthetic-candidates",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          },
        );
        setActionMsg(buildSyntheticRunSummary(result));
      } else {
        const result = await jsonFetch<SyntheticQueueResult>(
          "/api/training/synthetic-candidates/queue",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          },
        );
        setActionMsg(
          result.queued
            ? `Queued ${result.queued_batches} batch(es) for ${result.estimated_forms} forms.`
            : "No eligible surface forms found to queue.",
        );
      }
      setSyntheticDialogOpen(false);
      await Promise.all([loadList(), loadStats()]);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to generate synthetic candidates");
    } finally {
      setGeneratingSynthetic(false);
    }
  }

  async function handleDeleteSyntheticSet() {
    if (purgingSynthetic) return;
    setPurgingSynthetic(true);
    setListError(null);
    setActionMsg(null);
    try {
      const result = await jsonFetch<SyntheticDeleteResult>(
        "/api/training/synthetic-candidates",
        { method: "DELETE" },
      );
      setActionMsg(
        `Deleted synthetic set: ${result.deleted_gold_labels} labels and ${result.deleted_candidates} candidates.`,
      );
      await Promise.all([loadList(), loadStats()]);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to delete synthetic set");
    } finally {
      setPurgingSynthetic(false);
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
    const candidate = (items as Candidate[]).find((c) => c.candidate_id === candidateId);
    setDeleteCandidateTarget({
      id: candidateId,
      text: candidate?.text ?? "",
      entities: parseEntities(candidate?.entities_json ?? null),
    });
  }

  async function handleDeleteCandidate(
    candidateId: string,
    encounterText = "",
    suppressEncounterText = false,
  ) {
    if (!candidateId || deletingCandidateId) return;
    setDeletingCandidateId(candidateId);
    setExportMsg(null);
    setActionMsg(null);
    setListError(null);
    try {
      const tasks: Promise<unknown>[] = [
        jsonFetch<DeleteTrainingCandidateResult>(
          `/api/training/candidates/${encodeURIComponent(candidateId)}`,
          { method: "DELETE" },
        ),
      ];
      if (suppressEncounterText && encounterText.trim()) {
        tasks.push(
          createEncounterSuppressRule(
            encounterText,
            `Encounter suppressed on candidate delete (candidate: ${candidateId})`,
          ).catch(() => null),
        );
      }
      const [result] = await Promise.all(tasks);
      const suppressNote = suppressEncounterText
        ? " Encounter text added to pipeline suppression list."
        : "";
      const del = result as DeleteTrainingCandidateResult;
      setActionMsg(
        `Candidate deleted. Removed ${del.gold_labels_deleted} gold labels and ${del.surface_form_tasks_deleted} surface-form tasks.${suppressNote}`,
      );
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
      await Promise.all([loadList(), loadStats()]);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Could not mark candidate as gold data");
    } finally {
      setMarkingGoldCandidateId(null);
    }
  }

  async function previewCandidateDedupe() {
    if (dedupePreviewLoading) return;
    setDedupePreviewLoading(true);
    setListError(null);
    setActionMsg(null);
    try {
      const normalizedThreshold = clampNumber(
        dedupeThreshold,
        DEDUPE_MIN_THRESHOLD,
        DEDUPE_MAX_THRESHOLD,
        0.85,
      );
      const normalizedMaxCandidates = Math.round(
        clampNumber(
          dedupeMaxCandidates,
          DEDUPE_MIN_CANDIDATES,
          DEDUPE_MAX_CANDIDATES,
          1200,
        ),
      );
      const payload = {
        status: dedupeStatus || null,
        max_candidates: normalizedMaxCandidates,
        similarity_threshold: normalizedThreshold,
      };
      setDedupeThreshold(normalizedThreshold);
      setDedupeMaxCandidates(normalizedMaxCandidates);
      const result = await jsonFetch<CandidateDedupePreview>(
        "/api/training/candidates/dedupe/preview",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      setDedupePreview(result);
      setExpandedDedupeGroup(result.groups?.[0]?.canonical?.candidate_id ?? false);
    } catch (e) {
      setListError(
        e instanceof Error ? e.message : "Could not preview duplicate candidates",
      );
      setDedupePreview(null);
    } finally {
      setDedupePreviewLoading(false);
    }
  }

  async function applyCandidateDedupe() {
    if (dedupeApplyLoading) return;
    setDedupeApplyLoading(true);
    setListError(null);
    setActionMsg(null);
    try {
      const normalizedThreshold = clampNumber(
        dedupeThreshold,
        DEDUPE_MIN_THRESHOLD,
        DEDUPE_MAX_THRESHOLD,
        0.85,
      );
      const normalizedMaxCandidates = Math.round(
        clampNumber(
          dedupeMaxCandidates,
          DEDUPE_MIN_CANDIDATES,
          DEDUPE_MAX_CANDIDATES,
          1200,
        ),
      );
      const payload = {
        status: dedupeStatus || null,
        max_candidates: normalizedMaxCandidates,
        similarity_threshold: normalizedThreshold,
      };
      setDedupeThreshold(normalizedThreshold);
      setDedupeMaxCandidates(normalizedMaxCandidates);
      const result = await jsonFetch<CandidateDedupeApplyResult>(
        "/api/training/candidates/dedupe/apply",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      setActionMsg(
        result.message ??
          `Deduped ${result.duplicates_marked} candidates across ${result.group_count} groups.`,
      );
      setDedupeDialogOpen(false);
      setDedupePreview(null);
      await Promise.all([loadList(), loadStats()]);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Could not apply dedupe");
    } finally {
      setDedupeApplyLoading(false);
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
        <Stack direction="row" spacing={1}>
          {tab === "candidates" && (
            <Tooltip title="Preview and mark very similar candidates as duplicates">
              <Button
                variant="outlined"
                color="secondary"
                onClick={() => {
                  setDedupeDialogOpen(true);
                  setDedupePreview(null);
                  setExpandedDedupeGroup(false);
                }}
                size="small"
              >
                Deduplicate similar
              </Button>
            </Tooltip>
          )}
          <Tooltip title="Export all verified gold labels as MedSpaCy training data">
            <span>
              <Button
                variant="outlined"
                startIcon={exporting ? <CircularProgress size={14} /> : <DownloadIcon />}
                disabled={exporting || !goldStats || goldStats.total === 0}
                onClick={handleExport}
                size="small"
              >
                Export training data
              </Button>
            </span>
          </Tooltip>
        </Stack>
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
              label="Synthetic gold labels"
              value={syntheticStats?.synthetic_gold_labels ?? 0}
              color="secondary.main"
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
        <Tab
          value="synthetic"
          label={
            <Stack direction="row" spacing={0.75} alignItems="center">
              <span>Synthetic</span>
              {syntheticStats && (
                <Chip label={syntheticStats.synthetic_gold_labels} size="small" color="secondary" sx={{ height: 18, fontSize: "0.7rem" }} />
              )}
            </Stack>
          }
        />
      </Tabs>

      {tab === "synthetic" && syntheticStats && (
        <Card variant="outlined" sx={{ mb: 2 }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ xs: "flex-start", sm: "center" }} justifyContent="space-between">
              <Box sx={{ width: "100%" }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Surface-form coverage: {syntheticStats.covered_surface_forms.toLocaleString()} / {syntheticStats.total_surface_forms.toLocaleString()}
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={syntheticStats.total_surface_forms > 0 ? (syntheticStats.covered_surface_forms / syntheticStats.total_surface_forms) * 100 : 0}
                  sx={{ mt: 1, height: 8, borderRadius: 1 }}
                />
                <Stack direction="row" spacing={0.75} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
                  {syntheticStats.tag_breakdown.slice(0, 6).map((row) => (
                    <Chip
                      key={row.semantic_tag}
                      size="small"
                      label={`${row.semantic_tag}: ${row.covered_surface_forms}`}
                      variant="outlined"
                    />
                  ))}
                </Stack>
              </Box>
              <Button
                variant="contained"
                color="secondary"
                startIcon={generatingSynthetic ? <CircularProgress size={14} color="inherit" /> : <SyncIcon />}
                onClick={() => setSyntheticDialogOpen(true)}
                disabled={generatingSynthetic}
                size="small"
              >
                Generate synthetic
              </Button>
              <Button
                variant="outlined"
                color="error"
                startIcon={purgingSynthetic ? <CircularProgress size={14} color="inherit" /> : <DeleteOutlineIcon />}
                onClick={handleDeleteSyntheticSet}
                disabled={purgingSynthetic}
                size="small"
              >
                Delete synthetic set
              </Button>
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Search */}
      <TextField
        size="small"
        placeholder={
          tab === "candidates"
            ? "Search candidate text..."
            : tab === "synthetic"
              ? "Search synthetic gold text..."
              : "Search gold label text..."
        }
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        fullWidth
        sx={{
          mb: 2,
          "& .MuiOutlinedInput-root": {
            borderRadius: 2,
            bgcolor: "background.paper",
          },
        }}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" sx={{ color: "text.disabled" }} />
              </InputAdornment>
            ),
            endAdornment: search ? (
              <InputAdornment position="end">
                <IconButton size="small" onClick={() => setSearch("")} edge="end">
                  <CloseIcon sx={{ fontSize: 16 }} />
                </IconButton>
              </InputAdornment>
            ) : undefined,
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
              ? `No ${
                tab === "candidates"
                  ? "candidates"
                  : tab === "synthetic"
                    ? "synthetic labels"
                    : "verified labels"
              } matching "${debouncedSearch}".`
              : tab === "candidates"
                ? "No training candidates yet. Run the pipeline to generate them."
                : tab === "synthetic"
                  ? "No synthetic labels yet. Generate from the Synthetic tab controls above."
                  : "No verified gold labels yet. Labels appear here after a reviewer saves a candidate as gold data."}
          </Typography>
        </Box>
      ) : (
        <>
          {tab === "candidates"
            ? (items as Candidate[]).map((item, i) => (
                <CandidateRow
                  key={item.candidate_id ?? `c-${i}`}
                  item={item}
                  onClick={() => void openCandidateLabelEditor(item.candidate_id)}
                  onMarkGold={markCandidateAsGold}
                  onDelete={requestDeleteCandidate}
                  openingLabelEditor={openingCandidateLabelId === item.candidate_id}
                  markingGold={markingGoldCandidateId === item.candidate_id}
                  deleting={deletingCandidateId === item.candidate_id}
                />
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
      {selectedItem && tab === "gold" && (
        <GoldLabelDetailDialog
          item={selectedItem as GoldLabel}
          onClose={() => setSelectedItem(null)}
          onEntitiesChanged={() => void loadList()}
        />
      )}
      {selectedItem && tab === "synthetic" && (
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
      {deleteCandidateTarget && (
        <DeleteCandidateDialog
          target={deleteCandidateTarget}
          onCancel={() => setDeleteCandidateTarget(null)}
          onConfirm={(suppressEncounterText) => {
            const target = deleteCandidateTarget;
            setDeleteCandidateTarget(null);
            void handleDeleteCandidate(target.id, target.text, suppressEncounterText);
          }}
        />
      )}
      {candidateGoldLabel && (
        <GoldLabelDetailDialog
          item={candidateGoldLabel}
          onClose={() => setCandidateGoldLabel(null)}
          onEntitiesChanged={async () => {
            await Promise.all([loadList(), loadStats()]);
          }}
          onMarkGold={() => {
            setCandidateGoldLabel(null);
            void markCandidateAsGold(candidateGoldLabel.candidate_id ?? "");
          }}
          markingGold={markingGoldCandidateId === candidateGoldLabel.candidate_id}
        />
      )}
      <Dialog
        open={dedupeDialogOpen}
        onClose={() => !dedupeApplyLoading && setDedupeDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Deduplicate similar candidates</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <Typography variant="body2" color="text.secondary">
              Preview duplicate groups first, then apply to mark non-canonical items as
              duplicate.
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                select
                label="Status scope"
                value={dedupeStatus}
                size="small"
                sx={{ minWidth: 180 }}
                onChange={(event) => setDedupeStatus(event.target.value)}
              >
                <MenuItem value="completed">completed</MenuItem>
                <MenuItem value="pending">pending</MenuItem>
                <MenuItem value="processing">processing</MenuItem>
                <MenuItem value="failed">failed</MenuItem>
                <MenuItem value="">all statuses</MenuItem>
              </TextField>
              <TextField
                label="Max candidates"
                type="number"
                size="small"
                value={dedupeMaxCandidates}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setDedupeMaxCandidates(
                    clampNumber(
                      next,
                      DEDUPE_MIN_CANDIDATES,
                      DEDUPE_MAX_CANDIDATES,
                      1200,
                    ),
                  );
                }}
                inputProps={{
                  min: DEDUPE_MIN_CANDIDATES,
                  max: DEDUPE_MAX_CANDIDATES,
                }}
                sx={{ minWidth: 180 }}
              />
              <TextField
                label="Similarity threshold"
                type="number"
                size="small"
                value={dedupeThreshold}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setDedupeThreshold(
                    clampNumber(
                      next,
                      DEDUPE_MIN_THRESHOLD,
                      DEDUPE_MAX_THRESHOLD,
                      0.85,
                    ),
                  );
                }}
                inputProps={{
                  min: DEDUPE_MIN_THRESHOLD,
                  max: DEDUPE_MAX_THRESHOLD,
                  step: 0.01,
                }}
                sx={{ minWidth: 180 }}
              />
            </Stack>
            {dedupePreview && (
              <Alert severity="info">
                Pool: {dedupePreview.candidate_pool_size.toLocaleString()} candidates.
                Potential duplicates: {dedupePreview.duplicate_count.toLocaleString()} in{" "}
                {dedupePreview.group_count.toLocaleString()} groups.
              </Alert>
            )}
            {dedupePreview?.groups?.length ? (
              <Box sx={{ maxHeight: 280, overflowY: "auto", pr: 0.5 }}>
                <Stack spacing={1.25}>
                  {dedupePreview.groups.slice(0, 20).map((group) => (
                    <Accordion
                      key={group.canonical.candidate_id}
                      disableGutters
                      expanded={expandedDedupeGroup === group.canonical.candidate_id}
                      onChange={(_, expanded) =>
                        setExpandedDedupeGroup(
                          expanded ? group.canonical.candidate_id : false,
                        )
                      }
                      sx={{
                        border: "1px solid",
                        borderColor: "divider",
                        borderRadius: 2,
                        boxShadow: "none",
                        "&:before": { display: "none" },
                        overflow: "hidden",
                      }}
                    >
                      <AccordionSummary
                        expandIcon={<ExpandMoreIcon />}
                        sx={{
                          px: 1.25,
                          py: 0.5,
                          minHeight: 56,
                          "& .MuiAccordionSummary-content": {
                            margin: "6px 0",
                          },
                        }}
                      >
                        <Box sx={{ width: "100%", minWidth: 0 }}>
                          <Typography variant="caption" color="text.secondary">
                            Canonical {group.canonical.candidate_id}
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.25 }}>
                            {group.canonical.text_preview}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {group.duplicates.length} duplicate
                            {group.duplicates.length === 1 ? "" : "s"}
                          </Typography>
                        </Box>
                      </AccordionSummary>
                      <AccordionDetails sx={{ px: 1.25, pt: 0, pb: 1.25 }}>
                        <Stack spacing={1}>
                          {group.duplicates.map((duplicate) => (
                            <Card
                              key={duplicate.candidate_id}
                              variant="outlined"
                              sx={{ p: 1, borderRadius: 1.5 }}
                            >
                              <Stack
                                direction={{ xs: "column", sm: "row" }}
                                spacing={1}
                                justifyContent="space-between"
                                alignItems={{ xs: "flex-start", sm: "center" }}
                              >
                                <Box sx={{ minWidth: 0 }}>
                                  <Typography
                                    variant="caption"
                                    sx={{ fontFamily: "monospace", color: "text.secondary" }}
                                  >
                                    {duplicate.candidate_id}
                                  </Typography>
                                  <Typography variant="body2" sx={{ mt: 0.25 }}>
                                    {duplicate.text_preview}
                                  </Typography>
                                  <Stack
                                    direction="row"
                                    spacing={0.75}
                                    alignItems="center"
                                    sx={{ mt: 0.5 }}
                                  >
                                    <Chip
                                      size="small"
                                      label={duplicate.status || "unknown"}
                                      color={statusColor(duplicate.status || "default")}
                                      sx={{
                                        height: 20,
                                        fontSize: "0.7rem",
                                        textTransform: "capitalize",
                                      }}
                                    />
                                    {typeof duplicate.similarity === "number" && (
                                      <Typography variant="caption" color="text.secondary">
                                        Similarity {Math.round(duplicate.similarity * 100)}%
                                      </Typography>
                                    )}
                                  </Stack>
                                </Box>
                                <Button
                                  size="small"
                                  color="error"
                                  variant="outlined"
                                  startIcon={
                                    deletingCandidateId === duplicate.candidate_id ? (
                                      <CircularProgress size={14} />
                                    ) : (
                                      <DeleteOutlineIcon fontSize="small" />
                                    )
                                  }
                                  disabled={deletingCandidateId === duplicate.candidate_id}
                                  onClick={() => requestDeleteCandidate(duplicate.candidate_id)}
                                >
                                  Delete duplicate
                                </Button>
                              </Stack>
                            </Card>
                          ))}
                        </Stack>
                      </AccordionDetails>
                    </Accordion>
                  ))}
                  {dedupePreview.groups.length > 20 && (
                    <Typography variant="caption" color="text.secondary">
                      Showing first 20 groups.
                    </Typography>
                  )}
                </Stack>
              </Box>
            ) : dedupePreview ? (
              <Alert severity="success">No duplicates met this threshold.</Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDedupeDialogOpen(false)} disabled={dedupeApplyLoading}>
            Close
          </Button>
          <Button
            variant="outlined"
            onClick={previewCandidateDedupe}
            disabled={dedupePreviewLoading || dedupeApplyLoading}
          >
            {dedupePreviewLoading ? "Previewing..." : "Preview duplicates"}
          </Button>
          <Button
            variant="contained"
            color="secondary"
            onClick={applyCandidateDedupe}
            disabled={
              dedupeApplyLoading ||
              dedupePreviewLoading ||
              !dedupePreview ||
              dedupePreview.duplicate_count < 1
            }
          >
            {dedupeApplyLoading ? "Applying..." : "Apply dedupe"}
          </Button>
        </DialogActions>
      </Dialog>
      <Dialog open={syntheticDialogOpen} onClose={() => !generatingSynthetic && setSyntheticDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Generate synthetic gold labels</DialogTitle>
        <DialogContent dividers sx={{ overflowY: "auto", maxHeight: "70vh" }}>
          <Stack spacing={3} sx={{ mt: 0.5 }}>
            {/* ── Run options ── */}
            <Stack direction="row" spacing={2}>
              <TextField
                select
                label="Mode"
                value={syntheticMode}
                onChange={(e) => setSyntheticMode(e.target.value as "inline" | "queue")}
                size="small"
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="inline">Inline (up to 50 forms)</MenuItem>
                <MenuItem value="queue">Queued (up to 500 forms)</MenuItem>
              </TextField>
              <TextField
                label="Surface forms to process"
                type="number"
                size="small"
                value={syntheticLimit}
                onChange={(e) => setSyntheticLimit(Number(e.target.value || 0))}
                inputProps={{ min: 1, max: syntheticMode === "inline" ? 50 : 500 }}
                helperText="10 sentences per form."
                sx={{ minWidth: 180 }}
              />
            </Stack>

            {/* ── Domain / Sub-domain ── */}
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Domain / Sub-domain
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                Restrict generation to concepts in one or more clinical domains.
                Each chip shows <strong>covered / total concepts</strong>.
                Grey count = concepts with existing surface forms.
                Orange count = concepts derivable from preferred term (no surface forms yet).
              </Typography>
              {availableValuesets.length === 0 ? (
                <Typography variant="caption" color="text.disabled">
                  Loading domains…
                </Typography>
              ) : (
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {availableValuesets
                    .filter((vs) => vs.concept_count > 0)
                    .map((vs) => {
                      const selected = selectedValuesetIds.includes(vs.id);
                      const pct = vs.concept_count > 0
                        ? Math.round((vs.sf_count / vs.concept_count) * 100)
                        : 0;
                      const derivableLabel = useDerivedForms && vs.derivable_count > 0
                        ? ` +${vs.derivable_count}`
                        : "";
                      return (
                        <Tooltip
                          key={vs.id}
                          title={
                            vs.sf_count === 0
                              ? `No surface forms yet — ${vs.concept_count} concept(s) will use preferred term`
                              : `${vs.sf_count} surface-form-mapped, ${vs.derivable_count} derivable from preferred term`
                          }
                        >
                          <Chip
                            label={`${vs.title}  ${vs.sf_count}${derivableLabel} / ${vs.concept_count} (${pct}%)`}
                            color={selected ? "primary" : "default"}
                            variant={selected ? "filled" : "outlined"}
                            sx={
                              selected && vs.sf_count === 0
                                ? { borderColor: "warning.main", color: "warning.main" }
                                : undefined
                            }
                            onClick={() => {
                              setSelectedValuesetIds((prev) =>
                                prev.includes(vs.id)
                                  ? prev.filter((id) => id !== vs.id)
                                  : [...prev, vs.id],
                              );
                            }}
                          />
                        </Tooltip>
                      );
                    })}
                </Stack>
              )}
              {selectedValuesetIds.length > 0 && (
                <Stack direction="row" alignItems="center" spacing={2} sx={{ mt: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    {selectedValuesetIds.length} domain{selectedValuesetIds.length > 1 ? "s" : ""} selected
                    {" — "}
                    <Box
                      component="span"
                      sx={{ cursor: "pointer", textDecoration: "underline" }}
                      onClick={() => setSelectedValuesetIds([])}
                    >
                      clear
                    </Box>
                  </Typography>
                  <FormControlLabel
                    control={
                      <Switch
                        size="small"
                        checked={useDerivedForms}
                        onChange={(e) => setUseDerivedForms(e.target.checked)}
                        color="warning"
                      />
                    }
                    label={
                      <Typography variant="caption">
                        Include concepts without surface forms
                        {useDerivedForms && (() => {
                          const total = selectedValuesetIds.reduce((sum, id) => {
                            const vs = availableValuesets.find((v) => v.id === id);
                            return sum + (vs?.derivable_count ?? 0);
                          }, 0);
                          return total > 0 ? ` (${total} derivable)` : "";
                        })()}
                      </Typography>
                    }
                  />
                </Stack>
              )}
              {useDerivedForms && (
                <Typography variant="caption" color="warning.main" display="block" sx={{ mt: 0.5 }}>
                  Derived forms use the concept preferred term as the surface form.
                  Generated sentences will bootstrap new surface form mappings.
                </Typography>
              )}
            </Box>

            {/* ── Semantic type filter ── */}
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Semantic type filter <Typography component="span" variant="caption" color="text.secondary">(optional — leave blank for all types)</Typography>
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {(syntheticStats?.tag_options ?? []).map((opt) => {
                  const selected = selectedSyntheticTags.includes(opt.semantic_tag);
                  return (
                    <Chip
                      key={opt.semantic_tag}
                      label={`${opt.semantic_tag} (${opt.total_surface_forms})`}
                      color={selected ? "secondary" : "default"}
                      variant={selected ? "filled" : "outlined"}
                      size="small"
                      onClick={() => {
                        setSelectedSyntheticTags((prev) =>
                          prev.includes(opt.semantic_tag)
                            ? prev.filter((tag) => tag !== opt.semantic_tag)
                            : [...prev, opt.semantic_tag],
                        );
                      }}
                    />
                  );
                })}
              </Stack>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSyntheticDialogOpen(false)} disabled={generatingSynthetic}>Cancel</Button>
          <Button variant="contained" color="secondary" onClick={handleGenerateSynthetic} disabled={generatingSynthetic}>
            {generatingSynthetic ? "Generating..." : "Run"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
