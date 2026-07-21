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
  filterRulesForReview,
  formatApiDetail,
  formatRelativeUpdatedAt,
  mergeEditedRuleIntoCache,
  ruleReviewKey,
  sortRulesForStatus,
  upsertApprovedRule,
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
        logic_tree: NEW_LOGIC_TREE_WITH_EXTRA_SEEDS,
      },
    );

    expect(merged.rule_id).toBe("r1:edit:abcd1234");
    expect(merged.status).toBe("active");
  });

  it("keeps the pre-edit actions when the reviewer did not change them", () => {
    const merged = mergeEditedRuleIntoCache(
      PRE_EDIT_RULE,
      "r1:edit:abcd1234",
      {
        name: PRE_EDIT_RULE.name,
        logic_tree: NEW_LOGIC_TREE_WITH_EXTRA_SEEDS,
      },
    );

    // Mirrors BE behaviour: _decide_rule_with_edits coalesces a null
    // actions payload back to the predecessor's actionJson so a
    // recommendation never silently loses its coded procedures.
    expect(merged.actions).toBeUndefined();
    expect(merged.action?.snomed_concept_id).toBe("710081004");
  });

  it("overlays the new actions array when the reviewer changed it", () => {
    const merged = mergeEditedRuleIntoCache(
      PRE_EDIT_RULE,
      "r1:edit:abcd1234",
      {
        name: PRE_EDIT_RULE.name,
        logic_tree: NEW_LOGIC_TREE_WITH_EXTRA_SEEDS,
        actions: [
          {
            criterion: {
              snomed_concept_id: "313306003",
              preferred_term: "Refer to smoking cessation clinic",
            },
            strength: "refer",
          },
        ],
      },
    );

    expect(merged.actions?.[0]?.criterion.snomed_concept_id).toBe(
      "313306003",
    );
    expect(merged.actions?.[0]?.criterion.preferred_term).toBe(
      "Refer to smoking cessation clinic",
    );
    // The derived top-level strength field mirrors actions[0].strength.
    expect(merged.strength).toBe("refer");
  });

  it("falls back to the pre-edit name and strength when the payload omits them", () => {
    // (kept below)
  });
});

describe("RuleReviewSection recommendation-level de-duping", () => {
  const rule112a = {
    ...PRE_EDIT_RULE,
    rule_id: "rule-ng12-112-a",
    guideline_id: "NG12",
    recommendation_text: "1.1.2 Offer an urgent chest X-ray.",
  };
  const rule112b = {
    ...PRE_EDIT_RULE,
    rule_id: "rule-ng12-112-b",
    guideline_id: "NG12",
    recommendation_text: "1.1.2 Offer an urgent chest X-ray.",
  };
  const rule113 = {
    ...PRE_EDIT_RULE,
    rule_id: "rule-ng12-113",
    guideline_id: "NG12",
    recommendation_text: "1.1.3 Consider an urgent chest X-ray.",
  };

  it("uses the NICE recommendation number as the stable review key", () => {
    expect(ruleReviewKey(rule112a)).toBe(ruleReviewKey(rule112b));
    expect(ruleReviewKey(rule112a)).not.toBe(ruleReviewKey(rule113));
  });

  it("keeps one approved card per NICE recommendation", () => {
    const approved = upsertApprovedRule([rule112a], rule112b);

    expect(approved).toHaveLength(1);
    expect(approved[0].rule_id).toBe("rule-ng12-112-b");
  });

  it("hides pending duplicates already approved in this session", () => {
    const visible = filterRulesForReview(
      [rule112a, rule112b, rule113],
      [rule112a],
      "pending_review",
    );

    expect(visible.map((rule) => rule.rule_id)).toEqual(["rule-ng12-113"]);
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
// Static-source VT: dual review pools with search and pagination
// ---------------------------------------------------------------------------

const RULE_REVIEW_POOL_SOURCE = fs.readFileSync(
  path.resolve(__dirname, "../RuleReviewPool.tsx"),
  "utf-8",
);

describe("RuleReviewSection -- dual pools (Tier 1)", () => {
  it("declares pending and active status filter values for card accents", () => {
    const typesSource = fs.readFileSync(
      path.resolve(__dirname, "../ruleReviewTypes.ts"),
      "utf-8",
    );
    expect(typesSource).toMatch(
      /export type RuleStatusFilter = "pending_review" \| "active" \| "superseded";/,
    );
  });

  it("loads pending and active rule pools in parallel", () => {
    const helpersSource = fs.readFileSync(
      path.resolve(__dirname, "../ruleReviewHelpers.ts"),
      "utf-8",
    );
    expect(helpersSource).toMatch(/export async function fetchRules\(status: RuleStatusFilter\)/);
    expect(RULE_REVIEW_SOURCE).toMatch(/fetchRules\("pending_review"\)/);
    expect(RULE_REVIEW_SOURCE).toMatch(/fetchRules\("active"\)/);
    expect(RULE_REVIEW_SOURCE).toMatch(/Promise\.all\(\[/);
  });

  it("renders separate awaiting-review and approved pools", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(/poolId="pending"/);
    expect(RULE_REVIEW_SOURCE).toMatch(/title="Awaiting review"/);
    expect(RULE_REVIEW_SOURCE).toMatch(/poolId="approved"/);
    expect(RULE_REVIEW_SOURCE).toMatch(/title="Approved"/);
  });

  it("scopes Approve all to the awaiting-review pool only", () => {
    expect(RULE_REVIEW_POOL_SOURCE).toMatch(/showApproveAll/);
    expect(RULE_REVIEW_SOURCE).toMatch(/showApproveAll/);
    expect(RULE_REVIEW_SOURCE).not.toMatch(/ToggleButtonGroup/);
  });

  it("passes approve and reject handlers only to the pending pool", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(/onApprove=\{\(rule\) => decide\(rule, "approve"\)\}/);
    expect(RULE_REVIEW_SOURCE).toMatch(/onReject=\{\(rule\) => decide\(rule, "reject", "Rejected by reviewer"\)\}/);
  });

  it("lazy-loads superseded history behind a disclosure control", () => {
    expect(RULE_REVIEW_SOURCE).toMatch(/Show superseded history/);
    expect(RULE_REVIEW_SOURCE).toMatch(/fetchRules\("superseded"\)/);
  });

  it("declares Rule.updated_at / reviewed_at / reviewed_by so the FE can sort and label staleness", () => {
    const typesSource = fs.readFileSync(
      path.resolve(__dirname, "../ruleReviewTypes.ts"),
      "utf-8",
    );
    expect(typesSource).toMatch(/created_at\?: string;/);
    expect(typesSource).toMatch(/updated_at\?: string;/);
    expect(typesSource).toMatch(/reviewed_at\?: string;/);
    expect(typesSource).toMatch(/reviewed_by\?: string;/);
  });
});

describe("RuleReviewPool -- search, filters, pagination", () => {
  it("renders FilterBar search and pagination controls", () => {
    expect(RULE_REVIEW_POOL_SOURCE).toMatch(/<FilterBar/);
    expect(RULE_REVIEW_POOL_SOURCE).toMatch(/<Pagination/);
    expect(RULE_REVIEW_POOL_SOURCE).toMatch(/ruleMatchesSearch/);
  });

  it("filters by guideline and action type", () => {
    expect(RULE_REVIEW_POOL_SOURCE).toMatch(/filterRulesByGuideline/);
    expect(RULE_REVIEW_POOL_SOURCE).toMatch(/filterRulesByStrength/);
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
