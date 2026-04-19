/**
 * Regression test for the in-session edit cache (RuleReviewSection).
 *
 * Bug: when a reviewer added extra synonym seeds to a CONCEPT chip and
 * saved, the BE persisted the new logic_tree but the in-session
 * `sessionApproved` cache spread the PRE-edit `editRule` and only
 * overlayed `name` / `strength`, dropping the new seeds. Re-opening the
 * rule in the same session showed the original concept only -- looking
 * exactly like a persistence failure even though Neo4j had the new tree.
 *
 * Fix: `mergeEditedRuleIntoCache` always overlays `logic_tree` from the
 * payload (the dialog is the source of truth for the new tree) and
 * overlays `action` only when the reviewer changed it (mirroring the
 * BE's coalesce-on-null behaviour in _decide_rule_with_edits).
 *
 * Pinning the helper directly is intentional: a future refactor of
 * handleSaveEdit cannot quietly drop these fields again without breaking
 * this test.
 */

import {
  formatApiDetail,
  formatRelativeUpdatedAt,
  mergeEditedRuleIntoCache,
  sortRulesForStatus,
} from "../RuleReviewSection";

const PRE_EDIT_RULE = {
  rule_id: "r1",
  name: "Smoker check",
  status: "pending_review",
  strength: "consider",
  guideline_id: "NG12",
  recommendation_text: "Offer smoking cessation.",
  plain_english: "Triggers when: patient HAS smoker",
  present_criteria: [
    { predicate: "PRESENT", concept_id: "77176002", preferred_term: "Smoker" },
  ],
  absent_criteria: [],
  has_predecessor: false,
  logic_tree: {
    kind: "AND",
    children: [
      {
        kind: "CONCEPT",
        criterion: {
          snomed_concept_id: "77176002",
          preferred_term: "Smoker",
          seeds: [{ snomed_concept_id: "77176002", preferred_term: "Smoker" }],
          primary_concept_id: "77176002",
          excluded_concept_ids: [],
        },
      },
    ],
  },
  action: {
    snomed_concept_id: "710081004",
    preferred_term: "Smoking cessation advice",
  },
};

const NEW_LOGIC_TREE_WITH_EXTRA_SEEDS = {
  kind: "AND",
  children: [
    {
      kind: "CONCEPT",
      criterion: {
        snomed_concept_id: "77176002",
        preferred_term: "Smoker",
        seeds: [
          { snomed_concept_id: "77176002", preferred_term: "Smoker" },
          { snomed_concept_id: "266919005", preferred_term: "Cigarette smoker" },
          { snomed_concept_id: "230063004", preferred_term: "Pipe smoker" },
        ],
        primary_concept_id: "77176002",
        excluded_concept_ids: ["56294008"],
      },
    },
  ],
};

describe("mergeEditedRuleIntoCache (synonym-set persistence regression)", () => {
  it("overlays the new logic_tree from the payload, not the pre-edit one", () => {
    const merged = mergeEditedRuleIntoCache(
      PRE_EDIT_RULE,
      "r1:edit:abcd1234",
      {
        name: PRE_EDIT_RULE.name,
        strength: PRE_EDIT_RULE.strength,
        logic_tree: NEW_LOGIC_TREE_WITH_EXTRA_SEEDS,
      },
    );

    // The cached row MUST carry the new tree (with all three seeds), not
    // the pre-edit single-seed tree.
    expect(merged.logic_tree).toBe(NEW_LOGIC_TREE_WITH_EXTRA_SEEDS);
    const conceptNode =
      (merged.logic_tree as { children: Array<{ criterion: { seeds: unknown[] } }> })
        .children[0];
    expect(conceptNode.criterion.seeds).toHaveLength(3);
  });

  it("forwards excluded_concept_ids the reviewer just added", () => {
    const merged = mergeEditedRuleIntoCache(
      PRE_EDIT_RULE,
      "r1:edit:abcd1234",
      {
        name: PRE_EDIT_RULE.name,
        strength: PRE_EDIT_RULE.strength,
        logic_tree: NEW_LOGIC_TREE_WITH_EXTRA_SEEDS,
      },
    );

    const conceptNode =
      (merged.logic_tree as {
        children: Array<{ criterion: { excluded_concept_ids: string[] } }>;
      }).children[0];
    expect(conceptNode.criterion.excluded_concept_ids).toEqual(["56294008"]);
  });

  it("flips the cached status to active and adopts the new rule_id", () => {
    const merged = mergeEditedRuleIntoCache(
      PRE_EDIT_RULE,
      "r1:edit:abcd1234",
      {
        name: PRE_EDIT_RULE.name,
        strength: PRE_EDIT_RULE.strength,
        logic_tree: NEW_LOGIC_TREE_WITH_EXTRA_SEEDS,
      },
    );

    expect(merged.rule_id).toBe("r1:edit:abcd1234");
    expect(merged.status).toBe("active");
  });

  it("keeps the pre-edit action when the reviewer did not change it", () => {
    const merged = mergeEditedRuleIntoCache(
      PRE_EDIT_RULE,
      "r1:edit:abcd1234",
      {
        name: PRE_EDIT_RULE.name,
        strength: PRE_EDIT_RULE.strength,
        logic_tree: NEW_LOGIC_TREE_WITH_EXTRA_SEEDS,
      },
    );

    // Mirrors BE behaviour: _decide_rule_with_edits coalesces null
    // action_json back to the predecessor's action so a recommendation
    // never silently loses its coded action.
    expect(merged.action?.snomed_concept_id).toBe("710081004");
  });

  it("overlays the new action when the reviewer changed it", () => {
    const merged = mergeEditedRuleIntoCache(
      PRE_EDIT_RULE,
      "r1:edit:abcd1234",
      {
        name: PRE_EDIT_RULE.name,
        strength: PRE_EDIT_RULE.strength,
        logic_tree: NEW_LOGIC_TREE_WITH_EXTRA_SEEDS,
        action: {
          snomed_concept_id: "313306003",
          preferred_term: "Refer to smoking cessation clinic",
        },
      },
    );

    expect(merged.action?.snomed_concept_id).toBe("313306003");
    expect(merged.action?.preferred_term).toBe(
      "Refer to smoking cessation clinic",
    );
  });

  it("falls back to the pre-edit name and strength when the payload omits them", () => {
    // (kept below)
  });
});

describe("formatApiDetail (Pydantic 422 readable error regression)", () => {
  it("renders an array of validation errors as a readable, joined string", () => {
    // Real shape produced by a FastAPI 422 -- previously stringified as
    // "[object Object],[object Object],..." which hid the cause.
    const detail = [
      {
        type: "extra_forbidden",
        loc: ["body", "updates", "logic_tree", "criterion", "source_text"],
        msg: "Extra inputs are not permitted",
      },
      {
        type: "extra_forbidden",
        loc: ["body", "updates", "logic_tree", "criterion", "candidates"],
        msg: "Extra inputs are not permitted",
      },
    ];

    const out = formatApiDetail(detail);

    expect(out).not.toMatch(/\[object Object\]/);
    expect(out).toMatch(/source_text/);
    expect(out).toMatch(/candidates/);
    expect(out).toMatch(/Extra inputs are not permitted/);
    // "body" / "updates" prefixes are stripped from the loc path so the
    // message is intelligible to a non-engineer reviewer.
    expect(out).not.toMatch(/^body\./);
  });

  it("passes a plain-string detail through unchanged", () => {
    expect(formatApiDetail("Rule not found")).toBe("Rule not found");
  });

  it("never returns the literal string '[object Object]' for unexpected shapes", () => {
    const out = formatApiDetail({ unexpected: { nested: "shape" } });
    expect(out).not.toMatch(/\[object Object\]/);
    expect(out.length).toBeGreaterThan(0);
  });

  it("returns an empty string for null / undefined so callers fall back to statusText", () => {
    expect(formatApiDetail(null)).toBe("");
    expect(formatApiDetail(undefined)).toBe("");
  });
});

describe("mergeEditedRuleIntoCache name/strength fallback", () => {
  it("falls back to the pre-edit name and strength when the payload omits them", () => {
    const merged = mergeEditedRuleIntoCache(
      PRE_EDIT_RULE,
      "r1:edit:abcd1234",
      {
        name: "",
        strength: "",
        logic_tree: NEW_LOGIC_TREE_WITH_EXTRA_SEEDS,
      },
    );

    expect(merged.name).toBe(PRE_EDIT_RULE.name);
    expect(merged.strength).toBe(PRE_EDIT_RULE.strength);
  });
});

// ---------------------------------------------------------------------------
// Static-source VT: "Approved in this session" exposes an Edit affordance
// ---------------------------------------------------------------------------
//
// Bug: once a reviewer clicked "Looks right" on a pending rule, the rule
// landed in the "Approved in this session" card with ONLY an "Add to
// domain" button -- there was no UI route back into EditRuleDialog. The
// BE has always supported editing active rules
// (apply_rule_edit accepts predecessor status in
// {pending_review, active}), so this was purely a missing FE affordance
// and the practical effect was: "approve, notice a mistake, can't fix
// without reloading and finding another surface." The fix wires
// setEditRule(rule) into a primary-coloured Edit button placed inside
// the same action Stack as Add to domain, kept visible whether or not
// the rule has been promoted to a domain.
//
// Static-source assertions (per ui-testing.mdc convention) because
// RuleReviewSection mounts a /api/guidance/rules/review fetch on
// render; we assert the structural invariants of the new affordance
// directly against the source string.

import * as fs from "fs";
import * as path from "path";

const RULE_REVIEW_SOURCE = fs.readFileSync(
  path.resolve(__dirname, "../RuleReviewSection.tsx"),
  "utf-8",
);

describe("RuleReviewSection -- Edit affordance on the approved card", () => {
  it("imports an Edit icon for the approved-card affordance", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(
      /import EditOutlinedIcon from "@mui\/icons-material\/EditOutlined";/,
    );
  });

  it("wires an Edit button inside the Approved-in-this-session card", () => {
    // The button MUST appear after the "Approved in this session"
    // heading so it is part of the approved card, not the pending list.
    const approvedSectionStart = RULE_REVIEW_SOURCE.indexOf(
      "Approved in this session",
    );
    expect(approvedSectionStart).toBeGreaterThan(-1);
    const approvedSection = RULE_REVIEW_SOURCE.slice(approvedSectionStart);

    expect(approvedSection).toMatch(
      /onClick=\{\(\) => setEditRule\(rule\)\}/,
    );
    expect(approvedSection).toMatch(
      /aria-label=\{`Edit approved rule \$\{rule\.rule_id\}`\}/,
    );
    expect(approvedSection).toMatch(/<EditOutlinedIcon/);
  });

  it("keeps the Edit button visible regardless of promotion state", () => {
    // The Edit button MUST sit OUTSIDE the
    // promotedRules[rule.rule_id] ? Alert : Add-to-domain ternary so
    // that an author can still tighten a rule after it has been added
    // to a domain (e.g. the domain promotion was correct but the
    // criteria need narrowing).
    const approvedSectionStart = RULE_REVIEW_SOURCE.indexOf(
      "Approved in this session",
    );
    const approvedSection = RULE_REVIEW_SOURCE.slice(approvedSectionStart);
    const editButtonIdx = approvedSection.indexOf(
      "aria-label={`Edit approved rule",
    );
    const ternaryIdx = approvedSection.indexOf("promotedRules[rule.rule_id] ?");
    expect(editButtonIdx).toBeGreaterThan(-1);
    expect(ternaryIdx).toBeGreaterThan(-1);
    // The Edit button MUST be declared before the ternary inside the
    // same action Stack so it always renders.
    expect(editButtonIdx).toBeLessThan(ternaryIdx);
  });
});

// ---------------------------------------------------------------------------
// Static-source VT: Pending / Active / Superseded status filter (Tier 1)
// ---------------------------------------------------------------------------
//
// Bug: previously the Review section hard-coded
// /api/guidance/rules/review?status=pending_review which meant a
// reviewer could not find -- let alone edit -- a rule that had already
// been approved in a prior session. The BE always supported any
// status via the ?status= query param and apply_rule_edit always
// accepted predecessor status in {pending_review, active}; this was a
// purely missing FE surface.
//
// Fix: a ToggleButtonGroup with three options -- Pending review /
// Active / Superseded -- drives the fetch URL. The accordion list
// re-uses RuleAccordionCard with status-aware affordances:
//   - Pending review: Looks right + Edit + Reject (today's behaviour)
//   - Active        : Edit only
//   - Superseded    : Edit only (Tier 3 will add Restore)
// Approve-all stays scoped to Pending review.

describe("RuleReviewSection -- status filter (Tier 1)", () => {
  it("declares the three filter values that map to BE statuses", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(
      /export type RuleStatusFilter = "pending_review" \| "active" \| "superseded";/,
    );
    // STATUS_FILTER_OPTIONS list MUST contain exactly the three labels
    // the reviewer sees, in this order (mirrors the BE statuses and
    // the rule lifecycle: pending -> active -> superseded).
    const optionsBlock = RULE_REVIEW_SOURCE.slice(
      RULE_REVIEW_SOURCE.indexOf("STATUS_FILTER_OPTIONS"),
      RULE_REVIEW_SOURCE.indexOf("export default function RuleReviewSection"),
    );
    expect(optionsBlock).toMatch(/value: "pending_review",[\s\S]*?label: "Pending review"/);
    expect(optionsBlock).toMatch(/value: "active",[\s\S]*?label: "Active"/);
    expect(optionsBlock).toMatch(/value: "superseded",[\s\S]*?label: "Superseded"/);
  });

  it("forwards the selected status to the BE list endpoint", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(
      /fetch\(`\/api\/guidance\/rules\/review\?status=\$\{statusFilter\}`\)/,
    );
    // The effect MUST re-fetch when statusFilter changes (otherwise
    // switching tabs would leave the previous list rendered).
    expect(RULE_REVIEW_SOURCE).toMatch(
      /\}, \[refreshKey, internalKey, statusFilter\]\);/,
    );
  });

  it("defaults to pending_review so today's flow is unchanged on first paint", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(
      /useState<RuleStatusFilter>\(\s*"pending_review",?\s*\)/,
    );
  });

  it("renders the ToggleButtonGroup with an aria-label for screen readers", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(
      /<ToggleButtonGroup[\s\S]*?aria-label="Filter rules by status"/,
    );
  });

  it("never lands the user in an empty 'no filter selected' state", () => {
    // ToggleButtonGroup with exclusive emits null when the active
    // option is clicked again -- the handler MUST guard against that
    // and keep the previous filter set.
    expect(RULE_REVIEW_SOURCE).toMatch(
      /if \(next\) setStatusFilter\(next as RuleStatusFilter\);/,
    );
  });

  it("hides Approve-all when not viewing the pending list", () => {
    // Approve-all is a bulk decision endpoint that only makes sense
    // for pending_review rules; for active or superseded lists it is
    // either a no-op or actively dangerous, so it must not render.
    expect(RULE_REVIEW_SOURCE).toMatch(
      /\{statusFilter === "pending_review" && \([\s\S]*?Approve all[\s\S]*?\)\}/,
    );
  });

  it("hides Looks right and Reject for non-pending rules", () => {
    // The accordion card receives undefined for onApprove / onReject
    // when statusFilter !== 'pending_review' -- the card already
    // (RuleAccordionCardProps) renders the corresponding button only
    // when the handler is supplied, so omitting them suppresses the
    // affordance without duplicating the markup.
    expect(RULE_REVIEW_SOURCE).toMatch(
      /onApprove=\{\s*statusFilter === "pending_review"\s*\? \(\) => decide\(rule, "approve"\)\s*: undefined,?\s*\}/,
    );
    expect(RULE_REVIEW_SOURCE).toMatch(
      /onReject=\{\s*statusFilter === "pending_review"\s*\? \(\) => decide\(rule, "reject", "Rejected by reviewer"\)\s*: undefined,?\s*\}/,
    );
  });

  it("keeps the Edit affordance on every status (so any rule can be edited)", () => {
    // onEdit is unconditional in the JSX; the BE accepts predecessor
    // status in {pending_review, active}, and the dialog drives the
    // edit through handleSaveEdit which is status-agnostic.
    expect(RULE_REVIEW_SOURCE).toMatch(/onEdit=\{\(\) => setEditRule\(rule\)\}/);
  });

  it("makes RuleAccordionCard's onApprove / onReject optional so the same card serves all three lists", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(/onApprove\?: \(\) => void;/);
    expect(RULE_REVIEW_SOURCE).toMatch(/onReject\?: \(\) => void;/);
  });

  it("declares Rule.updated_at / reviewed_at / reviewed_by so the FE can sort and label staleness (DI-LEO-AI-528 AC-001 / AC-002)", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(/created_at\?: string;/);
    expect(RULE_REVIEW_SOURCE).toMatch(/updated_at\?: string;/);
    expect(RULE_REVIEW_SOURCE).toMatch(/reviewed_at\?: string;/);
    expect(RULE_REVIEW_SOURCE).toMatch(/reviewed_by\?: string;/);
  });

  it("renders the per-row 'Updated <relative>' hint via formatRelativeUpdatedAt (DI-LEO-AI-528 AC-002)", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(
      /data-testid="rule-updated-relative"[\s\S]*?formatRelativeUpdatedAt\(rule\.updated_at\)/,
    );
  });

  it("sorts the rendered list with sortRulesForStatus(rules, statusFilter) so Active surfaces stalest first (DI-LEO-AI-528 AC-001)", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(
      /sortRulesForStatus\(rules, statusFilter\)\.map\(\(rule\) => \(/,
    );
  });

  it("gives each filter chip a tooltip explaining what it shows", () => {
    // Tooltips are critical for first-time reviewers who have not
    // seen the rule lifecycle before -- "Superseded" especially is
    // jargon. Per health-literacy.mdc: tooltips MUST explain "why",
    // not just "what".
    const optionsBlock = RULE_REVIEW_SOURCE.slice(
      RULE_REVIEW_SOURCE.indexOf("STATUS_FILTER_OPTIONS"),
      RULE_REVIEW_SOURCE.indexOf("export default function RuleReviewSection"),
    );
    expect(optionsBlock).toMatch(/helper:[\s\S]*?Pending review/);
    expect(optionsBlock).toMatch(/helper:[\s\S]*?Active/);
    expect(optionsBlock).toMatch(/helper:[\s\S]*?Superseded/);
  });
});

// ---- formatRelativeUpdatedAt + sortRulesForStatus (DI-LEO-AI-528) -----------
//
// These are pure helpers; we drive them with a fixed `now` so the tests
// are deterministic across CI runs and time-zones. The hint copy MUST
// stay short and unambiguous (no "a few", no future tense) so the
// Active list scans at a glance.

describe("RuleReviewSection -- formatRelativeUpdatedAt", () => {
  const NOW = new Date("2026-04-19T12:00:00Z");

  it("returns an empty string for missing / unparseable input", () => {
    expect(formatRelativeUpdatedAt(undefined, NOW)).toBe("");
    expect(formatRelativeUpdatedAt(null, NOW)).toBe("");
    expect(formatRelativeUpdatedAt("", NOW)).toBe("");
    expect(formatRelativeUpdatedAt("not-a-date", NOW)).toBe("");
  });

  it("renders sub-minute deltas (and future timestamps) as 'just now'", () => {
    // Future timestamps should never produce negative-time copy --
    // clock skew between BE and FE is real and we never want to
    // confuse a reviewer with "Updated -2 minutes ago".
    expect(formatRelativeUpdatedAt("2026-04-19T11:59:30Z", NOW)).toBe(
      "Updated just now",
    );
    expect(formatRelativeUpdatedAt("2026-04-19T12:05:00Z", NOW)).toBe(
      "Updated just now",
    );
  });

  it("singularises 1 minute / 1 hour / 1 day / 1 month / 1 year", () => {
    expect(formatRelativeUpdatedAt("2026-04-19T11:59:00Z", NOW)).toBe(
      "Updated 1 minute ago",
    );
    expect(formatRelativeUpdatedAt("2026-04-19T11:00:00Z", NOW)).toBe(
      "Updated 1 hour ago",
    );
    expect(formatRelativeUpdatedAt("2026-04-18T12:00:00Z", NOW)).toBe(
      "Updated 1 day ago",
    );
    expect(formatRelativeUpdatedAt("2026-03-19T12:00:00Z", NOW)).toBe(
      "Updated 1 month ago",
    );
    expect(formatRelativeUpdatedAt("2025-04-19T11:00:00Z", NOW)).toBe(
      "Updated 1 year ago",
    );
  });

  it("renders multi-unit deltas with plurals", () => {
    expect(formatRelativeUpdatedAt("2026-04-19T11:55:00Z", NOW)).toBe(
      "Updated 5 minutes ago",
    );
    expect(formatRelativeUpdatedAt("2026-04-19T09:00:00Z", NOW)).toBe(
      "Updated 3 hours ago",
    );
    expect(formatRelativeUpdatedAt("2026-04-12T12:00:00Z", NOW)).toBe(
      "Updated 7 days ago",
    );
  });
});

describe("RuleReviewSection -- sortRulesForStatus", () => {
  const RULES = [
    { rule_id: "r-young", updated_at: "2026-04-19T11:00:00Z" },
    { rule_id: "r-stale", updated_at: "2026-01-01T00:00:00Z" },
    { rule_id: "r-newest", updated_at: "2026-04-19T11:55:00Z" },
  ];

  it("preserves BE order when the filter is pending_review or superseded", () => {
    expect(sortRulesForStatus(RULES, "pending_review").map((r) => r.rule_id)).toEqual([
      "r-young",
      "r-stale",
      "r-newest",
    ]);
    expect(sortRulesForStatus(RULES, "superseded").map((r) => r.rule_id)).toEqual([
      "r-young",
      "r-stale",
      "r-newest",
    ]);
  });

  it("reorders Active list stalest-first by updated_at", () => {
    expect(sortRulesForStatus(RULES, "active").map((r) => r.rule_id)).toEqual([
      "r-stale",
      "r-young",
      "r-newest",
    ]);
  });

  it("does not mutate the input array", () => {
    const input = [...RULES];
    const before = input.map((r) => r.rule_id);
    sortRulesForStatus(input, "active");
    expect(input.map((r) => r.rule_id)).toEqual(before);
  });

  it("breaks ties on rule_id so the order is deterministic across renders", () => {
    const tied = [
      { rule_id: "r-b", updated_at: "2026-01-01T00:00:00Z" },
      { rule_id: "r-a", updated_at: "2026-01-01T00:00:00Z" },
    ];
    expect(sortRulesForStatus(tied, "active").map((r) => r.rule_id)).toEqual([
      "r-a",
      "r-b",
    ]);
  });

  it("treats missing / unparseable updated_at as epoch zero so legacy rules surface first", () => {
    const mixed = [
      { rule_id: "r-modern", updated_at: "2026-04-19T00:00:00Z" },
      { rule_id: "r-legacy" },
    ];
    expect(sortRulesForStatus(mixed, "active").map((r) => r.rule_id)).toEqual([
      "r-legacy",
      "r-modern",
    ]);
  });
});
