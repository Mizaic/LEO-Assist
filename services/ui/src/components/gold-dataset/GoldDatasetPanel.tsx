/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-1E9BCC70
 *   Also implements: DO-236545C8, DO-54397CCD, DO-A15BFFE4, DO-B88D4941
 *   DI: DI-21946271, DI-2D9F5064, DI-3035F221, DI-6EFD68D0, DI-AF5A1668
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-1E9BCC70")
 */
"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
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
import MenuItem from "@mui/material/MenuItem";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Popover from "@mui/material/Popover";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import BookmarkIcon from "@mui/icons-material/Bookmark";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import BookmarkBorderIcon from "@mui/icons-material/BookmarkBorder";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DownloadIcon from "@mui/icons-material/Download";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ArrowRightAltIcon from "@mui/icons-material/ArrowRightAlt";
import LinkIcon from "@mui/icons-material/Link";
import NotInterestedIcon from "@mui/icons-material/NotInterested";
import SearchIcon from "@mui/icons-material/Search";
import SyncIcon from "@mui/icons-material/Sync";
import VerifiedIcon from "@mui/icons-material/Verified";
import {
  FilterBar,
  ProgressStrip,
  SegmentedTabs,
  StatHero,
  ToolbarActions,
  type StatTile as DsStatTile,
  type ToolbarAction,
} from "@leo/design-system";
import { createEncounterSuppressRule, createSuppressRule, exportMedSpaCyTraining, fetchGoldLabel, fetchSurfaceForms, patchGoldLabelEntities, searchTerms, upsertSurfaceFormMapping } from "@/lib/api/legacy";
import {
  addConceptToSubdomain,
  fetchConceptSubdomainMemberships,
  type SubdomainMembershipItem,
} from "@/lib/analyticsApi";
import type { TermSearchResult } from "@/lib/types";
import {
  coerceEntitySemanticLabel,
  normaliseEntitySemanticRows,
  VALID_ENTITY_SEMANTIC_LABELS as ENTITY_LABEL_OPTIONS,
  type EntitySemanticLabel,
} from "@/lib/entitySemanticLabels";
import { renderNerSpans, themeForAssertion, type AnnotatedSpan } from "@/lib/nerAnnotation";
import ConfirmDialog from "@/components/ConfirmDialog";
import CandidateReviewList from "@/components/gold-dataset/CandidateReviewList";
import CandidatePruneDialog from "@/components/gold-dataset/CandidatePruneDialog";
import AIFirstPassDialog from "@/components/gold-dataset/AIFirstPassDialog";
import DatasetHealthPanel from "@/components/gold-dataset/DatasetHealthPanel";
import DialogActionsBar from "@/components/gold-dataset/GoldLabelDetailDialog/DialogActionsBar";
import DialogTitleStrip from "@/components/gold-dataset/GoldLabelDetailDialog/DialogTitleStrip";
import DeleteConfirmPanel from "@/components/gold-dataset/GoldLabelDetailDialog/DeleteConfirmPanel";
import SuggestionsPanel from "@/components/gold-dataset/GoldLabelDetailDialog/SuggestionsPanel";
import GoldLabelReviewList from "@/components/gold-dataset/GoldLabelReviewList";
import SimilarCandidatesBatch from "@/components/gold-dataset/SimilarCandidatesBatch";
import SnomedInlineSearch from "@/components/gold-dataset/SnomedInlineSearch";
import useKeyboardShortcuts from "@/components/gold-dataset/useKeyboardShortcuts";
import type { RejectedRelation, SimilarCandidateItem } from "@/components/gold-dataset/goldDatasetTypes";
import { entityLabelColour } from "@/components/gold-dataset/goldDatasetUtils";

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

interface AnnotationGuidelinesResponse {
  name: string;
  version: number;
  guidelines: string;
  applies_to: string[];
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
  relation_changes?: string | null;
  source: string;
  status: string;
  uncertainty_score?: number | null;
  rarity_score?: number | null;
  priority_score?: number | null;
  rare_labels?: string[] | null;
  hitl_reason?: string | null;
  hitl_guidance?: string | null;
  created_at: string;
  updated_at: string;
  // -- AI first-pass audit fields (DI-LEO-AI-208 / DI-LEO-AI-209) --
  // Surfaced from GET_TRAINING_CANDIDATES_PAGE so the candidate row can
  // render an "AI suggested" chip on pre_done items without having to
  // re-fetch each row.
  ai_first_pass_run_id?: string | null;
  ai_first_pass_at?: string | null;
  entities_json_original?: string | null;
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
  // -- AI first-pass audit fields (DI-LEO-AI-208 / DI-LEO-AI-209) --
  // Set when the candidate has been touched by a Haiku first-pass:
  //   - ai_first_pass_run_id: non-null while the AI pass is the
  //     latest writer of entities_json
  //   - entities_json_original: the pre-AI entities_json snapshot
  //     written once by UPSERT_AI_FIRST_PASS_ENTITIES so the
  //     reviewer can always toggle back to the pre-AI baseline.
  ai_first_pass_run_id?: string | null;
  ai_first_pass_at?: string | null;
  entities_json_original?: string | null;
}

interface Entity {
  text: string;
  label?: string;
  semantic_tag?: string;
  snomed_concept_id?: string;
  snomed_term?: string;
  assertion?: string;
  body_site_concept_id?: string;
  body_site_term?: string;
  relations?: EntityRelation[];
  rejected_relations?: RejectedRelation[];
}

interface EntityRelation {
  type: string;
  target_idx: number;
  target_text?: string;
  confidence?: number;
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

interface SimilarCandidatesResponse {
  source_candidate_id: string;
  count: number;
  items: SimilarCandidateItem[];
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
      const rows = parsed
        .filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object")
        .map((entry, index, all) => {
          const coding = (entry.coding && typeof entry.coding === "object"
            ? (entry.coding as Record<string, unknown>)
            : {}) as Record<string, unknown>;
          const snomedConceptId = String(
            entry.snomed_concept_id ?? entry.concept_id ?? coding.snomed_concept_id ?? "",
          ).trim();
          const snomedTerm = String(
            entry.snomed_term ?? entry.term ?? entry.preferred_term ?? coding.snomed_term ?? "",
          ).trim();
          const bodySiteConceptId = String(entry.body_site_concept_id ?? "").trim();
          const bodySiteTerm = String(entry.body_site_term ?? "").trim();
          const text = String(entry.text ?? "").trim();
          const rawRelations = Array.isArray(entry.relations)
            ? (entry.relations as Array<Record<string, unknown>>)
            : Array.isArray(entry.__relations)
              ? (entry.__relations as Array<Record<string, unknown>>)
              : [];
          const relations = rawRelations
            .map((relation) => {
              const type = String(relation.type ?? "").trim().toLowerCase();
              const targetIdx = Number(relation.target_idx);
              if (!type || !Number.isInteger(targetIdx) || targetIdx < 0) return null;
              return {
                type,
                target_idx: targetIdx,
                target_text: String(relation.target_text ?? "").trim() || undefined,
                confidence:
                  typeof relation.confidence === "number"
                    ? Number(relation.confidence)
                    : undefined,
              } as EntityRelation;
            })
            .filter((relation): relation is EntityRelation => Boolean(relation));
          if (!relations.some((relation) => relation.type === "finding_site")) {
            const legacySite = bodySiteTerm || String(entry.body_site ?? "").trim();
            if (legacySite) {
              const targetIdx = all.findIndex((target, idx) => {
                if (idx === index || !target || typeof target !== "object") return false;
                const targetText = String(target.text ?? "").trim().toLowerCase();
                const targetTerm = String(target.snomed_term ?? target.term ?? "").trim().toLowerCase();
                return legacySite.toLowerCase() === targetText || legacySite.toLowerCase() === targetTerm;
              });
              if (targetIdx >= 0) {
                relations.push({
                  type: "finding_site",
                  target_idx: targetIdx,
                  target_text: String((all[targetIdx] as Record<string, unknown>).text ?? ""),
                  confidence: 1,
                });
              }
            }
          }
          return {
            ...entry,
            text,
            snomed_concept_id: snomedConceptId || undefined,
            snomed_term: snomedTerm || undefined,
            body_site_concept_id: bodySiteConceptId || undefined,
            body_site_term: bodySiteTerm || undefined,
            relations,
          } as Entity;
        });
      return normaliseEntitySemanticRows(rows);
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

const ASSERTION_OPTIONS = [
  "absent",
  "cancelled",
  "declined",
  "family",
  "historical",
  "hypothetical",
  "planned",
  "possible",
  "present",
  "refuted",
  "uncertain",
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

function isBodySiteEntity(entity: Entity): boolean {
  const label = (entity.label ?? entity.semantic_tag ?? "").toLowerCase();
  return label.includes("body_structure") || label.includes("body structure");
}

interface RelationSuggestion {
  sourceIdx: number;
  targetIdx: number;
  type: string;
  confidence: number;
  reason: string;
}

const RELATION_POLICY_UI: Array<{
  sourceLabels: string[];
  targetLabels: string[];
  type: string;
  reason: string;
}> = [
  {
    sourceLabels: ["finding", "disorder", "situation", "procedure"],
    targetLabels: ["body_structure"],
    type: "finding_site",
    reason: "Use this when a finding or procedure is linked to a body site.",
  },
  {
    sourceLabels: ["finding"],
    targetLabels: ["observable_entity"],
    type: "interprets",
    reason: "Use this when the finding describes what the observation means.",
  },
  {
    sourceLabels: ["qualifier_value", "finding"],
    targetLabels: ["finding", "disorder", "procedure"],
    type: "qualifies",
    reason: "Use this when one term qualifies or describes another (e.g. severity, progression).",
  },
  {
    sourceLabels: ["finding"],
    targetLabels: ["disorder", "finding"],
    type: "associated_finding",
    reason: "Use this when the finding supports a linked disorder or another finding.",
  },
  {
    sourceLabels: ["observable_entity"],
    targetLabels: ["procedure"],
    type: "component_of",
    reason: "Use this when an observable (e.g. gamma GT) is a component of a procedure (e.g. LFTs).",
  },
];

function normaliseLabel(label: string | undefined): string {
  return String(label ?? "").trim().toLowerCase().replace(/ /g, "_");
}

/** All linkable relation types defined in RELATION_POLICY_UI. */
const LINKABLE_RELATION_TYPES = new Set(RELATION_POLICY_UI.map((r) => r.type));

function canHaveBodySite(entity: Entity): boolean {
  if (isBodySiteEntity(entity)) return false;
  const src = normaliseLabel(entity.label ?? entity.semantic_tag);
  return RELATION_POLICY_UI.some((rule) => rule.sourceLabels.includes(src));
}

/** Returns all relation-target indices for any linkable relation type. */
function findingSiteTargetIndices(entity: Entity, entityCount: number): number[] {
  const relationTargets = (entity.relations ?? [])
    .filter((relation) => LINKABLE_RELATION_TYPES.has(relation.type))
    .map((relation) => relation.target_idx)
    .filter((targetIdx) => Number.isInteger(targetIdx) && targetIdx >= 0 && targetIdx < entityCount);
  return Array.from(new Set(relationTargets));
}

/** Derives the correct relation type for a given source/target label pair. */
function relationTypeForPair(sourceLabel: string, targetLabel: string): string {
  const src = normaliseLabel(sourceLabel);
  const tgt = normaliseLabel(targetLabel);
  const rule = RELATION_POLICY_UI.find(
    (r) => r.sourceLabels.includes(src) && r.targetLabels.includes(tgt),
  );
  return rule?.type ?? "finding_site";
}

function relationAllowedForLabels(
  sourceLabel: string,
  targetLabel: string,
  sourceText?: string,
): RelationSuggestion | null {
  const src = normaliseLabel(sourceLabel);
  const tgt = normaliseLabel(targetLabel);
  const sourceTextNorm = String(sourceText ?? "").toLowerCase();
  const qualifierHint =
    /\b(increased|decreased|worse|worsened|improved|severe|mild|moderate|larger|smaller|size)\b/.test(
      sourceTextNorm,
    );
  for (const rule of RELATION_POLICY_UI) {
    if (!rule.sourceLabels.includes(src) || !rule.targetLabels.includes(tgt)) {
      continue;
    }
    // Skip the text-hint guard if the source is already labelled qualifier_value
    // — its entity type is a sufficient signal without needing keyword clues.
    const srcIsQualifier = src === "qualifier_value";
    if (rule.type === "qualifies" && !qualifierHint && !srcIsQualifier) {
      continue;
    }
    return {
      sourceIdx: -1,
      targetIdx: -1,
      type: rule.type,
      confidence: rule.type === "qualifies" ? 0.86 : 0.81,
      reason: rule.reason,
    };
  }
  return null;
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
    <Box sx={{ p: 1.25, border: "1px solid", borderColor: "divider", borderRadius: 1.5, minWidth: 110, textAlign: "center" }}>
      <Typography variant="h6" sx={{ fontWeight: 700, color: color ?? "text.primary", lineHeight: 1.3 }}>
        {value}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ fontSize: "0.7rem", lineHeight: 1.4 }}>
        {label}
      </Typography>
      {sub && (
        <Typography variant="caption" color="text.disabled" display="block" sx={{ fontSize: "0.65rem" }}>
          {sub}
        </Typography>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Detail dialog
// ---------------------------------------------------------------------------

// State for the row being looked up: index into entities array
interface LookupTarget {
  entityIndex: number;
  entityText: string;
  entityLabel: string;
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

// -- Annotation guidelines panel ------------------------------------------

const _GUIDELINE_COLORS = [
  "#5C6BC0",
  "#039BE5",
  "#00897B",
  "#43A047",
  "#FB8C00",
  "#E53935",
  "#8E24AA",
  "#00ACC1",
];

interface _ParsedRule {
  number: number;
  title: string;
  body: string;
}

function _parseAnnotationRules(text: string): _ParsedRule[] {
  const rules: _ParsedRule[] = [];
  let current: _ParsedRule | null = null;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const m = line.match(/^(\d+)\)\s+(.+)/);
    if (m) {
      if (current) rules.push(current);
      current = { number: parseInt(m[1], 10), title: m[2].trim(), body: "" };
    } else if (current && line && !line.startsWith("#") && !line.startsWith("Apply")) {
      const stripped = line.replace(/^-\s+/, "");
      current.body += (current.body ? "\n" : "") + stripped;
    }
  }
  if (current) rules.push(current);
  return rules;
}

function AnnotationGuidelinesPanel({
  text,
  defaultExpanded = false,
}: {
  text: string;
  defaultExpanded?: boolean;
}) {
  const [open, setOpen] = useState(defaultExpanded);
  const [page, setPage] = useState(0);
  const rules = _parseAnnotationRules(text);
  const total = rules.length;
  const rule = rules[page] ?? null;
  const accent = rule
    ? _GUIDELINE_COLORS[(rule.number - 1) % _GUIDELINE_COLORS.length]
    : _GUIDELINE_COLORS[0];

  const handlePrev = (e: React.MouseEvent) => {
    e.stopPropagation();
    setPage((p) => Math.max(0, p - 1));
  };
  const handleNext = (e: React.MouseEvent) => {
    e.stopPropagation();
    setPage((p) => Math.min(total - 1, p + 1));
  };
  const handleDot = (e: React.MouseEvent, i: number) => {
    e.stopPropagation();
    setPage(i);
  };

  const _SPAN_LABEL_COLORS: Record<string, { bg: string; text: string }> = {
    procedure: { bg: "#1565C0", text: "#fff" },
    situation: { bg: "#6A1B9A", text: "#fff" },
    finding: { bg: "#BF360C", text: "#fff" },
    disorder: { bg: "#B71C1C", text: "#fff" },
    observable_entity: { bg: "#0277BD", text: "#fff" },
    qualifier_value: { bg: "#558B2F", text: "#fff" },
    regime_therapy: { bg: "#E65100", text: "#fff" },
    substance: { bg: "#004D40", text: "#fff" },
  };

  const _ASSERTION_COLORS: Record<string, string> = {
    present: "#2E7D32",
    absent: "#C62828",
    planned: "#1565C0",
    historical: "#795548",
    hypothetical: "#6A1B9A",
    possible: "#E65100",
    family: "#37474F",
  };

  const _bodyLines = (body: string) =>
    body.split("\n").map((line, i) => {
      const trimmed = line.trim();

      if (trimmed.startsWith(">> ")) {
        const parts = trimmed.slice(3).split("|").map((s) => s.trim());
        const spanText = parts[0] ?? "";
        const rawLabels = (parts[1] ?? "")
          .split("+")
          .map((s) => s.trim().toLowerCase())
          .filter(Boolean);
        const assertion = parts[2]?.trim().toLowerCase() ?? "";
        const snomed = parts[3]?.replace(/^SNOMED:\s*/i, "").trim() ?? "";
        return (
          <Box
            key={i}
            sx={{
              display: "flex",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 0.5,
              mt: 0.75,
              mb: 0.1,
            }}
          >
            <Box
              component="span"
              sx={{
                px: 0.75,
                py: 0.2,
                bgcolor: "grey.100",
                border: "1px solid",
                borderColor: "grey.300",
                borderRadius: 0.75,
                fontSize: "0.71rem",
                fontFamily: "monospace",
                color: "text.primary",
                fontWeight: 500,
              }}
            >
              {spanText}
            </Box>
            <Box component="span" sx={{ color: "text.disabled", fontSize: "0.65rem", mx: 0.25 }}>
              {"\u2192"}
            </Box>
            {rawLabels.map((lbl) => {
              const c = _SPAN_LABEL_COLORS[lbl] ?? { bg: "#607D8B", text: "#fff" };
              return (
                <Box
                  key={lbl}
                  component="span"
                  sx={{
                    px: 0.75,
                    py: 0.2,
                    bgcolor: c.bg,
                    color: c.text,
                    borderRadius: 0.75,
                    fontSize: "0.63rem",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.03em",
                  }}
                >
                  {lbl}
                </Box>
              );
            })}
            {assertion && (
              <Box
                component="span"
                sx={{
                  px: 0.75,
                  py: 0.2,
                  bgcolor: (_ASSERTION_COLORS[assertion] ?? "#607D8B") + "1a",
                  color: _ASSERTION_COLORS[assertion] ?? "#607D8B",
                  border: "1px solid",
                  borderColor: (_ASSERTION_COLORS[assertion] ?? "#607D8B") + "44",
                  borderRadius: 0.75,
                  fontSize: "0.63rem",
                  fontWeight: 600,
                }}
              >
                {assertion}
              </Box>
            )}
            {snomed && (
              <Box
                component="span"
                sx={{
                  px: 0.75,
                  py: 0.2,
                  bgcolor: "grey.50",
                  border: "1px dashed",
                  borderColor: "grey.400",
                  borderRadius: 0.75,
                  fontSize: "0.62rem",
                  color: "text.disabled",
                  fontFamily: "monospace",
                }}
              >
                {snomed}
              </Box>
            )}
          </Box>
        );
      }

      const isExample = trimmed.toLowerCase().startsWith("example");
      return (
        <Box
          key={i}
          sx={{
            display: "flex",
            alignItems: "baseline",
            gap: 0.5,
            mt: isExample ? 0.6 : 0.1,
          }}
        >
          {isExample && (
            <Box
              component="span"
              sx={{
                display: "inline-block",
                px: 0.6,
                py: 0.1,
                borderRadius: 0.75,
                bgcolor: accent + "22",
                color: accent,
                fontSize: "0.62rem",
                fontWeight: 700,
                lineHeight: 1.4,
                whiteSpace: "nowrap",
                flexShrink: 0,
              }}
            >
              eg.
            </Box>
          )}
          <Typography
            component="span"
            sx={{
              fontSize: "0.72rem",
              lineHeight: 1.5,
              color: isExample ? "text.primary" : "text.secondary",
              fontStyle: isExample ? "italic" : "normal",
            }}
          >
            {isExample ? trimmed.replace(/^example:\s*/i, "") : trimmed}
          </Typography>
        </Box>
      );
    });

  return (
    <Box>
      {/* Header / toggle bar */}
      <Box
        onClick={() => setOpen((v) => !v)}
        role="button"
        aria-expanded={open}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: 1.5,
          py: 0.85,
          borderRadius: open ? "10px 10px 0 0" : "10px",
          border: "1px solid",
          borderBottom: open ? "none" : "1px solid",
          borderColor: open ? "primary.200" : "grey.200",
          bgcolor: open ? "primary.50" : "background.paper",
          cursor: "pointer",
          userSelect: "none",
          transition: "background-color 0.15s, border-color 0.15s",
          "&:hover": { bgcolor: "primary.50", borderColor: "primary.200" },
        }}
      >
        <InfoOutlinedIcon sx={{ color: "primary.main", fontSize: 15, flexShrink: 0 }} />
        <Typography
          variant="body2"
          sx={{ flex: 1, fontWeight: 600, fontSize: "0.78rem", color: "primary.main" }}
        >
          Annotation guidelines
        </Typography>
        <Chip
          label={open ? `${page + 1} of ${total}` : `${total} rules`}
          size="small"
          sx={{
            height: 18,
            fontSize: "0.66rem",
            bgcolor: open ? accent : "grey.200",
            color: open ? "white" : "text.secondary",
            transition: "background-color 0.2s",
            "& .MuiChip-label": { px: 0.75 },
          }}
        />
        <ExpandMoreIcon
          sx={{
            color: "primary.main",
            fontSize: 16,
            flexShrink: 0,
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s",
          }}
        />
      </Box>

      {/* Paged rule card */}
      {open && rule && (
        <Box
          sx={{
            border: "1px solid",
            borderColor: "primary.100",
            borderRadius: "0 0 10px 10px",
            overflow: "hidden",
            bgcolor: "background.paper",
          }}
        >
          {/* Coloured top accent bar */}
          <Box sx={{ height: 3, bgcolor: accent, transition: "background-color 0.25s" }} />

          {/* Rule content */}
          <Box sx={{ px: 2, pt: 1.5, pb: 1.25, minHeight: 120 }}>
            <Stack direction="row" alignItems="flex-start" gap={1.5}>
              <Box
                sx={{
                  minWidth: 26,
                  height: 26,
                  borderRadius: "50%",
                  bgcolor: accent,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  mt: 0.1,
                  transition: "background-color 0.25s",
                  boxShadow: `0 2px 6px ${accent}55`,
                }}
              >
                <Typography sx={{ fontSize: "0.65rem", color: "white", fontWeight: 800, lineHeight: 1 }}>
                  {rule.number}
                </Typography>
              </Box>
              <Box sx={{ minWidth: 0 }}>
                <Typography
                  variant="body2"
                  sx={{ fontWeight: 700, fontSize: "0.8rem", lineHeight: 1.4, color: "text.primary", mb: 0.5 }}
                >
                  {rule.title}
                </Typography>
                {rule.body && (
                  <Box>{_bodyLines(rule.body)}</Box>
                )}
              </Box>
            </Stack>
          </Box>

          {/* Navigation footer */}
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              px: 1.5,
              py: 0.75,
              borderTop: "1px solid",
              borderColor: "grey.100",
              bgcolor: "grey.50",
            }}
          >
            {/* Pill progress dots */}
            <Stack direction="row" spacing={0.5} alignItems="center">
              {rules.map((_, i) => (
                <Box
                  key={i}
                  onClick={(e) => handleDot(e, i)}
                  sx={{
                    width: i === page ? 18 : 6,
                    height: 6,
                    borderRadius: 3,
                    bgcolor: i === page
                      ? _GUIDELINE_COLORS[i % _GUIDELINE_COLORS.length]
                      : "grey.300",
                    cursor: "pointer",
                    transition: "width 0.2s, background-color 0.2s",
                    "&:hover": { bgcolor: i !== page ? "grey.400" : undefined },
                  }}
                />
              ))}
            </Stack>

            {/* Prev / Next */}
            <Stack direction="row" spacing={0.25} alignItems="center">
              <IconButton
                size="small"
                onClick={handlePrev}
                disabled={page === 0}
                sx={{ width: 28, height: 28, color: "text.secondary" }}
              >
                <ChevronLeftIcon sx={{ fontSize: 18 }} />
              </IconButton>
              <Typography
                variant="caption"
                sx={{ fontSize: "0.68rem", color: "text.disabled", minWidth: 32, textAlign: "center" }}
              >
                {page + 1} / {total}
              </Typography>
              <IconButton
                size="small"
                onClick={handleNext}
                disabled={page === total - 1}
                sx={{ width: 28, height: 28, color: "text.secondary" }}
              >
                <ChevronRightIcon sx={{ fontSize: 18 }} />
              </IconButton>
            </Stack>
          </Box>
        </Box>
      )}
    </Box>
  );
}

// -- End annotation guidelines panel ---------------------------------------

// -- Shared "saved" entity payload shape ---------------------------------
//
// This is the wire shape produced by the dialog when persisting changes.
// Default save mode posts it to PATCH /training/gold-labels/{id}/entities.
// Dual-save consumers (e.g. /care/patients, /care/encounters in
// DI-LEO-AI-221) pass a custom `entitySaver` that posts to
// /patients/{p}/encounters/{e}/coded-links/sync-from-gold so the live
// :DOCUMENTS coded links are mirrored alongside the de-identified
// gold training copy. R-LEO-AI-206 governs the safety controls on
// the dual-save path.
export interface SavedGoldEntity {
  text: string;
  label: string;
  assertion?: string;
  snomed_concept_id?: string;
  snomed_term?: string;
  semantic_tag?: string;
  body_site_concept_id?: string;
  body_site_term?: string;
  relations: Array<{
    type: string;
    target_idx: number;
    target_text?: string;
    confidence?: number;
  }>;
  rejected_relations: Array<{
    type: string;
    target_text: string;
    reason: string;
  }>;
}

export type GoldDialogSaveMode = "gold" | "dual";

export type GoldDialogEntitySaver = (
  entities: SavedGoldEntity[],
) => Promise<void>;

export function GoldLabelDetailDialog({
  item,
  onClose,
  onEntitiesChanged,
  onMarkGold,
  onNextCandidate,
  onDeleteCandidate,
  markingGold,
  annotationGuidelines,
  saveMode = "gold",
  entitySaver,
  onAfterSave,
  headerChrome,
}: {
  item: GoldLabel;
  onClose: () => void;
  onEntitiesChanged?: () => void;
  onMarkGold?: () => void;
  onNextCandidate?: () => void;
  onDeleteCandidate?: (suppressText: boolean) => void;
  markingGold?: boolean;
  annotationGuidelines?: string | null;
  // -- Shared component plumbing (DI-LEO-AI-219) -----------------------
  // saveMode: 'gold' (default, candidates+evaluate) writes only to the
  //   GoldLabel via PATCH /training/gold-labels/{id}/entities.
  //   'dual' enables the explicit warning banner used on the /care
  //   surfaces; the host MUST also pass a matching entitySaver.
  // entitySaver: optional override for persistence. Default behaviour
  //   calls patchGoldLabelEntities(item.label_id, entities). Hosts may
  //   inject e.g. a sync-from-gold call for dual writes.
  // onAfterSave: optional success callback fired after each persist
  //   resolves (in addition to onEntitiesChanged).
  // headerChrome: optional React node rendered just below the title
  //   strip, intended for surface-specific context like search match
  //   rationale chips on /care/encounters (DI-LEO-AI-223).
  saveMode?: GoldDialogSaveMode;
  entitySaver?: GoldDialogEntitySaver;
  onAfterSave?: () => void;
  headerChrome?: React.ReactNode;
}) {
  const [entities, setEntities] = useState<Entity[]>(() => parseEntities(item.entities_json));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [newEntityText, setNewEntityText] = useState("");
  const [newEntityLabel, setNewEntityLabel] = useState<EntitySemanticLabel>("finding");
  const [newEntityAssertion, setNewEntityAssertion] = useState<(typeof ASSERTION_OPTIONS)[number]>("present");
  const [lookupTarget, setLookupTarget] = useState<LookupTarget | null>(null);
  const [termDrafts, setTermDrafts] = useState<Record<number, string>>({});
  const [suppressingIndex, setSuppressingIndex] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<Record<number, TermSearchResult | null>>({});
  const [rejectedRelationKeys, setRejectedRelationKeys] = useState<Record<string, string>>(() => {
    // Rehydrate from persisted rejected_relations on each entity (text-keyed ->
    // index-keyed for in-memory lookup).
    const parsed = parseEntities(item.entities_json);
    const initial: Record<string, string> = {};
    for (const [srcIdx, entity] of parsed.entries()) {
      for (const rej of entity.rejected_relations ?? []) {
        const targetIdx = parsed.findIndex((e) => e.text === rej.target_text);
        if (targetIdx >= 0) {
          initial[`${srcIdx}:${rej.type}:${targetIdx}`] = rej.reason;
        }
      }
    }
    return initial;
  });
  const [searchingAll, setSearchingAll] = useState(false);
  const [showShortcutHelp, setShowShortcutHelp] = useState(false);
  const [showGuidelines, setShowGuidelines] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [selectionAdded, setSelectionAdded] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [suppressOnDelete, setSuppressOnDelete] = useState(false);
  const [sfExpandedIdx, setSfExpandedIdx] = useState<number | null>(null);
  const [sfDrafts, setSfDrafts] = useState<Record<number, string>>({});
  // key: `${conceptId}::${normalizedText}` -> true=exists, false=missing, undefined=loading
  const [sfStatusMap, setSfStatusMap] = useState<Record<string, boolean>>({});
  const [sfSaving, setSfSaving] = useState<number | null>(null);
  const [sfMsg, setSfMsg] = useState<Record<number, string>>({});
  const sentenceBoxRef = useRef<HTMLDivElement>(null);
  const addTermInputRef = useRef<HTMLInputElement>(null);
  const [sentenceRelationPaths, setSentenceRelationPaths] = useState<
    Array<{ path: string; relType: string; midX: number; midY: number }>
  >([]);

  // -- AI first-pass: "show original" toggle (DI-LEO-AI-209 / R-LEO-AI-197) --
  // When the candidate has been touched by an AI first-pass run,
  // ai_first_pass_run_id is set and entities_json_original holds the
  // pre-AI snapshot. The toggle lets the reviewer flip the entity
  // list back to the original (read-only) so they can confirm what
  // the AI actually changed before approving the candidate.
  const [showOriginalEntities, setShowOriginalEntities] = useState(false);
  const isAISuggested = !!item.ai_first_pass_run_id;
  const originalEntities = useMemo(
    () => parseEntities(item.entities_json_original ?? null),
    [item.entities_json_original],
  );
  const hasOriginalSnapshot = originalEntities.length > 0;

  // Belt-and-braces resync: callers SHOULD pass `key={item.label_id}` so the
  // dialog remounts per record (the lazy useState initialisers above only
  // run on mount). If they forget, this effect re-derives `entities` and
  // `rejectedRelationKeys` from the new `item.entities_json`, preventing the
  // class of bug where the previous candidate's entities leak into the next
  // one (DI-LEO-AI-185, R-LEO-AI-179).
  const prevLabelIdRef = useRef(item.label_id);
  useEffect(() => {
    if (prevLabelIdRef.current === item.label_id) return;
    prevLabelIdRef.current = item.label_id;
    const parsed = parseEntities(item.entities_json);
    setEntities(parsed);
    const nextRejected: Record<string, string> = {};
    for (const [srcIdx, entity] of parsed.entries()) {
      for (const rej of entity.rejected_relations ?? []) {
        const targetIdx = parsed.findIndex((e) => e.text === rej.target_text);
        if (targetIdx >= 0) {
          nextRejected[`${srcIdx}:${rej.type}:${targetIdx}`] = rej.reason;
        }
      }
    }
    setRejectedRelationKeys(nextRejected);
    setSuggestions({});
    setTermDrafts({});
    setSfDrafts({});
    setSfMsg({});
    setSfExpandedIdx(null);
    setLookupTarget(null);
    setSaveError(null);
    setSaveMsg(null);
    setNewEntityText("");
    setShowDeleteConfirm(false);
    setSuppressOnDelete(false);
    setShowOriginalEntities(false);
  }, [item.label_id, item.entities_json]);

  function copyToClipboard(text: string, key: string) {
    void navigator.clipboard.writeText(text).then(() => {
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((prev) => (prev === key ? null : prev)), 1800);
    });
  }

  async function saveSurfaceFormSynonym(entityIdx: number, conceptId: string) {
    const synonym = (sfDrafts[entityIdx] ?? "").trim();
    if (!synonym) return;
    setSfSaving(entityIdx);
    try {
      await upsertSurfaceFormMapping(synonym.toLowerCase(), synonym, conceptId, {
        provenance: "manual_correction",
        source: "gold_label_editor",
      });
      // Mark this synonym as registered in the status map
      const key = `${conceptId}::${synonym.toLowerCase()}`;
      setSfStatusMap((prev) => ({ ...prev, [key]: true }));
      setSfMsg((prev) => ({ ...prev, [entityIdx]: `"${synonym}" saved.` }));
      setSfDrafts((prev) => { const n = { ...prev }; delete n[entityIdx]; return n; });
      setSfExpandedIdx(null);
      setTimeout(() => setSfMsg((prev) => { const n = { ...prev }; delete n[entityIdx]; return n; }), 2500);
    } catch {
      setSfMsg((prev) => ({ ...prev, [entityIdx]: "Could not save." }));
    } finally {
      setSfSaving(null);
    }
  }

  function handleSentenceMouseUp() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;
    const selected = selection.toString().trim();
    if (selected.length < 2) return;
    const range = selection.getRangeAt(0);
    if (!sentenceBoxRef.current?.contains(range.commonAncestorContainer)) return;
    setNewEntityText(selected);
    setSelectionAdded(true);
    setTimeout(() => setSelectionAdded(false), 2200);
    setTimeout(() => {
      addTermInputRef.current?.focus();
      addTermInputRef.current?.select();
    }, 50);
  }

  const pendingSuggestionCount = Object.values(suggestions).filter(Boolean).length;
  const uncodedCount = entities.filter((entity) => !entity.snomed_concept_id).length;
  const relationSuggestions = useMemo(() => {
    const rows: RelationSuggestion[] = [];
    for (let sourceIdx = 0; sourceIdx < entities.length; sourceIdx += 1) {
      const source = entities[sourceIdx];
      const existing = new Set(
        (source.relations ?? []).map((relation) => `${relation.type}:${relation.target_idx}`),
      );
      for (let targetIdx = 0; targetIdx < entities.length; targetIdx += 1) {
        if (sourceIdx === targetIdx) continue;
        const target = entities[targetIdx];
        const suggestion = relationAllowedForLabels(
          source.label ?? source.semantic_tag ?? "",
          target.label ?? target.semantic_tag ?? "",
          source.text,
        );
        if (!suggestion) continue;
        const dedupKey = `${suggestion.type}:${targetIdx}`;
        const suggestionKey = `${sourceIdx}:${suggestion.type}:${targetIdx}`;
        if (rejectedRelationKeys[suggestionKey]) continue;
        if (existing.has(dedupKey)) continue;
        rows.push({
          ...suggestion,
          sourceIdx,
          targetIdx,
          confidence: suggestion.type === "finding_site" ? 0.88 : suggestion.confidence,
        });
      }
    }
    return rows.sort((a, b) => b.confidence - a.confidence).slice(0, 8);
  }, [entities, rejectedRelationKeys]);
  const bodySiteOptionsByIndex = useMemo(() => {
    return entities.map((source, idx) => {
      const srcLabel = normaliseLabel(source.label ?? source.semantic_tag);
      return entities
        .map((candidate, candidateIdx) => {
          if (candidateIdx === idx) return null;
          const tgtLabel = normaliseLabel(candidate.label ?? candidate.semantic_tag);
          const rule = RELATION_POLICY_UI.find(
            (r) => r.sourceLabels.includes(srcLabel) && r.targetLabels.includes(tgtLabel),
          );
          if (!rule) return null;
          return { candidate, candidateIdx, relationType: rule.type };
        })
        .filter(
          (x): x is { candidate: Entity; candidateIdx: number; relationType: string } =>
            x !== null,
        );
    });
  }, [entities]);
  const canAcceptAllAndMark = Boolean(onMarkGold) && uncodedCount > 0 && pendingSuggestionCount >= uncodedCount;
  const linkedBodySitePairs = useMemo(() => {
    const pairs: Array<{
      sourceText: string;
      sourceType: string;
      relationType: string;
      siteText: string;
      siteType: string;
    }> = [];
    for (const [sourceIdx, entity] of entities.entries()) {
      if (!canHaveBodySite(entity)) continue;
      const sourceText = String(entity.text || "").trim();
      for (const rel of entity.relations ?? []) {
        const siteIdx = rel.target_idx;
        if (siteIdx === sourceIdx || siteIdx < 0 || siteIdx >= entities.length) continue;
        const siteEntity = entities[siteIdx];
        const siteText = String(siteEntity?.snomed_term ?? siteEntity?.text ?? "").trim();
        if (!sourceText || !siteText) continue;
        pairs.push({
          sourceText,
          sourceType: String(entity.label ?? entity.semantic_tag ?? "").trim(),
          relationType: rel.type,
          siteText,
          siteType: String(siteEntity?.label ?? siteEntity?.semantic_tag ?? "").trim(),
        });
      }
    }
    return pairs;
  }, [entities]);
  const sentenceRender = useMemo(() => {
    const text = String(item.text || "");
    if (!text.trim() || entities.length === 0) {
      return {
        content: text || "-",
        spanDomIdByEntityIndex: {} as Record<number, string>,
      };
    }

    // Step 1: find each entity's first occurrence in the sentence.
    // Include entity surface text in the chip so merged spans are readable.
    const lowerText = text.toLowerCase();
    type RawSpan = {
      start: number;
      end: number;
      chip: ReturnType<typeof themeForAssertion>;
      entityIndex: number;
    };
    const raw: RawSpan[] = [];
    for (const [idx, entity] of entities.entries()) {
      const needle = String((termDrafts[idx] ?? entity.text) || "").trim();
      if (!needle) continue;
      const start = lowerText.indexOf(needle.toLowerCase());
      if (start < 0) continue;
      const chip = themeForAssertion(entity.assertion, entity.label ?? entity.semantic_tag);
      raw.push({
        start,
        end: start + needle.length,
        chip: { ...chip, entityText: needle },
        entityIndex: idx,
      });
    }
    if (!raw.length) {
      return {
        content: text,
        spanDomIdByEntityIndex: {} as Record<number, string>,
      };
    }

    // Step 2: greedy interval merge so overlapping entities become a single
    // AnnotatedSpan with multiple chips (one per entity). This ensures ALL
    // entities are visible — even when their surface text overlaps.
    raw.sort((a, b) => a.start - b.start);
    const merged: AnnotatedSpan[] = [];
    const spanDomIdByEntityIndex: Record<number, string> = {};
    let i = 0;
    let spanCounter = 0;
    while (i < raw.length) {
      let uStart = raw[i].start;
      let uEnd = raw[i].end;
      const chips = [raw[i].chip];
      const entityIndices = [raw[i].entityIndex];
      let j = i + 1;
      while (j < raw.length && raw[j].start < uEnd) {
        uEnd = Math.max(uEnd, raw[j].end);
        chips.push(raw[j].chip);
        entityIndices.push(raw[j].entityIndex);
        j++;
      }
      const domId = `ner-span-${spanCounter}`;
      spanCounter += 1;
      for (const entityIndex of entityIndices) {
        spanDomIdByEntityIndex[entityIndex] = domId;
      }
      merged.push({ start: uStart, end: uEnd, chips, domId });
      i = j;
    }

    return {
      content: renderNerSpans(text, merged),
      spanDomIdByEntityIndex,
    };
  }, [entities, item.text, termDrafts]);
  const encounterAnnotated = sentenceRender.content;

  useLayoutEffect(() => {
    const container = sentenceBoxRef.current;
    if (!container) {
      setSentenceRelationPaths([]);
      return;
    }
    const boxRect = container.getBoundingClientRect();
    if (boxRect.width <= 0 || boxRect.height <= 0) {
      setSentenceRelationPaths([]);
      return;
    }

    const nextPaths: Array<{
      path: string;
      relType: string;
      midX: number;
      midY: number;
    }> = [];

    // Track how many arcs each source entity has drawn so far, so we can
    // stagger them vertically and prevent label/line overlap.
    const arcCountBySource: Record<number, number> = {};

    for (let idx = 0; idx < entities.length; idx += 1) {
      const source = entities[idx];
      if (!canHaveBodySite(source)) continue;
      for (const rel of source.relations ?? []) {
        const targetIdx = rel.target_idx;
        if (targetIdx < 0) continue;
        const sourceDomId = sentenceRender.spanDomIdByEntityIndex[idx];
        const targetDomId = sentenceRender.spanDomIdByEntityIndex[targetIdx];
        if (!sourceDomId || !targetDomId || sourceDomId === targetDomId) continue;

        const sourceEl = container.querySelector(
          `[data-ner-id="${sourceDomId}"]`,
        ) as HTMLElement | null;
        const targetEl = container.querySelector(
          `[data-ner-id="${targetDomId}"]`,
        ) as HTMLElement | null;
        if (!sourceEl || !targetEl) continue;

        const sourceRect = sourceEl.getBoundingClientRect();
        const targetRect = targetEl.getBoundingClientRect();
        const x1 = sourceRect.left - boxRect.left + sourceRect.width / 2;
        const x2 = targetRect.left - boxRect.left + targetRect.width / 2;

        // Anchor each arc just above the top of its chips, then bow upward.
        const arcN = arcCountBySource[idx] ?? 0;
        arcCountBySource[idx] = arcN + 1;

        // Stagger: each additional arc from the same source rises 14px higher.
        const baseY = Math.max(
          10,
          Math.min(sourceRect.top - boxRect.top, targetRect.top - boxRect.top) - 6,
        );
        const stagger = arcN * 14;
        const span = Math.abs(x2 - x1);
        // Minimum bow of 22px, scaled by span, plus per-arc stagger.
        const bow = Math.min(48, Math.max(22, span * 0.18)) + stagger;
        const y = baseY;
        const controlY = Math.max(2, y - bow);
        const path = `M ${x1} ${y} Q ${(x1 + x2) / 2} ${controlY} ${x2} ${y}`;
        nextPaths.push({
          path,
          relType: rel.type,
          midX: (x1 + x2) / 2,
          midY: controlY - 3,
        });
      }
    }
    setSentenceRelationPaths(nextPaths);
  }, [entities, sentenceRender.spanDomIdByEntityIndex]);

  async function flushTermDraftsAndMarkGold() {
    const dirtyIndices = Object.keys(termDrafts)
      .map(Number)
      .filter((i) => {
        const draft = termDrafts[i]?.trim();
        return draft !== undefined && draft !== (entities[i]?.text ?? "").trim();
      });
    if (dirtyIndices.length > 0) {
      const next = entities.map((e, i) =>
        termDrafts[i] !== undefined ? { ...e, text: termDrafts[i].trim() } : e,
      );
      const ok = await persistEntities(next, "Term edits saved.");
      if (!ok) return;
    }
    onMarkGold?.();
  }

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
    const entityText = entities[idx]?.text ?? suggestion.term ?? "";
    let surfaceFormNote = "";
    try {
      const normalized = entityText.toLowerCase().trim();
      if (normalized) {
        const existing = await fetchSurfaceForms(
          normalized,
          suggestion.snomed_concept_id,
          1,
          0,
        );
        const mappingExists = existing.items.some(
          (item) =>
            item.normalized === normalized &&
            item.concept_id === suggestion.snomed_concept_id,
        );
        if (!mappingExists) {
          await upsertSurfaceFormMapping(
            normalized,
            entityText,
            suggestion.snomed_concept_id,
            {
              provenance: "manual_correction",
              source: "gold_label_editor",
            },
          );
          surfaceFormNote = " Surface form mapping created.";
        }
      }
    } catch {
      surfaceFormNote = " Surface form mapping check failed.";
    }
    const next = entities.map((e, i) =>
      i === idx
        ? {
            ...e,
            snomed_concept_id: suggestion.snomed_concept_id,
            snomed_term: suggestion.term,
            semantic_tag: suggestion.semantic_tag ?? e.semantic_tag,
            label: coerceEntitySemanticLabel(suggestion.semantic_tag ?? e.semantic_tag),
          }
        : e,
    );
    const ok = await persistEntities(
      next,
      `Code applied: ${suggestion.snomed_concept_id} - ${suggestion.term}.${surfaceFormNote}`,
    );
    if (ok) {
      handleDismissSuggestion(idx);
      // Mark surface form as registered for the entity that was just updated
      const updatedEntity = next[idx];
      if (updatedEntity) refreshSfStatus(updatedEntity, true);
    }
  }

  async function handleAcceptAllSuggestions() {
    const entries = Object.entries(suggestions).filter(([, v]) => v !== null) as [string, TermSearchResult][];
    if (!entries.length) return;
    const next = entities.map((e, i) => {
      const suggestion = suggestions[i];
      return suggestion
        ? {
            ...e,
            snomed_concept_id: suggestion.snomed_concept_id,
            snomed_term: suggestion.term,
            semantic_tag: suggestion.semantic_tag ?? e.semantic_tag,
            label: coerceEntitySemanticLabel(suggestion.semantic_tag ?? e.semantic_tag),
          }
        : e;
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

  // Load surface form status for each coded entity
  useEffect(() => {
    let cancelled = false;
    const coded = entities
      .map((e, i) => ({ e, i }))
      .filter(({ e }) => e.snomed_concept_id && e.text?.trim());
    if (!coded.length) return () => { cancelled = true; };
    void Promise.all(
      coded.map(async ({ e }) => {
        const normalized = e.text.toLowerCase().trim();
        const key = `${e.snomed_concept_id}::${normalized}`;
        if (key in sfStatusMap) return;
        try {
          const result = await fetchSurfaceForms(normalized, e.snomed_concept_id!, 1, 0);
          const exists = result.items?.some(
            (sf) => sf.normalized === normalized && sf.concept_id === e.snomed_concept_id,
          ) ?? false;
          if (!cancelled) setSfStatusMap((prev) => ({ ...prev, [key]: exists }));
        } catch {
          // non-blocking
        }
      }),
    );
    return () => { cancelled = true; };
  }, [entities]);

  function sfKey(e: Entity): string {
    return `${e.snomed_concept_id}::${(e.text ?? "").toLowerCase().trim()}`;
  }

  function refreshSfStatus(e: Entity, exists: boolean) {
    setSfStatusMap((prev) => ({ ...prev, [sfKey(e)]: exists }));
  }

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
      const payload: SavedGoldEntity[] = next.map((e) => ({
        text: e.text,
        label: e.label ?? "finding",
        assertion: e.assertion,
        snomed_concept_id: e.snomed_concept_id,
        snomed_term: e.snomed_term,
        semantic_tag: e.semantic_tag,
        body_site_concept_id: e.body_site_concept_id,
        body_site_term: e.body_site_term,
        relations: (e.relations ?? []).map((relation) => ({
          type: relation.type,
          target_idx: relation.target_idx,
          target_text: relation.target_text,
          confidence: relation.confidence,
        })),
        rejected_relations: (e.rejected_relations ?? []).map((r) => ({
          type: r.type,
          target_text: r.target_text,
          reason: r.reason,
        })),
      }));
      if (entitySaver) {
        await entitySaver(payload);
      } else {
        await patchGoldLabelEntities(item.label_id, payload);
      }
      setEntities(next);
      setTermDrafts({});
      setSaveMsg(successMsg);
      onEntitiesChanged?.();
      onAfterSave?.();
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

  function handleUpdateEntityBodySite(
    idx: number,
    targetValue: string | string[],
  ) {
    const next = entities.map((entity, i) => {
      if (i !== idx) return entity;
      const values = (Array.isArray(targetValue) ? targetValue : [targetValue])
        .map((value) => Number(value))
        .filter(
          (targetIdx) =>
            Number.isInteger(targetIdx) &&
            targetIdx >= 0 &&
            targetIdx < entities.length &&
            targetIdx !== idx,
        );
      const sourceLabel = entity.label ?? entity.semantic_tag ?? "";
      const keepRelations = (entity.relations ?? []).filter(
        (relation) => !LINKABLE_RELATION_TYPES.has(relation.type),
      );
      if (values.length === 0) {
        return {
          ...entity,
          body_site_concept_id: undefined,
          body_site_term: undefined,
          relations: keepRelations,
        };
      }
      const newRelations = values.map((targetIdx) => {
        const target = entities[targetIdx];
        const relType = relationTypeForPair(sourceLabel, target?.label ?? target?.semantic_tag ?? "");
        return {
          type: relType,
          target_idx: targetIdx,
          target_text: target?.text ?? "",
          confidence: 1,
        };
      });
      const findingSiteRel = newRelations.find((r) => r.type === "finding_site");
      const bodySiteTarget = findingSiteRel ? entities[findingSiteRel.target_idx] : undefined;
      return {
        ...entity,
        body_site_concept_id: bodySiteTarget?.snomed_concept_id ?? undefined,
        body_site_term: bodySiteTarget ? (bodySiteTarget.snomed_term ?? bodySiteTarget.text) : undefined,
        relations: [...keepRelations, ...newRelations],
      };
    });
    void persistEntities(next, `Updated linked body sites for "${entities[idx].text}".`);
  }

  function handleAcceptRelationSuggestion(suggestion: RelationSuggestion) {
    const next = entities.map((entity, index) => {
      if (index !== suggestion.sourceIdx) return entity;
      const existing = entity.relations ?? [];
      const dedupKey = `${suggestion.type}:${suggestion.targetIdx}`;
      if (existing.some((relation) => `${relation.type}:${relation.target_idx}` === dedupKey)) {
        return entity;
      }
      const target = entities[suggestion.targetIdx];
      const relations = [
        ...existing,
        {
          type: suggestion.type,
          target_idx: suggestion.targetIdx,
          target_text: target?.text ?? "",
          confidence: suggestion.confidence,
        },
      ];
      const patch: Partial<Entity> = { relations };
      if (suggestion.type === "finding_site" && target) {
        patch.body_site_concept_id = target.snomed_concept_id;
        patch.body_site_term = target.snomed_term ?? target.text;
      }
      return { ...entity, ...patch };
    });
    const source = entities[suggestion.sourceIdx];
    const target = entities[suggestion.targetIdx];
    void persistEntities(
      next,
      `Accepted link: ${source?.text ?? "term"} -> ${target?.text ?? "term"}.`,
    );
  }

  function handleRejectRelationSuggestion(suggestion: RelationSuggestion, reason: string) {
    const key = `${suggestion.sourceIdx}:${suggestion.type}:${suggestion.targetIdx}`;
    setRejectedRelationKeys((prev) => ({ ...prev, [key]: reason }));
    // Persist so the dismissal survives page reload.
    const targetText = entities[suggestion.targetIdx]?.text ?? "";
    const next = entities.map((entity, index) => {
      if (index !== suggestion.sourceIdx) return entity;
      const existing = entity.rejected_relations ?? [];
      const alreadyStored = existing.some(
        (r) => r.type === suggestion.type && r.target_text === targetText,
      );
      if (alreadyStored) return entity;
      return {
        ...entity,
        rejected_relations: [
          ...existing,
          { type: suggestion.type, target_text: targetText, reason },
        ],
      };
    });
    void persistEntities(next, "Relation suggestion dismissed.");
  }

  function handleUndoRejectedRelation(suggestion: RelationSuggestion) {
    const key = `${suggestion.sourceIdx}:${suggestion.type}:${suggestion.targetIdx}`;
    setRejectedRelationKeys((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
    // Remove from persisted storage so the suggestion can reappear.
    const targetText = entities[suggestion.targetIdx]?.text ?? "";
    const next = entities.map((entity, index) => {
      if (index !== suggestion.sourceIdx) return entity;
      return {
        ...entity,
        rejected_relations: (entity.rejected_relations ?? []).filter(
          (r) => !(r.type === suggestion.type && r.target_text === targetText),
        ),
      };
    });
    void persistEntities(next, "Relation dismissal undone.");
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
    const nextEntity = {
      ...current,
      label,
      ...(isBodySiteEntity({ ...current, label })
        ? { body_site_concept_id: undefined, body_site_term: undefined }
        : {}),
    };
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
            label: coerceEntitySemanticLabel(result.semantic_tag ?? e.semantic_tag),
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

    persistEntities(
      next,
      `Updated SNOMED code to ${result.snomed_concept_id} - ${result.term}.${surfaceFormNote}${subdomainNote}`,
    ).then((ok) => {
      if (ok && alsoFixSurfaceForm) {
        const updatedEntity = next[entityIndex];
        if (updatedEntity) refreshSfStatus(updatedEntity, true);
      }
    }).catch(() => { /* non-blocking */ });
  }

  useEffect(() => {
    if (searchingAll) return;
    const hasUncoded = entities.some((entity) => !entity.snomed_concept_id && entity.text?.trim());
    if (!hasUncoded) return;
    if (Object.keys(suggestions).length > 0) return;
    void handleAutoCodeAll();
  }, [entities, searchingAll, suggestions]);

  useKeyboardShortcuts({
    enabled: true,
    onMarkGold: onMarkGold,
    onAcceptAll: () => {
      if (!saving && pendingSuggestionCount > 0) {
        void handleAcceptAllSuggestions();
      }
    },
    onNext: onNextCandidate,
    onClose,
    onToggleHelp: () => setShowShortcutHelp((prev) => !prev),
  });

  const summary = assertionSummary(entities);

  return (
    <>
      <Dialog open onClose={onClose} maxWidth="lg" fullWidth scroll="paper">
        <DialogTitleStrip
          title="Review this example"
          uncodedCount={uncodedCount}
          suggestionCount={pendingSuggestionCount}
          hasGuidelines={Boolean(annotationGuidelines)}
          guidelinesOpen={showGuidelines}
          shortcutsOpen={showShortcutHelp}
          copied={copiedKey === "sentence"}
          onCopySentence={() =>
            copyToClipboard(String(item.text || ""), "sentence")
          }
          onToggleGuidelines={() => setShowGuidelines((v) => !v)}
          onToggleShortcuts={() => setShowShortcutHelp((v) => !v)}
          onClose={onClose}
        />
        <DialogContent dividers sx={{ borderTopColor: "divider" }}>
          {headerChrome && (
            <Box sx={{ mb: 2 }} data-testid="gold-dialog-header-chrome">
              {headerChrome}
            </Box>
          )}
          {saveMode === "dual" && (
            <Alert
              severity="warning"
              data-testid="dual-save-banner"
              sx={{ mb: 2 }}
              icon={<InfoOutlinedIcon fontSize="inherit" />}
            >
              Saving here updates the live coded data on this encounter and
              records a de-identified copy in gold training (R-LEO-AI-206).
            </Alert>
          )}
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
          {showShortcutHelp && (
            <Alert severity="info" sx={{ mb: 1.5 }} onClose={() => setShowShortcutHelp(false)}>
              Shortcuts: Enter = mark gold, A = accept all suggestions, N = next, Esc = close
            </Alert>
          )}
          {showGuidelines && annotationGuidelines && (
            <Box sx={{ mb: 1.5 }}>
              <AnnotationGuidelinesPanel text={annotationGuidelines} defaultExpanded />
            </Box>
          )}

          {/* Sentence */}
          <Box sx={{ mb: 2 }}>
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.75 }}>
              <Typography variant="overline" color="text.secondary" sx={{ fontSize: "0.68rem", lineHeight: 1 }}>
                Sentence
              </Typography>
              <Tooltip title={copiedKey === "sentence" ? "Copied!" : "Copy sentence"}>
                <IconButton
                  size="small"
                  onClick={() => copyToClipboard(String(item.text || ""), "sentence")}
                  sx={{ p: 0.4, color: copiedKey === "sentence" ? "success.main" : "text.disabled" }}
                >
                  <ContentCopyIcon sx={{ fontSize: 14 }} />
                </IconButton>
              </Tooltip>
            </Stack>
            <Box
              ref={sentenceBoxRef}
              onMouseUp={handleSentenceMouseUp}
              sx={{
                bgcolor: "primary.50",
                border: "1px solid",
                borderColor: selectionAdded ? "success.main" : "primary.100",
                borderRadius: 1.5,
                px: 2.5,
                py: 2,
                cursor: "text",
                userSelect: "text",
                transition: "border-color 0.2s",
                position: "relative",
              }}
            >
              {sentenceRelationPaths.length > 0 && (
                <Box
                  component="svg"
                  viewBox={`0 0 ${Math.max(1, sentenceBoxRef.current?.clientWidth ?? 1)} ${Math.max(1, sentenceBoxRef.current?.clientHeight ?? 1)}`}
                  sx={{
                    position: "absolute",
                    inset: 0,
                    width: "100%",
                    height: "100%",
                    pointerEvents: "none",
                    zIndex: 1,
                    overflow: "visible",
                  }}
                >
                  <defs>
                    {["#2563eb","#e65100","#00838f","#2e7d32","#6a1b9a"].map((c, i) => (
                      <marker
                        key={`ah-${i}`}
                        id={`rel-arrow-${i}`}
                        markerWidth="7" markerHeight="7"
                        refX="6" refY="3.5" orient="auto"
                      >
                        <path d="M 0 0 L 7 3.5 L 0 7 z" fill={c} />
                      </marker>
                    ))}
                  </defs>
                  {sentenceRelationPaths.slice(0, 5).map((line, idx) => {
                    const REL_ARC_COLOUR: Record<string, string> = {
                      finding_site: "#2563eb",
                      procedure_site: "#2563eb",
                      qualifies: "#e65100",
                      interprets: "#00838f",
                      associated_finding: "#2e7d32",
                      component_of: "#6a1b9a",
                    };
                    const REL_ARC_MARKER: Record<string, string> = {
                      finding_site: "url(#rel-arrow-0)",
                      procedure_site: "url(#rel-arrow-0)",
                      qualifies: "url(#rel-arrow-1)",
                      interprets: "url(#rel-arrow-2)",
                      associated_finding: "url(#rel-arrow-3)",
                      component_of: "url(#rel-arrow-4)",
                    };
                    const REL_DASH: Record<string, string> = {
                      finding_site: "5 2",
                      procedure_site: "5 2",
                      qualifies: "3 2",
                      interprets: "7 3",
                      associated_finding: "5 2",
                      component_of: "3 3",
                    };
                    const REL_SHORT: Record<string, string> = {
                      finding_site: "site",
                      procedure_site: "site",
                      qualifies: "qualifies",
                      interprets: "interprets",
                      associated_finding: "associated",
                      component_of: "component",
                    };
                    const colour = REL_ARC_COLOUR[line.relType] ?? "#64748b";
                    const marker = REL_ARC_MARKER[line.relType] ?? "url(#rel-arrow-0)";
                    const dash = REL_DASH[line.relType] ?? "4 2";
                    const label = REL_SHORT[line.relType] ?? line.relType;
                    return (
                      <g key={`relation-group-${idx}`}>
                        <path
                          d={line.path}
                          fill="none"
                          stroke={colour}
                          strokeWidth="1.8"
                          strokeDasharray={dash}
                          markerEnd={marker}
                          opacity={0.75}
                        />
                        <rect
                          x={line.midX - label.length * 3.1}
                          y={line.midY - 9}
                          width={label.length * 6.2}
                          height={11}
                          rx={3}
                          fill="white"
                          opacity={0.85}
                        />
                        <text
                          x={line.midX}
                          y={line.midY}
                          textAnchor="middle"
                          fontSize="8.5"
                          fill={colour}
                          fontFamily="system-ui,sans-serif"
                          fontWeight="600"
                        >
                          {label}
                        </text>
                      </g>
                    );
                  })}
                </Box>
              )}
              <Typography
                variant="body1"
                sx={{
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  lineHeight: 3.8,
                  fontSize: "1rem",
                  fontWeight: 400,
                  position: "relative",
                  zIndex: 2,
                }}
              >
                {encounterAnnotated}
              </Typography>
              <Typography
                variant="caption"
                sx={{
                  position: "absolute",
                  bottom: 5,
                  right: 10,
                  fontSize: "0.65rem",
                  color: selectionAdded ? "success.main" : "text.disabled",
                  pointerEvents: "none",
                  transition: "color 0.2s",
                  fontStyle: "italic",
                }}
              >
                {selectionAdded ? "Added to term field below" : "Highlight text to add a term"}
              </Typography>
            </Box>
            {linkedBodySitePairs.length > 0 && (
              <Box
                sx={{
                  mt: 1.25,
                  px: 1.5,
                  py: 1,
                  borderRadius: 1.25,
                  border: "1px dashed",
                  borderColor: "info.light",
                  bgcolor: "info.50",
                }}
              >
                <Typography
                  variant="overline"
                  sx={{
                    display: "block",
                    color: "text.secondary",
                    fontSize: "0.62rem",
                    lineHeight: 1,
                    mb: 0.75,
                    letterSpacing: "0.08em",
                  }}
                >
                  Linked terms
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {linkedBodySitePairs.map((pair, idx) => {
                    const REL_LINK_COLOUR: Record<string, string> = {
                      finding_site: "#2563eb",
                      procedure_site: "#2563eb",
                      qualifies: "#e65100",
                      interprets: "#00838f",
                      associated_finding: "#2e7d32",
                      component_of: "#6a1b9a",
                    };
                    const REL_LINK_LABEL: Record<string, string> = {
                      finding_site: "site",
                      procedure_site: "site",
                      qualifies: "qualifies",
                      interprets: "interprets",
                      associated_finding: "associated",
                      component_of: "component of",
                    };
                    const colour = REL_LINK_COLOUR[pair.relationType] ?? "#64748b";
                    const relLabel = REL_LINK_LABEL[pair.relationType] ?? pair.relationType.replace(/_/g, " ");
                    return (
                      <Box
                        key={`${pair.sourceText}-${pair.relationType}-${idx}`}
                        sx={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          border: "1px solid",
                          borderColor: colour,
                          borderRadius: 1.25,
                          px: 0.75,
                          py: 0.4,
                          bgcolor: "background.paper",
                          fontSize: "0.72rem",
                        }}
                      >
                        <Box
                          component="span"
                          sx={{
                            width: 6,
                            height: 6,
                            borderRadius: "50%",
                            bgcolor: entityLabelColour(pair.sourceType),
                            flexShrink: 0,
                          }}
                        />
                        <Box component="span" sx={{ fontWeight: 600, color: "text.primary" }}>
                          {pair.sourceText}
                        </Box>
                        <Box
                          component="span"
                          sx={{
                            px: 0.5,
                            py: "1px",
                            borderRadius: 0.5,
                            bgcolor: colour,
                            color: "white",
                            fontSize: "0.62rem",
                            fontWeight: 700,
                            letterSpacing: "0.03em",
                            mx: 0.25,
                          }}
                        >
                          {relLabel}
                        </Box>
                        <Box
                          component="span"
                          sx={{
                            width: 6,
                            height: 6,
                            borderRadius: "50%",
                            bgcolor: entityLabelColour(pair.siteType),
                            flexShrink: 0,
                          }}
                        />
                        <Box component="span" sx={{ color: "text.primary" }}>
                          {pair.siteText}
                        </Box>
                      </Box>
                    );
                  })}
                </Stack>
              </Box>
            )}
          </Box>

          {/* Terms */}
          <Box sx={{ mb: 1.5 }}>
            {/* -- AI first-pass banner (DI-LEO-AI-209 / R-LEO-AI-197) -- */}
            {/* When ai_first_pass_run_id is set, surface the AI provenance */}
            {/* and let the reviewer toggle the read-only original snapshot. */}
            {isAISuggested && (
              <Stack
                direction="row"
                spacing={1}
                alignItems="center"
                sx={{
                  mb: 1,
                  px: 1,
                  py: 0.5,
                  borderRadius: 1,
                  bgcolor: "info.50",
                  border: "1px solid",
                  borderColor: "info.200",
                }}
              >
                <Chip
                  size="small"
                  label="AI suggested"
                  color="info"
                  data-testid="ai-suggested-banner"
                  sx={{ fontWeight: 600 }}
                />
                <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
                  These entities were proposed by the AI first-pass.
                  Confirm before approving.
                </Typography>
                {hasOriginalSnapshot && (
                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={showOriginalEntities}
                        onChange={(e) => setShowOriginalEntities(e.target.checked)}
                        data-testid="show-original-toggle"
                      />
                    }
                    label="Show original"
                    componentsProps={{ typography: { variant: "caption" } }}
                  />
                )}
              </Stack>
            )}
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.75 }}>
              <Typography variant="overline" color="text.secondary" sx={{ fontSize: "0.68rem", lineHeight: 1 }}>
                Terms ({entities.length})
              </Typography>
              <Stack direction="row" spacing={0.75} alignItems="center">
                {searchingAll && (
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    <CircularProgress size={11} />
                    <Typography variant="caption" color="text.secondary">Finding codes...</Typography>
                  </Stack>
                )}
                {pendingSuggestionCount > 0 && !searchingAll && (
                  <Button
                    variant="contained"
                    color="warning"
                    size="small"
                    startIcon={saving ? <CircularProgress size={11} color="inherit" /> : <CheckCircleOutlineIcon sx={{ fontSize: 14 }} />}
                    disabled={saving}
                    onClick={() => void handleAcceptAllSuggestions()}
                    sx={{ height: 26, fontSize: "0.73rem", px: 1.25 }}
                  >
                    Accept all {pendingSuggestionCount} suggestion{pendingSuggestionCount !== 1 ? "s" : ""}
                  </Button>
                )}
                <Tooltip title="Re-run automatic code search for all terms">
                  <span>
                    <IconButton
                      size="small"
                      disabled={searchingAll || saving}
                      onClick={() => void handleAutoCodeAll()}
                      sx={{ p: 0.4 }}
                    >
                      <SyncIcon sx={{ fontSize: 15 }} />
                    </IconButton>
                  </span>
                </Tooltip>
              </Stack>
            </Stack>

            <SuggestionsPanel
              suggestions={relationSuggestions}
              entities={entities}
              rejectedKeys={rejectedRelationKeys}
              saving={saving}
              onAccept={handleAcceptRelationSuggestion}
              onReject={(s, reason) => handleRejectRelationSuggestion(s, reason)}
              onUndoReject={handleUndoRejectedRelation}
              onAcceptAll={() => {
                relationSuggestions
                  .filter(
                    (s) =>
                      !rejectedRelationKeys[
                        `${s.sourceIdx}:${s.type}:${s.targetIdx}`
                      ],
                  )
                  .forEach((s) => handleAcceptRelationSuggestion(s));
              }}
            />

            {/* -- Read-only original entities (R-LEO-AI-197 audit view) -- */}
            {/* When the reviewer flips "Show original" we render the    */}
            {/* pre-AI snapshot from entities_json_original. This view is */}
            {/* deliberately read-only: no save handlers fire from here. */}
            {showOriginalEntities && (
              <Stack spacing={0.5} data-testid="original-entities-list">
                {originalEntities.map((oe, oi) => (
                  <Box
                    key={`original-${oi}`}
                    sx={{
                      border: "1px dashed",
                      borderColor: "divider",
                      borderRadius: 1,
                      px: 1.25,
                      py: 0.75,
                    }}
                  >
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {oe.text}
                      </Typography>
                      <Chip
                        size="small"
                        label={oe.label ?? oe.semantic_tag ?? "-"}
                        sx={{ fontSize: "0.66rem", height: 18 }}
                      />
                      <Chip
                        size="small"
                        label={(oe.assertion ?? "present").toLowerCase()}
                        sx={{ fontSize: "0.66rem", height: 18 }}
                      />
                      {oe.snomed_concept_id && (
                        <Typography variant="caption" color="text.secondary">
                          {oe.snomed_concept_id} {oe.snomed_term ?? ""}
                        </Typography>
                      )}
                    </Stack>
                  </Box>
                ))}
                {originalEntities.length === 0 && (
                  <Typography variant="caption" color="text.secondary">
                    No original snapshot recorded.
                  </Typography>
                )}
              </Stack>
            )}

            {!showOriginalEntities && entities.map((e, i) => {
              const nonPresent = isNonPresent(e.assertion);
              const aColor = assertionColor(e.assertion);
              const hasSnomed = !!e.snomed_concept_id;
              const allowBodySite = canHaveBodySite(e);
              const siteOptions = bodySiteOptionsByIndex[i] ?? [];
              const selectedSiteValues = findingSiteTargetIndices(e, entities.length)
                .map((targetIdx) => String(targetIdx));
              const suggestion = suggestions[i];
              const domainCount = conceptSubdomainCounts[e.snomed_concept_id ?? ""] ?? 0;
              const domainLoaded = e.snomed_concept_id ? e.snomed_concept_id in conceptSubdomainCounts : false;
              const leftBorderColor = hasSnomed ? "success.main" : suggestion !== undefined && suggestion !== null ? "warning.main" : "error.light";
              return (
                <Box
                  key={i}
                  sx={{
                    border: "1px solid",
                    borderColor: nonPresent ? `${aColor}.200` : "divider",
                    borderLeft: "3px solid",
                    borderLeftColor: leftBorderColor,
                    borderRadius: 1.5,
                    px: 1.5,
                    py: 1,
                    mb: 0.75,
                    bgcolor: nonPresent ? `${aColor}.50` : "background.paper",
                  }}
                >
                  {/* Row 1: term + type + assertion + actions */}
                  <Stack direction="row" spacing={0.75} alignItems="center">
                    {isAISuggested && (
                      <Chip
                        size="small"
                        label="AI"
                        color="info"
                        variant="outlined"
                        data-testid="ai-suggested-chip"
                        sx={{
                          height: 18,
                          fontSize: "0.62rem",
                          fontWeight: 700,
                          letterSpacing: "0.04em",
                          "& .MuiChip-label": { px: 0.6 },
                        }}
                      />
                    )}
                    <TextField
                      size="small"
                      value={termDrafts[i] ?? e.text}
                      onChange={(event) => setTermDrafts((prev) => ({ ...prev, [i]: event.target.value }))}
                      onBlur={() => void handleCommitEntityTerm(i)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          (event.currentTarget.querySelector("input") as HTMLInputElement | null)?.blur();
                        }
                      }}
                      disabled={saving}
                      sx={{
                        flex: 1,
                        "& .MuiInputBase-input": { py: 0.4, fontSize: "0.875rem", fontWeight: 500 },
                      }}
                    />
                    <TextField
                      select
                      size="small"
                      value={coerceEntitySemanticLabel(e.label)}
                      onChange={(event) => handleUpdateEntityType(i, event.target.value)}
                      disabled={saving}
                      sx={{
                        minWidth: 128,
                        "& .MuiInputBase-input": { py: 0.4, fontSize: "0.73rem", fontWeight: 600, color: "primary.main" },
                      }}
                    >
                      {ENTITY_LABEL_OPTIONS.map((option) => (
                        <MenuItem key={option} value={option}>{option}</MenuItem>
                      ))}
                    </TextField>
                    <TextField
                      select
                      size="small"
                      value={(e.assertion ?? "present").toLowerCase()}
                      onChange={(event) => handleUpdateEntityAssertion(i, event.target.value)}
                      disabled={saving}
                      sx={{
                        minWidth: 110,
                        "& .MuiInputBase-input": { py: 0.4, fontSize: "0.73rem", fontWeight: 600 },
                      }}
                    >
                      {ASSERTION_OPTIONS.map((option) => (
                        <MenuItem key={option} value={option}>{formatAssertion(option)}</MenuItem>
                      ))}
                    </TextField>
                    {allowBodySite && (
                      <TextField
                        select
                        size="small"
                        SelectProps={{ multiple: true }}
                        value={selectedSiteValues}
                        onChange={(event) =>
                          handleUpdateEntityBodySite(
                            i,
                            event.target.value as unknown as string | string[],
                          )
                        }
                        disabled={saving}
                        placeholder="Body sites"
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <LinkIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                            </InputAdornment>
                          ),
                        }}
                        sx={{
                          minWidth: 150,
                          "& .MuiInputBase-input": { py: 0.4, fontSize: "0.73rem" },
                        }}
                      >
                        <MenuItem value="" disabled>
                          <em>No linked site</em>
                        </MenuItem>
                        {siteOptions.map(({ candidate, candidateIdx, relationType }) => (
                          <MenuItem key={`${relationType}-${candidateIdx}`} value={String(candidateIdx)}>
                            {candidate.text}
                            {relationType !== "finding_site" && (
                              <Typography
                                component="span"
                                variant="caption"
                                sx={{ ml: 0.75, color: "text.secondary" }}
                              >
                                ({relationType.replace(/_/g, "\u00a0")})
                              </Typography>
                            )}
                          </MenuItem>
                        ))}
                      </TextField>
                    )}
                    <Stack direction="row" spacing={0.125}>
                      {hasSnomed && (
                        <Tooltip title={domainLoaded ? (domainCount > 0 ? `In ${domainCount} domain${domainCount === 1 ? "" : "s"} - click to manage` : "Not in any domain yet - click to add") : "Check domains"}>
                          <span>
                            <IconButton
                              size="small"
                              color={domainLoaded && domainCount > 0 ? "success" : "default"}
                              disabled={saving}
                              onClick={(ev) => void handleOpenDomainPopover(ev.currentTarget, e.snomed_concept_id!, e.snomed_term ?? e.text)}
                              sx={{ p: 0.4 }}
                            >
                              {domainLoaded && domainCount > 0 ? <BookmarkIcon sx={{ fontSize: 16 }} /> : <BookmarkBorderIcon sx={{ fontSize: 16 }} />}
                            </IconButton>
                          </span>
                        </Tooltip>
                      )}
                      <Tooltip title={hasSnomed ? "Fix the code" : "Find a code"}>
                        <span>
                          <IconButton
                            size="small"
                            color={hasSnomed ? "default" : "warning"}
                            disabled={saving || suppressingIndex !== null}
                            onClick={() => setLookupTarget({ entityIndex: i, entityText: e.text, entityLabel: e.label ?? e.semantic_tag ?? "" })}
                            sx={{ p: 0.4 }}
                          >
                            <SearchIcon sx={{ fontSize: 16 }} />
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Tooltip title="Ignore this term in future runs">
                        <span>
                          <IconButton
                            size="small"
                            color="default"
                            disabled={saving || suppressingIndex !== null}
                            onClick={() => void handleSuppressEntity(i)}
                            sx={{ p: 0.4, opacity: 0.55, "&:hover": { opacity: 1 } }}
                          >
                            {suppressingIndex === i ? <CircularProgress size={14} /> : <NotInterestedIcon sx={{ fontSize: 15 }} />}
                          </IconButton>
                        </span>
                      </Tooltip>
                      <Tooltip title="Remove this term">
                        <span>
                          <IconButton
                            size="small"
                            color="error"
                            disabled={saving || suppressingIndex !== null}
                            onClick={() => handleRemoveEntity(i)}
                            sx={{ p: 0.4 }}
                          >
                            <DeleteOutlineIcon sx={{ fontSize: 16 }} />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </Stack>
                  </Stack>
                  {!!selectedSiteValues.length && canHaveBodySite(e) && (
                    <Stack
                      direction="column"
                      alignItems="center"
                      spacing={0.5}
                      sx={{ mt: 0.5, pl: 0.5, alignItems: "flex-start" }}
                    >
                      {selectedSiteValues.map((value) => {
                        const siteIdx = Number(value);
                        const site = entities[siteIdx];
                        if (!site) return null;
                        return (
                          <Stack key={`${i}-${siteIdx}`} direction="row" alignItems="center" spacing={0.5}>
                            <LinkIcon sx={{ fontSize: 14, color: "info.main" }} />
                            <Typography variant="caption" sx={{ color: "info.dark", fontWeight: 600 }}>
                              Linked site
                            </Typography>
                            <ArrowRightAltIcon sx={{ fontSize: 15, color: "info.main" }} />
                            <Typography variant="caption" sx={{ color: "text.primary" }}>
                              {site.snomed_term ?? site.text}
                            </Typography>
                          </Stack>
                        );
                      })}
                    </Stack>
                  )}

                  {/* Row 2: SNOMED status + surface form synonym */}
                  <Box sx={{ mt: 0.5, pl: 0.5 }}>
                    {hasSnomed ? (() => {
                      const key = sfKey(e);
                      const sfStatus = sfStatusMap[key];
                      const sfLoaded = key in sfStatusMap;
                      return (
                      <Box>
                        <Stack direction="row" alignItems="center" spacing={0.5} flexWrap="wrap">
                          <Typography variant="caption" sx={{ color: "success.dark", fontWeight: 500 }}>
                            {e.snomed_term}
                            <Box component="span" sx={{ fontFamily: "monospace", color: "text.disabled", ml: 0.75, fontWeight: 400 }}>
                              {e.snomed_concept_id}
                            </Box>
                          </Typography>
                          <Tooltip title={copiedKey === `snomed-${i}` ? "Copied!" : "Copy code"}>
                            <IconButton
                              size="small"
                              onClick={() => copyToClipboard(e.snomed_concept_id!, `snomed-${i}`)}
                              sx={{ p: 0.25, color: copiedKey === `snomed-${i}` ? "success.main" : "text.disabled" }}
                            >
                              <ContentCopyIcon sx={{ fontSize: 12 }} />
                            </IconButton>
                          </Tooltip>
                          {/* Surface form status + actions */}
                          {!sfLoaded ? (
                            <Box sx={{ width: 14, height: 14, display: "flex", alignItems: "center" }}>
                              <CircularProgress size={10} sx={{ color: "text.disabled" }} />
                            </Box>
                          ) : sfStatus ? (
                            // Already registered — offer synonym
                            <>
                              <Chip
                                size="small"
                                label="Surface form matched"
                                color="success"
                                variant="outlined"
                                sx={{ height: 18, fontSize: "0.62rem", fontWeight: 600, color: "success.dark", borderColor: "success.light", cursor: "default", "& .MuiChip-label": { px: 0.75 } }}
                              />
                              <Tooltip title={sfExpandedIdx === i ? "Cancel" : "Register another way this term can be written"}>
                                <Button
                                  size="small"
                                  onClick={() => setSfExpandedIdx((prev) => (prev === i ? null : i))}
                                  sx={{ fontSize: "0.65rem", px: 0.75, py: 0.1, minWidth: 0, color: sfExpandedIdx === i ? "text.disabled" : "primary.main", textDecoration: "underline", textDecorationStyle: "dotted", textUnderlineOffset: 2 }}
                                >
                                  {sfExpandedIdx === i ? "cancel" : "+ add synonym"}
                                </Button>
                              </Tooltip>
                            </>
                          ) : (
                            // Not registered yet — one-click register, no typing needed
                            <>
                              <Tooltip title={`"${e.text}" has no surface form yet. Click to register it now.`}>
                                <Button
                                  size="small"
                                  variant="outlined"
                                  color="warning"
                                  disabled={sfSaving === i}
                                  onClick={async () => {
                                    setSfSaving(i);
                                    try {
                                      await upsertSurfaceFormMapping(
                                        e.text.toLowerCase().trim(),
                                        e.text.trim(),
                                        e.snomed_concept_id!,
                                        { provenance: "manual_correction", source: "gold_label_editor" },
                                      );
                                      refreshSfStatus(e, true);
                                      setSfMsg((prev) => ({ ...prev, [i]: "Registered." }));
                                      setTimeout(() => setSfMsg((prev) => { const n = { ...prev }; delete n[i]; return n; }), 2000);
                                    } catch {
                                      setSfMsg((prev) => ({ ...prev, [i]: "Could not save." }));
                                    } finally {
                                      setSfSaving(null);
                                    }
                                  }}
                                  sx={{ height: 18, fontSize: "0.62rem", px: 0.75, py: 0, minWidth: 0 }}
                                >
                                  {sfSaving === i ? <CircularProgress size={10} color="inherit" /> : "Register this term"}
                                </Button>
                              </Tooltip>
                              <Tooltip title="Register a different text variant instead">
                                <Button
                                  size="small"
                                  onClick={() => setSfExpandedIdx((prev) => (prev === i ? null : i))}
                                  sx={{ fontSize: "0.65rem", px: 0.5, py: 0.1, minWidth: 0, color: "text.disabled", textDecoration: "underline", textDecorationStyle: "dotted", textUnderlineOffset: 2 }}
                                >
                                  {sfExpandedIdx === i ? "cancel" : "different text?"}
                                </Button>
                              </Tooltip>
                            </>
                          )}
                          {sfMsg[i] && (
                            <Typography variant="caption" sx={{ color: sfMsg[i] === "Could not save." ? "error.main" : "success.main", fontSize: "0.68rem" }}>
                              {sfMsg[i]}
                            </Typography>
                          )}
                        </Stack>
                        {sfExpandedIdx === i && (
                          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
                            <TextField
                              size="small"
                              autoFocus
                              placeholder={sfStatus ? `Another way to write "${e.text}" e.g. abbreviation or synonym` : `Type the text to register e.g. abbreviation of "${e.text}"`}
                              value={sfDrafts[i] ?? ""}
                              onChange={(ev) => setSfDrafts((prev) => ({ ...prev, [i]: ev.target.value }))}
                              onKeyDown={(ev) => {
                                if (ev.key === "Enter" && sfDrafts[i]?.trim()) {
                                  void saveSurfaceFormSynonym(i, e.snomed_concept_id!);
                                }
                                if (ev.key === "Escape") setSfExpandedIdx(null);
                              }}
                              disabled={sfSaving === i}
                              sx={{ flex: 1, "& .MuiInputBase-input": { py: 0.35, fontSize: "0.78rem" } }}
                            />
                            <Button
                              size="small"
                              variant="contained"
                              color="primary"
                              disabled={sfSaving === i || !sfDrafts[i]?.trim()}
                              onClick={() => void saveSurfaceFormSynonym(i, e.snomed_concept_id!)}
                              sx={{ height: 26, fontSize: "0.72rem", px: 1.25, flexShrink: 0 }}
                            >
                              {sfSaving === i ? <CircularProgress size={11} color="inherit" /> : "Save"}
                            </Button>
                          </Stack>
                        )}
                      </Box>
                    );
                    })() : suggestion === null ? (
                      <Typography variant="caption" color="text.disabled" sx={{ fontStyle: "italic" }}>
                        No match found. Use the search button above to find a code.
                      </Typography>
                    ) : suggestion ? (
                      <Stack direction="row" spacing={0.75} alignItems="center">
                        <Typography variant="caption" sx={{ color: "warning.dark", fontWeight: 500 }}>
                          Suggested: {suggestion.term}
                          <Box component="span" sx={{ fontFamily: "monospace", color: "text.disabled", ml: 0.75, fontWeight: 400 }}>
                            {suggestion.snomed_concept_id}
                          </Box>
                        </Typography>
                        <Button
                          size="small"
                          color="success"
                          variant="contained"
                          disabled={saving}
                          onClick={() => void handleAcceptSuggestion(i)}
                          sx={{ height: 20, fontSize: "0.68rem", px: 1, minWidth: 0 }}
                        >
                          Accept
                        </Button>
                        <IconButton size="small" onClick={() => handleDismissSuggestion(i)} sx={{ p: 0.25 }}>
                          <CloseIcon sx={{ fontSize: 13 }} />
                        </IconButton>
                      </Stack>
                    ) : searchingAll ? (
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <CircularProgress size={10} />
                        <Typography variant="caption" color="text.secondary">Looking for a code...</Typography>
                      </Stack>
                    ) : (
                      <Typography variant="caption" sx={{ color: "error.main", fontStyle: "italic" }}>
                        No code yet - click the search button to find one
                      </Typography>
                    )}
                  </Box>
                </Box>
              );
            })}
          </Box>

          {/* Add a missing term */}
          <Box
            sx={{
              border: "1px dashed",
              borderColor: "divider",
              borderRadius: 1.5,
              px: 1.5,
              py: 1,
              mb: 1.5,
              bgcolor: "action.hover",
            }}
          >
            <Typography variant="overline" color="text.secondary" sx={{ fontSize: "0.65rem", lineHeight: 1, display: "block", mb: 0.75 }}>
              Add a missing term
            </Typography>
            <Stack direction={{ xs: "column", md: "row" }} spacing={0.75} alignItems={{ md: "center" }} useFlexGap>
              <TextField
                value={newEntityText}
                onChange={(event) => setNewEntityText(event.target.value)}
                size="small"
                fullWidth
                placeholder="Type or highlight text above to add a term"
                disabled={saving}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && newEntityText.trim()) {
                    handleAddEntity();
                  }
                }}
                sx={{
                  "& .MuiInputBase-input": { py: 0.5 },
                  "& .MuiOutlinedInput-root": selectionAdded
                    ? { "& fieldset": { borderColor: "success.main" } }
                    : {},
                }}
                slotProps={{ input: { inputRef: addTermInputRef } }}
              />
              <TextField
                select
                size="small"
                value={newEntityLabel}
                onChange={(event) => setNewEntityLabel(event.target.value as EntitySemanticLabel)}
                disabled={saving}
                sx={{ minWidth: 128, flexShrink: 0, "& .MuiInputBase-input": { py: 0.5, fontSize: "0.73rem" } }}
              >
                {ENTITY_LABEL_OPTIONS.map((option) => (
                  <MenuItem key={option} value={option}>{option}</MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                value={newEntityAssertion}
                onChange={(event) => setNewEntityAssertion(event.target.value as (typeof ASSERTION_OPTIONS)[number])}
                disabled={saving}
                sx={{ minWidth: 110, flexShrink: 0, "& .MuiInputBase-input": { py: 0.5, fontSize: "0.73rem" } }}
              >
                {ASSERTION_OPTIONS.map((option) => (
                  <MenuItem key={option} value={option}>{formatAssertion(option)}</MenuItem>
                ))}
              </TextField>
              <Button
                variant="outlined"
                size="small"
                onClick={handleAddEntity}
                disabled={saving || !newEntityText.trim()}
                sx={{ flexShrink: 0, height: 32 }}
              >
                Add
              </Button>
            </Stack>
          </Box>

          {/* Compact metadata footer */}
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ pt: 1, borderTop: "1px solid", borderColor: "divider", flexWrap: "wrap" }}>
            <Chip
              icon={<VerifiedIcon sx={{ fontSize: "12px !important" }} />}
              label={item.quality_score !== null ? `${Math.round(item.quality_score * 100)}% quality` : "Unscored"}
              color={qualityColor(item.quality_score)}
              size="small"
              sx={{ fontWeight: 600, height: 22, fontSize: "0.7rem" }}
            />
            {item.verified_by && (
              <Typography variant="caption" color="text.secondary">{item.verified_by.split("@")[0]}</Typography>
            )}
            {item.verified_at && (
              <Typography variant="caption" color="text.disabled">{formatDate(item.verified_at)}</Typography>
            )}
            <Box sx={{ flex: 1 }} />
            <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.65rem" }}>
              Press ? for keyboard shortcuts
            </Typography>
          </Stack>
        </DialogContent>
        {showDeleteConfirm && onDeleteCandidate && (
          <DeleteConfirmPanel
            suppressOnDelete={suppressOnDelete}
            onSuppressChange={setSuppressOnDelete}
            onCancel={() => {
              setShowDeleteConfirm(false);
              setSuppressOnDelete(false);
            }}
            onConfirm={() => {
              setShowDeleteConfirm(false);
              onDeleteCandidate(suppressOnDelete);
            }}
          />
        )}

        <DialogActionsBar
          saving={saving}
          markingGold={Boolean(markingGold)}
          pendingSuggestionCount={canAcceptAllAndMark ? uncodedCount : 0}
          canMarkGold={Boolean(onMarkGold)}
          canDelete={Boolean(onDeleteCandidate) && !showDeleteConfirm}
          canSkip={Boolean(onNextCandidate)}
          onMarkGold={() => void flushTermDraftsAndMarkGold()}
          onAcceptAllAndMark={async () => {
            await handleAcceptAllSuggestions();
            await flushTermDraftsAndMarkGold();
          }}
          onSkipNext={() => onNextCandidate?.()}
          onRequestDelete={() => setShowDeleteConfirm(true)}
        />
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
        <SnomedInlineSearch
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
// Skeleton list
// ---------------------------------------------------------------------------

function SkeletonList() {
  return (
    <>
      {[0, 1, 2, 3, 4].map((i) => (
        <Skeleton key={i} variant="rounded" height={64} sx={{ mb: 0.75 }} />
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
  const [entityLabelFilter, setEntityLabelFilter] = useState<string | null>(null);

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
  const [similarDialogOpen, setSimilarDialogOpen] = useState(false);
  const [similarCandidates, setSimilarCandidates] = useState<SimilarCandidateItem[]>([]);
  const [similarSelected, setSimilarSelected] = useState<Record<string, boolean>>({});
  const [similarApplying, setSimilarApplying] = useState(false);
  const [sourceEntityCount, setSourceEntityCount] = useState<number>(0);
  const [similarReviewedIds, setSimilarReviewedIds] = useState<Set<string>>(new Set());
  const [loadingReviewId, setLoadingReviewId] = useState<string | null>(null);
  const [similarCandidateLabel, setSimilarCandidateLabel] = useState<GoldLabel | null>(null);
  const [pendingNextCandidateId, setPendingNextCandidateId] = useState<string | null>(null);
  const [pruneDialogOpen, setPruneDialogOpen] = useState(false);
  const [aiFirstPassDialogOpen, setAiFirstPassDialogOpen] = useState(false);
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
  const [healthRefreshKey, setHealthRefreshKey] = useState(0);
  const [annotationGuidelines, setAnnotationGuidelines] = useState<string>("");
  const [annotationGuidelinesError, setAnnotationGuidelinesError] = useState<string | null>(
    null,
  );

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const deepLinkLabelId = searchParams?.get("labelId") ?? null;
  const deepLinkFrom = searchParams?.get("from") ?? null;
  const handledDeepLinkRef = useRef<string | null>(null);

  useEffect(() => {
    if (deepLinkFrom === "dry_run") {
      setTab("candidates");
    }
  }, [deepLinkFrom]);

  useEffect(() => {
    if (!deepLinkLabelId) return;
    if (handledDeepLinkRef.current === deepLinkLabelId) return;
    handledDeepLinkRef.current = deepLinkLabelId;

    const inMemory = items.find(
      (it): it is GoldLabel => "label_id" in it && it.label_id === deepLinkLabelId,
    );
    const open = (record: GoldLabel) => {
      setSelectedItem(record);
      const basePath = pathname ?? "/admin/knowledge?tab=training-data";
      router.replace(basePath, { scroll: false });
    };
    if (inMemory) {
      open(inMemory);
      return;
    }
    fetchGoldLabel(deepLinkLabelId)
      .then((rec) => open(rec as unknown as GoldLabel))
      .catch(() => {
        handledDeepLinkRef.current = null;
      });
  }, [deepLinkLabelId, items, pathname, router]);

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

  useEffect(() => {
    let cancelled = false;
    jsonFetch<AnnotationGuidelinesResponse>("/api/training/annotation-guidelines")
      .then((payload) => {
        if (cancelled) return;
        setAnnotationGuidelines(String(payload.guidelines || "").trim());
      })
      .catch((err) => {
        if (cancelled) return;
        setAnnotationGuidelinesError(
          err instanceof Error ? err.message : "Could not load annotation guidelines",
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
      if (tab === "candidates") {
        const url = `/api/training/candidates?page=${page}&page_size=${PAGE_SIZE}&exclude_completed=true${debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ""}`;
        const data = await jsonFetch<{ items: Candidate[]; total: number }>(url);
        setItems(data.items);
        setTotal(data.total);
      } else if (tab === "gold") {
        const labelParam = entityLabelFilter ? `&entity_label=${encodeURIComponent(entityLabelFilter)}` : "";
        const url = `/api/training/gold-labels?page=${page}&page_size=${PAGE_SIZE}${debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ""}${labelParam}`;
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
  }, [tab, page, debouncedSearch, entityLabelFilter]);

  // Background refresh — same fetch as loadList but never sets listLoading so the
  // list behind an open dialog does not flash skeleton state on every entity edit.
  const silentRefreshList = useCallback(async () => {
    try {
      if (tab === "candidates") {
        const url = `/api/training/candidates?page=${page}&page_size=${PAGE_SIZE}&exclude_completed=true${debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ""}`;
        const data = await jsonFetch<{ items: Candidate[]; total: number }>(url);
        setItems(data.items);
        setTotal(data.total);
      } else if (tab === "gold") {
        const labelParam = entityLabelFilter ? `&entity_label=${encodeURIComponent(entityLabelFilter)}` : "";
        const url = `/api/training/gold-labels?page=${page}&page_size=${PAGE_SIZE}${debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ""}${labelParam}`;
        const data = await jsonFetch<{ items: GoldLabel[]; total: number }>(url);
        setItems(data.items);
        setTotal(data.total);
      } else {
        const url = `/api/training/gold-labels?page=${page}&page_size=${PAGE_SIZE}&source=synthetic_llm${debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : ""}`;
        const data = await jsonFetch<{ items: GoldLabel[]; total: number }>(url);
        setItems(data.items);
        setTotal(data.total);
      }
    } catch {
      // silent — list stays stale rather than showing an error banner mid-edit
    }
    // Nudge the health panel to re-check span mismatches after any edit.
    setHealthRefreshKey((k) => k + 1);
  }, [tab, page, debouncedSearch, entityLabelFilter]);

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
    if (val !== "gold") setEntityLabelFilter(null);
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

  function removeCandidateFromDedupePreview(candidateId: string) {
    setDedupePreview((prev) => {
      if (!prev) return prev;
      const updatedGroups = prev.groups
        .map((group) => ({
          ...group,
          duplicates: group.duplicates.filter((d) => d.candidate_id !== candidateId),
        }))
        .filter((group) => group.duplicates.length > 0);
      const newDuplicateCount = updatedGroups.reduce(
        (sum, g) => sum + g.duplicates.length,
        0,
      );
      return {
        ...prev,
        groups: updatedGroups,
        group_count: updatedGroups.length,
        duplicate_count: newDuplicateCount,
        candidate_pool_size: Math.max(0, prev.candidate_pool_size - 1),
      };
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
      removeCandidateFromDedupePreview(candidateId);
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

  function flushPendingNextCandidate() {
    setPendingNextCandidateId((pending) => {
      if (pending) void openCandidateLabelEditor(pending);
      return null;
    });
  }

  function getNextCandidateId(afterCandidateId: string): string | null {
    const rows = items as Candidate[];
    const index = rows.findIndex((row) => row.candidate_id === afterCandidateId);
    if (index < 0) return null;
    return rows.slice(index + 1).find((row) => row.status !== "completed")?.candidate_id ?? null;
  }

  function openNextCandidate(afterCandidateId: string) {
    const nextId = getNextCandidateId(afterCandidateId);
    if (nextId) void openCandidateLabelEditor(nextId);
  }

  async function findSimilarCandidates(
    candidateId: string,
    sourceEntitiesJson: string | null = null,
  ): Promise<boolean> {
    try {
      const response = await jsonFetch<SimilarCandidatesResponse>(
        "/api/training/candidates/find-similar-by-entity",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ candidate_id: candidateId, limit: 20 }),
        },
      );
      if (!response.items?.length) return false;

      // Count entities on the source candidate so we can warn about mismatches.
      const srcEntities = parseEntities(sourceEntitiesJson ?? candidateGoldLabel?.entities_json ?? null);
      const srcCount = srcEntities.length;
      setSourceEntityCount(srcCount);

      // Default-untick candidates whose entity count differs from the source.
      const selected: Record<string, boolean> = {};
      for (const item of response.items) {
        const itemCount = parseEntities(item.entities_json).length;
        selected[item.candidate_id] = itemCount === srcCount;
      }
      setSimilarCandidates(response.items);
      setSimilarSelected(selected);
      setSimilarDialogOpen(true);
      return true;
    } catch {
      // Non-blocking helper -- user still completed the current candidate.
      return false;
    }
  }

  async function handleReviewSimilarCandidate(candidateId: string) {
    setLoadingReviewId(candidateId);
    try {
      const label = await jsonFetch<GoldLabel>(
        `/api/training/gold-labels/by-candidate/${encodeURIComponent(candidateId)}/ensure`,
        { method: "POST" },
      );
      setSimilarCandidateLabel(label);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Could not open candidate editor.");
    } finally {
      setLoadingReviewId(null);
    }
  }

  async function markSimilarCandidateAsGold(candidateId: string) {
    if (!candidateId) return;
    try {
      await jsonFetch<{ candidate_id: string; status: string }>(
        `/api/training/candidates/${encodeURIComponent(candidateId)}/mark-completed`,
        { method: "POST" },
      );
      setSimilarReviewedIds((prev) => new Set([...prev, candidateId]));
      await Promise.all([loadList(), loadStats()]);
    } catch (e) {
      // Dialog already closed optimistically; surface error in the list.
      setListError(e instanceof Error ? e.message : "Could not mark candidate as gold.");
    }
  }

  async function applySimilarSelections() {
    // Exclude candidates already individually reviewed and marked gold.
    const selectedIds = similarCandidates
      .filter(
        (row) =>
          Boolean(similarSelected[row.candidate_id]) &&
          !similarReviewedIds.has(row.candidate_id),
      )
      .map((row) => row.candidate_id)
      .filter(Boolean);
    if (!selectedIds.length) {
      setSimilarDialogOpen(false);
      setSimilarReviewedIds(new Set());
      return;
    }
    setSimilarApplying(true);
    try {
      await Promise.all(
        selectedIds.map(async (candidateId) => {
          // Ensure a gold label exists (created from candidate entities) before marking completed.
          await jsonFetch<{ label_id: string }>(
            `/api/training/gold-labels/by-candidate/${encodeURIComponent(candidateId)}/ensure`,
            { method: "POST" },
          );
          await jsonFetch<{ candidate_id: string; status: string }>(
            `/api/training/candidates/${encodeURIComponent(candidateId)}/mark-completed`,
            { method: "POST" },
          );
        }),
      );
      const totalAccepted = selectedIds.length + similarReviewedIds.size;
      setActionMsg(`Marked ${totalAccepted} similar candidate(s) as gold.`);
      setSimilarDialogOpen(false);
      setSimilarCandidates([]);
      setSimilarSelected({});
      setSimilarReviewedIds(new Set());
      flushPendingNextCandidate();
      await Promise.all([loadList(), loadStats()]);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Could not apply similar updates");
      setSimilarDialogOpen(false);
      setSimilarReviewedIds(new Set());
      flushPendingNextCandidate();
    } finally {
      setSimilarApplying(false);
    }
  }

  async function markCandidateAsGold(candidateId: string) {
    if (!candidateId || markingGoldCandidateId) return;
    setMarkingGoldCandidateId(candidateId);
    setActionMsg(null);
    setListError(null);
    // Capture entity JSON now -- candidateGoldLabel may be cleared before the
    // async findSimilarCandidates call resolves.
    const sourceEntitiesJson = candidateGoldLabel?.entities_json ?? null;
    try {
      await jsonFetch<{ candidate_id: string; status: string; gold_label_id: string | null }>(
        `/api/training/candidates/${encodeURIComponent(candidateId)}/mark-completed`,
        { method: "POST" },
      );
      setActionMsg("Saved as gold data. Candidate status updated to completed.");
      await Promise.all([loadList(), loadStats()]);
      const similarOpened = await findSimilarCandidates(candidateId, sourceEntitiesJson);
      if (similarOpened) {
        // Defer opening the next candidate until the similar dialog is dismissed.
        const nextId = getNextCandidateId(candidateId);
        if (nextId) setPendingNextCandidateId(nextId);
      } else {
        openNextCandidate(candidateId);
      }
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
    <Box sx={{ py: 2, px: 2 }}>

      {/* Header + toolbar (Wave E Phase 2) */}
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2, mb: 2, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>Training data review</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, fontSize: "0.82rem" }}>
            Check each sentence, fix any wrong codes, then mark it as gold.
          </Typography>
          {annotationGuidelinesError && (
            <Typography variant="caption" color="warning.main" sx={{ display: "block", mt: 0.5 }}>
              Annotation guide unavailable: {annotationGuidelinesError}
            </Typography>
          )}
        </Box>
        <ToolbarActions
          actions={(() => {
            const items: ToolbarAction[] = [];
            if (tab === "candidates") {
              items.push({
                id: "ai-first-pass",
                label: "AI first-pass",
                variant: "primary",
                onClick: () => setAiFirstPassDialogOpen(true),
              });
              items.push({
                id: "auto-prune",
                label: "Auto-prune low confidence",
                variant: "secondary",
                onClick: () => setPruneDialogOpen(true),
              });
              items.push({
                id: "deduplicate",
                label: "Deduplicate similar",
                variant: "secondary",
                onClick: () => {
                  setDedupeDialogOpen(true);
                  setDedupePreview(null);
                  setExpandedDedupeGroup(false);
                },
              });
            }
            items.push({
              id: "export",
              label: "Export training data",
              variant: "primary",
              loading: exporting,
              disabled: exporting || !goldStats || goldStats.total === 0,
              onClick: handleExport,
            });
            return items;
          })()}
        />
      </Box>

      {annotationGuidelines && (
        <Box sx={{ mb: 1.5 }}>
          <AnnotationGuidelinesPanel text={annotationGuidelines} defaultExpanded={false} />
        </Box>
      )}

      {/* Stats row (design-system StatHero with framer-motion stagger) */}
      {statsError && <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setStatsError(null)}>{statsError}</Alert>}
      {statsLoading ? (
        <Stack direction="row" spacing={1.25} sx={{ mb: 1.5 }} flexWrap="wrap" useFlexGap>
          {[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} variant="rounded" width={160} height={96} />)}
        </Stack>
      ) : (() => {
        const stats: DsStatTile[] = [
          { id: "received", label: "Received", value: candidateStats?.total ?? 0 },
          {
            id: "ready",
            label: "Ready for training",
            value: goldStats?.total ?? 0,
            tone: "positive",
          },
          {
            id: "failed",
            label: "Failed",
            value: candidateStats?.failed ?? 0,
            tone: (candidateStats?.failed ?? 0) > 0 ? "danger" : "neutral",
          },
          {
            id: "verified",
            label: "Verified gold",
            value: goldStats?.total ?? 0,
          },
          {
            id: "synthetic",
            label: "Synthetic gold",
            value: syntheticStats?.synthetic_gold_labels ?? 0,
          },
          {
            id: "quality",
            label: "Avg quality",
            value:
              goldStats?.avg_quality_score !== null && goldStats?.avg_quality_score !== undefined
                ? `${Math.round((goldStats.avg_quality_score ?? 0) * 100)}%`
                : "-",
            hint:
              goldStats && goldStats.total > 0 ? `${goldStats.high_quality} high quality` : undefined,
            tone:
              goldStats?.avg_quality_score !== null && goldStats?.avg_quality_score !== undefined
                ? goldStats.avg_quality_score >= 0.8
                  ? "positive"
                  : goldStats.avg_quality_score >= 0.5
                    ? "warning"
                    : "danger"
                : "neutral",
          },
        ];
        return <StatHero stats={stats} maxTiles={6} />;
      })()}

      {/* Progress strip (design-system ProgressStrip) */}
      {!statsLoading && tab === "candidates" && candidateStats && candidateStats.total > candidateStats.completed && (
        <Box sx={{ mb: 1.5 }}>
          <ProgressStrip
            label={`${candidateStats.total - candidateStats.completed} item${
              candidateStats.total - candidateStats.completed !== 1 ? "s" : ""
            } left to review`}
            value={candidateStats.completed}
            total={candidateStats.total}
            tone="positive"
          />
        </Box>
      )}

      {exportMsg && <Alert severity="success" sx={{ mb: 1.5 }} onClose={() => setExportMsg(null)}>{exportMsg}</Alert>}
      {actionMsg && <Alert severity="success" sx={{ mb: 1.5 }} onClose={() => setActionMsg(null)}>{actionMsg}</Alert>}

      {/* Segmented tabs (design-system SegmentedTabs with keyboard nav + pill styling) */}
      <Box sx={{ mb: 1.5 }}>
        <SegmentedTabs
          aria-label="Training data views"
          value={tab}
          onChange={(id) => handleTabChange({} as React.SyntheticEvent, id as typeof tab)}
          tabs={[
            {
              id: "candidates",
              label: "Candidates",
              count:
                candidateStats != null
                  ? candidateStats.total - candidateStats.completed
                  : undefined,
            },
            { id: "gold", label: "Verified gold", count: goldStats?.total },
            { id: "synthetic", label: "Synthetic", count: syntheticStats?.synthetic_gold_labels },
          ]}
        />
      </Box>

      {tab === "gold" && (
        <DatasetHealthPanel
          refreshKey={healthRefreshKey}
          activeLabel={entityLabelFilter}
          onLabelFilter={(label) => {
            setEntityLabelFilter(label);
            setPage(1);
          }}
          onOpenLabel={(labelId) => {
            // Try the in-memory list first; fall back to a direct API fetch
            // so records on other pages (or not yet loaded) still open.
            const inMemory = items.find(
              (it): it is GoldLabel => "label_id" in it && it.label_id === labelId,
            );
            if (inMemory) {
              setSelectedItem(inMemory);
              return;
            }
            fetchGoldLabel(labelId)
              .then((rec) => setSelectedItem(rec as unknown as GoldLabel))
              .catch(() => {/* silently ignore -- label may have been deleted */});
          }}
        />
      )}

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
            ? "Search by sentence text..."
            : tab === "synthetic"
              ? "Search synthetic examples..."
              : "Search verified examples..."
        }
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        fullWidth
        sx={{
          mb: 1.25,
          "& .MuiOutlinedInput-root": {
            borderRadius: 1.5,
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
      {listError && <Alert severity="error" sx={{ mb: 1.25 }} onClose={() => setListError(null)}>{listError}</Alert>}

      {listLoading ? (
        <SkeletonList />
      ) : items.length === 0 ? (
        <Box sx={{ py: 4, textAlign: "center" }}>
          <Typography color="text.secondary" variant="body2">
            {debouncedSearch
              ? `Nothing matches "${debouncedSearch}". Try different words.`
              : tab === "candidates"
                ? "No sentences to review yet. Run the pipeline to get started."
                : tab === "synthetic"
                  ? "No synthetic examples yet. Use the button above to create some."
                  : "No verified examples yet. Mark sentences as gold and they will show up here."}
          </Typography>
        </Box>
      ) : (
        <>
          {tab === "candidates"
            ? (
                <CandidateReviewList
                  items={items as Candidate[]}
                  onOpen={(id) => void openCandidateLabelEditor(id)}
                  onMarkGold={markCandidateAsGold}
                  onDelete={requestDeleteCandidate}
                  openingLabelId={openingCandidateLabelId}
                  markingGoldId={markingGoldCandidateId}
                  deletingId={deletingCandidateId}
                  search={debouncedSearch}
                />
              )
            : (
                <GoldLabelReviewList
                  items={(items as GoldLabel[]).filter((item) => item.label_id)}
                  onOpen={(item) => setSelectedItem(item)}
                  onReset={(item) => requestDeleteGoldLabel(item)}
                  resettingLabelId={resettingLabelId}
                  search={debouncedSearch}
                />
              )
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
          key={`gold-${(selectedItem as GoldLabel).label_id}`}
          item={selectedItem as GoldLabel}
          onClose={() => setSelectedItem(null)}
          onEntitiesChanged={() => void silentRefreshList()}
          annotationGuidelines={annotationGuidelines}
        />
      )}
      {selectedItem && tab === "synthetic" && (
        <GoldLabelDetailDialog
          key={`syn-${(selectedItem as GoldLabel).label_id}`}
          item={selectedItem as GoldLabel}
          onClose={() => setSelectedItem(null)}
          onEntitiesChanged={() => void silentRefreshList()}
          annotationGuidelines={annotationGuidelines}
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
          key={`cand-${candidateGoldLabel.label_id}-${candidateGoldLabel.candidate_id ?? ""}`}
          item={candidateGoldLabel}
          onClose={() => setCandidateGoldLabel(null)}
          onEntitiesChanged={() => void silentRefreshList()}
          annotationGuidelines={annotationGuidelines}
          onMarkGold={() => {
            setCandidateGoldLabel(null);
            void markCandidateAsGold(candidateGoldLabel.candidate_id ?? "");
          }}
          onNextCandidate={() =>
            openNextCandidate(candidateGoldLabel.candidate_id ?? "")
          }
          onDeleteCandidate={(suppressText) => {
            const id = candidateGoldLabel.candidate_id ?? "";
            const text = candidateGoldLabel.text ?? "";
            setCandidateGoldLabel(null);
            void handleDeleteCandidate(id, text, suppressText);
          }}
          markingGold={markingGoldCandidateId === candidateGoldLabel.candidate_id}
        />
      )}
      <SimilarCandidatesBatch
        open={similarDialogOpen}
        candidates={similarCandidates}
        selected={similarSelected}
        loading={similarApplying}
        sourceEntityCount={sourceEntityCount}
        reviewedIds={similarReviewedIds}
        loadingReviewId={loadingReviewId}
        search={debouncedSearch}
        onClose={() => {
          setSimilarDialogOpen(false);
          setSimilarCandidates([]);
          setSimilarSelected({});
          setSimilarReviewedIds(new Set());
          flushPendingNextCandidate();
        }}
        onToggle={(candidateId, checked) =>
          setSimilarSelected((prev) => ({ ...prev, [candidateId]: checked }))
        }
        onReviewCandidate={(candidateId) => void handleReviewSimilarCandidate(candidateId)}
        onApply={() => void applySimilarSelections()}
      />
      {similarCandidateLabel && (
        <GoldLabelDetailDialog
          key={`sim-${similarCandidateLabel.label_id}-${similarCandidateLabel.candidate_id ?? ""}`}
          item={similarCandidateLabel}
          onClose={() => setSimilarCandidateLabel(null)}
          onEntitiesChanged={() => void silentRefreshList()}
          annotationGuidelines={annotationGuidelines}
          onMarkGold={() => {
            const candidateId = similarCandidateLabel.candidate_id ?? "";
            setSimilarCandidateLabel(null);
            void markSimilarCandidateAsGold(candidateId);
          }}
        />
      )}
      <CandidatePruneDialog
        open={pruneDialogOpen}
        onClose={() => setPruneDialogOpen(false)}
        onPruned={() => {
          void Promise.all([loadList(), loadStats()]);
        }}
      />
      <AIFirstPassDialog
        open={aiFirstPassDialogOpen}
        onClose={() => setAiFirstPassDialogOpen(false)}
        onJobComplete={() => {
          void Promise.all([loadList(), loadStats()]);
        }}
      />
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
                                      <CircularProgress size={14} aria-label="Deleting" />
                                    ) : (
                                      <DeleteOutlineIcon fontSize="small" />
                                    )
                                  }
                                  disabled={deletingCandidateId === duplicate.candidate_id}
                                  onClick={() => requestDeleteCandidate(duplicate.candidate_id)}
                                >
                                  {deletingCandidateId === duplicate.candidate_id
                                    ? "Deleting..."
                                    : "Delete duplicate"}
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
