/**
 * Unit tests for recommendation picker rule selection helpers.
 *
 * Atlas: DI-EB716E68 / VT-C6B93AF0
 */

import {
  pickAttachRule,
  pickLatestRule,
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
