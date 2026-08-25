/**
 * VT-LEO-AI-134 TC-004 - TaskQueue primitive in @leo/design-system.
 *
 * Renders the component with synthetic tasks and verifies ordering,
 * deep-link anchors, counts strip, and empty-state behaviour.
 */

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import {
  TaskQueue,
  MotionProvider,
  type CountsBySource,
  type WorkTask,
} from "@leo/design-system";

const COUNTS: CountsBySource = {
  coding_review: 3,
  safety_net_alert: 1,
  gold_label: 7,
  extraction_quality_pause: 2,
  surface_form_approval: 0,
};

const TASKS: WorkTask[] = [
  {
    task_id: "coding_review:cr-1",
    task_type: "coding_review",
    severity: 3,
    summary: "Code check: chest pain",
    age_days: 2,
    resolve_url: "/admin/operations/reviews?review_id=cr-1",
    patient_id: "pat-a",
    episode_id: null,
  },
  {
    task_id: "safety_net_alert:sn-1",
    task_type: "safety_net_alert",
    severity: 5,
    summary: "Safety alert: red flag needs review",
    age_days: 0,
    resolve_url: "/safety-netting?alert_id=sn-1",
    patient_id: "pat-b",
    episode_id: "ep-1",
  },
  {
    task_id: "gold_label:tc-1",
    task_type: "gold_label",
    severity: 2,
    summary: "Label review: sore throat note",
    age_days: 5,
    resolve_url:
      "/admin/knowledge?tab=training-data&candidate_id=tc-1",
    patient_id: null,
    episode_id: null,
  },
];

function mountInto(
  container: HTMLElement,
  element: React.ReactElement,
): Root {
  const root = createRoot(container);
  act(() => {
    root.render(element);
  });
  return root;
}

describe("TaskQueue primitive (VT-LEO-AI-134 TC-004)", () => {
  let container: HTMLElement;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    document.body.removeChild(container);
  });

  test("renders counts-by-source strip with three buttons", () => {
    mountInto(
      container,
      <MotionProvider>
        <TaskQueue tasks={TASKS} countsBySource={COUNTS} />
      </MotionProvider>,
    );
    const strip = container.querySelector(
      "[data-testid='task-queue-counts']",
    );
    expect(strip).not.toBeNull();
    expect(
      container.querySelector(
        "[data-testid='task-queue-count-coding_review']",
      ),
    ).not.toBeNull();
    expect(
      container.querySelector(
        "[data-testid='task-queue-count-safety_net_alert']",
      ),
    ).not.toBeNull();
    expect(
      container.querySelector(
        "[data-testid='task-queue-count-gold_label']",
      ),
    ).not.toBeNull();
  });

  test("renders one anchor per task row with resolve_url", () => {
    mountInto(
      container,
      <MotionProvider>
        <TaskQueue tasks={TASKS} countsBySource={COUNTS} />
      </MotionProvider>,
    );
    const anchors = container.querySelectorAll(
      "[data-testid^='task-queue-row-']",
    );
    expect(anchors.length).toBe(3);
    anchors.forEach((a) => {
      expect(a.tagName.toLowerCase()).toBe("a");
      expect((a as HTMLAnchorElement).getAttribute("href")).toMatch(
        /^\/(admin|safety-netting)/,
      );
    });
  });

  test("orders rows by severity desc then age desc", () => {
    mountInto(
      container,
      <MotionProvider>
        <TaskQueue tasks={TASKS} countsBySource={COUNTS} />
      </MotionProvider>,
    );
    const rows = container.querySelectorAll(
      "[data-testid^='task-queue-row-']",
    );
    const order = Array.from(rows).map((r) =>
      r.getAttribute("data-task-type"),
    );
    expect(order).toEqual([
      "safety_net_alert",
      "coding_review",
      "gold_label",
    ]);
  });

  test("shows empty state when no tasks", () => {
    mountInto(
      container,
      <MotionProvider>
        <TaskQueue tasks={[]} countsBySource={COUNTS} />
      </MotionProvider>,
    );
    const empty = container.querySelector(
      "[data-testid='task-queue-empty']",
    );
    expect(empty).not.toBeNull();
    expect(empty?.textContent).toMatch(/no open tasks/i);
  });

  test("row click calls onSelectTask and does not require navigation", () => {
    const selected: WorkTask[] = [];
    mountInto(
      container,
      <MotionProvider>
        <TaskQueue
          tasks={TASKS}
          countsBySource={COUNTS}
          onSelectTask={(task) => selected.push(task)}
        />
      </MotionProvider>,
    );
    const row = container.querySelector(
      "[data-testid='task-queue-row-safety_net_alert:sn-1']",
    ) as HTMLAnchorElement;
    const event = new MouseEvent("click", { bubbles: true, cancelable: true });
    act(() => {
      row.dispatchEvent(event);
    });
    expect(event.defaultPrevented).toBe(true);
    expect(selected).toHaveLength(1);
    expect(selected[0]?.task_id).toBe("safety_net_alert:sn-1");
  });

  test("counts strip buttons invoke onToggleSource", () => {
    const toggled: string[] = [];
    mountInto(
      container,
      <MotionProvider>
        <TaskQueue
          tasks={TASKS}
          countsBySource={COUNTS}
          activeSources={["coding_review"]}
          onToggleSource={(s) => toggled.push(s)}
        />
      </MotionProvider>,
    );
    const button = container.querySelector(
      "[data-testid='task-queue-count-safety_net_alert']",
    ) as HTMLButtonElement;
    act(() => {
      button.click();
    });
    expect(toggled).toEqual(["safety_net_alert"]);
  });
});
