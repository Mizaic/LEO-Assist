/**
 * Shared types for the EditRuleDialog.
 *
 * The shape mirrors the LogicNode contract on the API side
 * (services/api/app/services/guidance_rule_edit.py). Each editable node in the
 * UI carries a stable client-side ``node_id`` so list-style mutations
 * (replace, remove, insert) can target a specific node without relying on
 * object identity through React re-renders.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 *
 * Note: MEDICATION / ALLERGY / TREATMENT_HISTORY leaf enums also feed the
 * separate guideline-compiler leaf-evaluation surface tracked under
 * DI-2199E670 -> DO-0EC3A9CB (libs/guidance_schema, guideline_compiler.py,
 * guideline_evaluator.py). That DI/DO pair covers backend leaf matching,
 * not this UI type definitions file.
 */
export type LogicNodeKind =
  | "AND"
  | "OR"
  | "NOT"
  | "AT_LEAST"
  | "CONCEPT"
  | "DEMOGRAPHIC"
  | "OBSERVATION"
  | "MEDICATION"
  | "ALLERGY"
  | "TREATMENT_HISTORY"
  | "RULE_FIRED";

/**
 * One SNOMED code in a CONCEPT criterion's synonym set (UN-LEO-AI-093).
 *
 * Each seed is independently expandable via the bitmap compiler's
 * IS_A descendant closure. ``include_descendants: false`` forces an
 * exact-match-only contribution from this seed.
 */
export interface LogicSeed {
  snomed_concept_id: string;
  preferred_term: string;
  semantic_tag?: string;
  /** Default true; mirrors LogicSeed.include_descendants on the API side. */
  include_descendants?: boolean;
  /** Per-seed override of the rule-level distance_child default (3). */
  distance_child?: number | null;
}

/**
 * Backwards compatible: legacy single-seed callers populate
 * ``snomed_concept_id`` + ``preferred_term`` only. New synonym-set
 * callers populate ``seeds`` (and optionally ``primary_concept_id``
 * and ``excluded_concept_ids``); the legacy fields are auto-derived
 * from the primary seed by the API model_validator.
 */
export interface LogicCriterion {
  snomed_concept_id: string;
  preferred_term: string;
  semantic_tag?: string;
  term?: string;
  /** Optional synonym-set seeds. Empty / absent means legacy single-seed. */
  seeds?: LogicSeed[];
  /** SNOMED ids subtracted from the union of seed closures before bitmap. */
  excluded_concept_ids?: string[];
  /** Names which seed supplies the chip's headline label. */
  primary_concept_id?: string;
  /**
   * AI extraction confidence (0..1), written once by the coding
   * pipeline (``libs/pipeline_graph/subgraphs/
   * guidance_rule_extraction_v2_impl.py``) and never modified
   * afterwards. Banded via
   * ``services/ui/src/lib/terminologyConfidence.ts``
   * (``getTerminologyConfidenceBand``). Absent on hand-authored
   * criteria (no AI ever scored them).
   */
  confidence?: number | null;
  /**
   * True when the AI extractor flagged this criterion for mandatory
   * human review. Cleared implicitly once ``human_reviewed_at`` is
   * stamped -- the wizard/canvas gate reads
   * ``needs_human_review && !human_reviewed_at``, never
   * ``needs_human_review`` alone, so a reviewed row never re-gates on
   * reopen. See ``confidenceGate.ts``.
   */
  needs_human_review?: boolean;
  /**
   * When a reviewer's explicit tap confirms or changes a medium/low
   * confidence or needs-human-review row, these are stamped. Modeled
   * directly on ``CodingReview.resolved_at`` / ``resolved_by``
   * (``libs/cypher/coding_review_queries.py``): a separate, human-only
   * pair that is fully decoupled from the AI's own immutable
   * ``confidence`` score, so "reviewed once" and "the AI got more
   * sure" are never conflated.
   */
  human_reviewed_at?: string | null;
  human_reviewed_by?: string | null;
}

/**
 * How a set of recommended procedures relate to each other.
 * - ``all`` -- suggest each one (legacy multi-action AND).
 * - ``any`` -- either/or; any one is fine.
 * - ``preferred_fallback`` -- try the first; if not available, the next.
 */
export type ActionGroupMode = "all" | "any" | "preferred_fallback";

/**
 * One recommended procedure a rule suggests when it fires, paired with
 * its own strength (offer / consider / refer / ...). A rule may recommend
 * more than one procedure (e.g. "Offer an X-ray and refer urgently for a
 * biopsy"), so the editor and the API both carry an ``actions`` array
 * rather than a single action.
 *
 * When ``group_id`` is set, sibling actions share that id and
 * ``group_mode`` describes whether they are AND / OR / preferred+fallback.
 * ``group_rank`` orders preferred_fallback arms (0 = first choice).
 *
 * Mirrors ``RuleAction`` in
 * ``services/api/app/services/guidance_rule_edit.py``.
 */
export interface RuleAction {
  criterion: LogicCriterion;
  strength: string;
  group_id?: string;
  group_mode?: ActionGroupMode;
  group_rank?: number;
}

/**
 * Rule-level clinical priority written onto HAS_ACTION edges. Matches
 * the bitmap compiler / SBAR Assessment bucket vocabulary
 * (``"immediate"`` | ``"2ww"`` | ``"urgent"`` | ``"routine"``).
 * ``immediate`` covers NICE "immediate specialist assessment" (e.g. NG12 1.10.2).
 */
export type RulePriority = "immediate" | "2ww" | "urgent" | "routine";

/** Dropdown options for the PriorityPanel (value + plain-English label). */
export const RULE_PRIORITIES: ReadonlyArray<{
  value: RulePriority;
  label: string;
}> = [
  { value: "immediate", label: "Immediate specialist assessment" },
  { value: "2ww", label: "2 week wait (urgent suspected cancer)" },
  { value: "urgent", label: "Urgent" },
  { value: "routine", label: "Routine" },
];

/**
 * Comparison operators supported on an OBSERVATION leaf. Mirrors the
 * ``ComparisonOperator`` Literal in
 * ``libs/guidance_schema/observation_leaf.py``.
 */
export type ObservationOperator =
  | ">="
  | "<="
  | ">"
  | "<"
  | "="
  | "between";

/**
 * N-consecutive-readings temporal pattern (for example "two PSAs more
 * than six months apart"). Mirrors ``TemporalSpec``.
 */
export interface ObservationTemporalSpec {
  count: number;
  interval_min_days: number;
  interval_max_days?: number | null;
}

/**
 * Reference-range-relative comparison (for example "above ULN").
 * Mirrors ``ReferenceRangeSpec``.
 */
export interface ObservationReferenceRangeSpec {
  bound: "upper" | "lower";
  multiple_of_range?: number;
}

/**
 * Trend / delta over a window (for example "eGFR fell 25% in the last
 * year"). Mirrors ``TrendSpec``.
 */
export interface ObservationTrendSpec {
  delta_kind: "absolute" | "percent";
  window_days: number;
}

/**
 * Mean / median / min / max of the last N readings. Mirrors
 * ``AggregateSpec``.
 */
export interface ObservationAggregateSpec {
  kind: "mean" | "median" | "min" | "max";
  lookback_n: number;
}

/**
 * Flat wire shape for the OBSERVATION leaf payload. Matches
 * ``ObservationLeaf`` in ``libs/guidance_schema/observation_leaf.py``
 * 1-for-1 so the tree can round-trip through the Pydantic validator
 * without field-name translation.
 *
 * Exactly one of ``temporal`` / ``reference_range`` / ``trend`` /
 * ``aggregation`` may be populated. All four absent means "absolute"
 * mode (default).
 */
export interface EditableObservationPayload {
  kind?: "OBSERVATION";
  observable_id: string;
  observable_term?: string;
  operator: ObservationOperator;
  value: number | [number, number];
  unit: string;
  within_days?: number;
  temporal?: ObservationTemporalSpec | null;
  reference_range?: ObservationReferenceRangeSpec | null;
  trend?: ObservationTrendSpec | null;
  aggregation?: ObservationAggregateSpec | null;
}

export interface EditableLogicNode {
  node_id: string;
  kind: LogicNodeKind;
  children?: EditableLogicNode[];
  /**
   * Immutable pathway identity (stable-identity plan section). Minted
   * once when a pathway group is first created (either backfilled on
   * load for a legacy OR-split child, or freshly minted when a new
   * pathway is added / a split produces new pathway(s)) and, unlike
   * ``node_id``, PRESERVED through ``stripNodeIds`` so it survives
   * into the persisted ``logic_tree`` and round-trips back on the next
   * load. Decoupled from the cosmetic, index-derived A/B/C letter --
   * inserting or removing a pathway never changes another pathway's
   * ``pathway_key``, even though it does change its displayed letter.
   * Only meaningful on a direct child of a pathway-split OR; absent
   * (undefined) on every other node.
   */
  pathway_key?: string;
  min?: number;
  criterion?: LogicCriterion;
  field?: string;
  operator?: string;
  value?: number | string | null;
  /** Upper bound when operator === "between". Serialised as value[1] on save. */
  value2?: number | string | null;
  unit?: string | null;
  /**
   * Optional plain-English name for a group node (Phase 2 of the
   * edit-rule wizard redesign). Rendered as the pathway card title
   * in the editor and the read-only review view; falls back to a
   * positional "Pathway A/B/C" label when absent so legacy data
   * still renders sensibly.
   *
   * Stored as ``node.name`` in the saved JSON tree. The compiler and
   * evaluator ignore unknown fields, so this round-trips through
   * ``logic_tree`` without a Cypher schema change.
   */
  name?: string;
  /**
   * OBSERVATION leaf payload (Phase 6a). Present only on nodes with
   * ``kind === "OBSERVATION"``. Authoring in the sentence canvas is
   * limited to absolute-mode scalars in v1; ingest may populate the
   * advanced modes (temporal / reference_range / trend / aggregation)
   * which the canvas then renders read-only with a hint that the
   * Advanced view is needed for structural edits.
   */
  observation?: EditableObservationPayload;
  /**
   * RULE_FIRED chained-evaluation fields (DI-8899D4F3 / DI-6AE25829).
   * referenced_rule_id: the AppropriatenessRule the author is conditioning on.
   * outcome: "fired" (prerequisite rule matched) or "not_fired" (did not match).
   * display_name: human-readable label stored at authoring time so the chip
   *   shows a name even if the referenced rule has since been renamed.
   */
  referenced_rule_id?: string;
  outcome?: "fired" | "not_fired";
  display_name?: string;
  /**
   * Marks which of a pathway's (at most two) AT_LEAST subgroups this
   * one is, when the highlight wizard's Step 3 detected BOTH a
   * marker-less lead-or cluster (e.g. "nausea or vomiting") AND a
   * trailing "any of the following" cluster in the same pathway (see
   * `PathwayRows.leadCluster`'s doc comment in wizardMapping.ts).
   * Undefined is treated as "trailing" -- the overwhelmingly common
   * single-cluster case, so existing pathways with one unmarked
   * AT_LEAST subgroup keep working unchanged. Purely a routing aid
   * for `findClusterSubgroupByRole`; the compiler and evaluator
   * ignore it like every other unknown field.
   */
  cluster_role?: "lead" | "trailing";
  /**
   * The exact text of the Step 3 (or Step 1) row this leaf was added
   * for, when it was created via the highlight-to-build wizard's
   * row-click or highlight-a-sub-phrase add flow. A picked SNOMED
   * term very often does not share any words with the guideline's own
   * wording (e.g. "Indigestion" for a row that says "treatment-
   * resistant dyspepsia"), so `buildRowResolver`'s fuzzy text match
   * alone cannot re-discover which row this leaf answers. This exact
   * string gives it a reliable, non-fuzzy way to do that. Persisted on
   * the logic-tree leaf (API ``LogicNode.source_row_text``); the
   * compiler and evaluator ignore it. Absent on leaves authored any
   * other way (AI draft, Advanced/Sentence editor).
   */
  source_row_text?: string;
}

/** Server response shape from /api/terminology/search. */
export interface ConceptSearchHit {
  snomed_concept_id: string;
  term: string;
  semantic_tag: string;
  score?: number;
}

/**
 * Server response shape from /api/terminology/prior-resolutions: how a
 * free-text phrase has already been coded elsewhere in the guidance
 * rule library. Surfaced as a soft nudge only -- a suggested default,
 * never an auto-applied pick (see the highlight-to-build wizard plan's
 * rubber-stamping-risk discussion).
 */
export interface PriorConceptResolution {
  snomed_concept_id: string;
  preferred_term: string;
  semantic_tag: string | null;
  count: number;
}

/** Patches the dialog can apply to a node. */
export type NodeUpdate =
  | { kind: "replace_concept"; nodeId: string; criterion: LogicCriterion }
  | { kind: "set_min"; nodeId: string; min: number }
  | { kind: "set_demographic"; nodeId: string; field: string; operator: string; value: string; value2?: string; unit: string | null }
  | { kind: "change_kind"; nodeId: string; newKind: LogicNodeKind }
  | { kind: "remove"; nodeId: string }
  | {
      kind: "add_concept";
      parentNodeId: string;
      criterion: LogicCriterion;
      /** See `EditableLogicNode.source_row_text`'s doc comment. */
      sourceRowText?: string;
    }
  | {
      kind: "add_group";
      parentNodeId: string;
      groupKind: "AND" | "OR" | "NOT" | "AT_LEAST";
      /** See `EditableLogicNode.cluster_role`'s doc comment -- only
       *  meaningful when `groupKind === "AT_LEAST"` and the pathway
       *  needs a SECOND, independently-graded subgroup. */
      clusterRole?: "lead" | "trailing";
      /** Initial AT_LEAST.min from the guideline quantifier (e.g. 2
       *  for "2 or more of the following"). Ignored for other kinds. */
      min?: number;
    }
  | {
      kind: "add_demographic";
      parentNodeId: string;
      /** Defaults to age when omitted. Sex seeds a sex leaf instead. */
      field?: "age" | "sex";
      /**
       * Operator/value/unit parsed from a highlighted guideline phrase
       * (see `HighlightWizard/demographicPhraseMatch.ts`), so a selection
       * like "aged 40 and over" lands with the right threshold already
       * filled in instead of the field's generic blank default. Absent
       * for the "+ Add age" / "+ Add sex" button flows, which still seed
       * the same blank defaults as before.
       */
      prefill?: {
        operator?: string;
        value?: string | number;
        value2?: string | number;
        unit?: string | null;
      };
      /** See `EditableLogicNode.source_row_text`'s doc comment. */
      sourceRowText?: string;
    }
  // -- Phase 2: optional pathway name --
  | { kind: "set_name"; nodeId: string; name: string }
  // -- Phase 6a: OBSERVATION leaf --
  | {
      kind: "add_observation";
      parentNodeId: string;
      /**
       * Phase 6b: optional seed for the new OBSERVATION leaf. When a
       * reviewer picks an observable concept in the search panel we
       * preload the observable_id / observable_term / unit so the
       * reviewer only has to fill in the operator and threshold.
       */
      seed?: Partial<EditableObservationPayload>;
    }
  | {
      kind: "set_observation";
      nodeId: string;
      observation: EditableObservationPayload;
    }
  // -- Synonym chip ops (UN-LEO-AI-093) --
  | { kind: "add_seed"; nodeId: string; seed: LogicSeed }
  | { kind: "remove_seed"; nodeId: string; conceptId: string }
  | { kind: "set_primary_seed"; nodeId: string; conceptId: string }
  | { kind: "toggle_include_descendants"; nodeId: string; conceptId: string }
  | { kind: "set_seed_distance"; nodeId: string; conceptId: string; distance: number | null }
  | { kind: "add_excluded"; nodeId: string; conceptId: string }
  | { kind: "remove_excluded"; nodeId: string; conceptId: string }
  | { kind: "replace_root"; node: EditableLogicNode }
  // -- RULE_FIRED chained evaluation (DI-8899D4F3 / DI-6AE25829) --
  | { kind: "add_rule_fired"; parentNodeId: string }
  | {
      kind: "set_rule_fired";
      nodeId: string;
      referenced_rule_id: string;
      outcome: "fired" | "not_fired";
      display_name: string;
    }
  // -- Pathway boundary revision (highlight-to-build wizard, "Split and
  // merge a pathway boundary" plan section) -- both operate on an
  // existing pathway (a direct child of the tree's pathway-split OR)
  // and its children by reference, never via assignNodeIds, so a
  // confirmed leaf's node_id / criterion survive untouched. Both always
  // mint fresh pathway_key(s) and retire the originals -- the container
  // changes shape and gets a new identity; what's inside it does not.
  | {
      kind: "split_pathway";
      /** The pathway node (OR child) to partition. */
      nodeId: string;
      /** Index into that pathway's children where the second group starts. */
      splitAt: number;
    }
  | {
      kind: "merge_pathways";
      /** Two sibling pathway nodes (both children of the same OR) to combine. */
      firstNodeId: string;
      secondNodeId: string;
    };

export const GROUP_KINDS: ReadonlyArray<LogicNodeKind> = ["AND", "OR", "NOT", "AT_LEAST"];

export const LEAF_KINDS: ReadonlyArray<LogicNodeKind> = [
  "CONCEPT",
  "DEMOGRAPHIC",
  "OBSERVATION",
];

/** Demographic field/operator vocabularies must match the backend allow-list. */
export const DEMOGRAPHIC_FIELDS = ["age", "sex"] as const;
export const DEMOGRAPHIC_OPERATORS = [">=", "<=", ">", "<", "=", "between"] as const;
