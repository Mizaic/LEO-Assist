/**
 * Tests for the admin Guidance page sections -- VT-LEO-AI-066.
 *
 * Tests verify:
 * - Sections render without errors
 * - Autocomplete triggers catalogue fetch
 * - Fetch errors surface via Alert, not blank state
 * - ConfirmDialog gates approve-all before API call fires
 * - ConfirmDialog gates bitmap activation before API call fires
 * - Plain-English rule text is shown, not raw SNOMED IDs
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
      "/api/guidance/rules/review": [],
      "/api/terminology/guidelines/bitmap/status": { active_version: null, rule_count: 0 },
      "/api/terminology/guidelines/bitmap/versions": [],
    });
  });

  it("renders three section headings", async () => {
    render(<GuidancePage />);
    await waitFor(() => {
      expect(screen.getByText(/Step 1/i)).toBeInTheDocument();
      expect(screen.getByText(/Step 2/i)).toBeInTheDocument();
      expect(screen.getByText(/Step 3/i)).toBeInTheDocument();
    });
  });

  it("has a single h1 element (accessibility requirement)", () => {
    render(<GuidancePage />);
    const h1s = document.querySelectorAll("h1");
    expect(h1s.length).toBe(1);
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
      expect(screen.getByText(/No rules waiting for review/i)).toBeInTheDocument();
    });
  });

  it("shows an Alert when the rules fetch fails", async () => {
    mockFetchError("/api/guidance/rules/review");
    render(<RuleReviewSection />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("displays plain-English criteria text, not raw SNOMED IDs", async () => {
    mockFetch({ "/api/guidance/rules/review": [MOCK_RULE] });
    render(<RuleReviewSection />);
    await waitFor(() => {
      expect(screen.getByText(/patient HAS rectal bleeding/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/443416000/)).not.toBeInTheDocument();
  });

  it("shows Looks right, Edit, and Reject buttons for each rule", async () => {
    mockFetch({ "/api/guidance/rules/review": [MOCK_RULE] });
    render(<RuleReviewSection />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /looks right/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /edit/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /reject/i })).toBeInTheDocument();
    });
  });

  it("opens ConfirmDialog before approve-all fires an API call", async () => {
    mockFetch({ "/api/guidance/rules/review": [MOCK_RULE] });
    render(<RuleReviewSection />);
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
      "/api/guidance/rules/review/approve-all": { approved_count: 1 },
    });
    render(<RuleReviewSection />);
    await waitFor(() => screen.getByRole("button", { name: /approve all/i }));

    fireEvent.click(screen.getByRole("button", { name: /approve all/i }));
    fireEvent.click(screen.getByRole("button", { name: /yes, approve all/i }));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls.map(([u]) => String(u));
      expect(calls.some((u) => u.includes("approve-all"))).toBe(true);
    });
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
      expect(screen.getByRole("button", { name: /compile rules/i })).toBeInTheDocument();
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
      expect(screen.getByText("v20260308-120000")).toBeInTheDocument();
    });
  });

  it("opens ConfirmDialog before activate fires an API call", async () => {
    mockFetch({
      "/api/terminology/guidelines/bitmap/status": { active_version: null, rule_count: 0 },
      "/api/terminology/guidelines/bitmap/versions": [
        { version: "v20260308-120000", active: false },
      ],
    });
    render(<BitmapLifecycleSection />);
    await waitFor(() => screen.getByRole("button", { name: /make this live/i }));

    fireEvent.click(screen.getByRole("button", { name: /make this live/i }));
    expect(screen.getByText(/Make this version live/i)).toBeInTheDocument();

    const callsBefore = (global.fetch as jest.Mock).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect((global.fetch as jest.Mock).mock.calls.length).toBe(callsBefore);
  });

  it("calls activate API after ConfirmDialog confirmation", async () => {
    mockFetch({
      "/api/terminology/guidelines/bitmap/status": { active_version: null, rule_count: 0 },
      "/api/terminology/guidelines/bitmap/versions": [
        { version: "v20260308-120000", active: false },
      ],
      "/api/terminology/guidelines/bitmap/versions/v20260308-120000/activate": { activated: true },
    });
    render(<BitmapLifecycleSection />);
    await waitFor(() => screen.getByRole("button", { name: /make this live/i }));

    fireEvent.click(screen.getByRole("button", { name: /make this live/i }));
    fireEvent.click(screen.getByRole("button", { name: /yes, go live/i }));

    await waitFor(() => {
      const calls = (global.fetch as jest.Mock).mock.calls.map(([u]) => String(u));
      expect(calls.some((u) => u.includes("activate"))).toBe(true);
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
      expect(screen.getByText("Compile rules")).toBeInTheDocument();
      expect(screen.getByText("Go live")).toBeInTheDocument();
    });
  });
});
