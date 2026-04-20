/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E647765A
 *   DI: DI-0C8FBAF7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E647765A")
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

import type { LogicSeed } from "./EditRuleDialog/types";

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
}

export interface RuleForLogicView {
  strength?: string;
  logic_tree?: LogicTreeNode | null;
  present_criteria: RuleCriterion[];
  absent_criteria: RuleCriterion[];
}

// -- Helpers ----------------------------------------------------------------

/**
 * Match the editor's heuristic: an OR near the top of the tree that has
 * 2+ children is the "patient must match one of these pathways" pattern.
 * Anything deeper than depth 1 is treated as a regular nested OR (so we
 * never recurse into a card and produce another card layer).
 */
export function isPathwaySplit(node: LogicTreeNode, depth: number): boolean {
  const kind = String(node.kind || "").toUpperCase();
  if (kind !== "OR") return false;
  if (depth > 1) return false;
  return (node.children?.length ?? 0) >= 2;
}

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

function SnomedChip({ item }: { item: CriterionResult }) {
  const resolved = !!item.snomed_concept_id;
  const tag = item.semantic_tag ?? "concept";
  const fallbackLabel = item.term || item.preferred_term || "unknown concept";
  return (
    <Tooltip
      title={
        resolved
          ? `SNOMED: ${item.snomed_concept_id} | ${tag}`
          : "No SNOMED match found"
      }
      arrow
    >
      <Chip
        label={resolved ? item.preferred_term : `? ${fallbackLabel}`}
        size="small"
        color={resolved ? "success" : "warning"}
        variant={resolved ? "filled" : "outlined"}
        sx={{ height: 20, fontSize: "0.68rem", mr: 0.4, mb: 0.4 }}
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
        sx={{ fontWeight: 600, color: "text.primary", mb: 1, lineHeight: 1.4 }}
      >
        The rule fires if the patient matches any one of these pathways:
      </Typography>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={2}
        useFlexGap
        sx={{ alignItems: "stretch", flexWrap: "wrap" }}
      >
        {children.map((child, i) => (
          <PathwayCard
            key={child.node_id ?? `pathway-${i}`}
            node={child}
            index={i}
            isLast={i === children.length - 1}
            depth={depth + 1}
          />
        ))}
      </Stack>
    </Box>
  );
}

interface PathwayCardProps {
  node: LogicTreeNode;
  index: number;
  isLast: boolean;
  depth: number;
}

function PathwayCard({ node, index, isLast, depth }: PathwayCardProps) {
  const accent = pathwayAccent(index);
  const letter = String.fromCharCode(65 + index);
  const namedRaw = typeof node.name === "string" ? node.name.trim() : "";
  const titleLabel = namedRaw || `Pathway ${letter}`;
  return (
    <Box
      sx={{
        flex: 1,
        minWidth: { xs: "100%", md: 260 },
        position: "relative",
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        overflow: "hidden",
      }}
    >
      <Box aria-hidden sx={{ height: 4, width: "100%", bgcolor: accent.stripe }} />
      <Box sx={{ p: 1.5 }}>
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
            // Named pathways render as sentence-case so the label
            // reads like a clinical pathway title rather than a code.
            // Fallback letters stay uppercase for visual consistency.
            textTransform: namedRaw ? "none" : "uppercase",
            maxWidth: "100%",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={titleLabel}
        >
          {titleLabel}
        </Box>
        <PathwayCardBody node={node} depth={depth} />
      </Box>
      {!isLast && (
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
    const label = `${node.field ?? "?"} ${node.operator ?? "="} ${
      node.value ?? "?"
    }${node.unit ? ` ${node.unit}` : ""}`;
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
        mt: 0.5,
        pl: 1,
        borderLeft: "2px solid",
        borderColor: "divider",
      }}
    >
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          color: "text.secondary",
          display: "block",
          mb: 0.4,
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

export function RuleDetailPanel({ rule }: { rule: RuleForLogicView }) {
  const hasLogicTree = !!rule.logic_tree;
  return (
    <Box
      sx={{
        mt: 1.5,
        p: 1.5,
        bgcolor: "primary.50",
        border: "1px solid",
        borderColor: "primary.200",
        borderRadius: 1,
      }}
    >
      <Typography
        variant="caption"
        sx={{
          fontWeight: 700,
          color: "primary.dark",
          display: "block",
          mb: 1,
        }}
      >
        Exact rule logic
      </Typography>

      {hasLogicTree ? (
        <LogicNodePanel node={rule.logic_tree!} />
      ) : (
        <V1CriteriaFallback
          present={rule.present_criteria}
          absent={rule.absent_criteria}
        />
      )}

      {rule.strength && rule.strength !== "unspecified" && (
        <Box sx={{ mt: 1.5 }}>
          <Typography
            variant="caption"
            color="info.dark"
            sx={{ fontWeight: 600, display: "block", mb: 0.3 }}
          >
            Recommended action
          </Typography>
          <Chip
            label={rule.strength}
            size="small"
            variant="outlined"
            color="info"
            sx={{ fontSize: "0.68rem", height: 20 }}
          />
        </Box>
      )}
    </Box>
  );
}
