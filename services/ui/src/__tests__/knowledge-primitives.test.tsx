/**
 * VT-LEO-AI-141 -- Wave E Phase 1 Knowledge primitives.
 *
 * Verifies that every new primitive renders, carries the right
 * data-testid, honours keyboard + ARIA contracts, and that the
 * package barrel re-exports them. Static assertions ensure no
 * primitive reaches into @mui/material.
 */

import fs from "fs";
import path from "path";

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";

import {
  MetricTile,
  ProgressStrip,
  SegmentedTabs,
  FilterBar,
  ToolbarActions,
  ReviewListCard,
  DataGridCard,
  StatHero,
} from "@leo/design-system";

const PRIMITIVES_DIR = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "design-system",
  "src",
  "primitives",
);

function readSource(name: string): string {
  return fs.readFileSync(path.join(PRIMITIVES_DIR, name + ".tsx"), "utf-8");
}

describe("VT-141 TC-001 MetricTile", () => {
  it("renders with label, value and data-testid", () => {
    render(<MetricTile id="alpha" label="Gold labels" value={123} hint="so far" />);
    const node = screen.getByTestId("metric-tile-alpha");
    expect(node).toBeTruthy();
    expect(node.textContent ?? "").toContain("Gold labels");
    expect(node.textContent ?? "").toContain("123");
    expect(node.textContent ?? "").toContain("so far");
  });

  it("becomes a <button> when onClick is supplied", () => {
    render(<MetricTile id="beta" label="Candidates" value={9} onClick={() => undefined} />);
    const node = screen.getByTestId("metric-tile-beta");
    expect(node.tagName.toLowerCase()).toBe("button");
  });
});

describe("VT-141 TC-002 ProgressStrip", () => {
  it("clamps percentage and exposes role=progressbar", () => {
    render(<ProgressStrip label="Review progress" value={55} total={100} />);
    const track = screen.getByTestId("progress-strip-track");
    expect(track.getAttribute("role")).toBe("progressbar");
    expect(track.getAttribute("aria-valuenow")).toBe("55");
    expect(track.getAttribute("aria-valuemin")).toBe("0");
    expect(track.getAttribute("aria-valuemax")).toBe("100");
  });

  it("handles a zero total without throwing", () => {
    render(<ProgressStrip label="Empty" value={0} total={0} />);
    const track = screen.getByTestId("progress-strip-track");
    expect(track.getAttribute("aria-valuenow")).toBe("0");
  });

  it("renders indeterminate mindfulness pulse without a percent value", () => {
    render(
      <ProgressStrip
        label="Building the candidate lookup index..."
        indeterminate
        subtitle="Elapsed 12s"
      />,
    );
    const strip = screen.getByTestId("progress-strip");
    expect(strip.getAttribute("data-indeterminate")).toBe("true");
    expect(strip.getAttribute("aria-busy")).toBe("true");
    expect(screen.getByTestId("progress-strip-indeterminate")).toBeTruthy();
    expect(
      screen.getByTestId("progress-strip-track").getAttribute("aria-valuenow"),
    ).toBeNull();
    expect(screen.getByText("Elapsed 12s")).toBeTruthy();
  });
});

describe("VT-141 TC-003 SegmentedTabs", () => {
  function Harness() {
    const [value, setValue] = React.useState("one");
    return (
      <SegmentedTabs
        aria-label="Harness tabs"
        value={value}
        onChange={setValue}
        tabs={[
          { id: "one", label: "One", count: 4 },
          { id: "two", label: "Two" },
          { id: "three", label: "Three" },
        ]}
      />
    );
  }

  it("renders role=tablist and keyboard navigates with arrow keys", () => {
    render(<Harness />);
    const list = screen.getByTestId("segmented-tabs");
    expect(list.getAttribute("role")).toBe("tablist");

    const one = screen.getByTestId("segmented-tab-one");
    const two = screen.getByTestId("segmented-tab-two");
    expect(one.getAttribute("aria-selected")).toBe("true");

    one.focus();
    fireEvent.keyDown(one, { key: "ArrowRight" });
    expect(document.activeElement).toBe(two);

    fireEvent.click(two);
    expect(screen.getByTestId("segmented-tab-two").getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("segmented-tabs-pill")).toBeTruthy();
  });

  it("indexes button refs with optional chaining so current may be null", () => {
    const hook = fs.readFileSync(
      path.join(PRIMITIVES_DIR, "useSegmentedPill.ts"),
      "utf-8",
    );
    const tabs = readSource("SegmentedTabs");
    expect(hook).toMatch(/buttonRefs\.current\?\.\[activeIdx\]/);
    expect(tabs).toMatch(/refs\.current\?\.\[bounded\]/);
  });
});

describe("VT-141 TC-004 FilterBar", () => {
  function Harness() {
    const [search, setSearch] = React.useState("");
    const [active, setActive] = React.useState(false);
    return (
      <FilterBar
        search={search}
        onSearchChange={setSearch}
        chips={[
          {
            id: "needs-review",
            label: "Needs review",
            active,
            onToggle: () => setActive((v) => !v),
          },
        ]}
      />
    );
  }

  it("exposes role=search and aria-pressed chips", () => {
    render(<Harness />);
    const form = screen.getByTestId("filter-bar");
    expect(form.getAttribute("role")).toBe("search");
    const chip = screen.getByTestId("filter-chip-needs-review");
    expect(chip.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(chip);
    expect(chip.getAttribute("aria-pressed")).toBe("true");
  });

  it("propagates search changes", () => {
    render(<Harness />);
    const input = screen.getByTestId("filter-bar-search") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "mitral" } });
    expect(input.value).toBe("mitral");
  });
});

describe("VT-141 TC-005 ToolbarActions", () => {
  it("renders each action and fires onClick", () => {
    const spy = jest.fn();
    render(
      <ToolbarActions
        actions={[
          { id: "export", label: "Export", onClick: spy, variant: "secondary" },
          { id: "new", label: "New", onClick: () => undefined, variant: "primary" },
        ]}
      />,
    );
    fireEvent.click(screen.getByTestId("toolbar-action-export"));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("toolbar-action-new")).toBeTruthy();
  });
});

describe("VT-141 TC-006 ReviewListCard", () => {
  it("renders each item with accent and actions", () => {
    render(
      <ReviewListCard
        items={[
          {
            id: "r1",
            title: "Item one",
            tone: "warning",
            chips: <span>tag</span>,
            actions: <button type="button">Approve</button>,
          },
          { id: "r2", title: "Item two" },
        ]}
      />,
    );
    expect(screen.getByTestId("review-list-item-r1")).toBeTruthy();
    expect(screen.getByTestId("review-list-item-r2")).toBeTruthy();
  });

  it("renders the empty state when items is []", () => {
    render(<ReviewListCard items={[]} emptyState="Nothing to review" />);
    expect(screen.getByTestId("review-list-empty").textContent).toBe(
      "Nothing to review",
    );
  });
});

describe("VT-141 TC-007 DataGridCard", () => {
  interface Row {
    id: string;
    name: string;
  }

  it("renders columns as <th scope=col> and rows as data-grid-row-*", () => {
    const rows: Row[] = [
      { id: "a", name: "Alpha" },
      { id: "b", name: "Bravo" },
    ];
    render(
      <DataGridCard<Row>
        columns={[
          { id: "name", header: "Name", render: (r) => r.name },
        ]}
        rows={rows}
        rowKey={(r) => r.id}
      />,
    );
    expect(screen.getByTestId("data-grid-row-a")).toBeTruthy();
    expect(screen.getByTestId("data-grid-row-b")).toBeTruthy();
    const headers = document.querySelectorAll("th[scope='col']");
    expect(headers.length).toBe(1);
  });

  it("shows the empty state when rows is []", () => {
    render(
      <DataGridCard<Row>
        columns={[{ id: "name", header: "Name", render: (r) => r.name }]}
        rows={[]}
        rowKey={(r) => r.id}
        emptyState="No rows yet"
      />,
    );
    expect(screen.getByTestId("data-grid-empty").textContent).toBe("No rows yet");
  });
});

describe("VT-141 TC-008 StatHero staggers children on mount", () => {
  it("renders every tile, each wrapped in a motion frame", () => {
    render(
      <StatHero
        stats={[
          { id: "a", label: "Alpha", value: 1 },
          { id: "b", label: "Bravo", value: 2 },
          { id: "c", label: "Charlie", value: 3 },
        ]}
      />,
    );
    expect(screen.getByTestId("stat-tile-a-frame")).toBeTruthy();
    expect(screen.getByTestId("stat-tile-b-frame")).toBeTruthy();
    expect(screen.getByTestId("stat-tile-c-frame")).toBeTruthy();
    expect(screen.getByTestId("metric-tile-a")).toBeTruthy();
  });
});

describe("VT-141 TC-010 primitives never reach into @mui/material", () => {
  const files = [
    "MetricTile",
    "ProgressStrip",
    "SegmentedTabs",
    "FilterBar",
    "ToolbarActions",
    "ReviewListCard",
    "DataGridCard",
    "StatHero",
    "StickyChrome",
    "SpringSwap",
  ];

  for (const name of files) {
    it(name + ".tsx does not import from @mui/material", () => {
      const src = readSource(name);
      expect(src).not.toMatch(/from\s+["']@mui\/material/);
      expect(src).not.toMatch(/from\s+["']@mui\/icons/);
    });
  }
});
