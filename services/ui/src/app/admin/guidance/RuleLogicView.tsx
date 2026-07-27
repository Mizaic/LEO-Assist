/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 *
 * Read-only logic-tree renderer for the Check & approve view.
 *
 * The reviewer-facing tree mirrors the editor (LogicTreeEditor.tsx) in two
 * important ways:
 *
 *  1. A pure AT_LEAST group whose children are all SNOMED concepts renders
 *     inline (handled by the existing chip layout below).
 *  2. An OR group at depth 0 or 1 with two or more children renders as a
 *     row of "Pathway A / B / C" cards under a plain-English heading.
 *     Without this, NICE recommendations like NG12 (cancer) -- which have
 *     three independent symptom-set + risk-factor branches -- showed up as
 *     a single "ANY of these" with three nested "ALL of these" groups, so a
 *     reviewer scanning the tree could not tell at a glance that any one
 *     branch was sufficient. Same heuristic and copy as the editor.
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { STRENGTH_LABELS, friendlyTerm, priorityLabel } from "./EditRuleDialog/copy";
import { isPathwaySplit } from "./EditRuleDialog/pathwayDetection";
import type { LogicSeed, RuleAction, RulePriority } from "./EditRuleDialog/types";
import { normalizeRuleActions } from "./actionShape";

/**
 * Re-exported for backwards compatibility -- the canonical definition
 * now lives in EditRuleDialog/pathwayDetection.ts so LogicTreeEditor
 * and SentenceEditor can share it too. Prefer importing directly from
 * pathwayDetection.ts in new code.
 */
export { isPathwaySplit };

/**
 * An AT_LEAST group whose children are all SNOMED concepts is rendered as
 * a single bordered "pick N of M of these" card -- same heuristic as the
 * editor's InlineAtLeastView. This keeps the read-only chip cluster from
 * looking like a loose row of symptoms.
 */
function isPureConceptAtLeast(node: LogicTreeNode): boolean {
  const kind = String(node.kind || "").toUpperCase();
  if (kind !== "AT_LEAST") return false;
  const children = node.children ?? [];
  if (children.length === 0) return false;
  return children.every(
    (c) => String(c.kind || "").toUpperCase() === "CONCEPT",
  );
}

export interface RuleCriterion {
  predicate: string;
  concept_id: string;
  preferred_term: string;
}

/**
 * Read-only criterion shape served by the rule-list and rule-detail
 * endpoints. The BE has two flavours of CONCEPT criterion in the wire
 * tree:
 *
 * 1. Legacy single-seed (older fixtures, NICE seeds before synonym sets):
 *    only ``snomed_concept_id`` / ``preferred_term`` are guaranteed;
 *    ``term`` and ``semantic_tag`` are populated when the FE built the
 *    criterion from a typeahead lookup.
 * 2. Synonym-set / exclusion criterion (current schema; what the
 *    EditRuleDialog produces): same legacy fields plus ``seeds``,
 *    ``primary_concept_id`` and ``excluded_concept_ids``. The BE's
 *    Pydantic ``model_validator`` derives ``snomed_concept_id`` /
 *    ``preferred_term`` from the primary seed so legacy consumers
 *    keep working, but the optional fields MUST be reflected here so
 *    downstream renderers / tests can assert on the fuller shape
 *    without ``as unknown`` escape hatches.
 *
 * ``term`` and ``semantic_tag`` are optional because they are not
 * present on every wire row; ``SnomedChip`` falls back to
 * ``preferred_term`` when they are absent.
 */
export interface CriterionResult {
  snomed_concept_id: string | null;
  preferred_term: string;
  term?: string;
  semantic_tag?: string;
  verification_status?: string;
  seeds?: LogicSeed[];
  primary_concept_id?: string;
  excluded_concept_ids?: string[];
}

export interface ActionResult {
  snomed_concept_id: string | null;
  preferred_term: string;
  term?: string;
  semantic_tag?: string;
}

/**
 * Read-only shape of an OBSERVATION leaf's payload (Phase 6a).
 *
 * The wire type is a permissive superset of the editor's
 * EditableObservationPayload. This view only reads top-level fields
 * plus a ``mode`` discriminator that, when present, tells the reader
 * the row uses an advanced temporal / reference-range / trend /
 * aggregate shape and should be summarised softly.
 */
export interface ObservationLeafResult {
  observable_id?: string | null;
  observable_term?: string | null;
  operator?: string | null;
  value?: number | [number, number] | null;
  unit?: string | null;
  within_days?: number | null;
  temporal?: Record<string, unknown> | null;
  reference_range?: Record<string, unknown> | null;
  trend?: Record<string, unknown> | null;
  aggregation?: Record<string, unknown> | null;
}

export interface LogicTreeNode {
  kind: string;
  node_id?: string;
  children?: LogicTreeNode[];
  min?: number;
  criterion?: CriterionResult;
  field?: string;
  operator?: string;
  value?: number | string | null;
  unit?: string | null;
  /**
   * Optional plain-English pathway name (Phase 2 of the wizard
   * redesign). When set on the OR's child, the pathway card uses it
   * verbatim as the title; when absent, the card falls back to the
   * positional letter so legacy guidelines still render.
   */
  name?: string;
  /**
   * Optional OBSERVATION leaf payload (Phase 6a). Present only on
   * nodes with ``kind == "OBSERVATION"``. Missing fields are tolerated
   * so legacy rules without a canonicalised threshold still render
   * without crashing the review UI.
   */
  observation?: ObservationLeafResult;
}

export interface RuleForLogicView {
  strength?: string;
  /** One or more recommended procedures, each with its own strength.
   *  Preferred over ``action`` when present. */
  actions?: RuleAction[];
  /** Deprecated: legacy single recommended procedure, used as a
   *  fallback for rules not yet migrated to ``actions``. */
  action?: ActionResult | null;
  /** Rule-level clinical priority from HAS_ACTION (shown on the card). */
  action_priority?: RulePriority | string | null;
  /** Due-days paired with action_priority (null for routine). */
  action_due_days?: number | null;
  logic_tree?: LogicTreeNode | null;
  present_criteria: RuleCriterion[];
  absent_criteria: RuleCriterion[];
}

// -- Helpers ----------------------------------------------------------------

const PATHWAY_ACCENTS = [
  { stripe: "primary.main", chipBg: "primary.50", chipFg: "primary.dark" },
  { stripe: "info.main", chipBg: "info.50", chipFg: "info.dark" },
  { stripe: "secondary.main", chipBg: "secondary.50", chipFg: "secondary.dark" },
  { stripe: "success.main", chipBg: "success.50", chipFg: "success.dark" },
] as const;

function pathwayAccent(index: number) {
  return PATHWAY_ACCENTS[index % PATHWAY_ACCENTS.length];
}

// -- Leaf renderers ---------------------------------------------------------

function strengthPlainLabel(strength: string): string {
  const hit = STRENGTH_LABELS.find((row) => row.value === strength);
  return hit?.label ?? strength.replace(/_/g, " ");
}

function actionPlainLabel(action: ActionResult | null | undefined): string {
  return friendlyTerm(action?.preferred_term || action?.term);
}

/** Compact priority + due-days line for the read-only action block. */
function PriorityDueLine({
  priority,
  dueDays,
}: {
  priority?: string | null;
  dueDays?: number | null;
}) {
  const text = priorityLabel(priority, dueDays);
  return (
    <Typography
      variant="body2"
      color="text.secondary"
      sx={{ lineHeight: 1.5, mb: 0.75 }}
      aria-label={`Clinical priority: ${text}`}
    >
      Priority:{" "}
      <Box component="span" sx={{ fontWeight: 600, color: "text.primary" }}>
        {text}
      </Box>
    </Typography>
  );
}

/**
 * The other findings folded into a multi-seed CONCEPT chip via "Add
 * another code that means the same" -- every seed except the one
 * already shown as the chip's own headline label. Reviewers need to
 * see WHICH additional findings this single chip actually covers
 * (by their plain-English term, not a bare SNOMED id) rather than
 * having a chip that silently represents ten codes while only
 * naming one.
 */
function additionalSeedLabels(item: {
  snomed_concept_id?: string | null;
  primary_concept_id?: string;
  seeds?: LogicSeed[];
}): string[] {
  const seeds = item.seeds ?? [];
  if (seeds.length <= 1) return [];
  const primaryId = item.primary_concept_id ?? item.snomed_concept_id;
  return seeds
    .filter((seed) => seed.snomed_concept_id !== primaryId)
    .map((seed) => friendlyTerm(seed.preferred_term))
    .filter(Boolean);
}

function ConceptTooltipTitle({
  headline,
  extraTerms,
}: {
  headline: string;
  extraTerms: string[];
}) {
  if (extraTerms.length === 0) return <>{headline}</>;
  return (
    <Box>
      <Box>{headline}</Box>
      <Box sx={{ mt: 0.5 }}>Also matches: {extraTerms.join(", ")}</Box>
    </Box>
  );
}

function SnomedChip({ item }: { item: CriterionResult }) {
  const resolved = !!item.snomed_concept_id;
  const rawLabel = item.preferred_term || item.term || "unknown concept";
  const label = resolved ? friendlyTerm(rawLabel) : `? ${friendlyTerm(rawLabel)}`;
  const extraTerms = additionalSeedLabels(item);
  return (
    <Tooltip
      title={
        resolved ? (
          <ConceptTooltipTitle
            headline={`${rawLabel} (SNOMED ${item.snomed_concept_id})`}
            extraTerms={extraTerms}
          />
        ) : (
          "No SNOMED match found"
        )
      }
      arrow
    >
      <Chip
        label={label}
        size="small"
        color={resolved ? "success" : "warning"}
        variant={resolved ? "filled" : "outlined"}
        sx={{
          height: "auto",
          minHeight: 24,
          maxWidth: "100%",
          fontSize: "0.72rem",
          mr: 0.4,
          mb: 0.4,
          "& .MuiChip-label": {
            display: "block",
            whiteSpace: "normal",
            lineHeight: 1.35,
            py: 0.35,
          },
        }}
      />
    </Tooltip>
  );
}

// -- Pathway cards ----------------------------------------------------------

interface PathwayCardsViewProps {
  node: LogicTreeNode;
  depth: number;
}

function PathwayCardsView({ node, depth }: PathwayCardsViewProps) {
  const children = node.children ?? [];
  return (
    <Box
      role="group"
      aria-label="Patient pathways"
      sx={{ ml: depth === 0 ? 0 : 1.5, mt: 0.75 }}
    >
      <Typography
        variant="body2"
        sx={{ fontWeight: 600, color: "text.primary", mb: 1.25, lineHeight: 1.4 }}
      >
        The rule fires if the patient matches any one of these pathways:
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            sm: "repeat(2, minmax(0, 1fr))",
            lg: "repeat(3, minmax(0, 1fr))",
          },
          gap: 2,
          alignItems: "stretch",
        }}
      >
        {children.map((child, i) => (
          <PathwayCard
            key={child.node_id ?? `pathway-${i}`}
            node={child}
            index={i}
            isLast={i === children.length - 1}
            showOrConnector={children.length <= 3}
            depth={depth + 1}
          />
        ))}
      </Box>
    </Box>
  );
}

interface PathwayCardProps {
  node: LogicTreeNode;
  index: number;
  isLast: boolean;
  showOrConnector: boolean;
  depth: number;
}

function PathwayCard({
  node,
  index,
  isLast,
  showOrConnector,
  depth,
}: PathwayCardProps) {
  const accent = pathwayAccent(index);
  const letter = String.fromCharCode(65 + index);
  const namedRaw = typeof node.name === "string" ? node.name.trim() : "";
  const titleLabel = namedRaw || `Pathway ${letter}`;
  return (
    <Box
      sx={{
        minWidth: 0,
        position: "relative",
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Box aria-hidden sx={{ height: 4, width: "100%", bgcolor: accent.stripe }} />
      <Box sx={{ p: 1.75, flex: 1 }}>
        <Box
          sx={{
            display: "inline-flex",
            alignItems: "center",
            gap: 0.5,
            px: 0.85,
            py: 0.25,
            mb: 0.75,
            borderRadius: 1,
            bgcolor: accent.chipBg,
            color: accent.chipFg,
            fontSize: "0.7rem",
            fontWeight: 700,
            letterSpacing: 0.4,
            textTransform: namedRaw ? "none" : "uppercase",
            maxWidth: "100%",
          }}
          title={titleLabel}
        >
          {titleLabel}
        </Box>
        <PathwayCardBody node={node} depth={depth} />
      </Box>
      {showOrConnector && !isLast && (
        <Tooltip title="Either pathway is enough on its own" arrow>
          <Box
            role="img"
            aria-label="Or"
            sx={{
              display: { xs: "none", md: "flex" },
              position: "absolute",
              right: -14,
              top: "50%",
              transform: "translateY(-50%)",
              width: 28,
              height: 28,
              borderRadius: "50%",
              bgcolor: "background.paper",
              color: "primary.dark",
              border: "1px solid",
              borderColor: "primary.light",
              fontSize: "0.62rem",
              fontWeight: 800,
              letterSpacing: 0.5,
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1,
            }}
          >
            OR
          </Box>
        </Tooltip>
      )}
    </Box>
  );
}

/**
 * The card itself already implies "patient must have ALL of these", so when
 * the immediate child is a plain AND we render its children directly with
 * no extra "ALL of these" header. This mirrors the editor's
 * PathwayCardBody and avoids a redundant nested label inside every card.
 */
function PathwayCardBody({ node, depth }: { node: LogicTreeNode; depth: number }) {
  const kind = String(node.kind || "").toUpperCase();
  if (kind === "AND") {
    const children = node.children ?? [];
    if (children.length === 0) {
      return (
        <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
          This pathway is empty.
        </Typography>
      );
    }
    return (
      <Box>
        {children.map((child, i) => (
          <LogicNodePanel
            key={child.node_id ?? `${kind}-${i}`}
            node={child}
            depth={depth}
          />
        ))}
      </Box>
    );
  }
  return <LogicNodePanel node={node} depth={depth} />;
}

// -- Main recursive renderer -----------------------------------------------

export function LogicNodePanel({
  node,
  depth = 0,
}: {
  node: LogicTreeNode;
  depth?: number;
}) {
  const kind = String(node.kind || "").toUpperCase();

  if (kind === "CONCEPT") {
    if (node.criterion) return <SnomedChip item={node.criterion} />;
    return (
      <Chip
        label="unknown concept"
        size="small"
        variant="outlined"
        color="default"
        sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
      />
    );
  }

  if (kind === "DEMOGRAPHIC") {
    const field = (node.field ?? "detail").replace(/_/g, " ");
    const op =
      node.operator === ">="
        ? "is at least"
        : node.operator === "<="
          ? "is at most"
          : node.operator === ">"
            ? "is more than"
            : node.operator === "<"
              ? "is less than"
              : "is";
    const label = `${field.charAt(0).toUpperCase()}${field.slice(1)} ${op} ${
      node.value ?? "?"
    }${node.unit ? ` ${node.unit}` : ""}`;
    return (
      <Chip
        label={label}
        size="small"
        variant="filled"
        color="secondary"
        sx={{
          height: "auto",
          minHeight: 24,
          mr: 0.4,
          mb: 0.4,
          fontSize: "0.72rem",
          "& .MuiChip-label": { whiteSpace: "normal", lineHeight: 1.35, py: 0.35 },
        }}
      />
    );
  }

  if (kind === "OBSERVATION") {
    return <ObservationLeafChip node={node} />;
  }

  if (isPathwaySplit(node, depth)) {
    return <PathwayCardsView node={node} depth={depth} />;
  }

  if (isPureConceptAtLeast(node)) {
    return <InlineAtLeastView node={node} depth={depth} />;
  }

  const title =
    kind === "AND"
      ? "ALL of these"
      : kind === "OR"
        ? "ANY of these"
        : kind === "NOT"
          ? "NOT"
          : `Any ${node.min ?? 1} or more of these`;

  return (
    <Box
      sx={{
        ml: depth ? 1.5 : 0,
        mt: 0.75,
        pl: 1.25,
        py: 0.75,
        borderLeft: "2px solid",
        borderColor: "divider",
        bgcolor: depth === 0 ? "background.paper" : "transparent",
        borderRadius: depth === 0 ? 1 : 0,
      }}
    >
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          color: "text.secondary",
          display: "block",
          mb: 0.5,
          textTransform: "uppercase",
          letterSpacing: 0.4,
          fontSize: "0.68rem",
        }}
      >
        {title}
      </Typography>
      <Box>
        {(node.children ?? []).map((child, idx) => (
          <LogicNodePanel
            key={child.node_id ?? `${kind}-${idx}`}
            node={child}
            depth={depth + 1}
          />
        ))}
      </Box>
    </Box>
  );
}

// -- Observation leaf chip (Phase 6a) --------------------------------------

/**
 * Read-only renderer for an OBSERVATION leaf.
 *
 * Renders as a single plain-English chip so the reviewer view stays
 * compact and scannable. Four cases:
 *
 *  - Missing payload entirely -> warning chip "Lab value not filled in".
 *  - Advanced mode (temporal / reference_range / trend / aggregation)
 *    -> info chip summarising the mode without the numeric threshold,
 *    because these modes don't reduce cleanly to a single number.
 *  - Between -> "Platelet count between 150 and 400 x10*9/L in the last year".
 *  - Anything else -> "Platelet count at least 400 x10*9/L in the last year".
 *
 * The ``within_days`` recency window falls back to "in the last year"
 * if the wire value is missing or out of range, matching the editor's
 * default so read-only and edit views stay in sync.
 */
function ObservationLeafChip({ node }: { node: LogicTreeNode }) {
  const obs = node.observation;
  if (!obs) {
    return (
      <Chip
        label="Lab value not filled in"
        size="small"
        color="warning"
        variant="outlined"
        sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
      />
    );
  }
  const term = (obs.observable_term ?? "lab value").trim() || "lab value";
  const mode = pickObservationMode(obs);
  if (mode !== "absolute") {
    const label = `${term} -- ${observationModeShortLabel(mode)}`;
    return (
      <Tooltip
        title="Open the rule in the editor's Advanced view to see this timing rule"
        arrow
      >
        <Chip
          label={label}
          size="small"
          color="info"
          variant="outlined"
          sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
        />
      </Tooltip>
    );
  }
  const opWord = observationOpWord(obs.operator ?? ">=");
  const unit = obs.unit ? ` ${obs.unit}` : "";
  let valueText: string;
  if (Array.isArray(obs.value)) {
    valueText = `${obs.value[0]} and ${obs.value[1]}${unit}`;
  } else if (obs.value != null) {
    valueText = `${obs.value}${unit}`;
  } else {
    valueText = "?" + unit;
  }
  const recency = observationRecencyLabel(obs.within_days);
  const resolved = Boolean(obs.observable_id);
  const label = `${term} ${opWord} ${valueText} ${recency}`.replace(
    /\s+/g,
    " ",
  );
  return (
    <Tooltip
      title={resolved ? `Observable code: ${obs.observable_id}` : "No canonical observable code"}
      arrow
    >
      <Chip
        label={label}
        size="small"
        color={resolved ? "success" : "warning"}
        variant={resolved ? "filled" : "outlined"}
        sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
      />
    </Tooltip>
  );
}

type ObservationMode =
  | "absolute"
  | "temporal"
  | "reference_range"
  | "trend"
  | "aggregate";

function pickObservationMode(obs: ObservationLeafResult): ObservationMode {
  if (obs.temporal) return "temporal";
  if (obs.reference_range) return "reference_range";
  if (obs.trend) return "trend";
  if (obs.aggregation) return "aggregate";
  return "absolute";
}

function observationModeShortLabel(mode: ObservationMode): string {
  switch (mode) {
    case "temporal":
      return "timing rule";
    case "reference_range":
      return "out of expected range";
    case "trend":
      return "trend check";
    case "aggregate":
      return "average check";
    default:
      return "value check";
  }
}

function observationOpWord(op: string): string {
  switch (op) {
    case ">=":
      return "at least";
    case "<=":
      return "at most";
    case ">":
      return "more than";
    case "<":
      return "less than";
    case "=":
      return "exactly";
    case "between":
      return "between";
    default:
      return op;
  }
}

function observationRecencyLabel(days?: number | null): string {
  if (days == null) return "in the last year";
  if (days <= 7) return "in the last 7 days";
  if (days <= 30) return "in the last 30 days";
  if (days <= 90) return "in the last 90 days";
  if (days <= 180) return "in the last 180 days";
  if (days <= 365) return "in the last year";
  return "in the last 2 years";
}

// -- Inline AT LEAST card (mirrors LogicTreeEditor.InlineAtLeastView) ------

function InlineAtLeastView({
  node,
  depth,
}: {
  node: LogicTreeNode;
  depth: number;
}) {
  const min = node.min ?? 1;
  const children = node.children ?? [];
  const total = children.length;
  return (
    <Box
      role="group"
      aria-label={`At least ${min} of ${total}`}
      sx={{
        ml: depth ? 1.5 : 0,
        mt: 1,
        px: 1.25,
        py: 1,
        position: "relative",
        bgcolor: "primary.50",
        border: "1px solid",
        borderColor: "primary.100",
        borderRadius: 1.5,
        "&::before": {
          content: '""',
          position: "absolute",
          left: 0,
          top: 8,
          bottom: 8,
          width: 3,
          borderRadius: 2,
          bgcolor: depth <= 1 ? "primary.main" : "primary.light",
        },
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        spacing={0.75}
        useFlexGap
        sx={{ flexWrap: "wrap", rowGap: 0.5, pl: 0.5 }}
      >
        <Box
          sx={{
            display: "inline-flex",
            alignItems: "center",
            gap: 0.4,
            mr: 0.5,
            px: 0.85,
            py: 0.3,
            borderRadius: 1,
            bgcolor: "background.paper",
            border: "1px solid",
            borderColor: "primary.100",
            fontSize: "0.78rem",
            fontWeight: 600,
            color: "primary.dark",
          }}
        >
          Any {min} or more of these {total > 0 ? `(of ${total})` : ""}
        </Box>
        {children.map((child, idx) => (
          <LogicNodePanel
            key={child.node_id ?? `at-least-${idx}`}
            node={child}
            depth={depth + 1}
          />
        ))}
      </Stack>
    </Box>
  );
}

// -- v1 schema fallback (legacy rules without a logic_tree) ----------------

function V1CriteriaFallback({
  present,
  absent,
}: {
  present: RuleCriterion[];
  absent: RuleCriterion[];
}) {
  if (present.length === 0 && absent.length === 0) {
    return (
      <Typography
        variant="body2"
        color="text.disabled"
        sx={{ fontSize: "0.78rem", fontStyle: "italic" }}
      >
        No criteria stored for this rule.
      </Typography>
    );
  }
  return (
    <>
      {present.length > 0 && (
        <Box sx={{ mt: 0.5, pl: 1, borderLeft: "2px solid", borderColor: "divider" }}>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              color: "text.secondary",
              display: "block",
              mb: 0.4,
            }}
          >
            ANY of these
          </Typography>
          <Box>
            {present.map((c) => (
              <Tooltip
                key={c.concept_id}
                title={`${c.predicate} | ${c.concept_id}`}
                arrow
              >
                <Chip
                  label={c.preferred_term || c.concept_id}
                  size="small"
                  color="success"
                  variant="outlined"
                  sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
                />
              </Tooltip>
            ))}
          </Box>
        </Box>
      )}
      {absent.length > 0 && (
        <Box sx={{ mt: 0.5, pl: 1, borderLeft: "2px solid", borderColor: "error.light" }}>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              color: "text.secondary",
              display: "block",
              mb: 0.4,
            }}
          >
            NOT any of these
          </Typography>
          <Box>
            {absent.map((c) => (
              <Tooltip
                key={c.concept_id}
                title={`${c.predicate} | ${c.concept_id}`}
                arrow
              >
                <Chip
                  label={c.preferred_term || c.concept_id}
                  size="small"
                  color="error"
                  variant="outlined"
                  sx={{ mr: 0.4, mb: 0.4, fontSize: "0.68rem", height: 20 }}
                />
              </Tooltip>
            ))}
          </Box>
        </Box>
      )}
    </>
  );
}

// -- Outer card panel ------------------------------------------------------

/** Read-only chip cluster for the recommended-procedures list. */
function ActionChipList({ actions }: { actions: RuleAction[] }) {
  return (
    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
      {actions.map((item, i) => {
        const term = friendlyTerm(item.criterion?.preferred_term) || "unknown procedure";
        const label = `${strengthPlainLabel(item.strength)}: ${term}`;
        const extraTerms = item.criterion ? additionalSeedLabels(item.criterion) : [];
        return (
          <Tooltip
            key={item.criterion?.snomed_concept_id || i}
            title={
              item.criterion?.snomed_concept_id ? (
                <ConceptTooltipTitle
                  headline={`${term} (SNOMED ${item.criterion.snomed_concept_id})`}
                  extraTerms={extraTerms}
                />
              ) : (
                "No SNOMED match found"
              )
            }
            arrow
          >
            <Chip
              label={label}
              size="small"
              color={item.criterion?.snomed_concept_id ? "success" : "warning"}
              variant={item.criterion?.snomed_concept_id ? "filled" : "outlined"}
              sx={{
                height: "auto",
                minHeight: 24,
                maxWidth: "100%",
                fontSize: "0.72rem",
                "& .MuiChip-label": { whiteSpace: "normal", lineHeight: 1.35, py: 0.35 },
              }}
            />
          </Tooltip>
        );
      })}
    </Stack>
  );
}

export function RuleDetailPanel({ rule }: { rule: RuleForLogicView }) {
  const hasLogicTree = !!rule.logic_tree;
  const strengthText =
    rule.strength && rule.strength !== "unspecified"
      ? strengthPlainLabel(rule.strength)
      : null;
  const actionText = actionPlainLabel(rule.action);
  const normalizedActions = normalizeRuleActions(
    rule.actions as unknown[] | undefined,
  );
  const hasActionsList = Boolean(normalizedActions && normalizedActions.length > 0);
  return (
    <Box
      sx={{
        mt: 1.5,
        p: 2,
        bgcolor: "grey.50",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1.5,
      }}
    >
      <Typography
        variant="subtitle2"
        sx={{
          fontWeight: 700,
          color: "text.primary",
          display: "block",
          mb: 1.25,
        }}
      >
        Exact rule logic
      </Typography>

      <Box
        sx={{
          p: 1.5,
          bgcolor: "background.paper",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1.5,
        }}
      >
        {hasLogicTree ? (
          <LogicNodePanel node={rule.logic_tree!} />
        ) : (
          <V1CriteriaFallback
            present={rule.present_criteria}
            absent={rule.absent_criteria}
          />
        )}
      </Box>

      {(hasActionsList || strengthText || rule.action_priority) && (
        <Box
          sx={{
            mt: 1.5,
            pt: 1.5,
            borderTop: "1px solid",
            borderColor: "divider",
          }}
        >
          <PriorityDueLine
            priority={rule.action_priority}
            dueDays={rule.action_due_days}
          />
          {hasActionsList ? (
            <>
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ lineHeight: 1.5, mb: 0.75 }}
              >
                When this rule matches, the system should:
              </Typography>
              <ActionChipList actions={normalizedActions!} />
            </>
          ) : (
            strengthText && (
              <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.5 }}>
                When this rule matches, the system should:{" "}
                <Box component="span" sx={{ fontWeight: 600, color: "text.primary" }}>
                  {strengthText}
                  {actionText ? `: ${actionText}` : ""}
                </Box>
              </Typography>
            )
          )}
        </Box>
      )}
    </Box>
  );
}
