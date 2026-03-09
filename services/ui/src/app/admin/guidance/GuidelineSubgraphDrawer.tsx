"use client";

/**
 * GuidelineSubgraphDrawer
 *
 * Shows exactly what is stored in Neo4j for a given NICE guideline:
 * chapters, recommendations with their full verbatim text, and any rules.
 * Designed so admins can verify the graph content without opening Neo4j Browser.
 *
 * Data source: GET /api/nice/{code}/subgraph
 */

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import CloseIcon from "@mui/icons-material/Close";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import GavelIcon from "@mui/icons-material/Gavel";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import ScienceIcon from "@mui/icons-material/Science";
import TextSnippetIcon from "@mui/icons-material/TextSnippet";

// ── Types ─────────────────────────────────────────────────────────────────────

interface RuleEntry {
  rule_id: string;
  status: string;
  name: string;
  created_at: string;
}

interface RecEntry {
  rec_id: string;
  rec_title: string;
  verbatim: string;
  urgency: string;
  strength: string;
  /** Cancer site / topic label from the NICE section heading, e.g. "Lung cancer" */
  section_title: string;
  /** True = canonical numbered recommendation eligible for rule generation.
   *  False = cross-reference table entry (symptom/sign index) — NOT used for rules. */
  is_normative: boolean;
  version_id: string;
  rules: RuleEntry[];
}

interface ChapterEntry {
  chapter_id: string;
  chapter_title: string;
  order: number;
  recommendations: RecEntry[];
}

interface SubgraphData {
  guideline_id: string;
  guideline_title: string;
  ingest_version: number | null;
  publication_date: string;
  chapters: ChapterEntry[];
  totals: {
    chapters: number;
    recommendations: number;
    rules: number;
  };
}

interface Props {
  code: string | null;
  onClose: () => void;
}

// ── Extraction test types ─────────────────────────────────────────────────────

interface CriterionResult {
  node_id?: string;
  term: string;
  source_text?: string | null;
  snomed_concept_id: string | null;
  preferred_term: string;
  semantic_tag: string;
  verification_status?: string;
  verification_reason?: string;
}

interface ActionResult {
  term: string;
  snomed_concept_id: string | null;
  preferred_term: string;
  semantic_tag: string;
}

interface RawTerm {
  text: string;
  source_text?: string | null;
  search_terms?: string[];
}

interface LogicTreeRawNode {
  kind: string;
  node_id?: string;
  children?: LogicTreeRawNode[];
  min?: number;
  term?: RawTerm;
  field?: string;
  operator?: string;
  value?: number | string | null;
  unit?: string | null;
  raw_term?: string;
}

interface LogicTreeCodedNode {
  kind: string;
  node_id?: string;
  children?: LogicTreeCodedNode[];
  min?: number;
  criterion?: CriterionResult;
  field?: string;
  operator?: string;
  value?: number | string | null;
  unit?: string | null;
  raw_term?: string;
}

interface CodedCriteria {
  schema_version: number;
  logic_tree: LogicTreeCodedNode | null;
  action: ActionResult | null;
}

interface ExtractionTestResult {
  recommendation: {
    id: string;
    verbatim: string;
    guideline_id: string;
    chapter_title: string;
    section_title: string;
  };
  raw_criteria: { schema_version: number; logic_tree: LogicTreeRawNode | null; action: { text: string; search_terms?: string[] } | null } | null;
  coded_criteria: CodedCriteria | null;
  errors: string[];
  /** False when Terminology API failures mean this result would NOT be written
   *  to Neo4j by the rule generator (partial results only). */
  would_write?: boolean;
}

/** Keyed by rec_id — populated during a "Test All" run. */
type TestAllResults = Record<string, { result?: ExtractionTestResult; error?: string }>;

async function runExtractionTest(recId: string): Promise<ExtractionTestResult> {
  const encoded = encodeURIComponent(recId);
  const res = await fetch(`/api/guidance/rules/test/${encoded}`, { method: "POST" });

  // 422 = pipeline returned partial results (some terms failed) — parse body and
  // surface it in the UI with warnings rather than throwing and showing nothing.
  if (res.status === 422 || res.ok) {
    const body = await res.json().catch(() => null);
    if (body && (body.coded_criteria !== undefined || body.raw_criteria !== undefined)) {
      return body as ExtractionTestResult;
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? body?.errors?.[0] ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const URGENCY_LABEL: Record<string, string> = {
  urgent_2w: "2WW",
  immediate: "Immediate",
  very_urgent_48h: "48 h",
  urgent_1w: "1 wk",
  routine: "Routine",
};

const RULE_STATUS_COLOR: Record<string, "success" | "warning" | "error" | "default"> = {
  active: "success",
  pending_review: "warning",
  rejected: "error",
  superseded: "default",
};

function RuleChip({ rule }: { rule: RuleEntry }) {
  const color = RULE_STATUS_COLOR[rule.status] ?? "default";
  const icon =
    rule.status === "active" ? (
      <CheckCircleIcon sx={{ fontSize: 13 }} />
    ) : rule.status === "pending_review" ? (
      <HourglassEmptyIcon sx={{ fontSize: 13 }} />
    ) : (
      <GavelIcon sx={{ fontSize: 13 }} />
    );
  return (
    <Tooltip title={rule.name || rule.rule_id} arrow>
      <Chip
        icon={icon}
        label={rule.status.replace("_", " ")}
        size="small"
        color={color}
        variant="outlined"
        sx={{ height: 20, fontSize: "0.68rem", mr: 0.5, mb: 0.5 }}
      />
    </Tooltip>
  );
}

// ── Extraction test result panel ──────────────────────────────────────────────

function SnomedChip({ item }: { item: CriterionResult }) {
  const resolved = !!item.snomed_concept_id;
  return (
    <Tooltip
      title={
        resolved
          ? `SNOMED: ${item.snomed_concept_id} · ${item.semantic_tag}`
          : "Not resolved — no SNOMED match found"
      }
      arrow
    >
      <Chip
        label={resolved ? item.preferred_term : `⚠ ${item.term}`}
        size="small"
        color={resolved ? "success" : "warning"}
        variant={resolved ? "filled" : "outlined"}
        sx={{ height: 20, fontSize: "0.68rem", mr: 0.4, mb: 0.4 }}
      />
    </Tooltip>
  );
}

function LogicNodePanel({
  rawNode,
  codedNode,
  depth = 0,
}: {
  rawNode?: LogicTreeRawNode | null;
  codedNode?: LogicTreeCodedNode | null;
  depth?: number;
}) {
  const node = codedNode ?? rawNode;
  if (!node) return null;
  const kind = String(node.kind || "").toUpperCase();

  if (kind === "CONCEPT") {
    if (codedNode?.criterion) {
      return <SnomedChip item={codedNode.criterion} />;
    }
    const label = rawNode?.term?.text || "unknown concept";
    return (
      <Chip
        label={label}
        size="small"
        variant="outlined"
        color="primary"
        sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
      />
    );
  }

  if (kind === "DEMOGRAPHIC") {
    const label = `${node.field ?? "demographic"} ${node.operator ?? "="} ${node.value ?? "?"}${node.unit ? ` ${node.unit}` : ""}`;
    return (
      <Chip
        label={label}
        size="small"
        variant="filled"
        color="secondary"
        sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
      />
    );
  }

  const title =
    kind === "AND"
      ? "ALL of these"
      : kind === "OR"
      ? "ANY of these"
      : kind === "NOT"
      ? "NOT"
      : `AT LEAST ${node.min ?? 1}`;

  const rawChildren = rawNode?.children ?? [];
  const codedChildren = codedNode?.children ?? [];
  const childCount = Math.max(rawChildren.length, codedChildren.length);

  return (
    <Box sx={{ ml: depth ? 1.5 : 0, mt: 0.5, pl: 1, borderLeft: "2px solid", borderColor: "divider" }}>
      <Typography variant="caption" sx={{ fontWeight: 700, color: "text.secondary", display: "block", mb: 0.4 }}>
        {title}
      </Typography>
      <Box>
        {Array.from({ length: childCount }).map((_, idx) => (
          <LogicNodePanel
            key={`${node.node_id ?? kind}-${idx}`}
            rawNode={rawChildren[idx]}
            codedNode={codedChildren[idx]}
            depth={depth + 1}
          />
        ))}
      </Box>
    </Box>
  );
}

function ExtractionResultPanel({ result }: { result: ExtractionTestResult }) {
  const coded = result.coded_criteria;
  const raw = result.raw_criteria;

  return (
    <Box
      sx={{
        mt: 1,
        p: 1.5,
        bgcolor: "primary.50",
        border: "1px solid",
        borderColor: "primary.200",
        borderRadius: 1,
      }}
    >
      <Typography variant="caption" sx={{ fontWeight: 700, color: "primary.dark", display: "block", mb: 1 }}>
        AI Extraction Preview (dry run — nothing saved)
      </Typography>

      {result.errors.length > 0 && (() => {
        const hasApiFailure = result.errors.some((e) => e.includes("terminology_api_unavailable"));
        const hasHardFailure = result.errors.some((e) =>
          e.includes("prompt_missing") || e.includes("extraction_blocked") || e.includes("llm_error")
        );
        const severity = hasHardFailure ? "error" : hasApiFailure ? "warning" : "info";
        const prefix = hasHardFailure
          ? "Pipeline failure"
          : hasApiFailure
          ? result.would_write === false
            ? "Partial results — Terminology API unavailable for some terms. Rule would NOT be saved."
            : "Warning"
          : "Note";
        return (
          <Alert severity={severity} icon={<ErrorOutlineIcon fontSize="small" />} sx={{ mb: 1, py: 0.3, fontSize: "0.75rem" }}>
            <strong>{prefix}:</strong>{" "}
            {result.errors
              .map((e) => e.replace(/^terminology_api_unavailable:[^:]+:/, "Terminology API: "))
              .join(" · ")}
          </Alert>
        );
      })()}

      {!coded && !raw && (
        <Typography variant="body2" color="text.disabled" sx={{ fontSize: "0.78rem", fontStyle: "italic" }}>
          The AI could not extract clinical criteria from this recommendation.
        </Typography>
      )}

      {raw && (
        <>
          {raw.logic_tree && (
            <Box sx={{ mb: raw.action ? 1 : 0 }}>
              <Typography variant="caption" color="primary.dark" sx={{ fontWeight: 600, display: "block", mb: 0.3 }}>
                Exact rule logic
              </Typography>
              <LogicNodePanel rawNode={raw.logic_tree} codedNode={coded?.logic_tree ?? undefined} />
            </Box>
          )}

          {/* Recommended action */}
          {raw.action && (
            <Box>
              <Typography variant="caption" color="info.dark" sx={{ fontWeight: 600, display: "block", mb: 0.3 }}>
                Recommended action
              </Typography>
              {coded?.action ? (
                <SnomedChip item={{ term: coded.action.term, snomed_concept_id: coded.action.snomed_concept_id, preferred_term: coded.action.preferred_term, semantic_tag: coded.action.semantic_tag }} />
              ) : (
                <Chip label={raw.action.text} size="small" variant="outlined" color="info" sx={{ fontSize: "0.68rem", height: 20 }} />
              )}
            </Box>
          )}
        </>
      )}
    </Box>
  );
}

// ── Recommendation row ────────────────────────────────────────────────────────

interface RecommendationRowProps {
  rec: RecEntry;
  /** Result pushed from a "Test All" run in the parent. */
  externalResult?: ExtractionTestResult | null;
  externalError?: string | null;
  externalTesting?: boolean;
}

function RecommendationRow({ rec, externalResult, externalError, externalTesting }: RecommendationRowProps) {
  const [open, setOpen] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ExtractionTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  // Auto-expand when an external result arrives
  useEffect(() => {
    if (externalResult || externalError) setOpen(true);
  }, [externalResult, externalError]);

  const hasText = rec.verbatim && rec.verbatim.trim().length > 0;
  const preview = rec.verbatim ? rec.verbatim.slice(0, 120) : "(no text stored)";
  const borderColor = rec.is_normative ? "grey.200" : "warning.light";

  // Merge individual and external state — individual run takes precedence if active
  const displayResult = testResult ?? externalResult ?? null;
  const displayError = testError ?? externalError ?? null;
  const displayTesting = testing || (!testResult && !testError && !!externalTesting);

  async function handleTest(e: React.MouseEvent) {
    e.stopPropagation();
    setTesting(true);
    setTestResult(null);
    setTestError(null);
    setOpen(true);
    try {
      const result = await runExtractionTest(rec.rec_id);
      setTestResult(result);
    } catch (err) {
      setTestError(err instanceof Error ? err.message : String(err));
    } finally {
      setTesting(false);
    }
  }

  return (
    <Box sx={{ borderLeft: "2px solid", borderColor, pl: 1.5, mb: 0.5 }}>
      <Stack direction="row" alignItems="flex-start" spacing={0.5}>
        {/* Expand toggle */}
        <Box
          sx={{ cursor: hasText ? "pointer" : "default", display: "flex", alignItems: "flex-start", pt: 0.3 }}
          onClick={() => hasText && setOpen((o) => !o)}
        >
          {hasText ? (
            open ? (
              <ExpandMoreIcon sx={{ fontSize: 16, color: "text.secondary", flexShrink: 0 }} />
            ) : (
              <ChevronRightIcon sx={{ fontSize: 16, color: "text.secondary", flexShrink: 0 }} />
            )
          ) : (
            <Box sx={{ width: 16, flexShrink: 0 }} />
          )}
        </Box>

        <Box sx={{ flex: 1, minWidth: 0 }} onClick={() => hasText && setOpen((o) => !o)} style={{ cursor: hasText ? "pointer" : "default" }}>
          <Stack direction="row" spacing={0.8} alignItems="center" flexWrap="wrap">
            {rec.rec_title && (
              <Typography
                variant="caption"
                sx={{ fontWeight: 700, color: "primary.main", fontFamily: "monospace" }}
              >
                {rec.rec_title}
              </Typography>
            )}
            {!rec.is_normative && (
              <Tooltip title="Cross-reference table entry — not used for rule generation" arrow>
                <Chip
                  label="cross-ref"
                  size="small"
                  color="warning"
                  variant="filled"
                  sx={{ height: 16, fontSize: "0.60rem" }}
                />
              </Tooltip>
            )}
            {rec.urgency && URGENCY_LABEL[rec.urgency] && (
              <Chip
                label={URGENCY_LABEL[rec.urgency]}
                size="small"
                color="warning"
                variant="outlined"
                sx={{ height: 16, fontSize: "0.62rem" }}
              />
            )}
            {rec.strength && rec.strength !== "unspecified" && (
              <Chip
                label={rec.strength}
                size="small"
                variant="outlined"
                sx={{ height: 16, fontSize: "0.62rem" }}
              />
            )}
          </Stack>

          {/* Preview text */}
          <Typography
            variant="body2"
            sx={{
              fontSize: "0.78rem",
              color: hasText ? "text.primary" : "text.disabled",
              fontStyle: hasText ? "normal" : "italic",
              mt: 0.2,
            }}
          >
            {preview}
            {rec.verbatim && rec.verbatim.length > 120 && !open ? "…" : ""}
          </Typography>

          {/* Rules */}
          {rec.rules.length > 0 && (
            <Box sx={{ mt: 0.4 }}>
              {rec.rules.map((r) => (
                <RuleChip key={r.rule_id} rule={r} />
              ))}
            </Box>
          )}
        </Box>

        {/* Test button — only on canonical normative recs that have text */}
        {rec.is_normative && hasText && (
          <Tooltip title="Test rule extraction (AI dry run)" arrow>
            <span>
              <IconButton
                size="small"
                onClick={handleTest}
                disabled={testing}
                sx={{ color: "primary.main", flexShrink: 0, mt: 0.1 }}
              >
                {testing ? (
                  <CircularProgress size={14} />
                ) : (
                  <ScienceIcon sx={{ fontSize: 16 }} />
                )}
              </IconButton>
            </span>
          </Tooltip>
        )}
      </Stack>

      {/* Collapsible content: full text + test result */}
      <Collapse in={open}>
        <Box sx={{ ml: 2, mt: 0.5 }}>
          {/* Full verbatim text */}
          <Box
            sx={{
              p: 1.2,
              bgcolor: "grey.50",
              borderRadius: 1,
              border: "1px solid",
              borderColor: "grey.200",
            }}
          >
            <Typography variant="body2" sx={{ fontSize: "0.82rem", lineHeight: 1.6 }}>
              {rec.verbatim}
            </Typography>
            <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5, display: "block" }}>
              ID: {rec.rec_id}
            </Typography>
          </Box>

          {/* Test running indicator */}
          {displayTesting && (
            <Box sx={{ mt: 1 }}>
              <LinearProgress sx={{ borderRadius: 1 }} />
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.3 }}>
                Running AI extraction and SNOMED coding…
              </Typography>
            </Box>
          )}

          {/* Test error */}
          {displayError && (
            <Alert severity="error" sx={{ mt: 1, fontSize: "0.78rem", py: 0.3 }}>
              {displayError}
            </Alert>
          )}

          {/* Test result */}
          {displayResult && <ExtractionResultPanel result={displayResult} />}
        </Box>
      </Collapse>
    </Box>
  );
}

/**
 * Groups an array of recommendations by their section_title (cancer site / topic).
 * Returns an ordered list of [sectionLabel, recs[]] pairs.
 * Recs with no section_title are grouped under an empty-string key and shown first.
 */
function groupBySectionTitle(recs: RecEntry[]): [string, RecEntry[]][] {
  const map = new Map<string, RecEntry[]>();
  for (const rec of recs) {
    const key = rec.section_title || "";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(rec);
  }
  // Put un-labelled recs first, then alphabetical by label
  return [...map.entries()].sort(([a], [b]) => {
    if (!a) return -1;
    if (!b) return 1;
    return a.localeCompare(b);
  });
}

function ChapterAccordion({
  chapter,
  testAllResults,
  testAllRunning,
}: {
  chapter: ChapterEntry;
  testAllResults?: TestAllResults;
  testAllRunning?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ruleCount = chapter.recommendations.reduce((n, r) => n + r.rules.length, 0);
  const normativeCount = chapter.recommendations.filter((r) => r.is_normative).length;
  const crossRefCount = chapter.recommendations.length - normativeCount;
  const groups = groupBySectionTitle(chapter.recommendations.filter((r) => r.is_normative));
  // More than one distinct non-empty section title → worth grouping
  const hasGroups = groups.length > 1 || (groups.length === 1 && groups[0][0] !== "");

  return (
    <Box sx={{ mb: 1 }}>
      <Stack
        direction="row"
        alignItems="center"
        spacing={0.5}
        sx={{
          cursor: "pointer",
          p: 0.8,
          borderRadius: 1,
          bgcolor: open ? "primary.50" : "grey.100",
          "&:hover": { bgcolor: open ? "primary.100" : "grey.200" },
        }}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? (
          <ExpandMoreIcon fontSize="small" color="primary" />
        ) : (
          <ChevronRightIcon fontSize="small" />
        )}
        <MenuBookIcon sx={{ fontSize: 15, color: "text.secondary" }} />
        <Typography variant="body2" sx={{ fontWeight: 600, flex: 1, fontSize: "0.82rem" }}>
          {chapter.chapter_title || chapter.chapter_id}
        </Typography>
        <Chip
          label={`${normativeCount} rec`}
          size="small"
          color={normativeCount > 0 ? "primary" : "default"}
          variant="outlined"
          sx={{ height: 18, fontSize: "0.65rem" }}
        />
        {crossRefCount > 0 && (
          <Tooltip title="Cross-reference entries — not used for rule generation" arrow>
            <Chip
              label={`${crossRefCount} cross-ref`}
              size="small"
              color="warning"
              variant="outlined"
              sx={{ height: 18, fontSize: "0.65rem" }}
            />
          </Tooltip>
        )}
        {ruleCount > 0 && (
          <Chip
            label={`${ruleCount} rule${ruleCount !== 1 ? "s" : ""}`}
            size="small"
            color="success"
            variant="outlined"
            sx={{ height: 18, fontSize: "0.65rem" }}
          />
        )}
      </Stack>

      <Collapse in={open}>
        <Box sx={{ mt: 0.5, pl: 0.5 }}>
          {chapter.recommendations.length === 0 ? (
            <Typography variant="body2" color="text.disabled" sx={{ pl: 2, py: 0.5, fontSize: "0.78rem" }}>
              No recommendations stored in Neo4j for this chapter.
            </Typography>
          ) : hasGroups ? (
            /* ── Grouped by cancer site / section (normative only) ── */
            groups.map(([sectionLabel, recs]) => (
              <Box key={sectionLabel || "__ungrouped__"} sx={{ mb: 1 }}>
                <Stack
                  direction="row"
                  alignItems="center"
                  spacing={0.6}
                  sx={{
                    px: 1,
                    py: 0.4,
                    mb: 0.5,
                    bgcolor: "primary.50",
                    borderRadius: 0.8,
                    borderLeft: "3px solid",
                    borderColor: "primary.light",
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{ fontWeight: 700, color: "primary.dark", fontSize: "0.75rem" }}
                  >
                    {sectionLabel || "General"}
                  </Typography>
                  <Chip
                    label={`${recs.length}`}
                    size="small"
                    variant="outlined"
                    sx={{ height: 15, fontSize: "0.60rem", ml: "auto !important" }}
                  />
                </Stack>
                {recs.map((rec) => (
                  <RecommendationRow
                    key={rec.rec_id}
                    rec={rec}
                    externalResult={testAllResults?.[rec.rec_id]?.result}
                    externalError={testAllResults?.[rec.rec_id]?.error}
                    externalTesting={testAllRunning && !testAllResults?.[rec.rec_id]}
                  />
                ))}
              </Box>
            ))
          ) : (
            /* ── Flat list (normative, no section grouping) ── */
            chapter.recommendations
              .filter((r) => r.is_normative)
              .map((rec) => (
                <RecommendationRow
                  key={rec.rec_id}
                  rec={rec}
                  externalResult={testAllResults?.[rec.rec_id]?.result}
                  externalError={testAllResults?.[rec.rec_id]?.error}
                  externalTesting={testAllRunning && !testAllResults?.[rec.rec_id]}
                />
              ))
          )}

          {/* ── Cross-reference entries (not used for rules) ── */}
          {crossRefCount > 0 && (
            <Box sx={{ mt: 1 }}>
              <Divider sx={{ mb: 0.8 }}>
                <Typography variant="caption" color="warning.main" sx={{ fontSize: "0.68rem" }}>
                  {crossRefCount} cross-reference {crossRefCount === 1 ? "entry" : "entries"} — not used for rule generation
                </Typography>
              </Divider>
              {chapter.recommendations
                .filter((r) => !r.is_normative)
                .map((rec) => <RecommendationRow key={rec.rec_id} rec={rec} />)}
            </Box>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function GuidelineSubgraphDrawer({ code, onClose }: Props) {
  const [data, setData] = useState<SubgraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [testAllRunning, setTestAllRunning] = useState(false);
  const [testAllProgress, setTestAllProgress] = useState<{ done: number; total: number } | null>(null);
  const [testAllResults, setTestAllResults] = useState<TestAllResults>({});

  async function handleTestAll() {
    if (!data) return;
    const normativeRecs = data.chapters.flatMap((ch) =>
      ch.recommendations.filter((r) => r.is_normative && r.verbatim?.trim())
    );
    if (normativeRecs.length === 0) return;

    setTestAllRunning(true);
    setTestAllResults({});
    setTestAllProgress({ done: 0, total: normativeRecs.length });

    await Promise.all(
      normativeRecs.map(async (rec) => {
        try {
          const result = await runExtractionTest(rec.rec_id);
          setTestAllResults((prev) => ({ ...prev, [rec.rec_id]: { result } }));
        } catch (err) {
          setTestAllResults((prev) => ({
            ...prev,
            [rec.rec_id]: { error: err instanceof Error ? err.message : String(err) },
          }));
        }
        setTestAllProgress((prev) => prev ? { done: prev.done + 1, total: prev.total } : prev);
      })
    );

    setTestAllRunning(false);
  }

  const load = useCallback(async (c: string) => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const r = await fetch(`/api/nice/${encodeURIComponent(c)}/subgraph`);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      setData(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load subgraph.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (code) {
      load(code);
      setTestAllResults({});
      setTestAllProgress(null);
      setTestAllRunning(false);
    }
  }, [code, load]);

  const open = Boolean(code);
  const chaptersWithRecs = data?.chapters.filter((c) => c.recommendations.length > 0) ?? [];
  const chaptersEmpty = data?.chapters.filter((c) => c.recommendations.length === 0) ?? [];

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100vw", sm: 640 }, p: 0 } }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 2.5,
          py: 1.5,
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
          position: "sticky",
          top: 0,
          zIndex: 1,
        }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <AccountTreeIcon color="primary" fontSize="small" />
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
              {data?.guideline_title || code}
            </Typography>
            {data && (
              <Stack direction="row" spacing={1} sx={{ mt: 0.3 }} flexWrap="wrap">
                <Chip
                  label={`v${data.ingest_version ?? "?"}`}
                  size="small"
                  color={data.ingest_version && data.ingest_version > 1 ? "warning" : "default"}
                  sx={{ height: 18, fontSize: "0.65rem" }}
                />
                <Chip
                  label={`${data.totals.chapters} chapters`}
                  size="small"
                  variant="outlined"
                  sx={{ height: 18, fontSize: "0.65rem" }}
                />
                <Chip
                  label={`${data.totals.recommendations} recommendations`}
                  size="small"
                  color={data.totals.recommendations > 0 ? "primary" : "error"}
                  variant="outlined"
                  sx={{ height: 18, fontSize: "0.65rem" }}
                />
                {data.totals.rules > 0 && (
                  <Chip
                    label={`${data.totals.rules} rules`}
                    size="small"
                    color="success"
                    variant="outlined"
                    sx={{ height: 18, fontSize: "0.65rem" }}
                  />
                )}
              </Stack>
            )}
          </Box>

          {/* Test All button */}
          {data && data.totals.recommendations > 0 && (
            <Tooltip
              title={
                testAllRunning
                  ? `Testing… ${testAllProgress?.done ?? 0} / ${testAllProgress?.total ?? 0}`
                  : testAllProgress
                  ? `Tested ${testAllProgress.done} recommendations — click to re-run`
                  : "Run AI extraction on all normative recommendations (dry run)"
              }
              arrow
            >
              <span>
                <Button
                  size="small"
                  variant="outlined"
                  color="primary"
                  startIcon={
                    testAllRunning ? (
                      <CircularProgress size={12} color="inherit" />
                    ) : (
                      <PlayArrowIcon sx={{ fontSize: 15 }} />
                    )
                  }
                  onClick={handleTestAll}
                  disabled={testAllRunning || loading}
                  sx={{ fontSize: "0.72rem", py: 0.4, px: 1, whiteSpace: "nowrap", flexShrink: 0 }}
                >
                  {testAllRunning
                    ? `${testAllProgress?.done ?? 0} / ${testAllProgress?.total ?? 0}`
                    : "Test All"}
                </Button>
              </span>
            </Tooltip>
          )}

          <IconButton onClick={onClose} size="small" aria-label="Close subgraph view">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>

        {/* Test All progress bar */}
        {testAllRunning && testAllProgress && (
          <Box sx={{ mt: 1 }}>
            <LinearProgress
              variant="determinate"
              value={(testAllProgress.done / testAllProgress.total) * 100}
              sx={{ borderRadius: 1, height: 4 }}
            />
          </Box>
        )}

        {/* Test All completion summary */}
        {!testAllRunning && testAllProgress && testAllProgress.done === testAllProgress.total && (
          <Box sx={{ mt: 0.8 }}>
            {(() => {
              const errors = Object.values(testAllResults).filter((r) => r.error).length;
              const succeeded = testAllProgress.done - errors;
              return (
                <Alert
                  severity={errors === 0 ? "success" : errors === testAllProgress.total ? "error" : "warning"}
                  sx={{ py: 0.2, fontSize: "0.75rem" }}
                  icon={errors === 0 ? <CheckCircleIcon fontSize="small" /> : <ErrorOutlineIcon fontSize="small" />}
                >
                  {errors === 0
                    ? `All ${succeeded} recommendations extracted successfully.`
                    : `${succeeded} succeeded, ${errors} failed — check individual rows for details.`}
                </Alert>
              );
            })()}
          </Box>
        )}
      </Box>

      {/* Body */}
      <Box sx={{ p: 2, overflowY: "auto", flex: 1 }}>
        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress aria-label="Loading guideline subgraph from Neo4j" />
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {data && !loading && (
          <>
            {/* Health check banner */}
            {data.totals.recommendations === 0 ? (
              <Alert severity="error" sx={{ mb: 2 }}>
                <strong>No recommendations in Neo4j.</strong> The ingest may have failed or used an
                older pipeline version. Re-ingest this guideline to populate recommendation text.
              </Alert>
            ) : data.chapters.length === 0 ? (
              <Alert severity="warning" sx={{ mb: 2 }}>
                Recommendations exist but no chapters were found. This may indicate an older ingest
                that did not preserve the chapter hierarchy. Re-ingest to fix.
              </Alert>
            ) : null}

            {/* Chapters with recommendations */}
            {chaptersWithRecs.map((ch) => (
              <ChapterAccordion
                key={ch.chapter_id}
                chapter={ch}
                testAllResults={testAllResults}
                testAllRunning={testAllRunning}
              />
            ))}

            {/* Empty chapters (no recommendations — appendices etc.) */}
            {chaptersEmpty.length > 0 && (
              <>
                <Divider sx={{ my: 1.5 }}>
                  <Typography variant="caption" color="text.disabled">
                    {chaptersEmpty.length} chapter{chaptersEmpty.length !== 1 ? "s" : ""} with no
                    recommendations (appendices / evidence reviews)
                  </Typography>
                </Divider>
                {chaptersEmpty.map((ch) => (
                  <Box
                    key={ch.chapter_id}
                    sx={{
                      px: 1.5,
                      py: 0.6,
                      mb: 0.4,
                      bgcolor: "grey.50",
                      borderRadius: 1,
                      display: "flex",
                      alignItems: "center",
                      gap: 0.8,
                    }}
                  >
                    <TextSnippetIcon sx={{ fontSize: 14, color: "text.disabled" }} />
                    <Typography variant="caption" color="text.secondary">
                      {ch.chapter_title || ch.chapter_id}
                    </Typography>
                  </Box>
                ))}
              </>
            )}

            {/* Node ID legend */}
            <Divider sx={{ mt: 2, mb: 1 }} />
            <Typography variant="caption" color="text.disabled">
              Node IDs use version-scoped format: {code}:v{data.ingest_version}:CH###:SEC###:R###
            </Typography>
          </>
        )}
      </Box>
    </Drawer>
  );
}
