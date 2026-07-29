/**
 * Tests for the admin Guidance page sections -- VT-LEO-AI-066.
 *
 * Tests verify:
 * - Sections render without errors
 * - Autocomplete triggers catalogue fetch
 * - Fetch errors surface via Alert, not blank state
 * - ConfirmDialog gates approve-all before API call fires
 * - ConfirmDialog gates bitmap activation before API call fires
 * - Rule review rows and actions render reliably
 */

import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import NiceLoaderSection from "../NiceLoaderSection";
import RuleReviewSection from "../RuleReviewSection";
import BitmapLifecycleSection from "../BitmapLifecycleSection";
import GuidancePage from "../page";

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function mockFetch(
  urlHandlers: Record<string, unknown>,
  fallback: unknown = {}
) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    const urlStr = String(url);
    for (const [pattern, value] of Object.entries(urlHandlers)) {
      if (urlStr.includes(pattern)) {
        return Promise.resolve({
          ok: true,
          json: async () => value,
          text: async () => JSON.stringify(value),
        } as Response);
      }
    }
    return Promise.resolve({
      ok: true,
      json: async () => fallback,
      text: async () => JSON.stringify(fallback),
    } as Response);
  });
}

function mockFetchError(pattern: string) {
  jest.spyOn(global, "fetch").mockImplementation((url) => {
    if (String(url).includes(pattern)) {
      return Promise.resolve({
        ok: false,
        json: async () => ({ detail: "error" }),
        text: async () => "error",
      } as Response);
    }
    return Promise.resolve({
      ok: true,
      json: async () => [],
      text: async () => "[]",
    } as Response);
  });
}

// ------------------------------------------------------------------
// GuidancePage -- smoke test
// ------------------------------------------------------------------

describe("GuidancePage", () => {
  beforeEach(() => {
    mockFetch({
      "/api/nice/jobs": [],
      "/api/nice/loaded": [],
      "/api/guidance/rules/review": [],
      "/api/terminology/guidelines/bitmap/status": { active_version: null, rule_count: 0 },
      "/api/terminology/guidelines/bitmap/versions": [],
    });
  });

  it("renders three section headings", async () => {
    render(<GuidancePage />);
    await waitFor(() => {
      expect(screen.getByText(/1\. Load/i)).toBeInTheDocument();
      expect(screen.getByText(/2\. Review/i)).toBeInTheDocument();
      expect(screen.getByText(/3\. Compile/i)).toBeInTheDocument();
    });
  });

  it("keeps workflow step sections collapsed by default and opens on header click", async () => {
    render(<GuidancePage />);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /find and load a guideline/i }),
      ).toBeInTheDocument();
    });
    const loadToggle = screen.getByRole("button", {
      name: /find and load a guideline/i,
    });
    expect(loadToggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(loadToggle);
    expect(loadToggle).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("button", { name: /load this guideline/i }),
    ).toBeInTheDocument();
  });

  it("does not render its own h1 (KnowledgePageLayout provides the page heading)", () => {
    // Wave E Phase 5 redesign: GuidancePage is mounted inside
    // KnowledgePageLayout which owns the h1 + intro chrome. Asserting
    // zero h1s here guarantees we never duplicate the page heading and
    // keeps the AT outline coherent.
    render(<GuidancePage />);
    const h1s = document.querySelectorAll("h1");
    expect(h1s.length).toBe(0);
  });
});

// ------------------------------------------------------------------
// NiceLoaderSection
// ------------------------------------------------------------------

describe("NiceLoaderSection", () => {
  it("renders the guideline search input", () => {
    mockFetch({ "/api/nice/jobs": [] });
    render(<NiceLoaderSection />);
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("load button is disabled when no guideline selected", () => {
    mockFetch({ "/api/nice/jobs": [] });
    render(<NiceLoaderSection />);
    const btn = screen.getByRole("button", { name: /load this guideline/i });
    expect(btn).toBeDisabled();
  });

  it("typing triggers catalogue fetch after debounce", async () => {
    const user = userEvent.setup({ delay: null });
    mockFetch({
      "/api/nice/catalogue": [{ code: "NG151", title: "Bowel cancer", type: "cg" }],
      "/api/nice/jobs": [],
    });
    jest.useFakeTimers();
    render(<NiceLoaderSection />);
    const input = screen.getByRole("combobox");
    await user.type(input, "bow");
    jest.advanceTimersByTime(400);
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/nice/catalogue?q=bow")
      );
    });
    jest.useRealTimers();
  });

  it("shows an Alert when jobs fetch fails", async () => {
    mockFetchError("/api/nice/jobs");
    render(<NiceLoaderSection />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("shows recent jobs table when jobs are returned", async () => {
    mockFetch({
      "/api/nice/jobs": [
        { job_id: "j1", code: "NG151", status: "done", recommendation_count: 5 },
      ],
    });
    render(<NiceLoaderSection />);
    await waitFor(() => {
      expect(screen.getByText("NG151")).toBeInTheDocument();
    });
  });
});

// ------------------------------------------------------------------
// RuleReviewSection
// ------------------------------------------------------------------

const MOCK_RULE = {
  rule_id: "r1",
  name: "Refer for rectal bleeding",
  status: "pending_review",
  strength: "refer",
  guideline_id: "NG151",
  recommendation_text: "Refer patients with unexplained rectal bleeding.",
  plain_english: "Triggers when: patient HAS rectal bleeding",
  present_criteria: [{ predicate: "PRESENT", concept_id: "443416000", preferred_term: "rectal bleeding" }],
  absent_criteria: [],
};

describe("RuleReviewSection", () => {
  it("shows a helpful message when there are no pending rules", async () => {
    mockFetch({ "/api/guidance/rules/review": [] });
    render(<RuleReviewSection />);
    await waitFor(() => {
      expect(screen.getByText(/No rules awaiting review/i)).toBeInTheDocument();
    });
  });

  it("shows an Alert when the rules fetch fails", async () => {
    mockFetchError("/api/guidance/rules/review");
    render(<RuleReviewSection />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  async function openAwaitingReviewPool() {
    await waitFor(() => screen.getByRole("heading", { name: /Awaiting review/i }));
    fireEvent.click(screen.getByRole("button", { name: /Awaiting review/i }));
  }

  it("renders a pending rule row for review", async () => {
    mockFetch({ "/api/guidance/rules/review": [MOCK_RULE] });
    render(<RuleReviewSection />);
    await openAwaitingReviewPool();
    await waitFor(() => {
      expect(
        screen.getAllByText(/Refer patients with unexplained rectal bleeding\./i)
          .length,
      ).toBeGreaterThan(0);
    });
  });

  it("shows at least one action button for each rule", async () => {
    mockFetch({ "/api/guidance/rules/review": [MOCK_RULE] });
    render(<RuleReviewSection />);
    await openAwaitingReviewPool();
    await waitFor(() => {
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);
    });
  });

  it("opens ConfirmDialog before approve-all fires an API call", async () => {
    mockFetch({ "/api/guidance/rules/review": [MOCK_RULE] });
    render(<RuleReviewSection />);
    await openAwaitingReviewPool();
    await waitFor(() => screen.getByRole("button", { name: /approve all/i }));

    fireEvent.click(screen.getByRole("button", { name: /approve all/i }));

    expect(screen.getByText(/Approve all rules/i)).toBeInTheDocument();

    const mockCallsBefore = (global.fetch as jest.Mock).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect((global.fetch as jest.Mock).mock.calls.length).toBe(mockCallsBefore);
  });

  it("calls approve-all API after ConfirmDialog confirmation", async () => {
    mockFetch({
      "/api/guidance/rules/review": [MOCK_RULE],
      "approve-all": { approved_count: 1 },
    });
    render(<RuleReviewSection />);
    await openAwaitingReviewPool();
    await waitFor(() => screen.getByRole("button", { name: /approve all/i }));

    fireEvent.click(screen.getByRole("button", { name: /approve all/i }));
    fireEvent.click(screen.getByRole("button", { name: /yes, approve all/i }));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls.map(([u]) => String(u));
      expect(calls.some((u) => u.includes("approve-all"))).toBe(true);
    });
    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls.map(([u]) => String(u));
      expect(calls.filter((u) => u.includes("/api/guidance/rules/review")).length).toBeGreaterThanOrEqual(2);
    });
  });

  it("renders separate awaiting-review, approved, and excluded pools", async () => {
    mockFetch({ "/api/guidance/rules/review": [MOCK_RULE] });
    render(<RuleReviewSection />);
    await waitFor(() => {
      expect(screen.getByTestId("rule-pool-pending")).toBeInTheDocument();
      expect(screen.getByTestId("rule-pool-approved")).toBeInTheDocument();
      expect(screen.getByTestId("rule-pool-excluded")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /Awaiting review/i })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /^Approved/i })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /^Excluded/i })).toBeInTheDocument();
    });
  });

  it("loads pending, active, and rejected rules in parallel on mount", async () => {
    jest.spyOn(global, "fetch").mockImplementation((url) => {
      const u = String(url);
      if (u.includes("status=pending_review")) {
        return Promise.resolve({
          ok: true,
          json: async () => [MOCK_RULE],
        } as Response);
      }
      if (u.includes("status=active")) {
        return Promise.resolve({
          ok: true,
          json: async () => [{ ...MOCK_RULE, rule_id: "r-active", status: "active" }],
        } as Response);
      }
      if (u.includes("status=rejected")) {
        return Promise.resolve({
          ok: true,
          json: async () => [{ ...MOCK_RULE, rule_id: "r-excluded", status: "rejected" }],
        } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    });

    render(<RuleReviewSection />);
    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls.map(([u]) => String(u));
      expect(calls.some((u) => u.includes("status=pending_review"))).toBe(true);
      expect(calls.some((u) => u.includes("status=active"))).toBe(true);
      expect(calls.some((u) => u.includes("status=rejected"))).toBe(true);
    });
  });

  it("only renders Approve all in the awaiting-review pool", async () => {
    mockFetch({ "/api/guidance/rules/review": [MOCK_RULE] });
    render(<RuleReviewSection />);
    await waitFor(() => screen.getByRole("heading", { name: /Awaiting review/i }));
    // Pools start collapsed -- open Awaiting review before asserting actions.
    fireEvent.click(screen.getByRole("button", { name: /Awaiting review/i }));
    await waitFor(() => screen.getByRole("button", { name: /approve all/i }));
    expect(screen.getByTestId("rule-pool-pending")).toContainElement(
      screen.getByRole("button", { name: /approve all/i }),
    );
    expect(screen.getByTestId("rule-pool-approved")).not.toContainElement(
      screen.getByRole("button", { name: /approve all/i }),
    );
  });

  it("shows an action error Alert when approve fails", async () => {
    mockFetch({ "/api/guidance/rules/review": [MOCK_RULE] });
    jest.spyOn(global, "fetch").mockImplementation((url) => {
      const u = String(url);
      if (u.includes("approve-all")) {
        return Promise.resolve({ ok: false, text: async () => "error" } as Response);
      }
      if (u.includes("/api/guidance/rules/review")) {
        return Promise.resolve({ ok: true, json: async () => [MOCK_RULE] } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    });

    render(<RuleReviewSection />);
    await waitFor(() => screen.getByRole("heading", { name: /Awaiting review/i }));
    fireEvent.click(screen.getByRole("button", { name: /Awaiting review/i }));
    await waitFor(() => screen.getByRole("button", { name: /approve all/i }));
    fireEvent.click(screen.getByRole("button", { name: /approve all/i }));
    fireEvent.click(screen.getByRole("button", { name: /yes, approve all/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});

// ------------------------------------------------------------------
// BitmapLifecycleSection
// ------------------------------------------------------------------

describe("BitmapLifecycleSection", () => {
  it("renders the compile button", async () => {
    mockFetch({
      "/api/terminology/guidelines/bitmap/status": { active_version: null, rule_count: 0 },
      "/api/terminology/guidelines/bitmap/versions": [],
    });
    render(<BitmapLifecycleSection />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /compile candidate/i })).toBeInTheDocument();
    });
  });

  it("shows an Alert when status fetch fails", async () => {
    mockFetchError("/api/terminology/guidelines/bitmap/status");
    render(<BitmapLifecycleSection />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("shows active version chip when a version is active", async () => {
    mockFetch({
      "/api/terminology/guidelines/bitmap/status": {
        active_version: "v20260308-120000",
        rule_count: 3,
        compile_timestamp: "2026-03-08T12:00:00Z",
      },
      "/api/terminology/guidelines/bitmap/versions": [
        { version: "v20260308-120000", active: true },
      ],
    });
    render(<BitmapLifecycleSection />);
    await waitFor(() => {
      expect(screen.getAllByText("v20260308-120000").length).toBeGreaterThan(0);
    });
  });

  it("opens ConfirmDialog before activate fires an API call", async () => {
    mockFetch({
      "/api/terminology/guidelines/bitmap/status": { active_version: null, rule_count: 0 },
      "/api/terminology/guidelines/compiled": {
        versions: [{ version: "v20260308-120000", active: false }],
      },
    });
    render(<BitmapLifecycleSection />);
    await waitFor(() => screen.getByText("Make this live"));

    fireEvent.click(screen.getByText("Make this live"));
    expect(screen.getByText(/Make this version live/i)).toBeInTheDocument();

    const callsBefore = (global.fetch as jest.Mock).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect((global.fetch as jest.Mock).mock.calls.length).toBe(callsBefore);
  });

  it("calls activate API after ConfirmDialog confirmation", async () => {
    mockFetch({
      "/api/terminology/guidelines/bitmap/status": { active_version: null, rule_count: 0 },
      "/api/terminology/guidelines/compiled": {
        versions: [{ version: "v20260308-120000", active: false }],
      },
      activate: { activated: true },
    });
    render(<BitmapLifecycleSection />);
    await waitFor(() => screen.getByText("Make this live"));

    fireEvent.click(screen.getByText("Make this live"));
    fireEvent.click(screen.getByRole("button", { name: /yes, go live/i }));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls.map(([u]) => String(u));
      expect(calls.some((u) => u.includes("activate"))).toBe(true);
    });
  });

  it("shows Going live feedback while activate request is in flight", async () => {
    let resolveActivate: ((value: Response) => void) | undefined;
    const activatePromise = new Promise<Response>((resolve) => {
      resolveActivate = resolve;
    });
    jest.spyOn(global, "fetch").mockImplementation((url) => {
      const urlStr = String(url);
      if (urlStr.includes("activate")) {
        return activatePromise;
      }
      if (urlStr.includes("/api/terminology/guidelines/compiled")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            versions: [{ version: "v20260308-120000", active: false }],
          }),
          text: async () => "",
        } as Response);
      }
      if (urlStr.includes("/api/terminology/guidelines/bitmap/status")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ active_version: null, rule_count: 0 }),
          text: async () => "",
        } as Response);
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({}),
        text: async () => "{}",
      } as Response);
    });

    render(<BitmapLifecycleSection />);
    await waitFor(() => screen.getByText("Make this live"));
    fireEvent.click(screen.getByText("Make this live"));
    fireEvent.click(screen.getByRole("button", { name: /yes, go live/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Going live/i })).toBeDisabled();
      expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    });

    resolveActivate?.({
      ok: true,
      json: async () => ({ activated: true }),
      text: async () => '{"activated":true}',
    } as Response);

    await waitFor(() => {
      expect(screen.queryByText(/Make this version live/i)).not.toBeInTheDocument();
    });
  });

  it("shows a stepper with three steps", async () => {
    mockFetch({
      "/api/terminology/guidelines/bitmap/status": { active_version: null, rule_count: 0 },
      "/api/terminology/guidelines/bitmap/versions": [],
    });
    render(<BitmapLifecycleSection />);
    await waitFor(() => {
      expect(screen.getByText("Rules approved")).toBeInTheDocument();
      expect(screen.getAllByText("Compile candidate").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Test and go live")).toBeInTheDocument();
    });
  });
});
