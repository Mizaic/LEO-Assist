/**
 * Unit tests for recommendation picker rule selection helpers.
 *
 * Atlas: DI-EB716E68 / VT-C6B93AF0
 */

import {
  attachBadgeLabel,
  pickAttachRule,
  pickLatestRule,
  recHasApprovedRule,
  recHasCompiledRule,
  selectMatchingRecs,
} from "../recommendationPickerSelection";

describe("pickLatestRule", () => {
  test("returns null for empty list", () => {
    expect(pickLatestRule([])).toBeNull();
  });

  test("picks newest created_at", () => {
    const latest = pickLatestRule([
      { rule_id: "old", status: "active", created_at: "2024-01-01T00:00:00Z" },
      {
        rule_id: "new",
        status: "pending_review",
        created_at: "2025-06-01T00:00:00Z",
      },
      {
        rule_id: "mid",
        status: "superseded",
        created_at: "2024-06-01T00:00:00Z",
      },
    ]);
    expect(latest?.rule_id).toBe("new");
  });

  test("falls back to status rank when timestamps missing", () => {
    const latest = pickLatestRule([
      { rule_id: "rej", status: "rejected" },
      { rule_id: "act", status: "active" },
      { rule_id: "sup", status: "superseded" },
    ]);
    expect(latest?.rule_id).toBe("act");
  });
});

describe("pickAttachRule", () => {
  test("prefers active even when a newer rejected exists", () => {
    const chosen = pickAttachRule([
      {
        rule_id: "approved",
        status: "active",
        created_at: "2024-01-01T00:00:00Z",
      },
      {
        rule_id: "later-reject",
        status: "rejected",
        created_at: "2025-01-01T00:00:00Z",
      },
    ]);
    expect(chosen?.rule_id).toBe("approved");
  });

  test("uses latest when no active rule", () => {
    const chosen = pickAttachRule([
      {
        rule_id: "old",
        status: "superseded",
        created_at: "2024-01-01T00:00:00Z",
      },
      {
        rule_id: "pending",
        status: "pending_review",
        created_at: "2025-01-01T00:00:00Z",
      },
    ]);
    expect(chosen?.rule_id).toBe("pending");
  });
});

describe("attachBadgeLabel", () => {
  test("labels approved + compiled when active and in bitmap", () => {
    expect(attachBadgeLabel("active", true)).toBe("approved + compiled");
  });

  test("labels approved when active but not in bitmap", () => {
    expect(attachBadgeLabel("active", false)).toBe("approved");
  });
});

describe("selectMatchingRecs / approved / compiled filters", () => {
  const recs = [
    {
      rec_id: "a",
      is_normative: true,
      rules: [{ rule_id: "rule-a", status: "active" }],
    },
    {
      rec_id: "b",
      is_normative: true,
      rules: [{ rule_id: "rule-b", status: "active" }],
    },
    {
      rec_id: "c",
      is_normative: true,
      rules: [{ rule_id: "rule-c", status: "pending_review" }],
    },
  ];

  test("recHasApprovedRule only matches active attach rules", () => {
    expect(recHasApprovedRule(recs[0])).toBe(true);
    expect(recHasApprovedRule(recs[2])).toBe(false);
  });

  test("recHasCompiledRule matches only ids in the compiled set", () => {
    const compiled = new Set(["rule-a"]);
    expect(recHasCompiledRule(recs[0], compiled)).toBe(true);
    expect(recHasCompiledRule(recs[1], compiled)).toBe(false);
  });

  test("selectMatchingRecs checks only matching recs", () => {
    const prev = {
      a: { checked: false, mode: "ai" as const },
      b: { checked: false, mode: "ai" as const },
      c: { checked: true, mode: "ai" as const },
    };
    const next = selectMatchingRecs(prev, recs, recHasApprovedRule);
    expect(next.a.checked).toBe(true);
    expect(next.b.checked).toBe(true);
    expect(next.c.checked).toBe(true);
  });
});
